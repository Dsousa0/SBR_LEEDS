"""
Sincronização da base de clientes do Pedido Mobile.

A API expõe `GET /clienteintegracao/versao?versao=N&page=P` com versionamento incremental:
- versão 0 retorna todos os clientes (carga inicial)
- versões > 0 retornam apenas clientes alterados desde aquele número

Apenas operações de leitura (GET) são executadas — nunca POST/PUT/DELETE.
"""
import logging
import re
import time

import requests
from sqlalchemy import text
from sqlalchemy.orm import Session

from config import settings

logger = logging.getLogger(__name__)

ENDPOINT = "/clienteintegracao/versao"
TIMEOUT_SEGUNDOS = 60
MAX_TENTATIVAS = 3


class SyncError(Exception):
    pass


def _credenciais_ou_erro() -> tuple[str, str]:
    if not settings.pedido_mobile_user or not settings.pedido_mobile_password:
        raise SyncError(
            "Credenciais do Pedido Mobile não configuradas. "
            "Defina PEDIDO_MOBILE_USER e PEDIDO_MOBILE_PASSWORD no .env."
        )
    return settings.pedido_mobile_user, settings.pedido_mobile_password


def _normalizar_documento(doc: str | None) -> str:
    return re.sub(r"\D", "", doc or "")


def _ultima_versao(db: Session) -> int:
    # Considera apenas syncs CONCLUÍDOS sem erro — evita ler o registro
    # da execução em andamento (que tem concluida_em IS NULL).
    return db.execute(
        text(
            "SELECT COALESCE(MAX(ultima_versao), 0) "
            "FROM pedido_mobile_sync "
            "WHERE concluida_em IS NOT NULL AND erro IS NULL"
        )
    ).scalar() or 0


def _sync_em_andamento(db: Session) -> bool:
    return bool(db.execute(
        text("SELECT 1 FROM pedido_mobile_sync WHERE concluida_em IS NULL LIMIT 1")
    ).scalar())


_RESPOSTA_VAZIA: dict = {"dados": [], "totalPaginas": 0, "totalRegistros": 0}


def _buscar_pagina(versao: int, page: int) -> dict:
    user, pwd = _credenciais_ou_erro()
    url = settings.pedido_mobile_base_url.rstrip("/") + ENDPOINT

    for tentativa in range(1, MAX_TENTATIVAS + 1):
        try:
            r = requests.get(
                url,
                params={"versao": versao, "page": page},
                auth=(user, pwd),
                timeout=TIMEOUT_SEGUNDOS,
                headers={"Accept": "application/json"},
            )
            # API retorna 404 quando não há clientes alterados desde a versão.
            # Tratamos como resposta vazia (sucesso, 0 alterações).
            if r.status_code == 404:
                logger.info("Sem alterações desde a versão %d (HTTP 404)", versao)
                return {**_RESPOSTA_VAZIA, "ultimaVersao": versao}
            r.raise_for_status()
            return r.json()
        except requests.RequestException as e:
            logger.warning(
                "Falha ao buscar página %d (tentativa %d/%d): %s",
                page, tentativa, MAX_TENTATIVAS, e,
            )
            if tentativa == MAX_TENTATIVAS:
                raise SyncError(f"Falha ao buscar página {page}: {e}") from e
            time.sleep(2 ** tentativa)
    raise SyncError("Loop de retry encerrado sem sucesso")


_UPSERT_SQL = text("""
    INSERT INTO cliente_pedido_mobile
        (documento, tipo_documento, razao_social, nome_fantasia,
         vendedor, inativo, municipio, uf, atualizado_em)
    VALUES
        (:documento, :tipo_documento, :razao_social, :nome_fantasia,
         :vendedor, :inativo, :municipio, :uf, NOW())
    ON CONFLICT (documento) DO UPDATE SET
        tipo_documento = EXCLUDED.tipo_documento,
        razao_social   = EXCLUDED.razao_social,
        nome_fantasia  = EXCLUDED.nome_fantasia,
        vendedor       = EXCLUDED.vendedor,
        inativo        = EXCLUDED.inativo,
        municipio      = EXCLUDED.municipio,
        uf             = EXCLUDED.uf,
        atualizado_em  = NOW()
    RETURNING (xmax = 0) AS inserido
""")


