#!/usr/bin/env python3
"""
validators.py — Executa queries de validação após a importação.

Verifica contagens, sanidade dos dados e performance de busca típica.
Saída em texto no stdout; erros e logs no stderr.

Uso (dentro do container Docker):
    python validators.py
    python validators.py --uf PI --municipio FLORIANO
"""

import argparse
import logging
import os
import sys
import time

import psycopg2
import psycopg2.extras

logger = logging.getLogger(__name__)


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Valida a importação da base CNPJ.",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog=__doc__,
    )
    parser.add_argument(
        "--db-url",
        default=os.getenv("DATABASE_URL"),
        help="URL de conexão PostgreSQL (default: var DATABASE_URL)",
    )
    parser.add_argument(
        "--uf", default="PI",
        help="UF para teste de busca típica (default: PI)",
    )
    parser.add_argument(
        "--municipio", default="FLORIANO",
        help="Município para teste (default: FLORIANO)",
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


def conectar(db_url: str):
    try:
        return psycopg2.connect(db_url, cursor_factory=psycopg2.extras.RealDictCursor)
    except psycopg2.OperationalError as e:
        logger.error("Falha ao conectar: %s", e)
        sys.exit(3)


def executar(cur, sql: str, params=None):
    t0 = time.monotonic()
    cur.execute(sql, params)
    elapsed = time.monotonic() - t0
    return cur.fetchall(), elapsed


def separador(titulo: str) -> None:
    print(f"\n{'='*60}")
    print(f"  {titulo}")
    print("="*60)


def run(args: argparse.Namespace) -> int:
    if not args.db_url:
        logger.error("DATABASE_URL não configurada.")
        sys.exit(3)

    conn = conectar(args.db_url)
    cur = conn.cursor()
    erros = 0

    # ----------------------------------------------------------
    # 1. Contagem das tabelas
    # ----------------------------------------------------------
    separador("1. Contagem de registros por tabela")
    tabelas = [
        "empresa", "estabelecimento", "socio", "simples",
        "cnae", "municipio", "pais", "natureza_juridica",
        "qualificacao_socio", "motivo", "importacao",
    ]
    for tabela in tabelas:
        try:
            rows, elapsed = executar(cur, f"SELECT COUNT(*) AS total FROM {tabela}")
            total = rows[0]["total"]
            print(f"  {tabela:<30} {total:>12,d}   ({elapsed:.2f}s)")
            if total == 0:
                logger.warning("Tabela %s está VAZIA!", tabela)
                erros += 1
        except psycopg2.Error as e:
            logger.error("Erro ao contar %s: %s", tabela, e)
            conn.rollback()
            erros += 1

    # ----------------------------------------------------------
    # 2. Distribuição por situação cadastral
    # ----------------------------------------------------------
    separador("2. Estabelecimentos por situação cadastral")
    sql_situacao = """
        SELECT
            situacao_cadastral,
            CASE situacao_cadastral
                WHEN '01' THEN 'Nula'
                WHEN '02' THEN 'Ativa'
                WHEN '03' THEN 'Suspensa'
                WHEN '04' THEN 'Inapta'
                WHEN '08' THEN 'Baixada'
                ELSE 'Outra'
            END AS descricao,
            COUNT(*) AS total
        FROM estabelecimento
        GROUP BY situacao_cadastral
        ORDER BY total DESC
    """
    try:
        rows, elapsed = executar(cur, sql_situacao)
        for row in rows:
            print(f"  {row['situacao_cadastral']} ({row['descricao']:<10})  {row['total']:>12,d}")
        print(f"  {'':>40} ({elapsed:.2f}s)")
    except psycopg2.Error as e:
        logger.error("Erro na contagem por situação: %s", e)
        conn.rollback()
        erros += 1

    # ----------------------------------------------------------
    # 3. Top 10 UFs por ativos
    # ----------------------------------------------------------
    separador("3. Top 10 UFs por estabelecimentos ativos")
    sql_ufs = """
        SELECT uf, COUNT(*) AS total
        FROM estabelecimento
        WHERE situacao_cadastral = '02'
        GROUP BY uf
        ORDER BY total DESC
        LIMIT 10
    """
    try:
        rows, elapsed = executar(cur, sql_ufs)
        for row in rows:
            print(f"  {row['uf']}  {row['total']:>10,d}")
        print(f"  ({elapsed:.2f}s)")
    except psycopg2.Error as e:
        logger.error("Erro no top UFs: %s", e)
        conn.rollback()
        erros += 1

    # ----------------------------------------------------------
    # 4. Busca típica: cidade + CNAE (simula uso real)
    # ----------------------------------------------------------
    separador(f"4. Teste de busca: {args.uf} / {args.municipio} — farmácias")
    sql_busca = """
        SELECT COUNT(*) AS total
        FROM estabelecimento e
        JOIN municipio m ON e.municipio = m.codigo
        WHERE e.uf = %(uf)s
          AND m.descricao ILIKE %(municipio)s
          AND e.cnae_fiscal_principal IN ('4771701', '4771702', '4771703')
          AND e.situacao_cadastral = '02'
    """
    try:
        rows, elapsed = executar(cur, sql_busca, {"uf": args.uf, "municipio": f"%{args.municipio}%"})
        total = rows[0]["total"]
        print(f"  Farmácias ativas em {args.municipio}/{args.uf}: {total:,d}")
        print(f"  Tempo de consulta: {elapsed:.3f}s", end="")
        if elapsed > 1.0:
            print("  ⚠ LENTO — verifique se os índices foram criados")
        else:
            print("  ✓")
    except psycopg2.Error as e:
        logger.error("Erro na busca de teste: %s", e)
        conn.rollback()
        erros += 1

    # ----------------------------------------------------------
    # 5. Amostra de dados (5 estabelecimentos ativos com e-mail)
    # ----------------------------------------------------------
    separador("5. Amostra — 5 estabelecimentos ativos com e-mail")
    sql_amostra = """
        SELECT
            e.cnpj_basico || e.cnpj_ordem || e.cnpj_dv AS cnpj,
            COALESCE(e.nome_fantasia, emp.razao_social, '---') AS nome,
            e.uf,
            m.descricao AS municipio,
            e.correio_eletronico
        FROM estabelecimento e
        LEFT JOIN empresa emp ON e.cnpj_basico = emp.cnpj_basico
        LEFT JOIN municipio m ON e.municipio = m.codigo
        WHERE e.situacao_cadastral = '02'
          AND e.correio_eletronico IS NOT NULL
          AND e.correio_eletronico != ''
        LIMIT 5
    """
    try:
        rows, _ = executar(cur, sql_amostra)
        for row in rows:
            print(f"  {row['cnpj']}  {row['nome'][:30]:<30}  {row['uf']}/{row['municipio']:<20}  {row['correio_eletronico']}")
        if not rows:
            logger.warning("Nenhum estabelecimento com e-mail encontrado na amostra.")
    except psycopg2.Error as e:
        logger.error("Erro na amostra: %s", e)
        conn.rollback()
        erros += 1

    # ----------------------------------------------------------
    # 6. Última importação
    # ----------------------------------------------------------
    separador("6. Histórico de importações")
    try:
        rows, _ = executar(cur, "SELECT * FROM importacao ORDER BY iniciada_em DESC LIMIT 5")
        if rows:
            for row in rows:
                print(f"  {row['mes_referencia']}  {row['status']:<15}  apenas_ativos={row['apenas_ativos']}  {row['concluida_em']}")
        else:
            print("  Nenhuma importação registrada.")
    except psycopg2.Error as e:
        logger.error("Erro ao consultar importações: %s", e)
        conn.rollback()

    # ----------------------------------------------------------
    print()
    if erros:
        logger.error("Validação concluída com %d erro(s). Verifique os logs acima.", erros)
        return 1
    else:
        logger.info("Validação concluída. Base parece íntegra.")
        return 0


if __name__ == "__main__":
    args = parse_args()
    setup_logging(args.log_level)
    sys.exit(run(args))
