#!/usr/bin/env python3
"""
importer.py — Importa os arquivos CNPJ para o PostgreSQL via COPY.

Usa COPY FROM STDIN (psycopg2) com streaming direto dos ZIPs — sem extrair para disco.
A conversão de encoding LATIN1→UTF-8 e o pré-processamento são feitos em memória.

Uso (dentro do container Docker):
    python importer.py --segmento farmacia       # só farmácias/drogarias (recomendado)
    python importer.py --cnaes 4771701,4771702   # CNAEs customizados
    python importer.py                           # importação completa (Brasil inteiro)
    python importer.py --tudo                    # inclui estabelecimentos inativos
    python importer.py --tabela estabelecimento  # re-importa só uma tabela
    python importer.py --pular-indices           # não cria índices ao final
    python importer.py --downloads-dir /downloads/2026-04
"""

import argparse
import csv
import io
import logging
import os
import sys
import time
import zipfile
from pathlib import Path

import psycopg2

logger = logging.getLogger(__name__)

SCRIPT_DIR = Path(__file__).parent

SITUACAO_ATIVA = "02"

# Segmentos pré-definidos com seus CNAEs correspondentes
SEGMENTOS: dict[str, dict] = {
    "farmacia": {
        "descricao": "Farmácias e drogarias",
        "cnaes": {"4771701", "4771702", "4771703"},
    },
    "restaurante": {
        "descricao": "Restaurantes e lanchonetes",
        "cnaes": {"5611201", "5611203", "5611204", "5611205"},
    },
    "oficina": {
        "descricao": "Oficinas mecânicas",
        "cnaes": {"4520001", "4520002", "4520003", "4520004", "4520005"},
    },
    "supermercado": {
        "descricao": "Supermercados e mercados",
        "cnaes": {"4711301", "4711302"},
    },
    "padaria": {
        "descricao": "Padarias e confeitarias",
        "cnaes": {"1091102", "4721102"},
    },
    "salao": {
        "descricao": "Salões de beleza e barbearias",
        "cnaes": {"9602501", "9602502"},
    },
    "clinica": {
        "descricao": "Clínicas médicas",
        "cnaes": {"8630501", "8630502", "8630503"},
    },
}

INDICES_SQL = [
    "CREATE INDEX IF NOT EXISTS idx_estab_uf_municipio   ON estabelecimento(uf, municipio)",
    "CREATE INDEX IF NOT EXISTS idx_estab_cnae_principal ON estabelecimento(cnae_fiscal_principal)",
    "CREATE INDEX IF NOT EXISTS idx_estab_situacao       ON estabelecimento(situacao_cadastral)",
    "CREATE INDEX IF NOT EXISTS idx_estab_cnpj_basico    ON estabelecimento(cnpj_basico)",
    "CREATE INDEX IF NOT EXISTS idx_empresa_cnpj_basico  ON empresa(cnpj_basico)",
    "CREATE INDEX IF NOT EXISTS idx_cnae_gin             ON cnae USING gin(to_tsvector('portuguese', descricao))",
]

# Mapeamento prefixo ZIP → tabela
TABELAS_CONFIG = {
    "Cnaes":            {"tabela": "cnae"},
    "Motivos":          {"tabela": "motivo"},
    "Municipios":       {"tabela": "municipio"},
    "Naturezas":        {"tabela": "natureza_juridica"},
    "Paises":           {"tabela": "pais"},
    "Qualificacoes":    {"tabela": "qualificacao_socio"},
    "Empresas":         {"tabela": "empresa"},
    "Simples":          {"tabela": "simples"},
    "Socios":           {"tabela": "socio"},
    "Estabelecimentos": {"tabela": "estabelecimento"},
}

# Ordem padrão (sem filtro por CNAE)
ORDEM_PADRAO = [
    "Cnaes", "Motivos", "Municipios", "Naturezas",
    "Paises", "Qualificacoes",
    "Empresas", "Simples", "Socios", "Estabelecimentos",
]

