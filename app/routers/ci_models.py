import json
from fastapi import APIRouter, Depends, Request, Form
from fastapi.responses import HTMLResponse, RedirectResponse
from sqlalchemy.orm import Session
from app.database import get_db
from app.models import CiModel, CiAttribute, Asset
from app.template_utils import get_templates

router = APIRouter(prefix="/ci-models", tags=["ci_models"])
templates = get_templates()


@router.get("", response_class=HTMLResponse)
def ci_model_list(request: Request, db: Session = Depends(get_db)):
    models = db.query(CiModel).order_by(CiModel.name).all()
    attr_counts = {}
    for m in models:
        attr_counts[m.id] = db.query(CiAttribute).filter(CiAttribute.ci_model_id == m.id).count()
    return templates.TemplateResponse("ci_models.html", {
        "request": request, "models": models, "attr_counts": attr_counts,
    })


@router.get("/new", response_class=HTMLResponse)
def ci_model_new_form(request: Request):
    return templates.TemplateResponse("ci_model_form.html", {
        "request": request, "model": None,
    })


@router.post("/new")
def ci_model_new(
    name: str = Form(...),
    display_name: str = Form(""),
    description: str = Form(""),
    parent_type: str = Form(""),
    icon: str = Form(""),
    db: Session = Depends(get_db),
):
    m = CiModel(name=name, display_name=display_name, description=description,
                parent_type=parent_type or None, icon=icon)
    db.add(m)
    db.commit()
    return RedirectResponse(f"/ci-models/{m.id}", status_code=303)


@router.get("/{model_id}", response_class=HTMLResponse)
def ci_model_detail(model_id: int, request: Request, db: Session = Depends(get_db)):
    m = db.query(CiModel).filter(CiModel.id == model_id).first()
    if not m:
        return RedirectResponse("/ci-models", status_code=303)
    attrs = db.query(CiAttribute).filter(CiAttribute.ci_model_id == model_id).order_by(CiAttribute.order).all()
    assets = db.query(Asset).filter(Asset.ci_type == m.name).limit(20).all()
    return templates.TemplateResponse("ci_model_detail.html", {
        "request": request, "model": m, "attrs": attrs, "assets": assets,
    })


@router.post("/{model_id}/delete")
def ci_model_delete(model_id: int, db: Session = Depends(get_db)):
    db.query(CiAttribute).filter(CiAttribute.ci_model_id == model_id).delete()
    db.query(CiModel).filter(CiModel.id == model_id).delete()
    db.commit()
    return RedirectResponse("/ci-models", status_code=303)


@router.post("/{model_id}/attrs/new")
def attr_new(
    model_id: int,
    name: str = Form(...),
    display_name: str = Form(""),
    field_type: str = Form("string"),
    required: bool = Form(False),
    default_value: str = Form(""),
    options: str = Form(""),
    order: int = Form(0),
    db: Session = Depends(get_db),
):
    a = CiAttribute(ci_model_id=model_id, name=name, display_name=display_name,
                    field_type=field_type, required=required,
                    default_value=default_value, options=options, order=order)
    db.add(a)
    db.commit()
    return RedirectResponse(f"/ci-models/{model_id}", status_code=303)


@router.post("/{model_id}/attrs/{attr_id}/delete")
def attr_delete(model_id: int, attr_id: int, db: Session = Depends(get_db)):
    db.query(CiAttribute).filter(CiAttribute.id == attr_id, CiAttribute.ci_model_id == model_id).delete()
    db.commit()
    return RedirectResponse(f"/ci-models/{model_id}", status_code=303)
