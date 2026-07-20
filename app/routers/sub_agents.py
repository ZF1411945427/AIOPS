"""子智能体（Sub-agent）管理 API — Multi-Agent Orchestration 配置入口。

功能：
- GET    /agent/sub-agents          列出所有子专家
- GET    /agent/sub-agents/{name}   查询单个子专家
- POST   /agent/sub-agents/create   创建子专家（admin）
- PUT    /agent/sub-agents/{id}/edit 编辑子专家（admin）
- DELETE /agent/sub-agents/{id}     删除子专家（admin）
- POST   /agent/sub-agents/seed     重新播种预置子专家（admin）
- POST   /agent/sub-agents/route    测试路由（传 message，返回匹配的子专家）
- GET    /agent/sub-agents/manifest 返回子专家清单 + 工具数（前端 chips 用）
"""
from fastapi import APIRouter, Depends, Request
from fastapi.responses import JSONResponse
from sqlalchemy.orm import Session

from app.database import get_db
from app.models import SubAgent, User
from app.services.sub_agent_service import (
    list_sub_agents, get_sub_agent, seed_sub_agents, route_sub_agent,
    filter_tools_by_sub_agent, sub_agent_to_dict, PRESET_SUB_AGENTS,
)
from app.services.mcp_registry import get_mcp_manifest

router = APIRouter(prefix="/agent/sub-agents", tags=["sub-agents"])


def _get_user_id(request: Request):
    return request.session.get("user_id")


def _require_admin(request: Request, db: Session):
    """校验 admin 权限，返回 (user_id, error_response)。"""
    user_id = _get_user_id(request)
    if not user_id:
        return None, JSONResponse({"error": "未登录"}, status_code=401)
    user = db.query(User).filter(User.id == user_id).first()
    if not user or user.role != "admin":
        return None, JSONResponse({"error": "需要管理员权限"}, status_code=403)
    return user_id, None


@router.get("")
def list_all(request: Request, db: Session = Depends(get_db)):
    """列出所有子专家（含禁用的）。"""
    agents = db.query(SubAgent).order_by(SubAgent.sort_order).all()
    return {"sub_agents": [sub_agent_to_dict(a) for a in agents], "total": len(agents)}


@router.get("/manifest")
def manifest(request: Request, db: Session = Depends(get_db)):
    """前端 chips 用的精简清单（仅启用 + sort_order）。"""
    agents = list_sub_agents(db, enabled_only=True)
    return {
        "sub_agents": [
            {
                "name": a.name, "display_name": a.display_name, "domain": a.domain,
                "icon": a.icon, "color": a.color, "sort_order": a.sort_order,
                "description": a.description,
                "tool_count": len(a.get_tool_whitelist()) if a.get_tool_whitelist() else 45,
            }
            for a in agents
        ]
    }


@router.get("/{name}")
def get_one(name: str, request: Request, db: Session = Depends(get_db)):
    sa = get_sub_agent(db, name)
    if not sa:
        return JSONResponse({"error": "子专家不存在"}, status_code=404)
    return sub_agent_to_dict(sa)


@router.post("/create")
def create(request: Request, payload: dict, db: Session = Depends(get_db)):
    uid, err = _require_admin(request, db)
    if err:
        return err
    name = (payload.get("name") or "").strip()
    if not name:
        return JSONResponse({"error": "name 必填"}, status_code=400)
    if db.query(SubAgent).filter(SubAgent.name == name).first():
        return JSONResponse({"error": "name 已存在"}, status_code=400)
    import json as _json
    sa = SubAgent(
        name=name,
        display_name=payload.get("display_name", name),
        domain=payload.get("domain", "general"),
        description=payload.get("description", ""),
        system_prompt=payload.get("system_prompt", ""),
        tool_whitelist=_json.dumps(payload.get("tool_whitelist", []), ensure_ascii=False),
        keywords=_json.dumps(payload.get("keywords", []), ensure_ascii=False),
        icon=payload.get("icon", "🤖"),
        color=payload.get("color", "#6366f1"),
        is_enabled=bool(payload.get("is_enabled", True)),
        sort_order=int(payload.get("sort_order", 99)),
    )
    db.add(sa)
    db.commit()
    db.refresh(sa)
    return {"status": "ok", "id": sa.id, "sub_agent": sub_agent_to_dict(sa)}


