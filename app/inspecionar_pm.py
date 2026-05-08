"""
Script de inspeção: mostra os campos retornados pela API do Pedido Mobile.
Apenas leitura (GET). Não altera nada.

Uso (dentro do container):
    python inspecionar_pm.py
"""
import json
import sys

import requests

from config import settings


def main():
    if not settings.pedido_mobile_user or not settings.pedido_mobile_password:
        print("ERRO: PEDIDO_MOBILE_USER e PEDIDO_MOBILE_PASSWORD não configurados.")
        sys.exit(1)

    url = settings.pedido_mobile_base_url.rstrip("/") + "/clienteintegracao/versao"
    print(f"Consultando: {url}?versao=0&page=1\n")

    r = requests.get(
        url,
        params={"versao": 0, "page": 1},
        auth=(settings.pedido_mobile_user, settings.pedido_mobile_password),
        timeout=30,
        headers={"Accept": "application/json"},
    )
    r.raise_for_status()
    data = r.json()

    registros = data.get("dados") or []
    if not registros:
        print("Nenhum registro retornado.")
        print("Resposta completa:", json.dumps(data, indent=2, ensure_ascii=False))
        return

    primeiro = registros[0]
    print(f"Total de registros: {data.get('totalRegistros')}")
    print(f"Total de páginas:   {data.get('totalPaginas')}")
    print(f"Última versão:      {data.get('ultimaVersao')}")
    print(f"\n--- Campos do 1º registro ({len(registros)} na página) ---")
    for chave, valor in primeiro.items():
        print(f"  {chave!r:35} = {json.dumps(valor, ensure_ascii=False)}")


if __name__ == "__main__":
    main()
