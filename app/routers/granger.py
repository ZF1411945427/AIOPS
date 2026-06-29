import numpy as np
from statsmodels.tsa.stattools import grangercausalitytests
from datetime import datetime, timedelta
from fastapi import APIRouter, Depends, Request, Form
from fastapi.responses import HTMLResponse
from sqlalchemy.orm import Session
from app.database import get_db
from app.models import MetricRecord, Asset
from app.template_utils import get_templates

router = APIRouter(prefix="/granger", tags=["granger"])
templates = get_templates()


@router.get("", response_class=HTMLResponse)
def granger_page(request: Request, db: Session = Depends(get_db)):
    metrics = [r[0] for r in db.query(MetricRecord.name).distinct().all()]
    return templates.TemplateResponse("granger.html", {
        "request": request, "metrics": metrics, "result": None,
    })


@router.post("/analyze", response_class=HTMLResponse)
def granger_analyze(
    request: Request,
    metric_x: str = Form(...),
    metric_y: str = Form(...),
    hours: int = Form(24),
    max_lag: int = Form(5),
    db: Session = Depends(get_db),
):
    since = datetime.now() - timedelta(hours=hours)
    x_records = db.query(MetricRecord).filter(
        MetricRecord.name == metric_x, MetricRecord.timestamp >= since
    ).order_by(MetricRecord.timestamp).all()
    y_records = db.query(MetricRecord).filter(
        MetricRecord.name == metric_y, MetricRecord.timestamp >= since
    ).order_by(MetricRecord.timestamp).all()
    if len(x_records) < max_lag + 5 or len(y_records) < max_lag + 5:
        metrics = [r[0] for r in db.query(MetricRecord.name).distinct().all()]
        return templates.TemplateResponse("granger.html", {
            "request": request, "metrics": metrics,
            "error": "Data points insufficient (need >= {})".format(max_lag + 5),
        })

    min_len = min(len(x_records), len(y_records))
    x_vals = np.array([r.value for r in x_records[:min_len]])
    y_vals = np.array([r.value for r in y_records[:min_len]])
    data = np.column_stack([x_vals, y_vals])

    try:
        gc_res = grangercausalitytests(data, maxlag=max_lag, verbose=False)
        results = []
        for lag, res in gc_res.items():
            ssr_ftest = res[0]["ssr_ftest"]
            pvalue = ssr_ftest[1]
            results.append({
                "lag": lag,
                "ssr_f": round(ssr_ftest[0], 4),
                "pvalue": round(pvalue, 6),
                "significant": pvalue < 0.05,
            })
        # Also test reverse
        data_rev = np.column_stack([y_vals, x_vals])
        gc_rev = grangercausalitytests(data_rev, maxlag=max_lag, verbose=False)
        reverse_results = []
        for lag, res in gc_rev.items():
            ssr_ftest = res[0]["ssr_ftest"]
            pvalue = ssr_ftest[1]
            reverse_results.append({
                "lag": lag,
                "ssr_f": round(ssr_ftest[0], 4),
                "pvalue": round(pvalue, 6),
                "significant": pvalue < 0.05,
            })
    except Exception as e:
        metrics = [r[0] for r in db.query(MetricRecord.name).distinct().all()]
        return templates.TemplateResponse("granger.html", {
            "request": request, "metrics": metrics, "error": f"Analysis error: {e}",
        })

    metrics = [r[0] for r in db.query(MetricRecord.name).distinct().all()]
    return templates.TemplateResponse("granger.html", {
        "request": request, "metrics": metrics,
        "result": {
            "metric_x": metric_x, "metric_y": metric_y,
            "data_points": min_len,
            "x_causes_y": results,
            "y_causes_x": reverse_results,
        },
    })
