from fastapi import APIRouter, Depends
from fastapi.responses import JSONResponse
from pydantic import BaseModel
from sqlalchemy.orm import Session
from app.database import get_db
from app.models import Asset, SecurityBaselineTemplate, AssetBaselineCheck
from app.services.baseline_service import (
    get_baseline_templates,
    run_check,
    save_check,
    run_all_checks,
    ai_analyze,
)

router = APIRouter(prefix="/baseline", tags=["baseline"])


@router.get("/templates/{ci_type}")
def list_templates(ci_type: str, db: Session = Depends(get_db)):
    templates = (
        db.query(SecurityBaselineTemplate)
        .filter(SecurityBaselineTemplate.ci_type == ci_type, SecurityBaselineTemplate.enabled == True)
        .order_by(SecurityBaselineTemplate.sort_order)
        .all()
    )
    return {
        "ci_type": ci_type,
        "templates": [
            {
                "id": t.id,
                "check_key": t.check_key,
                "check_name": t.check_name,
                "category": t.category,
                "severity": t.severity,
                "check_method": t.check_method,
                "remediation": t.remediation,
            }
            for t in templates
        ],
    }


@router.get("/checks/{asset_id}")
def get_checks(asset_id: int, db: Session = Depends(get_db)):
    asset = db.query(Asset).filter(Asset.id == asset_id).first()
    if not asset:
        return JSONResponse({"error": "资产不存在"}, status_code=404)
    items = get_baseline_templates(asset, db)
    return {"asset_id": asset_id, "asset_name": asset.name, "items": items}


class ManualCheckReq(BaseModel):
    asset_id: int
    template_id: int
    status: str
    actual_value: str = ""
    reason: str = ""


@router.post("/checks/manual")
def manual_check(req: ManualCheckReq, db: Session = Depends(get_db)):
    save_check(req.asset_id, req.template_id, req.status, req.actual_value, req.reason, db)
    return {"ok": True}


@router.post("/check/{asset_id}/{template_id}")
def run_single_check(asset_id: int, template_id: int, db: Session = Depends(get_db)):
    asset = db.query(Asset).filter(Asset.id == asset_id).first()
    if not asset:
        return JSONResponse({"error": "资产不存在"}, status_code=404)
    template = db.query(SecurityBaselineTemplate).filter(SecurityBaselineTemplate.id == template_id).first()
    if not template:
        return JSONResponse({"error": "基线模板不存在"}, status_code=404)
    result = run_check(asset, template, db)
    save_check(asset_id, template_id, result["status"], result.get("actual_value", ""), result.get("reason", ""), db)
    return {"asset_id": asset_id, "template_id": template_id, **result}


@router.post("/check-all/{asset_id}")
def run_all(asset_id: int, db: Session = Depends(get_db)):
    asset = db.query(Asset).filter(Asset.id == asset_id).first()
    if not asset:
        return JSONResponse({"error": "资产不存在"}, status_code=404)
    result = run_all_checks(asset, db)
    return result


@router.get("/analyze/{asset_id}")
def analyze(asset_id: int, db: Session = Depends(get_db)):
    asset = db.query(Asset).filter(Asset.id == asset_id).first()
    if not asset:
        return JSONResponse({"error": "资产不存在"}, status_code=404)
    items = get_baseline_templates(asset, db)
    analysis = ai_analyze(asset, items, db)
    return {"asset_id": asset_id, "asset_name": asset.name, "items": items, "analysis": analysis}
