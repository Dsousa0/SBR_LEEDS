#!/usr/bin/env python3
"""
sync_pedido_mobile.py — CLI para sincronizar a base de clientes do Pedido Mobile.

A lógica reside em app/pedido_mobile.py (chamada também pelo botão na UI).
Este script é apenas um wrapper para uso manual ou cron futuro.

Uso (dentro do container etl):
    docker compose --profile etl run --rm etl python sync_pedido_mobile.py
"""
import logging
import os
import sys

# Permite importar de /code (onde o app está montado no container)
sys.path.insert(0, "/code")

from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

from pedido_mobile import sincronizar, SyncError  # noqa: E402

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s %(levelname)s %(message)s",
    stream=sys.stderr,
)
logger = logging.getLogger(__name__)


def main() -> int:
    db_url = os.getenv("DATABASE_URL")
    if not db_url:
        logger.error("DATABASE_URL não configurada.")
        return 3

    engine = create_engine(db_url)
    Session = sessionmaker(bind=engine, autocommit=False, autoflush=False)

    with Session() as db:
        try:
            r = sincronizar(db)
        except SyncError as e:
            logger.error("Falha na sync: %s", e)
            return 2

    logger.info("Sync concluído: %s", r)
    return 0


if __name__ == "__main__":
    sys.exit(main())
