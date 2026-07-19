import json
from datetime import datetime, timedelta

from fastapi import APIRouter, Depends, Request
from fastapi.responses import JSONResponse
from sqlalchemy.orm import Session
from sqlalchemy import func, case

from app.database import get_db
from app.models import ChatSession, ChatMessage, PendingAction, ToolInvocation, AgentConfig, Alert, Asset, AlertSessionLink, AssetSessionLink, AIProvider
from app.services.agent_service import (
    process_chat_message, confirm_pending_action, cancel_pending_action, add_message)
from app.services.mcp_registry import _MCP_TOOLS
from app.routers.observability_correlation import run_correlation_analysis, format_correlation_for_llm

router = APIRouter(prefix="/agent", tags=["agent"])


def _get_user_id(request: Request):
    """获取已登录用户 ID，未登录返回 None"""
    return request.session.get("user_id")


@router.get("/sessions")
def list_sessions_json(request: Request, db: Session = Depends(get_db)):
    user_id = _get_user_id(request)
    if not user_id:
        return JSONResponse({"error": "未登录"}, status_code=401)
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


@router.post("/session/new")
def create_empty_session(request: Request, db: Session = Depends(get_db)):
    user_id = _get_user_id(request)
    if not user_id:
        return JSONResponse({"error": "未登录"}, status_code=401)
    session = ChatSession(user_id=user_id, title="新会话")
    db.add(session)
    db.commit()
    db.refresh(session)
    return {"session_id": session.id, "title": "新会话"}


