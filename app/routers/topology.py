from fastapi import APIRouter, Depends, Request, Form
from fastapi.responses import HTMLResponse, RedirectResponse
from app.template_utils import get_templates
from sqlalchemy.orm import Session

from app.database import get_db
from app.services import topology_service
from app.models import Asset

router = APIRouter(prefix="/topology", tags=["topology"])
templates = get_templates()


@router.get("", response_class=HTMLResponse)
def topology_page(request: Request, db: Session = Depends(get_db)):
    trees = topology_service.build_topo(db)
    assets = db.query(Asset).order_by(Asset.name).all()
    relations = topology_service.get_relations(db)
    return templates.TemplateResponse("topology.html", {
        "request": request, "trees": trees, "assets": assets, "relations": relations,
    })


@router.post("/relations/create")
def relation_create(
    request: Request,
    parent_id: int = Form(...),
    child_id: int = Form(...),
    relation_type: str = Form("depends_on"),
    db: Session = Depends(get_db),
):
    topology_service.create_relation(db, parent_id, child_id, relation_type)
    return RedirectResponse("/topology", status_code=303)


@router.post("/relations/{relation_id}/delete")
def relation_delete(relation_id: int, db: Session = Depends(get_db)):
    topology_service.delete_relation(db, relation_id)
    return RedirectResponse("/topology", status_code=303)


