"""第二十三章：外部告警入站集成 API。

端点（统一前缀 /api/inbound）：
- CRUD:      GET /api/inbound/sources, POST/.../create, POST/.../{id}/update, POST/.../{id}/delete
- Alertmanager: POST /api/inbound/{id}/alertmanager
- remote_write: POST /api/inbound/{id}/remote-write
- 通用 webhook: POST /api/inbound/{id}/webhook
- 状态回调:   POST /api/inbound/{id}/status-callback

鉴权：Authorization: Bearer <token> 或 ?token=<token>。
"""
import json
from typing import Optional

from fastapi import APIRouter, Depends, Request
from fastapi.responses import JSONResponse
from sqlalchemy.orm import Session

from app.database import get_db
from app.logger import logger
from app.services import inbound_alert_service

router = APIRouter(prefix="/api/inbound", tags=["inbound"])


def _authorize(request: Request, source_id: int, db: Session):
    """校验入站源是否启用 + token 匹配。失败返回错误响应，成功返回 source。"""
    source = inbound_alert_service.get_source(db, source_id)
    if not source:
        return None, JSONResponse({"ok": False, "message": "入站源不存在"}, status_code=404)
    if not source.enabled:
        return None, JSONResponse({"ok": False, "message": "入站源已禁用"}, status_code=403)
    token = ""
    auth = request.headers.get("Authorization", "")
    if auth.lower().startswith("bearer "):
        token = auth[7:].strip()
    if not token:
        token = request.query_params.get("token", "")
    if not inbound_alert_service.verify_token(source, token):
        return None, JSONResponse({"ok": False, "message": "token 校验失败"}, status_code=403)
    return source, None


# ── 入站源 CRUD ───────────────────────────────────────────
@router.get("/sources")
def list_sources(request: Request, db: Session = Depends(get_db)):
    """列出所有入站告警源。"""
    try:
        user_id = request.session.get("user_id")
        if not user_id:
            return {"warning": "未登录", "items": []}
        items = inbound_alert_service.list_sources(db)
        return {"items": items, "count": len(items)}
    except Exception as e:
        logger.warning(f"list_sources 异常: {e}")
        return {"items": [], "count": 0, "warning": str(e)}


@router.post("/sources/create")
def create_source(request: Request, payload: dict, db: Session = Depends(get_db)):
    """创建入站告警源：name/source_type/labels/metrics_to_rules/auto_create_rule/status_webhook_url。"""
    try:
        user_id = request.session.get("user_id")
        if not user_id:
            return JSONResponse({"ok": False, "message": "未登录"}, status_code=403)
        if not payload.get("name"):
            return JSONResponse({"ok": False, "message": "缺少 name"}, status_code=400)
        s = inbound_alert_service.create_source(db, payload)
        return {"ok": True, "source": inbound_alert_service._source_to_dict(s)}
    except Exception as e:
        logger.warning(f"create_source 异常: {e}")
        return JSONResponse({"ok": False, "message": str(e)}, status_code=400)


@router.post("/sources/{source_id}/update")
def update_source(source_id: int, request: Request, payload: dict, db: Session = Depends(get_db)):
    """更新入站告警源。"""
    try:
        user_id = request.session.get("user_id")
        if not user_id:
            return JSONResponse({"ok": False, "message": "未登录"}, status_code=403)
        s = inbound_alert_service.update_source(db, source_id, payload)
        if not s:
            return JSONResponse({"ok": False, "message": "入站源不存在"}, status_code=404)
        return {"ok": True, "source": inbound_alert_service._source_to_dict(s)}
    except Exception as e:
        logger.warning(f"update_source 异常: {e}")
        return JSONResponse({"ok": False, "message": str(e)}, status_code=400)