# Tabelas de referência (pequenas, sempre importadas)
REFERENCIAS = ["Cnaes", "Motivos", "Municipios", "Naturezas", "Paises", "Qualificacoes"]


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Importa dados CNPJ da Receita Federal para o PostgreSQL.",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog=__doc__,
    )
    parser.add_argument(
        "--db-url",
        default=os.getenv("DATABASE_URL"),
        help="URL de conexão PostgreSQL (default: var DATABASE_URL)",
    )
    parser.add_argument(
        "--downloads-dir", default="/downloads",
        help="Diretório com os ZIPs. Se for pasta raiz, detecta o mês mais recente. (default: /downloads)",
    )

    # Filtro por segmento / CNAE
    filtro = parser.add_mutually_exclusive_group()
    filtro.add_argument(
        "--segmento",
        choices=list(SEGMENTOS),
        metavar="SEGMENTO",
        help=f"Importa apenas um segmento pré-definido. Opções: {', '.join(SEGMENTOS)}",
    )
    filtro.add_argument(
        "--cnaes",
        help="CNAEs específicos separados por vírgula (ex: 4771701,4771702,4771703)",
    )

    parser.add_argument(
        "--tabela",
        help="Re-importa apenas esta tabela (ex: estabelecimento).",
    )
    parser.add_argument(
        "--tudo", action="store_true",
        help="Importa todos os estabelecimentos, inclusive inativos.",
    )
    parser.add_argument(
        "--incluir-socios", action="store_true",
        help="Inclui sócios na importação filtrada (omitidos por padrão quando há filtro por CNAE).",
    )
    parser.add_argument(
        "--pular-indices", action="store_true",
        help="Não cria índices ao final.",
    )
    parser.add_argument(
        "--truncar", action="store_true",
        help="Trunca as tabelas antes de importar.",
    )
    parser.add_argument(
        "--log-level", default="INFO",
        choices=["DEBUG", "INFO", "WARNING", "ERROR"],
    )
    return parser.parse_args()


def setup_logging(level: str) -> None:
    logging.basicConfig(
        level=getattr(logging, level),
        format="%(asctime)s %(levelname)s %(message)s",
        stream=sys.stderr,
    )


def validar_ambiente(args: argparse.Namespace) -> None:
    if not args.db_url:
        logger.error("DATABASE_URL não configurada. Use --db-url ou defina a variável de ambiente.")
        sys.exit(3)


def conectar(db_url: str) -> psycopg2.extensions.connection:
    try:
        conn = psycopg2.connect(db_url)
        conn.autocommit = False
        return conn
    except psycopg2.OperationalError as e:
        logger.error("Falha ao conectar no banco: %s", e)
        sys.exit(3)


def aplicar_schema(conn: psycopg2.extensions.connection) -> None:
    schema_path = SCRIPT_DIR / "schema.sql"
    if not schema_path.exists():
        logger.error("schema.sql não encontrado em %s", schema_path)
        sys.exit(3)

    logger.info("Aplicando schema.sql ...")
    with conn.cursor() as cur:
        cur.execute(schema_path.read_text(encoding="utf-8"))
    conn.commit()
    logger.info("Schema aplicado.")


def truncar_tabelas(conn: psycopg2.extensions.connection, tabelas: list[str]) -> None:
    with conn.cursor() as cur:
        for tabela in tabelas:
            logger.info("Truncando tabela: %s", tabela)
            cur.execute(f"TRUNCATE TABLE {tabela} RESTART IDENTITY CASCADE")
    conn.commit()


def detectar_pasta_downloads(downloads_dir: str) -> Path:
    base = Path(downloads_dir)
    if not base.exists():
        logger.error("Diretório de downloads não existe: %s", base)
        sys.exit(3)

    if list(base.glob("*.zip")):
        return base

    subpastas = sorted([
        p for p in base.iterdir()
        if p.is_dir() and len(p.name) == 7 and p.name[4] == "-"
    ])
    if not subpastas:
        logger.error("Nenhuma pasta YYYY-MM encontrada em %s", base)
        sys.exit(3)

    pasta = subpastas[-1]
    logger.info("Pasta de downloads detectada: %s", pasta)
    return pasta


def listar_zips(pasta: Path, prefixo: str) -> list[Path]:
    return sorted(pasta.glob(f"{prefixo}*.zip"))


# ---------------------------------------------------------
# Preprocessadores de linha
# ---------------------------------------------------------

def preprocessar_estabelecimento(
    row: list,
    apenas_ativos: bool,
    cnaes_filter: set | None,
) -> list | None:
    """
    Recebe a linha já parseada como lista de campos (via csv.reader).
    Filtra por situação cadastral (índice 5) e CNAE principal (índice 11).
    """
    if apenas_ativos and len(row) > 5:
        if row[5] != SITUACAO_ATIVA:
            return None

    if cnaes_filter and len(row) > 11:
        if row[11] not in cnaes_filter:
            return None

    return row


def preprocessar_empresa(
    row: list,
    cnpjs_validos: set | None = None,
) -> list | None:
    """
    Recebe a linha já parseada como lista de campos (via csv.reader).
    Converte capital_social (índice 4) de ',' para '.'.
    Quando cnpjs_validos é fornecido, descarta CNPJs não presentes no set.
    """
    if cnpjs_validos is not None:
        cnpj = row[0] if row else ""
        if cnpj not in cnpjs_validos:
            return None

    if len(row) > 4 and row[4]:
        row[4] = row[4].replace(",", ".")

    return row


