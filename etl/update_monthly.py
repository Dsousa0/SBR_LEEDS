#!/usr/bin/env python3
"""
update_monthly.py — Importa os ZIPs da Receita Federal já baixados manualmente.

Detecta a pasta YYYY-MM mais recente em --downloads-dir, compara com o banco
e importa se houver dados mais novos.

Fluxo manual esperado:
  1. Baixar os ZIPs do portal dados.gov.br para downloads/YYYY-MM/
  2. Rodar este script (ou importer.py diretamente)

Uso:
    python update_monthly.py --segmento farmacia
    python update_monthly.py --segmento farmacia --force
    python update_monthly.py --apenas-verificar
"""

import argparse
import logging
import os
import subprocess
import sys
from pathlib import Path

import psycopg2

logger = logging.getLogger(__name__)

SCRIPT_DIR = Path(__file__).parent


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Importa ZIPs baixados manualmente para o PostgreSQL.",
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
        help="Diretório com subpastas YYYY-MM/ (default: /downloads)",
    )
    parser.add_argument(
        "--force", action="store_true",
        help="Re-importa mesmo se o mês já estiver no banco",
    )
    parser.add_argument(
        "--apenas-verificar", action="store_true",
        help="Apenas mostra o que seria importado, sem importar",
    )
    filtro = parser.add_mutually_exclusive_group()
    filtro.add_argument(
        "--segmento",
        help="Segmento pré-definido (ex: farmacia, restaurante, clinica)",
    )
    filtro.add_argument(
        "--cnaes",
        help="CNAEs específicos separados por vírgula",
    )
    parser.add_argument(
        "--tudo", action="store_true",
        help="Importa todos os estabelecimentos (não só os ativos)",
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


def detectar_mes_disponivel(downloads_dir: str) -> str | None:
    base = Path(downloads_dir)
    if not base.exists():
        logger.error("Diretório não existe: %s", base)
        return None

    subpastas = sorted([
        p.name for p in base.iterdir()
        if p.is_dir() and len(p.name) == 7 and p.name[4] == "-"
    ])
    return subpastas[-1] if subpastas else None


def mes_atual_no_banco(db_url: str) -> str | None:
    try:
        conn = psycopg2.connect(db_url)
        with conn.cursor() as cur:
            cur.execute(
                "SELECT mes_referencia FROM importacao "
                "WHERE status = 'concluido' ORDER BY concluida_em DESC LIMIT 1"
            )
            row = cur.fetchone()
        conn.close()
        return row[0] if row else None
    except psycopg2.Error as e:
        logger.warning("Não foi possível verificar importações anteriores: %s", e)
        return None


def executar_importer(args: argparse.Namespace, mes: str) -> int:
    import_args = [
        sys.executable, str(SCRIPT_DIR / "importer.py"),
        "--db-url", args.db_url,
        "--downloads-dir", str(Path(args.downloads_dir) / mes),
        "--truncar",
    ]
    if args.segmento:
        import_args += ["--segmento", args.segmento]
    elif args.cnaes:
        import_args += ["--cnaes", args.cnaes]
    if args.tudo:
        import_args.append("--tudo")

    logger.debug("Executando: %s", " ".join(import_args))
    result = subprocess.run(import_args, check=False)
    return result.returncode


def run(args: argparse.Namespace) -> int:
    if not args.db_url and not args.apenas_verificar:
        logger.error("DATABASE_URL não configurada. Use --db-url ou defina a variável.")
        return 3

    mes_disponivel = detectar_mes_disponivel(args.downloads_dir)
    if not mes_disponivel:
        logger.error(
            "Nenhuma pasta YYYY-MM encontrada em %s. "
            "Baixe os ZIPs manualmente e coloque-os em uma subpasta YYYY-MM/.",
            args.downloads_dir,
        )
        return 1

    logger.info("Mês disponível em disco: %s", mes_disponivel)

    mes_banco = mes_atual_no_banco(args.db_url) if args.db_url else None
    if mes_banco:
        logger.info("Mês atual no banco: %s", mes_banco)

    if mes_banco and mes_banco >= mes_disponivel and not args.force:
        logger.info("Base já está atualizada com %s. Use --force para re-importar.", mes_banco)
        return 0

    if args.apenas_verificar:
        logger.info("--apenas-verificar: importação não executada.")
        logger.info("  Mês a importar: %s", mes_disponivel)
        return 0

    logger.info("Iniciando importação do mês %s ...", mes_disponivel)
    rc = executar_importer(args, mes_disponivel)
    if rc != 0:
        logger.error("importer.py falhou com código %d", rc)
        return rc

    logger.info("Importação concluída.")
    return 0


if __name__ == "__main__":
    args = parse_args()
    setup_logging(args.log_level)
    sys.exit(run(args))
