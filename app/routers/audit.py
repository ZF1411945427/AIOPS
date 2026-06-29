from fastapi import APIRouter, Depends
from fastapi.responses import JSONResponse
from sqlalchemy.orm import Session
from sqlalchemy import desc

from app.database import get_db
from app.models import ChangeRequest, AssetLifecycle, User

router = APIRouter(prefix="/api/audit", tags=["audit"])


@router.get("/logs")
def audit_logs(db: Session = Depends(get_db)):
    logs = []

    changes = (
        db.query(ChangeRequest)
        .order_by(desc(ChangeRequest.created_at))
        .limit(50)
        .all()
    )
    for c in changes:
        logs.append({
            "time": c.created_at.isoformat() if c.created_at else "",
            "user": "system",
            "action": "变更审批",
            "target": c.title,
            "detail": f"类型: {c.change_type} | 状态: {c.status} | 风险: {c.risk_level}",
            "ip": "",
        })

    lifecycle = (
        db.query(AssetLifecycle)
        .order_by(desc(AssetLifecycle.created_at))
        .limit(50)
        .all()
    )
    for lc in lifecycle:
        logs.append({
            "time": lc.created_at.isoformat() if lc.created_at else "",
            "user": str(lc.changed_by) if lc.changed_by else "system",
            "action": f"资产{ lc.previous_status }→{ lc.status }",
            "target": f"asset_{ lc.asset_id }",
            "detail": lc.comment or "",
            "ip": "",
        })

    logs.sort(key=lambda x: x["time"], reverse=True)
    return JSONResponse(logs[:100])