def carregar_cnpjs_importados(conn: psycopg2.extensions.connection) -> set:
    """Retorna o set de cnpj_basico presentes em estabelecimento."""
    logger.info("Carregando cnpj_basico dos estabelecimentos importados ...")
    with conn.cursor() as cur:
        cur.execute("SELECT DISTINCT cnpj_basico FROM estabelecimento")
        cnpjs = {row[0] for row in cur.fetchall()}
    logger.info("  %d CNPJs únicos para filtrar empresa.", len(cnpjs))
    return cnpjs


# ---------------------------------------------------------
# Stream de pré-processamento
# ---------------------------------------------------------

class PipedStream:
    """
    Usa csv.reader para tratar campos multi-linha corretamente, converte
    LATIN1→UTF-8 e aplica preprocessador por linha (recebe/retorna list[str]).
    Compatível com psycopg2.cursor.copy_expert() que chama read(n).
    """

    def __init__(self, file_bin, preprocessador=None, encoding="latin-1"):
        text_io = io.TextIOWrapper(file_bin, encoding=encoding, newline="")
        self._reader = csv.reader(text_io, delimiter=";", quotechar='"')
        self._preprocessador = preprocessador
        self._buf = b""
        self._out = io.StringIO()
        self._writer = csv.writer(
            self._out, delimiter=";", quotechar='"',
            quoting=csv.QUOTE_MINIMAL, lineterminator="\n",
        )

    def read(self, n: int = 8192) -> bytes:
        while len(self._buf) < n:
            try:
                row = next(self._reader)
            except StopIteration:
                break
            if self._preprocessador:
                row = self._preprocessador(row)
                if row is None:
                    continue
            self._out.seek(0)
            self._out.truncate()
            self._writer.writerow(row)
            self._out.seek(0)
            self._buf += self._out.read().encode("utf-8", errors="replace")

        result, self._buf = self._buf[:n], self._buf[n:]
        return result


# ---------------------------------------------------------
# Importação
# ---------------------------------------------------------

def importar_zip(
    conn: psycopg2.extensions.connection,
    zip_path: Path,
    tabela: str,
    preprocessador,
) -> int:
    copy_sql = (
        f"COPY {tabela} FROM STDIN WITH ("
        "FORMAT csv, DELIMITER ';', HEADER false, "
        "ENCODING 'UTF8', QUOTE '\"', NULL ''"
        ")"
    )

    with zipfile.ZipFile(zip_path) as zf:
        nomes = zf.namelist()
        if not nomes:
            logger.warning("ZIP vazio: %s", zip_path.name)
            return 0

        with zf.open(nomes[0]) as csv_bin:
            stream = PipedStream(csv_bin, preprocessador=preprocessador)
            with conn.cursor() as cur:
                cur.copy_expert(copy_sql, stream)
                rows = cur.rowcount
            conn.commit()

    return max(rows, 0)


def importar_grupo(
    conn: psycopg2.extensions.connection,
    pasta: Path,
    prefixo: str,
    tabela: str,
    preprocessador,
) -> int:
    zips = listar_zips(pasta, prefixo)
    if not zips:
        logger.warning("Nenhum ZIP para prefixo '%s' em %s", prefixo, pasta)
        return 0

    total = 0
    for i, zip_path in enumerate(zips, 1):
        logger.info("  [%d/%d] %s ...", i, len(zips), zip_path.name)
        t0 = time.monotonic()
        rows = importar_zip(conn, zip_path, tabela, preprocessador)
        total += rows
        logger.info("       %d linhas em %.1fs", rows, time.monotonic() - t0)

    return total


def criar_indices(conn: psycopg2.extensions.connection) -> None:
    logger.info("Criando índices (pode levar alguns minutos) ...")
    with conn.cursor() as cur:
        for sql in INDICES_SQL:
            nome = sql.split("idx_")[1].split(" ")[0] if "idx_" in sql else sql[:40]
            logger.info("  idx_%s ...", nome)
            t0 = time.monotonic()
            cur.execute(sql)
            conn.commit()
            logger.info("       concluído em %.1fs", time.monotonic() - t0)
    logger.info("Índices criados.")


def registrar_importacao(
    conn: psycopg2.extensions.connection,
    mes: str,
    apenas_ativos: bool,
    status: str,
    obs: str = "",
) -> None:
    with conn.cursor() as cur:
        cur.execute(
            "INSERT INTO importacao (mes_referencia, status, apenas_ativos, concluida_em, observacoes)"
            " VALUES (%s, %s, %s, NOW(), %s)",
            (mes, status, apenas_ativos, obs),
        )
    conn.commit()


