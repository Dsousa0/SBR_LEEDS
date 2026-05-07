import json

from fastapi import APIRouter, Depends, Form, Request
from fastapi.responses import HTMLResponse
from fastapi.templating import Jinja2Templates
from sqlalchemy import text
from sqlalchemy.exc import ProgrammingError
from sqlalchemy.orm import Session

from database import get_db
from routers.api import _UFS
from schemas import BuscarRequest, Stats, UF, Municipio, Cnae
from service import ATALHOS, buscar
from pedido_mobile import sincronizar, ultima_sync, total_clientes, SyncError

templates = Jinja2Templates(directory="templates")
router = APIRouter()


def _get_stats(db: Session) -> Stats:
    try:
        total_estab = db.execute(text("SELECT COUNT(*) FROM estabelecimento")).scalar() or 0
        total_emp = db.execute(text("SELECT COUNT(*) FROM empresa")).scalar() or 0
        ultima = db.execute(
            text("SELECT mes_referencia FROM importacao WHERE status='concluido' ORDER BY concluida_em DESC LIMIT 1")
        ).scalar()
    except ProgrammingError:
        db.rollback()
        return Stats(
            total_estabelecimentos=0,
            total_empresas=0,
            ultima_importacao=None,
            distribuicao_uf=[],
        )
    return Stats(
        total_estabelecimentos=total_estab,
        total_empresas=total_emp,
        ultima_importacao=ultima,
        distribuicao_uf=[],
    )


def _info_pedido_mobile(db: Session) -> dict:
    try:
        return {
            "total": total_clientes(db),
            "ultima": ultima_sync(db),
        }
    except Exception:
        db.rollback()
        return {"total": 0, "ultima": None}


@router.get("/", response_class=HTMLResponse)
def pagina_inicial(request: Request, db: Session = Depends(get_db)):
    stats = _get_stats(db)
    ufs = [UF(sigla=s, nome=n) for s, n in _UFS]
    atalhos_view = [{"segmento": a["segmento"], "descricao": a["descricao"]} for a in ATALHOS]
    return templates.TemplateResponse("index.html", {
        "request": request,
        "ufs": ufs,
        "atalhos": atalhos_view,
        "stats": stats,
        "pm": _info_pedido_mobile(db),
    })


@router.post("/sync-clientes", response_class=HTMLResponse)
def sync_clientes(request: Request, db: Session = Depends(get_db)):
    try:
        resultado = sincronizar(db)
        return templates.TemplateResponse("partials/pedido_mobile_card.html", {
            "request": request,
            "pm": _info_pedido_mobile(db),
            "resultado": resultado,
            "erro": None,
        })
    except SyncError as e:
        return templates.TemplateResponse("partials/pedido_mobile_card.html", {
            "request": request,
            "pm": _info_pedido_mobile(db),
            "resultado": None,
            "erro": str(e),
        })


@router.get("/municipios-options", response_class=HTMLResponse)
def municipios_options(request: Request, uf: str | None = None, db: Session = Depends(get_db)):
    municipios = []
    if uf:
        rows = db.execute(
            text("""
                SELECT DISTINCT m.codigo, m.descricao
                FROM municipio m
                JOIN estabelecimento e ON e.municipio = m.codigo
                WHERE e.uf = :uf
                ORDER BY m.descricao
            """),
            {"uf": uf.upper()},
        ).fetchall()
        municipios = [Municipio(codigo=r.codigo, descricao=r.descricao) for r in rows]
    return templates.TemplateResponse("partials/municipios_options.html", {
        "request": request,
        "municipios": municipios,
    })


@router.get("/cnaes-options", response_class=HTMLResponse)
def cnaes_options(request: Request, q: str = "", db: Session = Depends(get_db)):
    cnaes = []
    if q.strip():
        rows = db.execute(
            text("SELECT codigo, descricao FROM cnae WHERE descricao ILIKE :q ORDER BY descricao LIMIT 15"),
            {"q": f"%{q}%"},
        ).fetchall()
        cnaes = [Cnae(codigo=r.codigo, descricao=r.descricao) for r in rows]
    return templates.TemplateResponse("partials/cnaes_options.html", {
        "request": request,
        "cnaes": cnaes,
    })


@router.post("/buscar", response_class=HTMLResponse)
async def buscar_html(request: Request, db: Session = Depends(get_db)):
    form = await request.form()

    uf = form.get("uf") or None
    municipio_codigo = form.get("municipio_codigo") or None
    segmento = form.get("segmento") or None
    cnaes_raw = form.get("cnaes") or ""
    cnaes_lista = [c.strip() for c in cnaes_raw.split(",") if c.strip()] if cnaes_raw else None
    apenas_ativas = form.get("apenas_ativas") == "true"
    porte = form.get("porte") or None
    page = int(form.get("page") or 1)
    page_size = 50

    req = BuscarRequest(
        uf=uf,
        municipio_codigo=municipio_codigo,
        segmento=segmento,
        cnaes=cnaes_lista,
        apenas_ativas=apenas_ativas,
        porte=porte,
        page=page,
        page_size=page_size,
    )

    resultado = buscar(req, db)
    items = resultado.items

    leads_json = json.dumps([{
        "cnpj": l.cnpj,
        "razao_social": l.razao_social,
        "nome_fantasia": l.nome_fantasia,
        "logradouro": l.logradouro,
        "tipo_logradouro": l.tipo_logradouro,
        "numero": l.numero,
        "municipio": l.municipio,
        "uf": l.uf,
        "cep": l.cep,
        "ddd_1": l.ddd_1,
        "telefone_1": l.telefone_1,
    } for l in items], ensure_ascii=False)

    return templates.TemplateResponse("partials/resultados.html", {
        "request": request,
        "resultado": resultado,
        "leads_json": leads_json,
    })


@router.post("/exportar.csv")
async def exportar_csv_form(request: Request, db: Session = Depends(get_db)):
    from routers.api import exportar_csv
    form = await request.form()
    req = _form_to_req(form)
    return exportar_csv(req, db)


@router.post("/exportar.xlsx")
async def exportar_xlsx_form(request: Request, db: Session = Depends(get_db)):
    from routers.api import exportar_xlsx
    form = await request.form()
    req = _form_to_req(form)
    return exportar_xlsx(req, db)


def _form_to_req(form) -> BuscarRequest:
    cnaes_raw = form.get("cnaes") or ""
    return BuscarRequest(
        uf=form.get("uf") or None,
        municipio_codigo=form.get("municipio_codigo") or None,
        segmento=form.get("segmento") or None,
        cnaes=[c.strip() for c in cnaes_raw.split(",") if c.strip()] if cnaes_raw else None,
        apenas_ativas=form.get("apenas_ativas") == "true",
        porte=form.get("porte") or None,
        page=1,
        page_size=100000,
    )
