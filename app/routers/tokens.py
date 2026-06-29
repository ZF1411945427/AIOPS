from fastapi import APIRouter, Depends, Request, Form
from fastapi.responses import HTMLResponse, RedirectResponse
from app.template_utils import get_templates

from app.database import get_db
from app.services import token_service
from sqlalchemy.orm import Session

router = APIRouter(prefix="/api-tokens", tags=["api-tokens"])
templates = get_templates()


@router.get("", response_class=HTMLResponse)
def token_list(request: Request, db: Session = Depends(get_db)):
    tokens = token_service.list_tokens(db)
    return templates.TemplateResponse("api_tokens.html", {
        "request": request, "tokens": tokens,
    })


@router.post("/create")
def token_create(request: Request, name: str = Form(...), permissions: str = Form("read"), db: Session = Depends(get_db)):
    token = token_service.create_token(db, name, permissions)
    tokens = token_service.list_tokens(db)
    return templates.TemplateResponse("api_tokens.html", {
        "request": request,
        "tokens": tokens,
        "new_token": token.token,
        "new_token_name": token.name,
    })


@router.post("/{token_id}/delete")
def token_delete(token_id: int, db: Session = Depends(get_db)):
    token_service.delete_token(db, token_id)
    return RedirectResponse("/api-tokens", status_code=303)


