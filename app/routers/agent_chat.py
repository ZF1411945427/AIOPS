import json
from datetime import datetime

from fastapi import APIRouter, Depends, Request, Form
from fastapi.responses import JSONResponse, RedirectResponse
from sqlalchemy.orm import Session

from app.database import get_db
from app.models import ChatSession, ChatMessage, PendingAction, ToolInvocation, AgentConfig
from app.template_utils import get_templates
from app.services.agent_service import (
    process_chat_message, confirm_pending_action, cancel_pending_action,
)

router = APIRouter(prefix="/agent", tags=["agent"])
templates = get_templates()


@router.get("/chat")
def chat_page(request: Request, db: Session = Depends(get_db)):
    user_id = request.session.get("user_id", 1)
    sessions = (
        db.query(ChatSession)
        .filter(ChatSession.user_id == user_id)
        .order_by(ChatSession.last_message_at.desc())
        .limit(50)
        .all()
    )
    # 自动跳转到最近的会话，而不是显示空白欢迎页
    if sessions:
        from fastapi.responses import RedirectResponse
        return RedirectResponse(url=f"/agent/chat/{sessions[0].id}", status_code=303)
    config = db.query(AgentConfig).filter(AgentConfig.is_enabled == True).first()
    welcome = config.welcome_message if config else "你好，我可以帮你查询资源、分析告警、生成运维任务等。"
    suggested = config.get_suggested_questions() if config else []

    return templates.TemplateResponse("agent_chat.html", {
        "request": request,
        "sessions": sessions,
        "welcome_message": welcome,
        "suggested_questions": suggested,
        "active_session": None,
        "messages": [],
        "pending_actions": [],
    })


@router.get("/chat/{session_id}")
def chat_session_page(request: Request, session_id: int, db: Session = Depends(get_db)):
    user_id = request.session.get("user_id", 1)
    sessions = (
        db.query(ChatSession)
        .filter(ChatSession.user_id == user_id)
        .order_by(ChatSession.last_message_at.desc())
        .limit(50)
        .all()
    )
    active = db.query(ChatSession).filter(
        ChatSession.id == session_id, ChatSession.user_id == user_id,
    ).first()

    messages = []
    pending_list = []
    if active:
        messages = (
            db.query(ChatMessage)
            .filter(ChatMessage.session_id == active.id)
            .order_by(ChatMessage.created_at.asc())
            .all()
        )
        pending_list = (
            db.query(PendingAction)
            .filter(
                PendingAction.session_id == active.id,
                PendingAction.status == PendingAction.STATUS_PENDING,
            )
            .all()
        )

    config = db.query(AgentConfig).filter(AgentConfig.is_enabled == True).first()
    welcome = config.welcome_message if config else "你好，我可以帮你查询资源、分析告警、生成运维任务等。"
    suggested = config.get_suggested_questions() if config else []

    return templates.TemplateResponse("agent_chat.html", {
        "request": request,
        "sessions": sessions,
        "welcome_message": welcome,
        "suggested_questions": suggested,
        "active_session": active,
        "messages": messages,
        "pending_actions": pending_list,
    })


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
        ChatSession.id == session_id, ChatSession.user_id == user_id,
    ).first()
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
            {"id": a.id, "title": a.description, "risk_level": a.risk_level}
            for a in db.query(PendingAction)
            .filter(PendingAction.session_id == session.id, PendingAction.status == PendingAction.STATUS_PENDING).all()
        ]
    return {"messages": messages, "pending_actions": pending_list}


@router.post("/chat/send")
async def send_message(
    request: Request,
    db: Session = Depends(get_db),
):
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
        ChatSession.id == session_id, ChatSession.user_id == user_id,
    ).first()
    if session:
        db.query(ChatMessage).filter(ChatMessage.session_id == session.id).delete()
        db.query(PendingAction).filter(PendingAction.session_id == session.id).delete()
        db.query(ToolInvocation).filter(ToolInvocation.session_id == session.id).delete()
        db.delete(session)
        db.commit()
    return {"status": "ok"}


@router.post("/chat/{session_id}/delete")
def delete_session(session_id: int, request: Request, db: Session = Depends(get_db)):
    user_id = request.session.get("user_id", 1)
    session = db.query(ChatSession).filter(
        ChatSession.id == session_id, ChatSession.user_id == user_id,
    ).first()
    if session:
        db.query(ChatMessage).filter(ChatMessage.session_id == session.id).delete()
        db.query(PendingAction).filter(PendingAction.session_id == session.id).delete()
        db.query(ToolInvocation).filter(ToolInvocation.session_id == session.id).delete()
        db.delete(session)
        db.commit()
    return RedirectResponse(url="/agent/chat", status_code=303)


@router.post("/pending/{action_id}/confirm")
def confirm_action(action_id: int, request: Request, db: Session = Depends(get_db)):
    user_name = request.session.get("username", "unknown")
    confirm_pending_action(db, action_id, user_name)
    accept = request.headers.get("accept", "")
    if "json" in accept:
        return {"status": "ok"}
    return RedirectResponse(url="/agent/chat", status_code=303)


@router.post("/pending/{action_id}/cancel")
def cancel_action(action_id: int, request: Request, db: Session = Depends(get_db)):
    cancel_pending_action(db, action_id)
    accept = request.headers.get("accept", "")
    if "json" in accept:
        return {"status": "ok"}
    return RedirectResponse(url="/agent/chat", status_code=303)


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


@router.get("/pending")
def pending_list(request: Request, db: Session = Depends(get_db)):
    user_id = request.session.get("user_id", 1)
    actions = (
        db.query(PendingAction)
        .join(ChatSession, PendingAction.session_id == ChatSession.id)
        .filter(ChatSession.user_id == user_id)
        .order_by(PendingAction.created_at.desc())
        .all()
    )
    return templates.TemplateResponse("agent_pending.html", {
        "request": request,
        "actions": actions,
    })
