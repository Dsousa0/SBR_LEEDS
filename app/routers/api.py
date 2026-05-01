import csv
import io
import math

import openpyxl
from fastapi import APIRouter, Depends, HTTPException, Query
from fastapi.responses import StreamingResponse
from sqlalchemy import text
from sqlalchemy.orm import Session

from database import get_db
from schemas import (
    AtalhosCnae,
    BuscarRequest,
    BuscarResponse,
    Cnae,
    Lead,
    Municipio,
    Stats,
    UF,
)

router = APIRouter(prefix="/api")

# ---------------------------------------------------------------------------
# Dados estáticos
# ---------------------------------------------------------------------------

_UFS = [
    ("AC", "Acre"), ("AL", "Alagoas"), ("AP", "Amapá"), ("AM", "Amazonas"),
    ("BA", "Bahia"), ("CE", "Ceará"), ("DF", "Distrito Federal"),
    ("ES", "Espírito Santo"), ("GO", "Goiás"), ("MA", "Maranhão"),
    ("MT", "Mato Grosso"), ("MS", "Mato Grosso do Sul"), ("MG", "Minas Gerais"),
    ("PA", "Pará"), ("PB", "Paraíba"), ("PR", "Paraná"), ("PE", "Pernambuco"),
    ("PI", "Piauí"), ("RJ", "Rio de Janeiro"), ("RN", "Rio Grande do Norte"),
    ("RS", "Rio Grande do Sul"), ("RO", "Rondônia"), ("RR", "Roraima"),
    ("SC", "Santa Catarina"), ("SP", "São Paulo"), ("SE", "Sergipe"),
    ("TO", "Tocantins"),
]

ATALHOS = [
    {"segmento": "farmacia",     "descricao": "Farmácias e drogarias",        "cnaes": ["4771701", "4771702", "4771703"]},
    {"segmento": "restaurante",  "descricao": "Restaurantes e lanchonetes",   "cnaes": ["5611201", "5611203", "5611204", "5611205"]},
    {"segmento": "oficina",      "descricao": "Oficinas mecânicas",           "cnaes": ["4520001", "4520002", "4520003", "4520004", "4520005"]},
    {"segmento": "supermercado", "descricao": "Supermercados e mercados",     "cnaes": ["4711301", "4711302"]},
    {"segmento": "padaria",      "descricao": "Padarias e confeitarias",      "cnaes": ["1091102", "4721102"]},
    {"segmento": "salao",        "descricao": "Salões de beleza e barbearias","cnaes": ["9602501", "9602502"]},
    {"segmento": "clinica",      "descricao": "Clínicas médicas",             "cnaes": ["8630501", "8630502", "8630503"]},
    {"segmento": "academia",     "descricao": "Academias de ginástica",       "cnaes": ["9313100"]},
    {"segmento": "advocacia",    "descricao": "Escritórios de advocacia",     "cnaes": ["6911701"]},
    {"segmento": "contabilidade","descricao": "Contabilidade e auditoria",    "cnaes": ["6920601", "6920602"]},
]

_ATALHOS_MAP = {a["segmento"]: a["cnaes"] for a in ATALHOS}

PORTES = {
    "00": "Não informado",
    "01": "MEI",
    "03": "ME",
    "05": "EPP",
    "99": "Demais",
}


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _resolve_cnaes(req: BuscarRequest) -> list[str] | None:
    """Retorna lista de CNAEs resolvidos (segmento ou explícitos)."""
    if req.segmento:
        cnaes = _ATALHOS_MAP.get(req.segmento)
        if not cnaes:
            raise HTTPException(400, f"Segmento desconhecido: {req.segmento}")
        return cnaes
    return req.cnaes or None


def _build_where(req: BuscarRequest, cnaes: list[str] | None) -> tuple[str, dict]:
    """Constrói cláusula WHERE e dicionário de parâmetros para a busca."""
    conditions = ["1=1"]
    params: dict = {}

    if req.uf:
        conditions.append("e.uf = :uf")
        params["uf"] = req.uf.upper()

    if req.municipio_codigo:
        conditions.append("e.municipio = :municipio")
        params["municipio"] = req.municipio_codigo

    if cnaes:
        conditions.append("e.cnae_fiscal_principal = ANY(:cnaes)")
        params["cnaes"] = cnaes

    if req.apenas_ativas:
        conditions.append("e.situacao_cadastral = '02'")

    if req.porte:
        conditions.append("emp.porte = :porte")
        params["porte"] = req.porte

    return " AND ".join(conditions), params


