"""
Prospec Leads — API principal
"""
from fastapi import FastAPI
from fastapi.staticfiles import StaticFiles
from sqlalchemy import text

from database import engine
from routers.api import router as api_router
from routers.frontend import router as frontend_router

app = FastAPI(
    title="Prospec Leads",
    version="0.2.0",
    description="Ferramenta de prospecção de leads via base pública da Receita Federal",
)

app.include_router(api_router)
app.include_router(frontend_router)


@app.get("/health")
def health():
    try:
        with engine.connect() as conn:
            version = conn.execute(text("SELECT version()")).scalar()
        return {"status": "healthy", "database": "connected", "postgres_version": version}
    except Exception as e:
        return {"status": "unhealthy", "database": "disconnected", "error": str(e)}