def sincronizar(db: Session) -> dict:
    """Executa um ciclo de sincronização. Retorna estatísticas."""
    _credenciais_ou_erro()
    if _sync_em_andamento(db):
        raise SyncError(
            "Já existe uma sincronização em andamento. Aguarde a conclusão "
            "antes de iniciar outra."
        )
    versao_inicial = _ultima_versao(db)
    logger.info("Iniciando sync Pedido Mobile (versão local: %d)", versao_inicial)

    inicio_sync = db.execute(
        text(
            "INSERT INTO pedido_mobile_sync (ultima_versao) "
            "VALUES (:v) RETURNING id"
        ),
        {"v": versao_inicial},
    ).scalar()
    db.commit()

    novos = atualizados = 0
    nova_versao = versao_inicial
    paginas_processadas = 0
    total = 0

    try:
        page = 1
        while True:
            data = _buscar_pagina(versao_inicial, page)
            total = data.get("totalRegistros") or total
            total_paginas = data.get("totalPaginas") or 0
            nova_versao = max(nova_versao, data.get("ultimaVersao") or 0)
            registros = data.get("dados") or []

            for cliente in registros:
                documento = _normalizar_documento(cliente.get("documento"))
                if not documento:
                    continue
                inserido = db.execute(_UPSERT_SQL, {
                    "documento":      documento,
                    "tipo_documento": (cliente.get("tipoDocumento") or "")[:4] or None,
                    "razao_social":   (cliente.get("razaoSocial") or "")[:200] or None,
                    "nome_fantasia":  (cliente.get("nomeFantasia") or "")[:200] or None,
                    "vendedor":       (cliente.get("vendedor") or "")[:100] or None,
                    "inativo":        bool(cliente.get("inativo")),
                    "municipio":      (cliente.get("municipio") or "")[:100] or None,
                    "uf":             (cliente.get("estado") or "")[:2] or None,
                }).scalar()
                if inserido:
                    novos += 1
                else:
                    atualizados += 1
            db.commit()

            paginas_processadas = page
            logger.info(
                "Página %d/%d processada (novos=%d, atualizados=%d)",
                page, total_paginas, novos, atualizados,
            )
            if page >= total_paginas:
                break
            page += 1

    except Exception as e:
        db.rollback()
        db.execute(
            text(
                "UPDATE pedido_mobile_sync "
                "SET erro = :erro, concluida_em = NOW() WHERE id = :id"
            ),
            {"erro": str(e)[:500], "id": inicio_sync},
        )
        db.commit()
        raise

    db.execute(
        text("""
            UPDATE pedido_mobile_sync SET
                concluida_em   = NOW(),
                ultima_versao  = :v,
                total_clientes = :total,
                novos          = :novos,
                atualizados    = :atualizados,
                paginas        = :paginas
            WHERE id = :id
        """),
        {
            "id": inicio_sync,
            "v": nova_versao,
            "total": total,
            "novos": novos,
            "atualizados": atualizados,
            "paginas": paginas_processadas,
        },
    )
    db.commit()

    return {
        "total_registros": total,
        "novos": novos,
        "atualizados": atualizados,
        "paginas": paginas_processadas,
        "versao_inicial": versao_inicial,
        "nova_versao": nova_versao,
    }


def total_clientes(db: Session) -> int:
    return db.execute(text("SELECT COUNT(*) FROM cliente_pedido_mobile")).scalar() or 0


def ultima_sync(db: Session) -> dict | None:
    row = db.execute(
        text("""
            SELECT concluida_em, ultima_versao, total_clientes, novos, atualizados, erro
            FROM pedido_mobile_sync
            WHERE concluida_em IS NOT NULL
            ORDER BY concluida_em DESC
            LIMIT 1
        """)
    ).first()
    if not row:
        return None
    return {
        "concluida_em":   row.concluida_em,
        "ultima_versao":  row.ultima_versao,
        "total_clientes": row.total_clientes,
        "novos":          row.novos,
        "atualizados":    row.atualizados,
        "erro":           row.erro,
    }
