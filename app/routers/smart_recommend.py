from fastapi import APIRouter, Depends, Request
from fastapi.responses import HTMLResponse
from sqlalchemy.orm import Session
from app.database import get_db
from app.models import Alert, KnowledgeBase, AlertKbLink
from app.services.knowledge_graph_service import recommend_kb_for_alert
from app.template_utils import get_templates

router = APIRouter(prefix="/smart-recommend", tags=["smart_recommend"])
templates = get_templates()


@router.get("", response_class=HTMLResponse)
def recommend_page(request: Request, alert_id: int = 0, db: Session = Depends(get_db)):
    alerts = db.query(Alert).order_by(Alert.created_at.desc()).limit(20).all()
    recommendations = []
    selected_alert = None
    if alert_id:
        selected_alert = db.query(Alert).filter(Alert.id == alert_id).first()
        if selected_alert:
            recs = recommend_kb_for_alert(db, selected_alert)
            for entry in recs:
                linked = db.query(AlertKbLink).filter(
                    AlertKbLink.alert_id == alert_id,
                    AlertKbLink.kb_id == entry.id,
                ).first()
                recommendations.append({"kb": entry, "linked": bool(linked), "score": 0})
    return templates.TemplateResponse("smart_recommend.html", {
        "request": request, "alerts": alerts,
        "selected_alert": selected_alert,
        "recommendations": recommendations,
    })
