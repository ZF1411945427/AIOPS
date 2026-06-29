from fastapi import APIRouter, Depends, Request, Form
from fastapi.responses import HTMLResponse, RedirectResponse
from sqlalchemy.orm import Session
from app.database import get_db
from app.models import PredictionModel
from app.template_utils import get_templates

router = APIRouter(prefix="/prediction-models", tags=["prediction_models"])
templates = get_templates()


@router.get("", response_class=HTMLResponse)
def model_list(request: Request, db: Session = Depends(get_db)):
    models = db.query(PredictionModel).order_by(PredictionModel.created_at.desc()).all()
    return templates.TemplateResponse("prediction_models.html", {
        "request": request, "models": models,
    })


@router.post("/new")
def model_new(
    name: str = Form(...),
    metric_name: str = Form(...),
    asset_id: int = Form(0),
    model_type: str = Form("linear"),
    params: str = Form("{}"),
    db: Session = Depends(get_db),
):
    m = PredictionModel(
        name=name, metric_name=metric_name,
        asset_id=asset_id if asset_id else None,
        model_type=model_type, params=params,
    )
    db.add(m)
    db.commit()
    return RedirectResponse("/prediction-models", status_code=303)


@router.post("/{mid}/toggle")
def model_toggle(mid: int, db: Session = Depends(get_db)):
    m = db.query(PredictionModel).filter(PredictionModel.id == mid).first()
    if m:
        m.enabled = not m.enabled
        db.commit()
    return RedirectResponse("/prediction-models", status_code=303)


@router.post("/{mid}/delete")
def model_delete(mid: int, db: Session = Depends(get_db)):
    db.query(PredictionModel).filter(PredictionModel.id == mid).delete()
    db.commit()
    return RedirectResponse("/prediction-models", status_code=303)
