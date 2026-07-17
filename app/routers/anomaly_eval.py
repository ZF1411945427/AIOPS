from fastapi import APIRouter, Depends, Query
from fastapi.responses import JSONResponse
from sqlalchemy.orm import Session
from app.database import get_db
from app.services import anomaly_eval_service

router = APIRouter(prefix="/anomaly/api", tags=["anomaly_eval"])


def _bench_to_dict(b):
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
        "created_at": b.created_at.strftime("%Y-%m-%d %H:%M:%S") if b.created_at else None,
    }


@router.get("/benchmark")
def get_benchmarks(
    algorithm: str = Query(""),
    page: int = Query(1, ge=1),
    per_page: int = Query(20, ge=1, le=100),
    db: Session = Depends(get_db),
):
    items, total = anomaly_eval_service.get_benchmarks(db, algorithm=algorithm, page=page, per_page=per_page)
    return JSONResponse({
        "items": [_bench_to_dict(b) for b in items],
        "total": total,
        "page": page,
        "per_page": per_page,
    })


@router.post("/benchmark")
def record_benchmark(payload: dict, db: Session = Depends(get_db)):
    bench_id = anomaly_eval_service.record_benchmark(db, **payload)
    return JSONResponse({"ok": True, "id": bench_id})


@router.get("/benchmark/stats")
def get_stats(days: int = Query(90, ge=7, le=365), db: Session = Depends(get_db)):
    stats = anomaly_eval_service.get_benchmark_stats(db, days=days)
    return JSONResponse(stats)


@router.get("/benchmark/recommend")
def recommend_algorithm(asset_id: int = None, metric_name: str = "", db: Session = Depends(get_db)):
    rec = anomaly_eval_service.recommend_algorithm(db, asset_id=asset_id, metric_name=metric_name)
    return JSONResponse(rec)
