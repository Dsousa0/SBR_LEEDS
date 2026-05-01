#!/usr/bin/env python3
"""
download.py — Baixa os arquivos mais recentes da Receita Federal (dados abertos CNPJ).

Os arquivos (~5 GB compactados) são salvos em /downloads/<YYYY-MM>/.
Arquivos já existentes são pulados automaticamente (use --force para forçar re-download).

Uso (dentro do container Docker):
    python download.py
    python download.py --list-only
    python download.py --mes 2026-04
    python download.py --force --output-dir /downloads
"""

import argparse
import logging
import re
import sys
import time
from pathlib import Path

import requests

logger = logging.getLogger(__name__)

BASE_URL = "https://arquivos.receitafederal.gov.br/CNPJ/dados_abertos_cnpj/"

HEADERS = {
    "User-Agent": "Mozilla/5.0 (compatible; prospec-leads/1.0; +https://github.com/Dsousa0/prospec-leads)"
}

# Arquivos disponíveis por mês (nome sem o número de sequência)
ARQUIVOS_NUMERADOS = ["Empresas", "Estabelecimentos", "Socios"]
ARQUIVOS_SIMPLES = ["Cnaes", "Motivos", "Municipios", "Naturezas", "Paises", "Qualificacoes", "Simples"]


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Baixa os arquivos CNPJ mais recentes da Receita Federal.",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog=__doc__,
    )
    parser.add_argument(
        "--output-dir", default="/downloads",
        help="Diretório de destino dos ZIPs (default: /downloads)",
    )
    parser.add_argument(
        "--mes",
        help="Mês a baixar no formato YYYY-MM (default: mais recente disponível)",
    )
    parser.add_argument(
        "--list-only", action="store_true",
        help="Lista os arquivos sem baixar",
    )
    parser.add_argument(
        "--force", action="store_true",
        help="Re-baixa arquivos já existentes",
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


def listar_meses(sessao: requests.Session) -> list[str]:
    """Retorna lista de meses disponíveis ordenada (mais recente por último)."""
    try:
        resp = sessao.get(BASE_URL, timeout=30)
        resp.raise_for_status()
    except requests.RequestException as e:
        logger.error("Falha ao acessar %s: %s", BASE_URL, e)
        sys.exit(3)

    meses = sorted(set(re.findall(r'href="(\d{4}-\d{2})/?"', resp.text)))
    if not meses:
        logger.error("Nenhuma pasta YYYY-MM encontrada em %s", BASE_URL)
        sys.exit(3)
    return meses


def listar_arquivos(mes: str) -> list[str]:
    """Retorna lista de nomes de arquivo esperados para um mês."""
    arquivos = [f"{nome}{i}.zip" for nome in ARQUIVOS_NUMERADOS for i in range(10)]
    arquivos += [f"{nome}.zip" for nome in ARQUIVOS_SIMPLES]
    return sorted(arquivos)


def baixar_arquivo(
    sessao: requests.Session,
    url: str,
    destino: Path,
    force: bool = False,
) -> str:
    """
    Baixa um arquivo com retry e progresso no stderr.
    Retorna: 'baixado', 'pulado' ou 'erro'.
    """
    if destino.exists() and not force:
        logger.debug("Pulando (já existe): %s", destino.name)
        return "pulado"

    destino.parent.mkdir(parents=True, exist_ok=True)
    tmp = destino.with_suffix(".tmp")

    for tentativa in range(1, 4):
        try:
            resp = sessao.get(url, stream=True, timeout=60)
            if resp.status_code == 404:
                logger.warning("Arquivo não encontrado: %s", url)
                return "erro"
            resp.raise_for_status()

            total = int(resp.headers.get("content-length", 0))
            baixados = 0

            with tmp.open("wb") as f:
                for chunk in resp.iter_content(chunk_size=1024 * 256):
                    f.write(chunk)
                    baixados += len(chunk)
                    if total:
                        pct = baixados / total * 100
                        logger.debug("  %.0f%%  %s", pct, destino.name)

            tmp.rename(destino)
            tamanho_mb = destino.stat().st_size / 1024 / 1024
            logger.info("Baixado: %-45s (%.1f MB)", destino.name, tamanho_mb)
            return "baixado"

        except requests.RequestException as e:
            if tentativa < 3:
                espera = 2**tentativa
                logger.warning("Tentativa %d falhou (%s). Aguardando %ds...", tentativa, e, espera)
                time.sleep(espera)
            else:
                logger.error("Falha após 3 tentativas: %s — %s", destino.name, e)
                if tmp.exists():
                    tmp.unlink()
                return "erro"

    return "erro"


def run(args: argparse.Namespace) -> int:
    sessao = requests.Session()
    sessao.headers.update(HEADERS)

    logger.info("Consultando meses disponíveis em %s ...", BASE_URL)
    meses = listar_meses(sessao)
    logger.info("Meses disponíveis: %s", ", ".join(meses))

    mes = args.mes or meses[-1]
    if args.mes and args.mes not in meses:
        logger.error("Mês '%s' não encontrado. Disponíveis: %s", args.mes, ", ".join(meses))
        return 4

    arquivos = listar_arquivos(mes)
    logger.info("Mês selecionado: %s (%d arquivos)", mes, len(arquivos))

    if args.list_only:
        for nome in arquivos:
            url = f"{BASE_URL}{mes}/{nome}"
            print(url)
        return 0

    output_dir = Path(args.output_dir) / mes
    output_dir.mkdir(parents=True, exist_ok=True)
    logger.info("Destino: %s", output_dir)

    baixados = pulados = erros = 0
    for i, nome in enumerate(arquivos, 1):
        url = f"{BASE_URL}{mes}/{nome}"
        destino = output_dir / nome
        logger.info("[%d/%d] %s", i, len(arquivos), nome)
        resultado = baixar_arquivo(sessao, url, destino, force=args.force)
        if resultado == "baixado":
            baixados += 1
        elif resultado == "pulado":
            pulados += 1
        else:
            erros += 1

    logger.info("Concluído: %d baixados, %d pulados, %d erros", baixados, pulados, erros)
    return 0 if erros == 0 else 1


if __name__ == "__main__":
    args = parse_args()
    setup_logging(args.log_level)
    sys.exit(run(args))
