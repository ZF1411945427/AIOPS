from fastapi import APIRouter, Depends, Request, Form
from fastapi.responses import HTMLResponse, RedirectResponse
from app.template_utils import get_templates

from app.database import get_db
from app.services import knowledge_service
from sqlalchemy.orm import Session

router = APIRouter(prefix="/knowledge", tags=["knowledge"])
templates = get_templates()


@router.get("", response_class=HTMLResponse)
def kb_list(request: Request, tag: str = "", db: Session = Depends(get_db)):
    items = knowledge_service.list_kb(db, tag)
    return templates.TemplateResponse("knowledge.html", {
        "request": request, "items": items, "tag_filter": tag,
    })


@router.get("/{kb_id}", response_class=HTMLResponse)
def kb_detail(kb_id: int, request: Request, db: Session = Depends(get_db)):
    item = knowledge_service.get_kb(db, kb_id)
    if not item:
        return RedirectResponse("/knowledge", status_code=303)
    return templates.TemplateResponse("knowledge_detail.html", {
        "request": request, "item": item,
    })


@router.post("/create")
def kb_create(
    title: str = Form(...),
    symptom: str = Form(""),
    root_cause: str = Form(""),
    solution: str = Form(""),
    tags: str = Form(""),
    severity: str = Form("warning"),
    asset_type: str = Form(""),
    db: Session = Depends(get_db),
):
    knowledge_service.create_kb(db, {
        "title": title, "symptom": symptom,
        "root_cause": root_cause, "solution": solution,
        "tags": tags, "severity": severity,
        "asset_type": asset_type,
    })
    return RedirectResponse("/knowledge", status_code=303)


@router.post("/{kb_id}/update")
def kb_update(
    kb_id: int,
    title: str = Form(...),
    symptom: str = Form(""),
    root_cause: str = Form(""),
    solution: str = Form(""),
    tags: str = Form(""),
    severity: str = Form("warning"),
    asset_type: str = Form(""),
    db: Session = Depends(get_db),
):
    knowledge_service.update_kb(db, kb_id, {
        "title": title, "symptom": symptom,
        "root_cause": root_cause, "solution": solution,
        "tags": tags, "severity": severity,
        "asset_type": asset_type,
    })
    return RedirectResponse(f"/knowledge/{kb_id}", status_code=303)


@router.post("/{kb_id}/delete")
def kb_delete(kb_id: int, db: Session = Depends(get_db)):
    knowledge_service.delete_kb(db, kb_id)
    return RedirectResponse("/knowledge", status_code=303)


