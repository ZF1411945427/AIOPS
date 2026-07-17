from fastapi import APIRouter, Depends, Request, Form
from fastapi.responses import JSONResponse
from app.template_utils import get_templates

from app.database import get_db
from app.models import MetricRecord
from app.services import anomaly_service
from app.services import anomaly_eval_service
from sqlalchemy.orm import Session
from sqlalchemy import distinct

router = APIRouter(prefix="/anomaly", tags=["anomaly"])
templates = get_templates()


def _config_to_dict(c) -> dict:
    return {
        "id": c.id,
        "name": c.name or "",
        "metric_name": c.metric_name or "",
        "asset_id": c.asset_id,
        "algorithm": c.algorithm or "sigma",
        "sensitivity": c.sensitivity if c.sensitivity is not None else 3.0,
        "window_size": c.window_size or 20,
        "period": c.period or 12,
        "enabled": bool(c.enabled),
        "created_at": c.created_at.strftime("%Y-%m-%d %H:%M:%S") if c.created_at else None,
    }


def _bench_to_dict(b) -> dict:
    return {
        "id": b.id,
        "asset_id": b.asset_id,
        "metric_name": b.metric_name,
        "algorithm": b.algorithm,
        "window_minutes": b.window_minutes,
        "precision": b.precision,
        "recall": b.recall,
        "f1_score": b.f1_score,
        "threshold": b.threshold,
        "labeled_at": b.labeled_at.strftime("%Y-%m-%d %H:%M:%S") if b.labeled_at else None,
        "created_at": b.created_at.strftime("%Y-%m-%d %H:%M:%S") if b.created_at else None,
    }


@router.get("/api/list")
def api_config_list(db: Session = Depends(get_db)):
    """异常检测配置列表 JSON API."""
    configs = anomaly_service.list_configs(db)
    return JSONResponse({"configs": [_config_to_dict(c) for c in configs], "total": len(configs)})


@router.post("/api/configs/create")
def api_config_create(
    name: str = Form(...),
    metric_name: str = Form(...),
    asset_id: int = Form(0),
    algorithm: str = Form("sigma"),
    sensitivity: float = Form(3.0),
    window_size: int = Form(20),
    period: int = Form(12),
    db: Session = Depends(get_db)):
    """创建异常检测配置 JSON API."""
    cfg = anomaly_service.create_config(db, {
        "name": name, "metric_name": metric_name,
        "asset_id": asset_id if asset_id > 0 else None,
        "algorithm": algorithm,
        "sensitivity": sensitivity, "window_size": window_size,
        "period": period,
        "enabled": True,
    })
    return JSONResponse({"ok": True, "id": cfg.id})


@router.post("/api/configs/{config_id}/toggle")
def api_config_toggle(config_id: int, db: Session = Depends(get_db)):
    """启用/禁用异常检测配置 JSON API."""
    cfg = anomaly_service.toggle_config(db, config_id)
    if not cfg:
        return JSONResponse({"error": "not found"}, status_code=404)
    return JSONResponse({"ok": True, "enabled": bool(cfg.enabled)})


@router.post("/api/configs/{config_id}/delete")
def api_config_delete(config_id: int, db: Session = Depends(get_db)):
    """删除异常检测配置 JSON API."""
    anomaly_service.delete_config(db, config_id)
    return JSONResponse({"ok": True})


@router.get("/api/metrics")
def api_metric_list(db: Session = Depends(get_db)):
    """动态获取指标名列表（从 MetricRecord 表去重查询）."""
    names = db.query(distinct(MetricRecord.name)).order_by(MetricRecord.name).all()
    return JSONResponse({"metrics": [n[0] for n in names]})


@router.get("/api/benchmark/stats")
def api_benchmark_stats(days: int = 90, db: Session = Depends(get_db)):
    stats = anomaly_eval_service.get_benchmark_stats(db, days=days)
    return JSONResponse(stats)


@router.get("/api/benchmark")
def api_benchmark_list(
    algorithm: str = "",
    page: int = 1,
    per_page: int = 20,
    db: Session = Depends(get_db)
):
    items, total = anomaly_eval_service.get_benchmarks(db, algorithm=algorithm, page=page, per_page=per_page)
    return JSONResponse({
        "items": [_bench_to_dict(b) for b in items],
        "total": total,
        "page": page,
        "per_page": per_page,
    })


@router.post("/api/benchmark")
def api_benchmark_create(
    algorithm: str = Form(...),
    precision: float = Form(0.0),
    recall: float = Form(0.0),
    f1_score: float = Form(0.0),
    metric_name: str = Form(""),
    asset_id: int = Form(0),
    window_minutes: int = Form(60),
    threshold: float = Form(0.0),
    db: Session = Depends(get_db)
):
    bench_id = anomaly_eval_service.record_benchmark(
        db=db,
        asset_id=asset_id or None,
        metric_name=metric_name,
        algorithm=algorithm,
        window_minutes=window_minutes,
        precision=precision,
        recall=recall,
        f1_score=f1_score,
        threshold=threshold,
    )
    return JSONResponse({"ok": True, "id": bench_id})


@router.get("/api/benchmark/recommend")
def api_benchmark_recommend(
    asset_id: int = 0,
    metric_name: str = "",
    db: Session = Depends(get_db)
):
    rec = anomaly_eval_service.recommend_algorithm(
        db,
        asset_id=asset_id or None,
        metric_name=metric_name,
    )
    return JSONResponse(rec)


