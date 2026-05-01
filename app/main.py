"""
Prospec Leads — API principal
"""
from fastapi import FastAPI
from sqlalchemy import text
import os

from database import engine
from routers.api import router as api_router

app = FastAPI(
    title="Prospec Leads",
    version="0.2.0",
    description="Ferramenta de prospecção de leads via base pública da Receita Federal",
)

app.include_router(api_router)


@app.get("/")
def root():
    return {
        "app": "Prospec Leads",
        "version": "0.2.0",
        "docs": "/docs",
        "health": "/health",
        "api": "/api",
    }


@app.get("/health")
def health():
    try:
        with engine.connect() as conn:
            version = conn.execute(text("SELECT version()")).scalar()
        return {"status": "healthy", "database": "connected", "postgres_version": version}
    except Exception as e:
        return {"status": "unhealthy", "database": "disconnected", "error": str(e)}