@router.put("/{sa_id}/edit")
def edit(sa_id: int, request: Request, payload: dict, db: Session = Depends(get_db)):
    uid, err = _require_admin(request, db)
    if err:
        return err
    sa = db.query(SubAgent).filter(SubAgent.id == sa_id).first()
    if not sa:
        return JSONResponse({"error": "子专家不存在"}, status_code=404)
    import json as _json
    for field in ("display_name", "domain", "description", "system_prompt", "icon", "color"):
        if field in payload:
            setattr(sa, field, payload[field])
    if "tool_whitelist" in payload:
        sa.tool_whitelist = _json.dumps(payload["tool_whitelist"], ensure_ascii=False)
    if "keywords" in payload:
        sa.keywords = _json.dumps(payload["keywords"], ensure_ascii=False)
    if "is_enabled" in payload:
        sa.is_enabled = bool(payload["is_enabled"])
    if "sort_order" in payload:
        sa.sort_order = int(payload["sort_order"])
    db.commit()
    return {"status": "ok", "sub_agent": sub_agent_to_dict(sa)}


@router.delete("/{sa_id}")
def delete(sa_id: int, request: Request, db: Session = Depends(get_db)):
    uid, err = _require_admin(request, db)
    if err:
        return err
    sa = db.query(SubAgent).filter(SubAgent.id == sa_id).first()
    if not sa:
        return JSONResponse({"error": "子专家不存在"}, status_code=404)
    # 预置子专家禁止删除，只能禁用
    preset_names = [p["name"] for p in PRESET_SUB_AGENTS]
    if sa.name in preset_names:
        return JSONResponse({"error": "预置子专家不可删除，可设为禁用"}, status_code=400)
    db.delete(sa)
    db.commit()
    return {"status": "ok"}


@router.post("/seed")
def reseed(request: Request, db: Session = Depends(get_db)):
    """重新播种预置子专家（幂等，会更新预置字段）。"""
    uid, err = _require_admin(request, db)
    if err:
        return err
    added = seed_sub_agents(db)
    return {"status": "ok", "added": added, "message": f"新增 {added} 个，其余已更新"}


@router.post("/route")
def test_route(request: Request, payload: dict, db: Session = Depends(get_db)):
    """测试路由：传 message，返回匹配的子专家 name + 命中关键词。"""
    message = payload.get("message", "")
    sub_name = route_sub_agent(message, db)
    sa = get_sub_agent(db, sub_name) if sub_name != "general" else None
    # 命中关键词详情
    msg_lower = message.lower()
    hit_keywords = []
    if sa:
        hit_keywords = [kw for kw in sa.get_keywords() if kw.lower() in msg_lower]
    return {
        "message": message,
        "routed_to": sub_name,
        "display_name": sa.display_name if sa else "通用助手",
        "icon": sa.icon if sa else "🤖",
        "color": sa.color if sa else "#64748b",
        "hit_keywords": hit_keywords,
    }


@router.get("/{name}/tools")
def list_tools(name: str, request: Request, db: Session = Depends(get_db)):
    """查看某子专家可见的工具清单。"""
    sa = get_sub_agent(db, name)
    if not sa:
        return JSONResponse({"error": "子专家不存在"}, status_code=404)
    all_tools = get_mcp_manifest()
    filtered = filter_tools_by_sub_agent(all_tools, sa)
    return {
        "sub_agent": sub_agent_to_dict(sa),
        "total_tools": len(all_tools),
        "visible_tools": len(filtered),
        "tools": [{"name": t["name"], "display_name": t["display_name"], "category": t.get("category", "")} for t in filtered],
    }
