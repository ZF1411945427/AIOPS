from fastapi import APIRouter, Depends, Request, Form
from fastapi.responses import HTMLResponse, RedirectResponse, PlainTextResponse
from sqlalchemy.orm import Session
from app.database import get_db
from app.models import TraceAnomalyConfig, Span
from app.template_utils import get_templates

router = APIRouter(prefix="/trace-anomaly", tags=["trace-anomaly"])
templates = get_templates()


@router.get("", response_class=HTMLResponse)
def trace_anomaly_page(request: Request, db: Session = Depends(get_db)):
    configs = db.query(TraceAnomalyConfig).all()
    services = [r[0] for r in db.query(Span.service_name).distinct().all()]
    return templates.TemplateResponse("trace_anomaly.html", {
        "request": request, "configs": configs, "services": services,
    })


@router.post("/create")
def create_config(
    request: Request, name: str = Form(...), service_name: str = Form(""),
    latency_threshold_ms: float = Form(1000),
    error_rate_threshold: float = Form(0.05),
    db: Session = Depends(get_db),
):
    cfg = TraceAnomalyConfig(
        name=name, service_name=service_name,
        latency_threshold_ms=latency_threshold_ms,
        error_rate_threshold=error_rate_threshold,
    )
    db.add(cfg)
    db.commit()
    return RedirectResponse("/trace-anomaly", status_code=303)


@router.post("/toggle/{cfg_id}")
def toggle_config(cfg_id: int, db: Session = Depends(get_db)):
    cfg = db.query(TraceAnomalyConfig).filter(TraceAnomalyConfig.id == cfg_id).first()
    if cfg:
        cfg.enabled = not cfg.enabled
        db.commit()
    return RedirectResponse("/trace-anomaly", status_code=303)


@router.get("/detect", response_class=HTMLResponse)
def detect_anomalies(request: Request, db: Session = Depends(get_db)):
    configs = db.query(TraceAnomalyConfig).filter(TraceAnomalyConfig.enabled == True).all()
    anomalies = []
    for cfg in configs:
        q = db.query(Span)
        if cfg.service_name:
            q = q.filter(Span.service_name == cfg.service_name)
        # Latency anomaly
        slow = q.filter(Span.duration_ms > cfg.latency_threshold_ms).count()
        # Error anomaly
        total = q.count()
        errors = q.filter(Span.status != "OK").count()
        error_rate = errors / total if total > 0 else 0
        if slow > 0 or error_rate > cfg.error_rate_threshold:
            anomalies.append({
                "config": cfg,
                "slow_spans": slow,
                "total_spans": total,
                "errors": errors,
                "error_rate": round(error_rate * 100, 1),
            })
    services = [r[0] for r in db.query(Span.service_name).distinct().all()]
    configs = db.query(TraceAnomalyConfig).all()
    return templates.TemplateResponse("trace_anomaly.html", {
        "request": request, "configs": configs, "services": services,
        "anomalies": anomalies, "detected": True,
    })
