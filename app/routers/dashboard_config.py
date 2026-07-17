import json
from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel
from sqlalchemy.orm import Session
from app.database import get_db
from app.models import DashboardLayout, DashboardCardConfig

router = APIRouter(prefix="/dashboard-config", tags=["dashboard_config"])


CARD_TYPES = [
    {"type": "stat-asset", "title": "资产概览", "icon": "Box", "desc": "在线/离线/总数", "w": 3, "h": 2},
    {"type": "stat-alert", "title": "告警概览", "icon": "WarningFilled", "desc": "活跃/已恢复", "w": 3, "h": 2},
    {"type": "stat-incident", "title": "故障概览", "icon": "Tickets", "desc": "未关闭/总数", "w": 3, "h": 2},
    {"type": "stat-health", "title": "健康评分", "icon": "DataBoard", "desc": "全局健康度", "w": 3, "h": 2},
    {"type": "chart-alert-trend", "title": "告警趋势", "icon": "TrendCharts", "desc": "近7天告警趋势", "w": 6, "h": 4},
    {"type": "chart-asset-type", "title": "资产分布", "icon": "PieChart", "desc": "资产类型饼图", "w": 3, "h": 4},
    {"type": "chart-severity", "title": "告警级别", "icon": "Warning", "desc": "严重/警告/信息", "w": 3, "h": 4},
    {"type": "chart-health-trend", "title": "健康趋势", "icon": "DataLine", "desc": "健康评分变化", "w": 6, "h": 4},
    {"type": "list-recent-alerts", "title": "最新告警", "icon": "Bell", "desc": "最近10条告警", "w": 6, "h": 4},
    {"type": "list-recent-incidents", "title": "最新故障", "icon": "Tickets", "desc": "最近5条故障", "w": 6, "h": 4},
    {"type": "chart-mttr", "title": "MTTR 趋势", "icon": "Timer", "desc": "平均恢复时间", "w": 6, "h": 4},
    {"type": "chart-remediation", "title": "自愈统计", "icon": "CircleCheck", "desc": "自愈成功率", "w": 3, "h": 4},
    {"type": "stat-datasource", "title": "数据源", "icon": "Connection", "desc": "数据源数量", "w": 3, "h": 2},
    {"type": "stat-rule", "title": "告警规则", "icon": "Setting", "desc": "规则总数", "w": 3, "h": 2},
    {"type": "chart-ai-tool", "title": "AI 工具调用", "icon": "Cpu", "desc": "工具调用趋势", "w": 6, "h": 4},
    {"type": "chart-notification", "title": "通知统计", "icon": "Message", "desc": "通知送达率", "w": 3, "h": 4},
]


@router.get("/status")
def status():
    return {"module": "dashboard_config", "status": "ok"}


@router.get("/card-types")
def get_card_types():
    return {"types": CARD_TYPES}


@router.get("/layouts")
def list_layouts(db: Session = Depends(get_db)):
    layouts = db.query(DashboardLayout).order_by(DashboardLayout.is_default.desc(), DashboardLayout.id).all()
    result = []
    for l in layouts:
        result.append({
            "id": l.id,
            "name": l.name,
            "description": l.description,
            "is_default": l.is_default,
            "is_shared": l.is_shared,
            "layout_config": json.loads(l.layout_config) if l.layout_config else [],
            "card_count": len(json.loads(l.layout_config)) if l.layout_config else 0,
            "created_at": l.created_at.isoformat() if l.created_at else None,
            "updated_at": l.updated_at.isoformat() if l.updated_at else None,
        })
    return result


@router.get("/layouts/{layout_id}")
def get_layout(layout_id: int, db: Session = Depends(get_db)):
    l = db.query(DashboardLayout).filter(DashboardLayout.id == layout_id).first()
    if not l:
        raise HTTPException(404, "仪表盘布局不存在")
    return {
        "id": l.id,
        "name": l.name,
        "description": l.description,
        "is_default": l.is_default,
        "is_shared": l.is_shared,
        "layout_config": json.loads(l.layout_config) if l.layout_config else [],
    }


class LayoutCreate(BaseModel):
    name: str
    description: str = ""
    layout_config: list = []
    is_default: bool = False
    is_shared: bool = False


@router.post("/layouts")
def create_layout(body: LayoutCreate, db: Session = Depends(get_db)):
    if body.is_default:
        db.query(DashboardLayout).filter(DashboardLayout.is_default == True).update({"is_default": False})
    layout = DashboardLayout(
        name=body.name,
        description=body.description,
        layout_config=json.dumps(body.layout_config, ensure_ascii=False),
        is_default=body.is_default,
        is_shared=body.is_shared,
    )
    db.add(layout)
    db.commit()
    db.refresh(layout)
    return {"id": layout.id, "name": layout.name, "message": "创建成功"}


@router.put("/layouts/{layout_id}")
def update_layout(layout_id: int, body: LayoutCreate, db: Session = Depends(get_db)):
    layout = db.query(DashboardLayout).filter(DashboardLayout.id == layout_id).first()
    if not layout:
        raise HTTPException(404, "仪表盘布局不存在")
    if body.is_default:
        db.query(DashboardLayout).filter(DashboardLayout.is_default == True, DashboardLayout.id != layout_id).update({"is_default": False})
    layout.name = body.name
    layout.description = body.description
    layout.layout_config = json.dumps(body.layout_config, ensure_ascii=False)
    layout.is_default = body.is_default
    layout.is_shared = body.is_shared
    db.commit()
    return {"message": "更新成功"}


