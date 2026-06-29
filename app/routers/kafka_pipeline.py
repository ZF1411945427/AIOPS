from fastapi import APIRouter, Depends, Request, Form
from fastapi.responses import HTMLResponse, RedirectResponse, PlainTextResponse
from sqlalchemy.orm import Session
from app.database import get_db
from app.models import KafkaPipeline
from app.template_utils import get_templates

router = APIRouter(prefix="/kafka", tags=["kafka"])
templates = get_templates()


@router.get("", response_class=HTMLResponse)
def kafka_page(request: Request, db: Session = Depends(get_db)):
    pipelines = db.query(KafkaPipeline).all()
    return templates.TemplateResponse("kafka.html", {
        "request": request, "pipelines": pipelines,
    })


@router.post("/create")
def create_pipeline(
    request: Request, name: str = Form(...), brokers: str = Form(...),
    topic: str = Form(...), group_id: str = Form("aiops"),
    pipeline_type: str = Form("log"), transform: str = Form("raw"),
    db: Session = Depends(get_db),
):
    pipe = KafkaPipeline(
        name=name, brokers=brokers, topic=topic, group_id=group_id,
        pipeline_type=pipeline_type, transform=transform,
    )
    db.add(pipe)
    db.commit()
    return RedirectResponse("/kafka", status_code=303)


@router.post("/toggle/{pipe_id}")
def toggle_pipeline(pipe_id: int, db: Session = Depends(get_db)):
    pipe = db.query(KafkaPipeline).filter(KafkaPipeline.id == pipe_id).first()
    if pipe:
        pipe.enabled = not pipe.enabled
        db.commit()
    return RedirectResponse("/kafka", status_code=303)


@router.post("/delete/{pipe_id}")
def delete_pipeline(pipe_id: int, db: Session = Depends(get_db)):
    pipe = db.query(KafkaPipeline).filter(KafkaPipeline.id == pipe_id).first()
    if pipe:
        db.delete(pipe)
        db.commit()
    return RedirectResponse("/kafka", status_code=303)