@router.post("/sources/{source_id}/delete")
def delete_source(source_id: int, request: Request, db: Session = Depends(get_db)):
    """删除入站告警源。"""
    try:
        user_id = request.session.get("user_id")
        if not user_id:
            return JSONResponse({"ok": False, "message": "未登录"}, status_code=403)
        ok = inbound_alert_service.delete_source(db, source_id)
        if not ok:
            return JSONResponse({"ok": False, "message": "入站源不存在"}, status_code=404)
        return {"ok": True}
    except Exception as e:
        logger.warning(f"delete_source 异常: {e}")
        return JSONResponse({"ok": False, "message": str(e)}, status_code=400)


@router.post("/sources/{source_id}/regenerate-token")
def regenerate_token(source_id: int, request: Request, db: Session = Depends(get_db)):
    """重新生成入站 token。"""
    try:
        user_id = request.session.get("user_id")
        if not user_id:
            return JSONResponse({"ok": False, "message": "未登录"}, status_code=403)
        import secrets
        new_token = secrets.token_urlsafe(24)
        s = inbound_alert_service.update_source(db, source_id, {"endpoint_token": new_token})
        if not s:
            return JSONResponse({"ok": False, "message": "入站源不存在"}, status_code=404)
        return {"ok": True, "endpoint_token": s.endpoint_token}
    except Exception as e:
        logger.warning(f"regenerate_token 异常: {e}")
        return JSONResponse({"ok": False, "message": str(e)}, status_code=400)


# ── 入站端点（token 鉴权）─────────────────────────────────
@router.post("/{source_id}/alertmanager")
async def alertmanager_webhook(source_id: int, request: Request, db: Session = Depends(get_db)):
    """接收 Alertmanager webhook。body: {alerts:[{labels,annotations,status}]}"""
    source, err = _authorize(request, source_id, db)
    if err:
        return err
    body = await request.body()
    try:
        payload = json.loads(body)
    except Exception:
        return JSONResponse({"ok": False, "message": "JSON 解析失败"}, status_code=400)
    try:
        result = inbound_alert_service.handle_alertmanager(db, source, payload)
        return {"ok": True, **result}
    except Exception as e:
        logger.warning(f"alertmanager_webhook 异常: {e}")
        return JSONResponse({"ok": False, "message": str(e)}, status_code=500)


@router.post("/{source_id}/remote-write")
async def remote_write(source_id: int, request: Request, db: Session = Depends(get_db)):
    """接收 Prometheus remote_write（protobuf/snappy 或 JSON 兜底）。"""
    source, err = _authorize(request, source_id, db)
    if err:
        return err
    body = await request.body()
    try:
        result = inbound_alert_service.handle_remote_write(db, source, body)
        return {"ok": True, **result}
    except Exception as e:
        logger.warning(f"remote_write 异常: {e}")
        return JSONResponse({"ok": False, "message": str(e)}, status_code=500)


@router.post("/{source_id}/webhook")
async def generic_webhook(source_id: int, request: Request, db: Session = Depends(get_db)):
    """通用 JSON webhook。body: {title,severity,status,metric_name?,message?,labels?}"""
    source, err = _authorize(request, source_id, db)
    if err:
        return err
    body = await request.body()
    try:
        payload = json.loads(body)
    except Exception:
        return JSONResponse({"ok": False, "message": "JSON 解析失败"}, status_code=400)
    try:
        result = inbound_alert_service.handle_webhook(db, source, payload)
        return {"ok": True, **result}
    except Exception as e:
        logger.warning(f"generic_webhook 异常: {e}")
        return JSONResponse({"ok": False, "message": str(e)}, status_code=500)


@router.post("/{source_id}/status-callback")
async def status_callback(source_id: int, request: Request, db: Session = Depends(get_db)):
    """接收处置状态变更并回写源系统。body: {alert_id, status}"""
    source, err = _authorize(request, source_id, db)
    if err:
        return err
    body = await request.body()
    try:
        payload = json.loads(body)
    except Exception:
        return JSONResponse({"ok": False, "message": "JSON 解析失败"}, status_code=400)
    try:
        result = inbound_alert_service.callback_status(db, source, payload)
        return {"ok": True, **result}
    except Exception as e:
        logger.warning(f"status_callback 异常: {e}")
        return JSONResponse({"ok": False, "message": str(e)}, status_code=500)
