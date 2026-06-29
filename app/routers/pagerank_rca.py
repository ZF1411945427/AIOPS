from fastapi import APIRouter, Depends, Request, Form
from fastapi.responses import HTMLResponse
from sqlalchemy.orm import Session
from app.database import get_db
from app.models import Incident
from app.services.rca_service import analyze_pagerank
from app.template_utils import get_templates

router = APIRouter(prefix="/pagerank-rca", tags=["pagerank_rca"])
templates = get_templates()


@router.get("", response_class=HTMLResponse)
def pagerank_page(request: Request, db: Session = Depends(get_db)):
    incidents = db.query(Incident).order_by(Incident.created_at.desc()).limit(20).all()
    return templates.TemplateResponse("pagerank_rca.html", {
        "request": request, "incidents": incidents, "result": None,
    })


@router.post("/analyze", response_class=HTMLResponse)
def pagerank_analyze(
    request: Request,
    incident_id: int = Form(0),
    damping: float = Form(0.85),
    db: Session = Depends(get_db),
):
    result = analyze_pagerank(db, incident_id=incident_id or None, damping=damping)
    incidents = db.query(Incident).order_by(Incident.created_at.desc()).limit(20).all()
    return templates.TemplateResponse("pagerank_rca.html", {
        "request": request, "result": result, "incidents": incidents,
    })
