from fastapi import APIRouter, Depends, Request
from fastapi.responses import HTMLResponse, RedirectResponse
from app.template_utils import get_templates

from app.database import get_db
from app.services import incident_service, rca_service
from sqlalchemy.orm import Session

router = APIRouter(prefix="/incidents", tags=["incidents"])
templates = get_templates()


@router.get("", response_class=HTMLResponse)
def incident_list(request: Request, status: str = "", db: Session = Depends(get_db)):
    incidents = incident_service.list_incidents(db, status)
    return templates.TemplateResponse("incidents.html", {
        "request": request, "incidents": incidents, "status_filter": status,
    })


@router.get("/{incident_id}", response_class=HTMLResponse)
def incident_detail(incident_id: int, request: Request, db: Session = Depends(get_db)):
    detail = incident_service.get_incident_detail(db, incident_id)
    if not detail:
        return RedirectResponse("/incidents", status_code=303)
    return templates.TemplateResponse("incident_detail.html", {
        "request": request, **detail,
    })


@router.get("/{incident_id}/rca", response_class=HTMLResponse)
def incident_rca(incident_id: int, request: Request, db: Session = Depends(get_db)):
    detail = incident_service.get_incident_detail(db, incident_id)
    if not detail:
        return RedirectResponse("/incidents", status_code=303)
    analysis = rca_service.analyze_incident(db, incident_id)
    return templates.TemplateResponse("incident_rca.html", {
        "request": request, **detail, "analysis": analysis,
    })


@router.post("/{incident_id}/resolve")
def resolve_incident(incident_id: int, db: Session = Depends(get_db)):
    incident_service.resolve_incident(db, incident_id)
    return RedirectResponse("/incidents", status_code=303)