_SELECT_LEADS = """
    SELECT
        e.cnpj_basico || e.cnpj_ordem || e.cnpj_dv AS cnpj,
        emp.razao_social,
        e.nome_fantasia,
        e.cnae_fiscal_principal,
        c.descricao   AS cnae_descricao,
        e.tipo_logradouro,
        e.logradouro,
        e.numero,
        e.complemento,
        e.bairro,
        e.cep,
        e.uf,
        m.descricao   AS municipio,
        e.ddd_1,
        e.telefone_1,
        e.ddd_2,
        e.telefone_2,
        e.correio_eletronico,
        e.situacao_cadastral,
        emp.porte,
        emp.capital_social
    FROM estabelecimento e
    LEFT JOIN empresa    emp ON emp.cnpj_basico = e.cnpj_basico
    LEFT JOIN municipio  m   ON m.codigo        = e.municipio
    LEFT JOIN cnae       c   ON c.codigo        = e.cnae_fiscal_principal
"""


def _row_to_lead(row) -> Lead:
    return Lead(
        cnpj=row.cnpj or "",
        razao_social=row.razao_social,
        nome_fantasia=row.nome_fantasia,
        cnae_principal=row.cnae_fiscal_principal,
        cnae_descricao=row.cnae_descricao,
        tipo_logradouro=row.tipo_logradouro,
        logradouro=row.logradouro,
        numero=row.numero,
        complemento=row.complemento,
        bairro=row.bairro,
        cep=row.cep,
        uf=row.uf,
        municipio=row.municipio,
        ddd_1=row.ddd_1,
        telefone_1=row.telefone_1,
        ddd_2=row.ddd_2,
        telefone_2=row.telefone_2,
        email=row.correio_eletronico,
        situacao=row.situacao_cadastral,
        porte=row.porte,
        capital_social=float(row.capital_social) if row.capital_social else None,
    )


def _leads_to_rows(leads: list[Lead]) -> list[list]:
    """Converte lista de leads para linhas (header + dados) para CSV/XLSX."""
    header = [
        "CNPJ", "Razão Social", "Nome Fantasia", "CNAE", "Descrição CNAE",
        "Logradouro", "Número", "Complemento", "Bairro", "CEP",
        "UF", "Município", "DDD 1", "Telefone 1", "DDD 2", "Telefone 2",
        "E-mail", "Situação", "Porte", "Capital Social",
    ]
    rows = [header]
    for l in leads:
        logradouro = f"{l.tipo_logradouro or ''} {l.logradouro or ''}".strip()
        rows.append([
            l.cnpj, l.razao_social, l.nome_fantasia,
            l.cnae_principal, l.cnae_descricao,
            logradouro, l.numero, l.complemento, l.bairro, l.cep,
            l.uf, l.municipio,
            l.ddd_1, l.telefone_1, l.ddd_2, l.telefone_2,
            l.email, l.situacao, PORTES.get(l.porte or "", l.porte),
            l.capital_social,
        ])
    return rows


# ---------------------------------------------------------------------------
# Endpoints de referência
# ---------------------------------------------------------------------------

@router.get("/ufs", response_model=list[UF])
def listar_ufs():
    return [UF(sigla=s, nome=n) for s, n in _UFS]


@router.get("/municipios", response_model=list[Municipio])
def listar_municipios(
    uf: str | None = Query(None, description="Filtrar por UF"),
    q: str | None = Query(None, description="Busca parcial pelo nome"),
    db: Session = Depends(get_db),
):
    sql = """
        SELECT DISTINCT m.codigo, m.descricao
        FROM municipio m
        JOIN estabelecimento e ON e.municipio = m.codigo
        WHERE (:uf   IS NULL OR e.uf         = :uf)
          AND (:q    IS NULL OR m.descricao ILIKE :q_like)
        ORDER BY m.descricao
        LIMIT 50
    """
    rows = db.execute(
        text(sql),
        {"uf": uf.upper() if uf else None, "q": q, "q_like": f"%{q}%" if q else None},
    ).fetchall()
    return [Municipio(codigo=r.codigo, descricao=r.descricao) for r in rows]


