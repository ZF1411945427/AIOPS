"""外部 MCP 服务器管理 API(P1-5)。契约见 CONTRACT.md。"""
import json

from fastapi import APIRouter, Depends, Request
from fastapi.responses import JSONResponse

from app.database import get_db
from app.models import MCPServer
from app.services import mcp_external, mcp_registry
from sqlalchemy.orm import Session

router = APIRouter(prefix="/api/mcp", tags=["mcp"])


def _current_user_id(request: Request) -> int:
    uid = request.session.get("user_id")
    if not uid:
        auth = request.headers.get("authorization", "")
        if auth.startswith("Bearer "):
            try:
                from app.services.mobile_push_service import verify_login_token
                payload = verify_login_token(auth[7:])
                if payload:
                    uid = payload.get("user_id")
            except Exception as _exc:
                logger.warning("[except:pass] Exception: %s", _exc, exc_info=True)
    return uid


def _server_dict(s: MCPServer) -> dict:
    return {
        "id": s.id, "name": s.name, "server_type": s.server_type,
        "endpoint": s.endpoint, "description": s.description,
        "auth_type": "bearer", "api_key": "***", "has_api_key": bool(s.auth_config),
        "tool_whitelist": _load_json(s.tool_whitelist),
        "is_builtin": bool(s.is_builtin), "is_enabled": bool(s.is_enabled),
        "created_at": s.created_at.isoformat() if s.created_at else "",
    }


def _load_json(raw):
    try:
        v = json.loads(raw) if raw else []
        return v if isinstance(v, list) else []
    except Exception:
        return []


@router.get("")
def api_mcp_list(request: Request, db: Session = Depends(get_db)):
    servers = db.query(MCPServer).order_by(MCPServer.name).all()
    return JSONResponse({"ok": True, "servers": [_server_dict(s) for s in servers]})


@router.get("/tools")
def api_mcp_tools(request: Request, db: Session = Depends(get_db)):
    """已加载进 Agent 清单的外部工具。"""
    return JSONResponse({"ok": True, "tools": mcp_registry.get_external_manifest(),
                         "total": len(mcp_registry.get_external_manifest())})


@router.post("")
def api_mcp_create(request: Request, payload: dict, db: Session = Depends(get_db)):
    name = str(payload.get("name") or "").strip()
    endpoint = str(payload.get("endpoint") or "").strip()
    if not name:
        return JSONResponse({"ok": False, "error": "服务器名不能为空"}, status_code=400)
    if db.query(MCPServer).filter(MCPServer.name == name).first():
        return JSONResponse({"ok": False, "error": f"服务器 {name} 已存在"}, status_code=400)
    api_key = str(payload.get("api_key") or "").strip()
    auth_config = {}
    if api_key:
        auth_config["api_key"] = api_key
    s = MCPServer(
        name=name,
        server_type=payload.get("server_type") or "http",
        endpoint=endpoint,
        description=str(payload.get("description") or ""),
        auth_config=json.dumps(auth_config, ensure_ascii=False),
        tool_whitelist=json.dumps(payload.get("tool_whitelist") or [], ensure_ascii=False),
        is_builtin=False,
        is_enabled=bool(payload.get("is_enabled", True)),
    )
    db.add(s)
    db.commit()
    db.refresh(s)
    # 重载外部工具
    mcp_external.reload_external_tools(db)
    return JSONResponse({"ok": True, "server": _server_dict(s), "message": "已添加并尝试加载工具"})


@router.put("/{server_id}")
def api_mcp_update(server_id: int, request: Request, payload: dict, db: Session = Depends(get_db)):
    s = db.query(MCPServer).filter(MCPServer.id == server_id).first()
    if not s:
        return JSONResponse({"ok": False, "error": "服务器不存在"}, status_code=404)
    if "name" in payload and payload["name"]:
        s.name = str(payload["name"]).strip()
    for f in ("endpoint", "description", "server_type"):
        if f in payload and payload[f] is not None:
            setattr(s, f, str(payload[f]))
    old_cfg = {}
    try:
        old_cfg = json.loads(s.auth_config) if s.auth_config else {}
    except Exception as _exc1:
        logger.warning("[except:pass] Exception: %s", _exc1, exc_info=True)
    if payload.get("api_key"):  # 留空=不更新
        old_cfg["api_key"] = str(payload["api_key"])
    s.auth_config = json.dumps(old_cfg, ensure_ascii=False)
    if "tool_whitelist" in payload:
        s.tool_whitelist = json.dumps(payload["tool_whitelist"] or [], ensure_ascii=False)
    if "is_enabled" in payload:
        s.is_enabled = bool(payload["is_enabled"])
    db.commit()
    mcp_external.reload_external_tools(db)
    return JSONResponse({"ok": True, "server": _server_dict(s)})


@router.delete("/{server_id}")
def api_mcp_delete(server_id: int, request: Request, db: Session = Depends(get_db)):
    s = db.query(MCPServer).filter(MCPServer.id == server_id).first()
    if not s:
        return JSONResponse({"ok": False, "error": "服务器不存在"}, status_code=404)
    db.delete(s)
    db.commit()
    mcp_external.reload_external_tools(db)
    return JSONResponse({"ok": True, "message": "已删除"})


@router.post("/{server_id}/test")
def api_mcp_test(server_id: int, request: Request, db: Session = Depends(get_db)):
    s = db.query(MCPServer).filter(MCPServer.id == server_id).first()
    if not s:
        return JSONResponse({"ok": False, "error": "服务器不存在"}, status_code=404)
    try:
        tools = mcp_external.server_tools(s)
        return JSONResponse({"ok": True, "reachable": True, "tools": len(tools),
                             "tool_names": [t.get("name") for t in tools]})
    except Exception as e:
        return JSONResponse({"ok": True, "reachable": False, "error": str(e)})


@router.post("/reload")
def api_mcp_reload(request: Request, db: Session = Depends(get_db)):
    n = mcp_external.reload_external_tools(db)
    return JSONResponse({"ok": True, "loaded": n, "message": f"已重载 {n} 个外部工具"})


import logging
logger = logging.getLogger(__name__)
