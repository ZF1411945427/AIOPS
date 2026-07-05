from fastapi import APIRouter, Depends
from fastapi.responses import JSONResponse
from sqlalchemy.orm import Session
from app.database import get_db
from app.models import Alert, KnowledgeBase, AlertKbLink
from app.services.knowledge_graph_service import recommend_kb_for_alert

router = APIRouter(prefix="/smart-recommend", tags=["smart_recommend"])


def _alert_brief(a):
    return {
        "id": a.id,
        "metric_name": a.metric_name,
        "severity": a.severity,
        "status": a.status,
        "message": a.message or "",
        "asset_id": a.asset_id,
        "created_at": a.created_at.strftime("%Y-%m-%d %H:%M:%S") if a.created_at else None,
    }


def _kb_brief(kb):
    return {
        "id": kb.id,
        "title": kb.title,
        "symptom": kb.symptom or "",
        "root_cause": kb.root_cause or "",
        "solution": kb.solution or "",
        "tags": kb.tags or "",
        "severity": kb.severity or "warning",
        "asset_type": kb.asset_type or "",
    }


@router.get("/api/recommend")
def api_recommend(alert_id: int = 0, limit: int = 5, db: Session = Depends(get_db)):
    try:
        if not alert_id:
            return JSONResponse({"error": "alert_id is required", "alert_id": 0, "recommendations": []}, status_code=400)
        selected_alert = db.query(Alert).filter(Alert.id == alert_id).first()
        if not selected_alert:
            return JSONResponse({"error": "alert not found", "alert_id": alert_id, "recommendations": []}, status_code=404)
        recs = recommend_kb_for_alert(db, selected_alert, limit=min(limit, 20))
        recommendations = []
        for entry in recs:
            linked = db.query(AlertKbLink).filter(
                AlertKbLink.alert_id == alert_id,
                AlertKbLink.kb_id == entry.id).first()
            recommendations.append({
                "kb": _kb_brief(entry),
                "linked": bool(linked),
                "score": 0,
            })
        return JSONResponse({
            "alert_id": alert_id,
            "alert": _alert_brief(selected_alert),
            "recommendations": recommendations,
            "count": len(recommendations),
        })
    except Exception as e:
        return JSONResponse({"error": str(e), "alert_id": alert_id, "recommendations": []}, status_code=500)
