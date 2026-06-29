from fastapi import APIRouter, Depends, Request, Form
from fastapi.responses import HTMLResponse, JSONResponse
from sqlalchemy.orm import Session
from app.database import get_db
from app.models import Incident
from app.services.pcadr_service import run_pcadr
from app.template_utils import get_templates

router = APIRouter(prefix="/pcadr", tags=["pcadr"])
templates = get_templates()


@router.get("", response_class=HTMLResponse)
def pcadr_page(request: Request, db: Session = Depends(get_db)):
    incidents = db.query(Incident).order_by(Incident.created_at.desc()).limit(20).all()
    return templates.TemplateResponse("pcadr.html", {
        "request": request, "incidents": incidents,
    })


@router.post("/analyze")
def pcadr_analyze(
    request: Request,
    incident_id: int = Form(0),
    asset_id: int = Form(0),
    hours: int = Form(6),
    db: Session = Depends(get_db),
):
    result = run_pcadr(db, incident_id=incident_id or None, asset_id=asset_id or None, hours=hours)
    incidents = db.query(Incident).order_by(Incident.created_at.desc()).limit(20).all()
    return templates.TemplateResponse("pcadr.html", {
        "request": request, "result": result, "incidents": incidents,
    })
