from fastapi import APIRouter, Depends
from fastapi.responses import JSONResponse

from app.database import get_db
from app.services import knowledge_graph_service
from sqlalchemy.orm import Session

router = APIRouter(prefix="/knowledge/graph", tags=["knowledge-graph"])


@router.get("/api/graph")
def api_graph(db: Session = Depends(get_db)):
    try:
        graph = knowledge_graph_service.get_dependency_graph(db)
        return JSONResponse({
            "nodes": graph.get("nodes", []),
            "edges": graph.get("edges", []),
            "node_count": len(graph.get("nodes", [])),
            "edge_count": len(graph.get("edges", [])),
        })
    except Exception as e:
        return JSONResponse({"error": str(e), "nodes": [], "edges": []}, status_code=500)
