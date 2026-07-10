from fastapi import APIRouter, Depends, Request, Body
from sqlalchemy.orm import Session
from app.database import get_db
from app.models import PredictionModel
from app.services.prediction_service import predict_with_model

router = APIRouter(prefix="/prediction-models", tags=["prediction_models"])


@router.get("/api/list")
def api_model_list(db: Session = Depends(get_db), page: int = 1, page_size: int = 20):
    query = db.query(PredictionModel).order_by(PredictionModel.created_at.desc())
    total = query.count()
    models = query.offset((page - 1) * page_size).limit(page_size).all()
    return {
        "total": total,
        "page": page,
        "page_size": page_size,
        "models": [
            {
                "id": m.id, "name": m.name, "metric_name": m.metric_name,
                "asset_id": m.asset_id, "model_type": m.model_type,
                "params": m.params, "enabled": m.enabled,
                "created_at": m.created_at.isoformat() if m.created_at else None,
            }
            for m in models
        ],
    }


@router.post("/api/create")
def api_model_create(payload: dict = Body(...), db: Session = Depends(get_db)):
    m = PredictionModel(
        name=payload.get("name", ""), metric_name=payload.get("metric_name", ""),
        asset_id=payload.get("asset_id") or None,
        model_type=payload.get("model_type", "linear"),
        params=payload.get("params", "{}") or "{}")
    db.add(m)
    db.commit()
    db.refresh(m)
    return {"status": "ok", "id": m.id}


@router.post("/api/{mid}/toggle")
def api_model_toggle(mid: int, db: Session = Depends(get_db)):
    m = db.query(PredictionModel).filter(PredictionModel.id == mid).first()
    if m:
        m.enabled = not m.enabled
        db.commit()
    return {"status": "ok", "enabled": m.enabled if m else None}


@router.delete("/api/{mid}/delete")
def api_model_delete(mid: int, db: Session = Depends(get_db)):
    db.query(PredictionModel).filter(PredictionModel.id == mid).delete()
    db.commit()
    return {"status": "ok"}


@router.get("/api/{mid}/predict")
def api_model_predict(mid: int, hours_back: int = 168, db: Session = Depends(get_db)):
    """Execute prediction using a configured model."""
    model = db.query(PredictionModel).filter(PredictionModel.id == mid).first()
    if not model:
        return {"status": "error", "message": "Model not found"}
    if not model.enabled:
        return {"status": "error", "message": "Model is disabled"}

    result = predict_with_model(db, model, hours_back)
    if result is None:
        return {"status": "error", "message": "Not enough data for prediction"}

    return {"status": "ok", "result": result}


@router.get("/api/predict-all")
def api_predict_all(db: Session = Depends(get_db)):
    """Execute prediction for all enabled models."""
    models = db.query(PredictionModel).filter(PredictionModel.enabled == True).all()
    results = []
    for model in models:
        result = predict_with_model(db, model)
        if result:
            results.append(result)
    return {"status": "ok", "count": len(results), "results": results}