# ---------------------------------------------------------
# Orquestração principal
# ---------------------------------------------------------

def run(args: argparse.Namespace) -> int:
    validar_ambiente(args)

    # Resolve filtro por CNAE
    cnaes_filter: set | None = None
    segmento_desc = ""
    if args.segmento:
        cfg_seg = SEGMENTOS[args.segmento]
        cnaes_filter = cfg_seg["cnaes"]
        segmento_desc = f"{args.segmento} ({cfg_seg['descricao']})"
    elif args.cnaes:
        cnaes_filter = set(c.strip() for c in args.cnaes.split(",") if c.strip())
        segmento_desc = f"CNAEs customizados: {', '.join(sorted(cnaes_filter))}"

    apenas_ativos = not args.tudo

    if cnaes_filter:
        logger.info("Filtro por segmento: %s", segmento_desc)
        logger.info("CNAEs: %s", ", ".join(sorted(cnaes_filter)))
    if apenas_ativos:
        logger.info("Filtro de situação: apenas ATIVOS (02)")
    else:
        logger.info("Filtro de situação: TODOS")

    pasta = detectar_pasta_downloads(args.downloads_dir)
    mes = pasta.name

    conn = conectar(args.db_url)
    aplicar_schema(conn)

    # ----------------------------------------------------------
    # Determina ordem e sequência de importação
    # ----------------------------------------------------------
    if args.tabela:
        # Re-importação de tabela específica
        tabela_lower = args.tabela.lower()
        prefixos = [g for g in ORDEM_PADRAO if TABELAS_CONFIG[g]["tabela"] == tabela_lower]
        if not prefixos:
            logger.error("Tabela '%s' não reconhecida.", args.tabela)
            return 2
        sequencia = prefixos
        filtrar_empresa_por_cnpj = False
    elif cnaes_filter:
        # Importação filtrada por CNAE:
        # 1. Referências (sempre completas — são pequenas)
        # 2. Estabelecimentos (filtrado por CNAE + situação)
        # 3. Empresa (filtrado por cnpj_basico do estabelecimento)
        # 4. Socios (opcional)
        sequencia = REFERENCIAS + ["Estabelecimentos", "Empresas"]
        if args.incluir_socios:
            sequencia += ["Socios", "Simples"]
        filtrar_empresa_por_cnpj = True
    else:
        # Importação completa
        sequencia = ORDEM_PADRAO
        filtrar_empresa_por_cnpj = False

    # Trunca se solicitado
    if args.truncar:
        tabelas_truncar = list({TABELAS_CONFIG[g]["tabela"] for g in sequencia})
        truncar_tabelas(conn, tabelas_truncar)

    t_inicio = time.monotonic()
    total_linhas = 0
    cnpjs_para_empresa: set | None = None

    for prefixo in sequencia:
        tabela = TABELAS_CONFIG[prefixo]["tabela"]

        # Monta preprocessador específico para cada tabela
        if tabela == "estabelecimento":
            def preprocessador(linha, _ativos=apenas_ativos, _cnaes=cnaes_filter):  # noqa: E731
                return preprocessar_estabelecimento(linha, _ativos, _cnaes)

        elif tabela == "empresa":
            # Se filtramos estabelecimento por CNAE, agora filtramos empresa por cnpj_basico
            if filtrar_empresa_por_cnpj and cnpjs_para_empresa is None:
                cnpjs_para_empresa = carregar_cnpjs_importados(conn)

            def preprocessador(linha, _cnpjs=cnpjs_para_empresa):  # noqa: E731
                return preprocessar_empresa(linha, _cnpjs)

        else:
            preprocessador = None  # type: ignore[assignment]

        logger.info("=== Importando %s → '%s' ===", prefixo, tabela)
        t0 = time.monotonic()
        linhas = importar_grupo(conn, pasta, prefixo, tabela, preprocessador)
        total_linhas += linhas
        logger.info("    Total: %d linhas em %.0fs", linhas, time.monotonic() - t0)

    logger.info(
        "Importação concluída: %d linhas em %.0f min",
        total_linhas, (time.monotonic() - t_inicio) / 60,
    )

    if not args.pular_indices:
        criar_indices(conn)

    obs = segmento_desc or ("completa" if not cnaes_filter else "")
    registrar_importacao(conn, mes, apenas_ativos, "concluido", obs)

    conn.close()
    return 0


if __name__ == "__main__":
    args = parse_args()
    setup_logging(args.log_level)
    sys.exit(run(args))
