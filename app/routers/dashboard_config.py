import json
from fastapi import APIRouter, Depends, Request
from fastapi.responses import HTMLResponse, RedirectResponse
from sqlalchemy.orm import Session
from app.database import get_db
from app.models import DashboardCardConfig, User
from app.routers.auth import get_current_user
from app.template_utils import get_templates

router = APIRouter(prefix="/dashboard-config", tags=["dashboard_config"])
templates = get_templates()


@router.get("", response_class=HTMLResponse)
def config_view(request: Request, db: Session = Depends(get_db)):
    user = get_current_user(request, db)
    cards = db.query(DashboardCardConfig).filter(
        DashboardCardConfig.user_id == user.id
    ).order_by(DashboardCardConfig.position).all()
    return templates.TemplateResponse("dashboard_config.html", {
        "request": request, "cards": cards,
        "all_card_types": CARD_TYPES,
    })


CARD_TYPES = {
    "health_score": "系统健康评分",
    "asset_stats": "资产统计",
    "alert_summary": "告警概要",
    "recent_alerts": "最近告警",
    "asset_type_dist": "资产类型分布",
    "k8s_overview": "K8s 概览",
    "incident_summary": "故障单概要",
}


@router.post("/toggle/{card_type}")
def toggle_card(card_type: str, request: Request, db: Session = Depends(get_db)):
    from app.auth import get_current_user
    user = get_current_user(request, db)
    card = db.query(DashboardCardConfig).filter(
        DashboardCardConfig.user_id == user.id,
        DashboardCardConfig.card_type == card_type,
    ).first()
    if card:
        card.visible = not card.visible
    else:
        card = DashboardCardConfig(
            user_id=user.id,
            card_type=card_type,
            title=CARD_TYPES.get(card_type, card_type),
            visible=False,
            position=0,
        )
        db.add(card)
    db.commit()
    return RedirectResponse("/dashboard-config", status_code=303)
