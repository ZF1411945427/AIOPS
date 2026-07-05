import json
from fastapi import APIRouter, Depends, Request
from sqlalchemy.orm import Session

from app.database import get_db
from app.services import report_service

router = APIRouter(prefix="/reports", tags=["reports"])


@router.get("/api/list")
def api_report_list(db: Session = Depends(get_db)):
    reports = report_service.list_reports(db)
    return {
        "reports": [
            {
                "id": r.id, "title": r.title, "type": r.type,
                "period_start": r.period_start.isoformat() if r.period_start else None,
                "period_end": r.period_end.isoformat() if r.period_end else None,
                "summary": r.summary, "created_at": r.created_at.isoformat() if r.created_at else None,
            }
            for r in reports
        ],
        "count": len(reports),
    }


@router.get("/api/{report_id}")
def api_report_detail(report_id: int, db: Session = Depends(get_db)):
    report = report_service.get_report(db, report_id)
    if not report:
        return {"status": "error", "message": "报表不存在"}
    data = {}
    if report.data:
        try:
            data = json.loads(report.data)
        except (json.JSONDecodeError, TypeError):
            data = {}
    return {
        "id": report.id, "title": report.title, "type": report.type,
        "period_start": report.period_start.isoformat() if report.period_start else None,
        "period_end": report.period_end.isoformat() if report.period_end else None,
        "summary": report.summary, "data": data,
        "created_at": report.created_at.isoformat() if report.created_at else None,
    }


@router.post("/api/generate/{report_type}")
def api_report_generate(report_type: str, db: Session = Depends(get_db)):
    if report_type not in ("daily", "weekly", "monthly"):
        report_type = "daily"
    report = report_service.generate_report(db, report_type)
    return {"status": "ok", "id": report.id, "title": report.title}
