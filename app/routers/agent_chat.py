import json
from datetime import datetime

from fastapi import APIRouter, Depends, Request
from fastapi.responses import JSONResponse
from sqlalchemy.orm import Session

from app.database import get_db
from app.models import ChatSession, ChatMessage, PendingAction, ToolInvocation, AgentConfig
from app.services.agent_service import (
    process_chat_message, confirm_pending_action, cancel_pending_action)

router = APIRouter(prefix="/agent", tags=["agent"])


@router.get("/sessions")
def list_sessions_json(request: Request, db: Session = Depends(get_db)):
    user_id = request.session.get("user_id", 1)
    sessions = (
        db.query(ChatSession)
        .filter(ChatSession.user_id == user_id)
        .order_by(ChatSession.last_message_at.desc())
        .limit(50)
        .all()
    )
    return {
        "sessions": [
            {"id": s.id, "title": s.title or "新会话", "created_at": s.created_at.isoformat()}
            for s in sessions
        ]
    }


@router.get("/history/{session_id}")
def session_history_json(session_id: int, request: Request, db: Session = Depends(get_db)):
    user_id = request.session.get("user_id", 1)
    session = db.query(ChatSession).filter(
        ChatSession.id == session_id, ChatSession.user_id == user_id).first()
    messages = []
    pending_list = []
    if session:
        messages = [
            {"role": m.role, "content": m.content, "created_at": m.created_at.isoformat(),
             "message_type": m.message_type, "tool_calls": m.tool_calls}
            for m in db.query(ChatMessage)
            .filter(ChatMessage.session_id == session.id)
            .order_by(ChatMessage.created_at.asc()).all()
        ]
        pending_list = [
            {"id": a.id, "title": a.title, "risk_level": a.risk_level, "reason": a.reason or ""}
            for a in db.query(PendingAction)
            .filter(PendingAction.session_id == session.id, PendingAction.status == PendingAction.STATUS_PENDING).all()
        ]
    return {"messages": messages, "pending_actions": pending_list}


@router.post("/chat/send")
async def send_message(
    request: Request,
    db: Session = Depends(get_db)):
    data = await request.json()
    user_id = request.session.get("user_id", 1)
    session_id = data.get("session_id")
    message = data.get("message", "").strip()

    if not message:
        return JSONResponse({"error": "消息不能为空"}, status_code=400)

    result = process_chat_message(db, user_id, session_id, message)

    if result.get("error"):
        return JSONResponse({"error": result["reply"]}, status_code=500)

    return JSONResponse(result)


@router.post("/session/{session_id}/delete")
def delete_session_json(session_id: int, request: Request, db: Session = Depends(get_db)):
    user_id = request.session.get("user_id", 1)
    session = db.query(ChatSession).filter(
        ChatSession.id == session_id, ChatSession.user_id == user_id).first()
    if session:
        db.query(ChatMessage).filter(ChatMessage.session_id == session.id).delete()
        db.query(PendingAction).filter(PendingAction.session_id == session.id).delete()
        db.query(ToolInvocation).filter(ToolInvocation.session_id == session.id).delete()
        db.delete(session)
        db.commit()
    return {"status": "ok"}


@router.post("/pending/{action_id}/confirm")
def confirm_action(action_id: int, request: Request, db: Session = Depends(get_db)):
    user_name = request.session.get("username", "unknown")
    result = confirm_pending_action(db, action_id, user_name)
    return {"status": "ok", "result": result}


@router.get("/pending/{action_id}/status")
def pending_status(action_id: int, request: Request, db: Session = Depends(get_db)):
    """查询待确认动作的执行状态（前端轮询用）."""
    action = db.query(PendingAction).filter(PendingAction.id == action_id).first()
    if not action:
        return {"status": "not_found"}
    # 解析 result_payload 提取 message
    result_message = ""
    if action.result_payload and action.result_payload != "{}":
        try:
            parsed = json.loads(action.result_payload)
            result_message = parsed.get("message", "")
            if not result_message:
                inner = parsed.get("result", {})
                if isinstance(inner, dict):
                    result_message = inner.get("message", "")
        except (json.JSONDecodeError, TypeError):
            pass
    return {
        "status": action.status,
        "result_message": result_message,
        "is_terminal": action.status in (
            PendingAction.STATUS_EXECUTED, PendingAction.STATUS_FAILED, PendingAction.STATUS_CANCELED
        ),
    }


@router.post("/pending/{action_id}/cancel")
def cancel_action(action_id: int, request: Request, db: Session = Depends(get_db)):
    cancel_pending_action(db, action_id)
    return {"status": "ok"}


@router.get("/invocations")
def tool_invocations(request: Request, db: Session = Depends(get_db)):
    user_id = request.session.get("user_id", 1)
    invocations = (
        db.query(ToolInvocation)
        .join(ChatSession, ToolInvocation.session_id == ChatSession.id)
        .filter(ChatSession.user_id == user_id)
        .order_by(ToolInvocation.created_at.desc())
        .limit(100)
        .all()
    )
    return JSONResponse([
        {
            "id": t.id,
            "session_id": t.session_id,
            "tool_name": t.tool_name,
            "status": t.status,
            "latency_ms": t.latency_ms,
            "request_payload": json.loads(t.request_payload) if isinstance(t.request_payload, str) else {},
            "response_summary": json.loads(t.response_summary) if isinstance(t.response_summary, str) else {},
            "created_at": t.created_at.isoformat(),
        }
        for t in invocations
    ])


@router.get("/api/pending")
def api_pending_list(request: Request, db: Session = Depends(get_db)):
    """待确认动作列表 JSON API（Vue 用）."""
    user_id = request.session.get("user_id", 1)
    actions = (
        db.query(PendingAction)
        .join(ChatSession, PendingAction.session_id == ChatSession.id)
        .filter(ChatSession.user_id == user_id)
        .order_by(PendingAction.created_at.desc())
        .all()
    )
    result = []
    for a in actions:
        result_message = ""
        if a.result_payload and a.result_payload != "{}":
            try:
                parsed = json.loads(a.result_payload)
                if parsed.get("status") == "error":
                    result_message = parsed.get("message", "")
                elif parsed.get("status") == "success":
                    inner = parsed.get("result") or {}
                    if isinstance(inner, dict):
                        result_message = inner.get("message", "")
            except (json.JSONDecodeError, TypeError):
                pass
        result.append({
            "id": a.id,
            "session_id": a.session_id,
            "action_type": a.action_type,
            "title": a.title,
            "risk_level": a.risk_level,
            "reason": a.reason,
            "status": a.status,
            "action_payload": a.action_payload,
            "result_message": result_message,
            "confirmed_by": a.confirmed_by,
            "created_at": a.created_at.isoformat() if a.created_at else None,
        })
    return {"actions": result, "count": len(result)}