@router.get("/history/{session_id}")
def session_history_json(session_id: int, request: Request, db: Session = Depends(get_db)):
    user_id = _get_user_id(request)
    if not user_id:
        return JSONResponse({"error": "未登录"}, status_code=401)
    session = db.query(ChatSession).filter(
        ChatSession.id == session_id, ChatSession.user_id == user_id).first()
    messages = []
    pending_list = []
    if session:
        messages = [
            {"role": m.role, "content": m.message_content, "created_at": m.created_at.isoformat(),
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
    user_id = _get_user_id(request)
    if not user_id:
        return JSONResponse({"error": "未登录"}, status_code=401)
    session_id = data.get("session_id")
    message = data.get("message", "").strip()

    if not message:
        return JSONResponse({"error": "消息不能为空"}, status_code=400)

    result = process_chat_message(db, user_id, session_id, message)

    if result.get("error"):
        return JSONResponse({"warning": result["reply"]}, status_code=200)

    return JSONResponse(result)


@router.post("/session/{session_id}/delete")
def delete_session_json(session_id: int, request: Request, db: Session = Depends(get_db)):
    user_id = _get_user_id(request)
    if not user_id:
        return JSONResponse({"error": "未登录"}, status_code=401)
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
def tool_invocations(request: Request, db: Session = Depends(get_db), page: int = 1, page_size: int = 20):
    user_id = _get_user_id(request)
    if not user_id:
        return JSONResponse({"error": "未登录"}, status_code=401)
    query = (
        db.query(ToolInvocation)
        .join(ChatSession, ToolInvocation.session_id == ChatSession.id)
        .filter(ChatSession.user_id == user_id)
        .order_by(ToolInvocation.created_at.desc())
    )
    total = query.count()
    invocations = query.offset((page - 1) * page_size).limit(page_size).all()
    return JSONResponse({
        "total": total,
        "page": page,
        "page_size": page_size,
        "items": [
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
        ]
    })


@router.get("/stats")
def agent_stats(request: Request, db: Session = Depends(get_db)):
    """Agent 评估指标：工具调用成功率、耗时分布、工具分布、时间趋势"""
    user_id = _get_user_id(request)
    if not user_id:
        return JSONResponse({"error": "未登录"}, status_code=401)

    base_q = (
        db.query(ToolInvocation)
        .join(ChatSession, ToolInvocation.session_id == ChatSession.id)
        .filter(ChatSession.user_id == user_id)
    )

    total = base_q.count()
    success = base_q.filter(ToolInvocation.status == ToolInvocation.STATUS_SUCCESS).count()
    failed = base_q.filter(ToolInvocation.status == ToolInvocation.STATUS_FAILED).count()
    pending = base_q.filter(ToolInvocation.status == ToolInvocation.STATUS_PENDING).count()
    success_rate = round(success / total * 100, 1) if total > 0 else 0.0

    avg_latency = (
        db.query(func.avg(ToolInvocation.latency_ms))
        .join(ChatSession, ToolInvocation.session_id == ChatSession.id)
        .filter(ChatSession.user_id == user_id, ToolInvocation.status == ToolInvocation.STATUS_SUCCESS)
        .scalar()
    )
    avg_latency = int(avg_latency) if avg_latency else 0

    p50_latency = (
        db.query(ToolInvocation.latency_ms)
        .join(ChatSession, ToolInvocation.session_id == ChatSession.id)
        .filter(ChatSession.user_id == user_id, ToolInvocation.status == ToolInvocation.STATUS_SUCCESS)
        .order_by(ToolInvocation.latency_ms)
        .offset(max(0, success // 2))
        .limit(1)
        .first()
    )
    p50_latency = p50_latency[0] if p50_latency else 0

    p95_latency = (
        db.query(ToolInvocation.latency_ms)
        .join(ChatSession, ToolInvocation.session_id == ChatSession.id)
        .filter(ChatSession.user_id == user_id, ToolInvocation.status == ToolInvocation.STATUS_SUCCESS)
        .order_by(ToolInvocation.latency_ms)
        .offset(max(0, int(success * 0.95)))
        .limit(1)
        .first()
    )
    p95_latency = p95_latency[0] if p95_latency else 0

    tool_rows = (
        db.query(
            ToolInvocation.tool_name,
            func.count(ToolInvocation.id).label("count"),
            func.sum(case((ToolInvocation.status == ToolInvocation.STATUS_SUCCESS, 1), else_=0)).label("is_success"),
            func.avg(ToolInvocation.latency_ms).label("avg_latency"),
        )
        .join(ChatSession, ToolInvocation.session_id == ChatSession.id)
        .filter(ChatSession.user_id == user_id)
        .group_by(ToolInvocation.tool_name)
        .order_by(func.count(ToolInvocation.id).desc())
        .all()
    )
    tools = []
    for r in tool_rows:
        cnt = int(r.count or 0)
        scs = int(r.is_success or 0)
        tools.append({
            "tool_name": r.tool_name,
            "count": cnt,
            "is_success": scs,
            "failed": cnt - scs,
            "success_rate": round(scs / cnt * 100, 1) if cnt > 0 else 0.0,
            "avg_latency": int(r.avg_latency) if r.avg_latency else 0,
        })

    seven_days_ago = datetime.now() - timedelta(days=7)
    daily_rows = (
        db.query(
            func.date(ToolInvocation.created_at).label("day"),
            func.count(ToolInvocation.id).label("count"),
            func.sum(case((ToolInvocation.status == ToolInvocation.STATUS_SUCCESS, 1), else_=0)).label("is_success"),
        )
        .join(ChatSession, ToolInvocation.session_id == ChatSession.id)
        .filter(ChatSession.user_id == user_id, ToolInvocation.created_at >= seven_days_ago)
        .group_by(func.date(ToolInvocation.created_at))
        .order_by(func.date(ToolInvocation.created_at))
        .all()
    )
    daily = []
    for r in daily_rows:
        cnt = int(r.count or 0)
        scs = int(r.is_success or 0)
        daily.append({
            "date": str(r.day),
            "count": cnt,
            "is_success": scs,
            "success_rate": round(scs / cnt * 100, 1) if cnt > 0 else 0.0,
        })

    session_count = (
        db.query(ChatSession).filter(ChatSession.user_id == user_id).count()
    )
    message_count = (
        db.query(ChatMessage)
        .join(ChatSession, ChatMessage.session_id == ChatSession.id)
        .filter(ChatSession.user_id == user_id)
        .count()
    )
    pending_action_count = (
        db.query(PendingAction)
        .join(ChatSession, PendingAction.session_id == ChatSession.id)
        .filter(ChatSession.user_id == user_id, PendingAction.status == "pending")
        .count()
    )

    return JSONResponse({
        "total_calls": total,
        "is_success": success,
        "failed": failed,
        "pending": pending,
        "success_rate": success_rate,
        "avg_latency_ms": avg_latency,
        "p50_latency_ms": p50_latency,
        "p95_latency_ms": p95_latency,
        "tools": tools,
        "daily_trend": daily,
        "session_count": session_count,
        "message_count": message_count,
        "pending_actions": pending_action_count,
    })


@router.get("/api/pending")
def api_pending_list(request: Request, db: Session = Depends(get_db), status: str = "pending"):
    user_id = _get_user_id(request)
    if not user_id:
        return JSONResponse({"error": "未登录"}, status_code=401)
    query = (
        db.query(PendingAction)
        .join(ChatSession, PendingAction.session_id == ChatSession.id)
        .filter(ChatSession.user_id == user_id)
    )
    if status and status != "all":
        query = query.filter(PendingAction.status == status)
    actions = query.order_by(PendingAction.created_at.desc()).all()
    result = []
    for a in actions:
        result_message = ""
        if a.result_payload and a.result_payload != "{}":
            try:
                parsed = json.loads(a.result_payload)
                if parsed.get("status") == "error":
                    result_message = parsed.get("message", "")
                elif parsed.get("status") == "is_success":
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


@router.post("/session/{session_id}/link-alert")
async def link_alert_to_session(session_id: int, request: Request, db: Session = Depends(get_db)):
    user_id = _get_user_id(request)
    if not user_id:
        return JSONResponse({"error": "未登录"}, status_code=401)
        
    data = await request.json()
    alert_id = data.get("alert_id")
    if not alert_id:
        return JSONResponse({"error": "缺少 alert_id"}, status_code=400)

    session = db.query(ChatSession).filter(
        ChatSession.id == session_id, ChatSession.user_id == user_id
    ).first()
    if not session:
        return JSONResponse({"error": "会话不存在"}, status_code=404)

    alert = db.query(Alert).filter(Alert.id == alert_id).first()
    if not alert:
        return JSONResponse({"error": "告警不存在"}, status_code=404)

    # 更新 session context
    import json
    ctx = json.loads(session.context or "{}")
    ctx["alert_id"] = alert.id
    ctx["alert_metric"] = alert.metric_name
    ctx["alert_severity"] = alert.severity
    ctx["alert_status"] = alert.status
    ctx["alert_value"] = alert.actual_value
    ctx["alert_threshold"] = alert.threshold
    if alert.asset_id:
        ctx["asset_id"] = alert.asset_id
        asset = db.query(Asset).filter(Asset.id == alert.asset_id).first()
        if asset:
            ctx["asset_name"] = asset.name
            ctx["asset_ip"] = asset.ip
    
    session.context = json.dumps(ctx, ensure_ascii=False)
    db.commit()

    # 注入系统消息
    asset_name = ctx.get('asset_name', '未知')
    summary = (
        f"**用户手动关联了告警**\n"
        f"已关联告警 **#{alert.id}** ({alert.severity})：{alert.message or ''}\n"
        f"- 指标：{alert.metric_name}，当前值：{alert.actual_value}\n"
        f"- 涉事资产：{asset_name}\n"
        f"后续分析将自动参考此告警上下文。"
    )
    add_message(db, session.id, "system", summary, message_type="text")

    return {"status": "ok", "message": "关联成功"}


@router.post("/session/{session_id}/link-asset")
async def link_asset_to_session(session_id: int, request: Request, db: Session = Depends(get_db)):
    user_id = _get_user_id(request)
    if not user_id:
        return JSONResponse({"error": "未登录"}, status_code=401)
        
    data = await request.json()
    asset_id = data.get("asset_id")
    if not asset_id:
        return JSONResponse({"error": "缺少 asset_id"}, status_code=400)

    session = db.query(ChatSession).filter(
        ChatSession.id == session_id, ChatSession.user_id == user_id
    ).first()
    if not session:
        return JSONResponse({"error": "会话不存在"}, status_code=404)

    asset = db.query(Asset).filter(Asset.id == asset_id).first()
    if not asset:
        return JSONResponse({"error": "资产不存在"}, status_code=404)

    import json
    ctx = json.loads(session.context or "{}")
    # 如果已有关联告警，移除告警上下文以切换为资产上下文（避免冲突）
    if "alert_id" in ctx:
        del ctx["alert_id"]
        
    ctx["asset_id"] = asset.id
    ctx["asset_name"] = asset.name
    ctx["asset_ip"] = asset.ip
    
    session.context = json.dumps(ctx, ensure_ascii=False)
    db.commit()

    summary = (
        f"**用户手动关联了资产**\n"
        f"已关注资产 **{asset.name}** ({asset.ip or 'N/A'})。\n"
        f"后续分析将自动参考此资产上下文。"
    )
    add_message(db, session.id, "system", summary, message_type="text")

    return {"status": "ok", "message": "关联成功"}


@router.get("/api/capabilities")
def get_agent_capabilities(request: Request, db: Session = Depends(get_db)):
    """返回 Agent 能力中心数据：工具清单 + Agent 配置 + 统计"""
    config = db.query(AgentConfig).filter(AgentConfig.name == "default").first()
    provider = None
    if config and config.default_provider_id:
        provider = db.query(AIProvider).filter(AIProvider.id == config.default_provider_id).first()

    tools = []
    risk_counts = {"read_only": 0, "low": 0, "medium": 0, "high": 0, "critical": 0, "advisory": 0}
    for t in _MCP_TOOLS.values():
        risk_counts[t.risk_level] = risk_counts.get(t.risk_level, 0) + 1
        tools.append({
            "name": t.name,
            "display_name": t.display_name or t.name,
            "description": t.description,
            "input_schema": t.input_schema,
            "risk_level": t.risk_level,
            "expose_to_llm": t.expose_to_llm,
        })

    total = len(tools)
    llm_tools = sum(1 for t in tools if t["expose_to_llm"])
    internal_tools = total - llm_tools

    return {
        "tools": tools,
        "stats": {
            "total": total,
            "llm_tools": llm_tools,
            "internal_tools": internal_tools,
            "risk_counts": risk_counts,
        },
        "agent_config": {
            "name": config.name if config else "default",
            "system_prompt": config.system_prompt if config else "",
            "welcome_message": config.welcome_message if config else "",
            "allow_action_execution": config.allow_action_execution if config else True,
            "require_confirmation": config.require_confirmation if config else True,
            "max_history_messages": config.max_history_messages if config else 12,
            "is_enabled": config.is_enabled if config else True,
        } if config else None,
        "provider": {
            "name": provider.name if provider else None,
            "provider_type": provider.provider_type if provider else None,
            "default_model": provider.default_model if provider else None,
            "base_url": provider.base_url if provider else None,
            "is_enabled": provider.is_enabled if provider else None,
        } if provider else None,
    }


@router.post("/correlation-analyze")
async def correlation_analyze(request: Request, db: Session = Depends(get_db)):
    """关联分析深度诊断：获取关联分析数据 → 创建会话 → 注入上下文 → 返回会话ID"""
    user_id = _get_user_id(request)
    if not user_id:
        return JSONResponse({"error": "未登录"}, status_code=401)

    data = await request.json()
    hours = int(data.get("hours", 1))
    service = data.get("service", "")
    asset_id = int(data.get("asset_id", 0))

    # 1. 获取关联分析数据
    correlation_data = run_correlation_analysis(db, hours, service, asset_id)

    # 2. 创建新会话
    session = ChatSession(user_id=user_id, title="关联分析深度诊断", context="{}")
    db.add(session)
    db.commit()
    db.refresh(session)

    # 3. 注入关联分析上下文到 session.context
    ctx = json.loads(session.context or "{}")
    ctx["correlation_id"] = f"corr_{session.id}"
    ctx["correlation_hours"] = hours
    ctx["correlation_service"] = service
    ctx["correlation_asset_id"] = asset_id
    session.context = json.dumps(ctx, ensure_ascii=False)
    db.commit()

    # 4. 添加系统消息（完整关联分析数据）
    context_text = format_correlation_for_llm(correlation_data)
    add_message(db, session.id, "system", context_text, message_type="text")

    # 5. 添加用户消息（自动发起深度分析请求）
    analysis_prompt = (
        "请基于以上关联分析数据，进行深度诊断分析：\n"
        "1. **当前系统状态评估** — 是否存在正在发生的故障？故障的严重程度如何？\n"
        "2. **根因定位** — 如果存在故障，最可能的根因是什么？是应用层、基础设施层还是代码问题？\n"
        "3. **影响范围** — 哪些服务、资产或用户受到影响？\n"
        "4. **修复建议** — 给出具体的修复步骤和优先级排序（P0/P1/P2）\n"
        "5. **优化建议** — 如果无明显故障，基于数据给出系统优化建议\n\n"
        "请结合告警、指标异常、日志异常和链路追踪四个维度的数据进行综合分析。"
    )
    add_message(db, session.id, "user", analysis_prompt, message_type="text")

    return {
        "session_id": session.id,
        "title": "关联分析深度诊断",
    }


# ─── P1-P4: 会话级配置接口（模型切换 / 模式切换 / 重命名 / 多设备绑定） ───

@router.post("/session/{session_id}/set-provider")
async def set_session_provider(session_id: int, request: Request, db: Session = Depends(get_db)):
    """切换会话使用的 LLM Provider"""
    user_id = _get_user_id(request)
    if not user_id:
        return JSONResponse({"error": "未登录"}, status_code=401)
    data = await request.json()
    provider_id = data.get("provider_id")
    session = db.query(ChatSession).filter(
        ChatSession.id == session_id, ChatSession.user_id == user_id).first()
    if not session:
        return JSONResponse({"error": "会话不存在"}, status_code=404)
    if provider_id:
        p = db.query(AIProvider).filter(AIProvider.id == provider_id, AIProvider.is_enabled == True).first()
        if not p:
            return JSONResponse({"error": "Provider 不存在或已禁用"}, status_code=400)
    session.provider_id = provider_id or None
    db.commit()
    return {"status": "ok", "provider_id": session.provider_id}


@router.post("/session/{session_id}/set-mode")
async def set_session_mode(session_id: int, request: Request, db: Session = Depends(get_db)):
    """切换会话模式 chat / agent"""
    user_id = _get_user_id(request)
    if not user_id:
        return JSONResponse({"error": "未登录"}, status_code=401)
    data = await request.json()
    mode = data.get("mode")
    if mode not in (ChatSession.MODE_AGENT, ChatSession.MODE_CHAT):
        return JSONResponse({"error": "无效模式"}, status_code=400)
    session = db.query(ChatSession).filter(
        ChatSession.id == session_id, ChatSession.user_id == user_id).first()
    if not session:
        return JSONResponse({"error": "会话不存在"}, status_code=404)
    session.mode = mode
    db.commit()
    return {"status": "ok", "mode": session.mode}


@router.post("/session/{session_id}/rename")
async def rename_session(session_id: int, request: Request, db: Session = Depends(get_db)):
    """重命名会话"""
    user_id = _get_user_id(request)
    if not user_id:
        return JSONResponse({"error": "未登录"}, status_code=401)
    data = await request.json()
    title = (data.get("title") or "").strip()[:128]
    if not title:
        return JSONResponse({"error": "标题不能为空"}, status_code=400)
    session = db.query(ChatSession).filter(
        ChatSession.id == session_id, ChatSession.user_id == user_id).first()
    if not session:
        return JSONResponse({"error": "会话不存在"}, status_code=404)
    session.title = title
    db.commit()
    return {"status": "ok", "title": session.title}


@router.get("/session/{session_id}/devices")
def list_session_devices(session_id: int, request: Request, db: Session = Depends(get_db)):
    """获取会话绑定的设备（资产）列表"""
    user_id = _get_user_id(request)
    if not user_id:
        return JSONResponse({"error": "未登录"}, status_code=401)
    session = db.query(ChatSession).filter(
        ChatSession.id == session_id, ChatSession.user_id == user_id).first()
    if not session:
        return JSONResponse({"error": "会话不存在"}, status_code=404)
    try:
        ids = json.loads(session.linked_asset_ids or "[]")
    except Exception:
        ids = []
    assets = db.query(Asset).filter(Asset.id.in_(ids)).all() if ids else []
    return {
        "devices": [
            {"id": a.id, "name": a.name, "ip": a.ip, "ci_type": a.ci_type, "status": a.status}
            for a in assets
        ]
    }


@router.post("/session/{session_id}/link-device")
async def link_device_to_session(session_id: int, request: Request, db: Session = Depends(get_db)):
    """绑定设备（资产）到会话（多设备）"""
    user_id = _get_user_id(request)
    if not user_id:
        return JSONResponse({"error": "未登录"}, status_code=401)
    data = await request.json()
    asset_id = data.get("asset_id")
    if not asset_id:
        return JSONResponse({"error": "缺少 asset_id"}, status_code=400)
    session = db.query(ChatSession).filter(
        ChatSession.id == session_id, ChatSession.user_id == user_id).first()
    if not session:
        return JSONResponse({"error": "会话不存在"}, status_code=404)
    asset = db.query(Asset).filter(Asset.id == asset_id).first()
    if not asset:
        return JSONResponse({"error": "资产不存在"}, status_code=404)
    try:
        ids = json.loads(session.linked_asset_ids or "[]")
    except Exception:
        ids = []
    if asset_id not in ids:
        ids.append(asset_id)
        session.linked_asset_ids = json.dumps(ids, ensure_ascii=False)
        db.commit()
    return {"status": "ok", "devices_count": len(ids)}


@router.post("/session/{session_id}/unlink-device")
async def unlink_device_from_session(session_id: int, request: Request, db: Session = Depends(get_db)):
    """解绑设备"""
    user_id = _get_user_id(request)
    if not user_id:
        return JSONResponse({"error": "未登录"}, status_code=401)
    data = await request.json()
    asset_id = data.get("asset_id")
    session = db.query(ChatSession).filter(
        ChatSession.id == session_id, ChatSession.user_id == user_id).first()
    if not session:
        return JSONResponse({"error": "会话不存在"}, status_code=404)
    try:
        ids = json.loads(session.linked_asset_ids or "[]")
    except Exception:
        ids = []
    if asset_id in ids:
        ids.remove(asset_id)
        session.linked_asset_ids = json.dumps(ids, ensure_ascii=False)
        db.commit()
    return {"status": "ok", "devices_count": len(ids)}


@router.get("/providers")
def list_providers_for_chat(request: Request, db: Session = Depends(get_db)):
    """获取可用的 LLM Provider 列表（供模型下拉）"""
    user_id = _get_user_id(request)
    if not user_id:
        return JSONResponse({"error": "未登录"}, status_code=401)
    providers = db.query(AIProvider).filter(AIProvider.is_enabled == True).all()
    return {
        "providers": [
            {"id": p.id, "name": p.name, "provider_type": p.provider_type,
             "default_model": p.default_model}
            for p in providers
        ]
    }
