from fastapi import APIRouter, Depends, Request
from fastapi.responses import HTMLResponse, RedirectResponse
from app.template_utils import get_templates

from app.database import get_db
from app.services import report_service
from sqlalchemy.orm import Session

router = APIRouter(prefix="/reports", tags=["reports"])
templates = get_templates()


@router.get("", response_class=HTMLResponse)
def report_list(request: Request, db: Session = Depends(get_db)):
    reports = report_service.list_reports(db)
    return templates.TemplateResponse("reports.html", {
        "request": request, "reports": reports,
    })


@router.get("/{report_id}", response_class=HTMLResponse)
def report_detail(report_id: int, request: Request, db: Session = Depends(get_db)):
    report = report_service.get_report(db, report_id)
    if not report:
        return RedirectResponse("/reports", status_code=303)
    return templates.TemplateResponse("report_detail.html", {
        "request": request, "report": report,
    })


@router.post("/generate/{report_type}")
def report_generate(report_type: str, db: Session = Depends(get_db)):
    if report_type not in ("daily", "weekly", "monthly"):
        report_type = "daily"
    report_service.generate_report(db, report_type)
    return RedirectResponse("/reports", status_code=303)


