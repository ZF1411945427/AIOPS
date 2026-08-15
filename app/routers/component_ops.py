"""组件智能运维 —— 组件→资产绑定 API

「组件方案」页通过本接口获取组件当前匹配的真实资产,
点「问 AI」时携带 asset_id 发起针对真实实例的巡检。

端点:
  GET /component-ops/api/assets?name=MySQL   — 返回匹配组件的真实资产列表
"""
from typing import Optional

from fastapi import APIRouter, Query

from app.database import get_db
from app.services.component_ops_service import (
    resolve_component_assets,
    build_inspection_prompt,
)

router = APIRouter(prefix="/component-ops", tags=["ComponentOps"])


@router.get("/api/assets")
def api_component_assets(name: Optional[str] = Query(None)):
    db = next(get_db())
    try:
        if not name:
            return {"items": [], "name": name}
        assets = resolve_component_assets(db, name)
        return {"name": name, "items": assets}
    finally:
        db.close()


@router.get("/api/prompt")
def api_component_prompt(name: Optional[str] = Query(None), asset_id: Optional[int] = Query(None)):
    """构造带目标资产的巡检提问。供前端「问 AI」预填。"""
    db = next(get_db())
    try:
        asset = None
        if name:
            assets = resolve_component_assets(db, name)
            if asset_id is not None:
                asset = next((a for a in assets if a["id"] == asset_id), None)
            if asset is None and assets:
                asset = assets[0]
        prompt = build_inspection_prompt(name or "", asset)
        return {"prompt": prompt, "asset": asset}
    finally:
        db.close()
