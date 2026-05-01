"""
Prospec Leads - API principal
Etapa 1: Setup inicial - valida que app + banco estão funcionando.
"""
from fastapi import FastAPI
from sqlalchemy import create_engine, text
import os

app = FastAPI(
    title="Prospec Leads",
    version="0.1.0",
    description="Ferramenta de prospecção de leads via base pública da Receita Federal",
)

DATABASE_URL = os.getenv("DATABASE_URL")
engine = create_engine(DATABASE_URL, pool_pre_ping=True)


@app.get("/")
def root():
    """Endpoint raiz - retorna status básico da aplicação."""
    return {
        "app": "Prospec Leads",
        "version": "0.1.0",
        "status": "running",
        "stage": "Etapa 1 - Setup inicial",
        "docs": "/docs",
        "health": "/health",
    }


@app.get("/health")
def health():
    """Verifica conectividade com o banco de dados."""
    try:
        with engine.connect() as conn:
            result = conn.execute(text("SELECT version()"))
            version = result.scalar()
        return {
            "status": "healthy",
            "database": "connected",
            "postgres_version": version,
        }
    except Exception as e:
        return {
            "status": "unhealthy",
            "database": "disconnected",
            "error": str(e),
        }
