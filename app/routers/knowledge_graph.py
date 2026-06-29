from fastapi import APIRouter, Depends, Request
from fastapi.responses import HTMLResponse
from app.template_utils import get_templates

from app.database import get_db
from app.services import knowledge_graph_service
from sqlalchemy.orm import Session

router = APIRouter(prefix="/knowledge/graph", tags=["knowledge-graph"])
templates = get_templates()


@router.get("", response_class=HTMLResponse)
def knowledge_graph(request: Request, db: Session = Depends(get_db)):
    graph = knowledge_graph_service.get_dependency_graph(db)
    return templates.TemplateResponse("knowledge_graph.html", {
        "request": request, "graph": graph,
    })