@router.delete("/layouts/{layout_id}")
def delete_layout(layout_id: int, db: Session = Depends(get_db)):
    layout = db.query(DashboardLayout).filter(DashboardLayout.id == layout_id).first()
    if not layout:
        raise HTTPException(404, "仪表盘布局不存在")
    if layout.is_default:
        raise HTTPException(400, "默认布局不可删除")
    db.delete(layout)
    db.commit()
    return {"message": "已删除"}


@router.post("/layouts/{layout_id}/set-default")
def set_default(layout_id: int, db: Session = Depends(get_db)):
    layout = db.query(DashboardLayout).filter(DashboardLayout.id == layout_id).first()
    if not layout:
        raise HTTPException(404, "仪表盘布局不存在")
    db.query(DashboardLayout).filter(DashboardLayout.is_default == True).update({"is_default": False})
    layout.is_default = True
    db.commit()
    return {"message": "已设为默认"}


PRESET_LAYOUTS = [
    {
        "name": "运维总览",
        "description": "综合运维视图：资产、告警、故障、健康一目了然",
        "is_default": True,
        "is_shared": True,
        "layout_config": [
            {"id": "c1", "type": "stat-asset", "title": "资产概览", "x": 0, "y": 0, "w": 3, "h": 2},
            {"id": "c2", "type": "stat-alert", "title": "告警概览", "x": 3, "y": 0, "w": 3, "h": 2},
            {"id": "c3", "type": "stat-incident", "title": "故障概览", "x": 6, "y": 0, "w": 3, "h": 2},
            {"id": "c4", "type": "stat-health", "title": "健康评分", "x": 9, "y": 0, "w": 3, "h": 2},
            {"id": "c5", "type": "chart-alert-trend", "title": "告警趋势", "x": 0, "y": 2, "w": 6, "h": 4},
            {"id": "c6", "type": "chart-asset-type", "title": "资产分布", "x": 6, "y": 2, "w": 3, "h": 4},
            {"id": "c7", "type": "chart-severity", "title": "告警级别", "x": 9, "y": 2, "w": 3, "h": 4},
            {"id": "c8", "type": "list-recent-alerts", "title": "最新告警", "x": 0, "y": 6, "w": 6, "h": 4},
            {"id": "c9", "type": "list-recent-incidents", "title": "最新故障", "x": 6, "y": 6, "w": 6, "h": 4},
        ],
    },
    {
        "name": "告警中心",
        "description": "专注告警分析：趋势、级别、MTTR、通知",
        "is_default": False,
        "is_shared": True,
        "layout_config": [
            {"id": "c1", "type": "stat-alert", "title": "告警概览", "x": 0, "y": 0, "w": 4, "h": 2},
            {"id": "c2", "type": "stat-rule", "title": "告警规则", "x": 4, "y": 0, "w": 4, "h": 2},
            {"id": "c3", "type": "stat-datasource", "title": "数据源", "x": 8, "y": 0, "w": 4, "h": 2},
            {"id": "c4", "type": "chart-alert-trend", "title": "告警趋势", "x": 0, "y": 2, "w": 8, "h": 4},
            {"id": "c5", "type": "chart-severity", "title": "告警级别", "x": 8, "y": 2, "w": 4, "h": 4},
            {"id": "c6", "type": "chart-mttr", "title": "MTTR 趋势", "x": 0, "y": 6, "w": 6, "h": 4},
            {"id": "c7", "type": "chart-notification", "title": "通知统计", "x": 6, "y": 6, "w": 6, "h": 4},
        ],
    },
    {
        "name": "SRE 看板",
        "description": "SRE 可靠性视图：自愈、健康趋势、AI效能",
        "is_default": False,
        "is_shared": True,
        "layout_config": [
            {"id": "c1", "type": "stat-health", "title": "健康评分", "x": 0, "y": 0, "w": 4, "h": 2},
            {"id": "c2", "type": "stat-incident", "title": "故障概览", "x": 4, "y": 0, "w": 4, "h": 2},
            {"id": "c3", "type": "chart-remediation", "title": "自愈统计", "x": 8, "y": 0, "w": 4, "h": 2},
            {"id": "c4", "type": "chart-health-trend", "title": "健康趋势", "x": 0, "y": 2, "w": 8, "h": 4},
            {"id": "c5", "type": "chart-remediation", "title": "自愈成功率", "x": 8, "y": 2, "w": 4, "h": 4},
            {"id": "c6", "type": "chart-ai-tool", "title": "AI 工具调用", "x": 0, "y": 6, "w": 12, "h": 4},
        ],
    },
]


@router.post("/seed-presets")
def seed_preset_layouts(db: Session = Depends(get_db)):
    existing = db.query(DashboardLayout).count()
    if existing > 0:
        return {"message": "已有布局，跳过播种", "count": existing}
    for p in PRESET_LAYOUTS:
        layout = DashboardLayout(
            name=p["name"],
            description=p["description"],
            layout_config=json.dumps(p["layout_config"], ensure_ascii=False),
            is_default=p["is_default"],
            is_shared=p["is_shared"],
        )
        db.add(layout)
    db.commit()
    return {"message": "预置仪表盘已播种", "count": len(PRESET_LAYOUTS)}
