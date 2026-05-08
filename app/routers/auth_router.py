from fastapi import APIRouter, Depends, Form, Request
from fastapi.responses import HTMLResponse, RedirectResponse
from fastapi.templating import Jinja2Templates
from sqlalchemy import text
from sqlalchemy.orm import Session

from auth import TOKEN_EXPIRE_HOURS, criar_token, get_current_user, verificar_senha
from database import get_db

templates = Jinja2Templates(directory="templates")
router = APIRouter()


@router.get("/login", response_class=HTMLResponse)
def pagina_login(request: Request, user=Depends(get_current_user)):
    if user:
        return RedirectResponse("/", status_code=302)
    return templates.TemplateResponse("login.html", {"request": request, "erro": None})


@router.post("/login")
def fazer_login(
    request: Request,
    email: str = Form(...),
    senha: str = Form(...),
    db: Session = Depends(get_db),
):
    row = db.execute(
        text("SELECT email, senha_hash, role, ativo FROM usuario WHERE email = :email"),
        {"email": email.lower().strip()},
    ).fetchone()

    if not row or not row.ativo or not verificar_senha(senha, row.senha_hash):
        return templates.TemplateResponse(
            "login.html",
            {"request": request, "erro": "E-mail ou senha inválidos."},
            status_code=401,
        )

    token = criar_token(row.email, row.role)
    response = RedirectResponse("/", status_code=302)
    response.set_cookie(
        "access_token",
        token,
        httponly=True,
        samesite="lax",
        max_age=TOKEN_EXPIRE_HOURS * 3600,
    )
    return response


@router.get("/logout")
def logout():
    response = RedirectResponse("/login", status_code=302)
    response.delete_cookie("access_token")
    return response