@router.get("/cnaes", response_model=list[Cnae])
def buscar_cnaes(
    q: str = Query(..., description="Texto para busca na descrição do CNAE"),
    db: Session = Depends(get_db),
):
    rows = db.execute(
        text("SELECT codigo, descricao FROM cnae WHERE descricao ILIKE :q ORDER BY descricao LIMIT 30"),
        {"q": f"%{q}%"},
    ).fetchall()
    return [Cnae(codigo=r.codigo, descricao=r.descricao) for r in rows]


@router.get("/cnaes/atalhos", response_model=list[AtalhosCnae])
def listar_atalhos():
    return [AtalhosCnae(**a) for a in ATALHOS]


# ---------------------------------------------------------------------------
# Busca de leads
# ---------------------------------------------------------------------------

@router.post("/buscar", response_model=BuscarResponse)
def buscar_leads(req: BuscarRequest, db: Session = Depends(get_db)):
    cnaes = _resolve_cnaes(req)
    where, params = _build_where(req, cnaes)

    total = db.execute(
        text(f"SELECT COUNT(*) FROM estabelecimento e LEFT JOIN empresa emp ON emp.cnpj_basico = e.cnpj_basico WHERE {where}"),
        params,
    ).scalar() or 0

    page_size = max(1, min(req.page_size, 200))
    page = max(1, req.page)
    offset = (page - 1) * page_size

    rows = db.execute(
        text(f"{_SELECT_LEADS} WHERE {where} ORDER BY emp.razao_social LIMIT :limit OFFSET :offset"),
        {**params, "limit": page_size, "offset": offset},
    ).fetchall()

    return BuscarResponse(
        total=total,
        page=page,
        page_size=page_size,
        pages=math.ceil(total / page_size) if total else 0,
        items=[_row_to_lead(r) for r in rows],
    )


# ---------------------------------------------------------------------------
# Exportação
# ---------------------------------------------------------------------------

def _exportar_todos(req: BuscarRequest, db: Session) -> list[Lead]:
    cnaes = _resolve_cnaes(req)
    where, params = _build_where(req, cnaes)
    rows = db.execute(
        text(f"{_SELECT_LEADS} WHERE {where} ORDER BY emp.razao_social LIMIT 100000"),
        params,
    ).fetchall()
    return [_row_to_lead(r) for r in rows]


@router.post("/exportar.csv")
def exportar_csv(req: BuscarRequest, db: Session = Depends(get_db)):
    leads = _exportar_todos(req, db)
    tabela = _leads_to_rows(leads)

    buf = io.StringIO()
    writer = csv.writer(buf, delimiter=";")
    writer.writerows(tabela)
    buf.seek(0)

    return StreamingResponse(
        iter([buf.getvalue().encode("utf-8-sig")]),
        media_type="text/csv",
        headers={"Content-Disposition": "attachment; filename=prospec-leads.csv"},
    )


@router.post("/exportar.xlsx")
def exportar_xlsx(req: BuscarRequest, db: Session = Depends(get_db)):
    leads = _exportar_todos(req, db)
    tabela = _leads_to_rows(leads)

    wb = openpyxl.Workbook()
    ws = wb.active
    ws.title = "Leads"
    for row in tabela:
        ws.append(row)

    # Cabeçalho em negrito
    from openpyxl.styles import Font
    for cell in ws[1]:
        cell.font = Font(bold=True)

    buf = io.BytesIO()
    wb.save(buf)
    buf.seek(0)

    return StreamingResponse(
        buf,
        media_type="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
        headers={"Content-Disposition": "attachment; filename=prospec-leads.xlsx"},
    )


# ---------------------------------------------------------------------------
# Estatísticas
# ---------------------------------------------------------------------------

@router.get("/stats", response_model=Stats)
def estatisticas(db: Session = Depends(get_db)):
    total_estab = db.execute(text("SELECT COUNT(*) FROM estabelecimento")).scalar() or 0
    total_emp = db.execute(text("SELECT COUNT(*) FROM empresa")).scalar() or 0

    ultima = db.execute(
        text("SELECT mes_referencia FROM importacao WHERE status='concluido' ORDER BY concluida_em DESC LIMIT 1")
    ).scalar()

    dist = db.execute(
        text("""
            SELECT uf, COUNT(*) AS total
            FROM estabelecimento
            WHERE situacao_cadastral = '02'
            GROUP BY uf
            ORDER BY total DESC
        """)
    ).fetchall()

    return Stats(
        total_estabelecimentos=total_estab,
        total_empresas=total_emp,
        ultima_importacao=ultima,
        distribuicao_uf=[{"uf": r.uf, "total": r.total} for r in dist],
    )
