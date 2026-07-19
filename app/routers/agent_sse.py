"""
SSE 实时推送端点 /agent/chat/stream
StreamingResponse 逐步推送 AI 处理状态，前端 EventSource 实时显示
"""
import json
import asyncio
import time
import re
from datetime import datetime
from fastapi import APIRouter, Request, Depends
from fastapi.responses import StreamingResponse
from sqlalchemy.orm import Session
from app.database import get_db
from app.models import AIProvider
from app.services.agent_service import call_llm, get_mcp_manifest, call_mcp_tool
from app.services.agent_service import add_message, get_message_history, _parse_text_tool_calls, _strip_text_tool_call_tags
from app.services.mcp_registry import get_mcp_tool
from app.services.ws_manager import ws_manager
from app.logger import logger

router = APIRouter(prefix="/agent", tags=["agent_sse"])


def _get_user_id(request: Request):
    return request.session.get("user_id")


def _tool_display_name(tool_name: str) -> str:
    """从 SSOT (MCPToolDef.display_name) 读取中文简写名，fallback 到 tool_name."""
    tool = get_mcp_tool(tool_name)
    if tool and tool.display_name:
        return tool.display_name
    return tool_name


def _tool_title(tool_name: str, tool_args: dict) -> str:
    """生成步骤标题：优先用工具参数里的语义字段，否则用中文 display_name，再否则用工具名"""
    display = _tool_display_name(tool_name)
    for key in ("asset_name", "name", "service", "metric_name", "alert_id", "incident_id", "rule_name"):
        v = tool_args.get(key)
        if v:
            return f"{display} · {v}"
    return display


def _extract_step_fields(t_name: str, t_args: dict, t_result: dict) -> dict:
    """从工具调用结果中提炼摘要/结论/原始输出，供任务进度卡片渲染"""
    raw_output = json.dumps(t_result, ensure_ascii=False, indent=2)
    status = t_result.get("status", "unknown")
    result = t_result.get("result") if isinstance(t_result, dict) else None
    message = t_result.get("message") or (result.get("message") if isinstance(result, dict) else "")

    # 摘要：优先 message；其次 result 里的语义字段；最后截取 raw
    summary = message or ""
    if not summary and isinstance(result, dict):
        for k in ("summary", "conclusion", "anomaly", "rca", "description", "output", "data"):
            v = result.get(k)
            if isinstance(v, str) and v:
                summary = v
                break
            if isinstance(v, (dict, list)) and v:
                summary = json.dumps(v, ensure_ascii=False)[:300]
                break
    if not summary:
        summary = raw_output[:300]

    # 结论：从 result 里找结论性字段
    conclusion = ""
    if isinstance(result, dict):
        for k in ("conclusion", "anomaly", "rca", "root_cause", "finding", "recommendation", "suggestion"):
            v = result.get(k)
            if isinstance(v, str) and v:
                conclusion = v
                break
            if isinstance(v, list) and v:
                conclusion = "; ".join(str(x) for x in v[:3])
                break

    # 异常识别：从 result 里找异常性字段
    anomaly = ""
    if isinstance(result, dict):
        for k in ("anomaly", "anomalies", "abnormal", "risk", "risks", "issues", "errors"):
            v = result.get(k)
            if v:
                anomaly = json.dumps(v, ensure_ascii=False) if not isinstance(v, str) else v
                break

    return {
        "summary": summary[:500],
        "conclusion": conclusion[:500],
        "anomaly": anomaly[:500],
        "raw_output": raw_output[:20000],  # 截断超长输出避免 SSE 过大
        "tool_args": json.dumps(t_args, ensure_ascii=False)[:1000],
    }


async def _stream_chat(user_id: int, session_id: int, user_message: str, config_name: str, db: Session):
    """异步生成器，逐步 yield SSE 事件"""
    from app.services.agent_service import (
        get_or_create_session,
    )
    from app.services.agent_service import DEFAULT_SYSTEM_PROMPT
    from app.models import AgentConfig, Asset as AgentModel, PendingAction
    from app.services.agent_service import ChatSession as ChatSessionModel
    import app.services.agent_service as _svc

    session = get_or_create_session(db, user_id, session_id)

    def sse_json(event_type, content):
        return f"event: {event_type}\ndata: {json.dumps(content, ensure_ascii=False)}\n\n"

    config = db.query(AgentConfig).filter(AgentConfig.name == config_name).first() or AgentConfig(
        name="default", is_enabled=True, require_confirmation=True, allow_action_execution=True,
    )

    provider = None
    # 优先用 session.provider_id（会话级模型切换），其次用 config.default_provider_id
    if getattr(session, "provider_id", None):
        provider = db.query(AIProvider).filter(AIProvider.id == session.provider_id, AIProvider.is_enabled == True).first()
    if not provider and config.default_provider_id:
        provider = db.query(AIProvider).filter(AIProvider.id == config.default_provider_id, AIProvider.is_enabled == True).first()
    if not provider:
        provider = db.query(AIProvider).filter(AIProvider.is_enabled == True).first()
    if not provider:
        yield sse_json("error", {"content": "未配置可用的 LLM 提供商"})
        return

    # 模式判定：chat 模式不注入工具，纯对话
    session_mode = getattr(session, "mode", None) or "agent"
    is_chat_mode = (session_mode == "chat")

    user_msg = add_message(db, session.id, "user", user_message)
    if session.title == "新会话":
        session.title = user_message[:64]
        db.commit()

    system_prompt = config.system_prompt or _svc.DEFAULT_SYSTEM_PROMPT
    messages = _svc.get_message_history(db, session, config) + [{"role": "user", "content": user_message}]

    mcp_tools = get_mcp_manifest() if not is_chat_mode else []
    openai_tools = [{
        "type": "function", "function": {
            "name": t["name"], "description": t["description"], "parameters": t["input_schema"]
        }
    } for t in mcp_tools] if mcp_tools else []

    yield sse_json("status", {"content": "思考中..."})

    async def _call_llm_task(p, msgs, tools):
        loop = asyncio.get_running_loop()
        return await loop.run_in_executor(None, call_llm, p, msgs, tools)

    start = time.time()
    llm_task = asyncio.create_task(_call_llm_task(provider, messages, openai_tools if openai_tools else None))
    while not llm_task.done():
        done, _ = await asyncio.wait([llm_task], timeout=2)
        if not done:
            yield sse_json("keepalive", {"content": "思考中..."})
    response = llm_task.result()
    latency = int((time.time() - start) * 1000)

    if "error" in response:
        err = f"LLM 调用失败: {response['error']}"
        yield sse_json("error", {"content": err})
        add_message(db, session.id, "assistant", err, message_type="error")
        return

    tool_results = []
    pending_actions = []
    steps = []  # 任务进度卡片步骤列表
    content = ""
    max_rounds = 15
    task_card_sent = False
    urgency = "normal"  # normal / urgent

    for round_idx in range(max_rounds):
        choice = response.get("choices", [{}])[0]
        msg = choice.get("message", {})
        content = msg.get("content") or ""
        tool_calls_raw = msg.get("tool_calls") or []

        if not tool_calls_raw and content:
            parsed = _parse_text_tool_calls(content)
            if parsed:
                msg["tool_calls"] = parsed

        if not tool_calls_raw:
            break

        cleaned = _strip_text_tool_call_tags(content) if (
            "<invoke" in content or "<parameter" in content) else content
        yield sse_json("status", {"content": f"执行工具 ({round_idx+1}/{max_rounds})..."})

        # 首次工具调用时推送任务卡片元信息
        if not task_card_sent:
            task_card_sent = True
            yield sse_json("task_card", {
                "title": "运维任务进度", "urgency": urgency, "total_steps": 0,
            })

        for tc_idx, tc in enumerate(tool_calls_raw):
            t_name = tc.get("function", {}).get("name") or ""
            try:
                t_args = json.loads(tc.get("function", {}).get("arguments", "{}") or "{}")
            except (json.JSONDecodeError, KeyError):
                t_args = {}
            step_id = f"r{round_idx}_t{tc_idx}"
            step_title = _tool_title(t_name, t_args)
            step_display = _tool_display_name(t_name)
            started_at = datetime.now().isoformat()
            yield sse_json("step_start", {
                "step_id": step_id, "round": round_idx + 1,
                "tool_name": t_name, "display_name": step_display,
                "tool_args": t_args,
                "title": step_title, "started_at": started_at,
            })
            t_start = time.time()
            t_result = call_mcp_tool(t_name, t_args, db=db, user_id=user_id, allow_internal=False)
            duration_ms = int((time.time() - t_start) * 1000)
            fields = _extract_step_fields(t_name, t_args, t_result)
            step_status = "success" if t_result.get("status") == "success" else "failed"
            finished_at = datetime.now().isoformat()
            yield sse_json("step_finish", {
                "step_id": step_id, "status": step_status,
                "duration_ms": duration_ms, "finished_at": finished_at,
                **fields,
            })
            steps.append({
                "step_id": step_id, "round": round_idx + 1, "tool_name": t_name,
                "display_name": step_display,
                "title": step_title, "status": step_status,
                "duration_ms": duration_ms,
                "started_at": started_at, "finished_at": finished_at,
                **fields,
            })
            yield sse_json("progress", {
                "completed_steps": len(steps), "total_steps": len(steps) + 1,
                "percent": round(len(steps) * 100 / (len(steps) + 1)), "urgency": urgency,
            })
            from app.models import ToolInvocation as ToolInv
            db.add(ToolInv(session_id=session.id, message_id=user_msg.id, tool_name=t_name,
                    status=step_status,
                    latency_ms=duration_ms,
                    request_payload=json.dumps(t_args, ensure_ascii=False),
                    response_summary=json.dumps(t_result, ensure_ascii=False)))
            db.commit()
            tool_results.append({"tool_name": t_name, "result": t_result})

            if isinstance(t_result, dict) and t_result.get("status") == "success":
                result_data = t_result.get("result", {})
                if isinstance(result_data, dict) and result_data.get("_pending_action"):
                    pa_data = result_data["_pending_action"]
                    risk = pa_data.get("risk_level", "low")
                    if risk in ("critical", "high"):
                        urgency = "urgent"
                    if config.require_confirmation and not pa_data.get("auto_confirm"):
                        pa = PendingAction(
                            session_id=session.id, message_id=user_msg.id,
                            action_type=pa_data.get("action_type", "unknown"),
                            title=pa_data.get("title", ""),
                            risk_level=risk,
                            reason=pa_data.get("reason", ""),
                            action_payload=json.dumps(pa_data.get("payload", {}), ensure_ascii=False),
                            status=PendingAction.STATUS_PENDING,
                        )
                        db.add(pa)
                        db.commit()
                        pending_actions.append({"id": pa.id, "title": pa.title, "risk_level": pa.risk_level, "action_type": pa.action_type})
                        yield sse_json("pending_action", {
                            "id": pa.id, "title": pa.title, "risk_level": pa.risk_level, "action_type": pa.action_type
                        })

        messages.append(msg)
        for tc_item, tr_item in zip(tool_calls_raw, tool_results):
            messages.append({"role": "tool", "tool_call_id": tc_item.get("id", ""), "content": json.dumps(tr_item.get("result", {}), ensure_ascii=False)})

        llm_task = asyncio.create_task(_call_llm_task(provider, messages, openai_tools if openai_tools else None))
        while not llm_task.done():
            done, _ = await asyncio.wait([llm_task], timeout=2)
            if not done:
                yield sse_json("keepalive", {"content": f"分析工具结果 ({round_idx+1}/{max_rounds})..."})
        response = llm_task.result()
        if "error" in response:
            err = f"LLM 重试失败: {response['error']}"
            yield sse_json("error", {"content": err})
            return

    # 任务完成：推送最终进度 100%
    if steps:
        yield sse_json("progress", {
            "completed_steps": len(steps), "total_steps": len(steps),
            "percent": 100, "urgency": urgency,
        })

    # max_rounds reached but content looks like internal thinking — do one final call to summarize
    _THINKING_PATTERNS = ("让我", "好的", "现在我", "让我进一步", "我先", "我需要先", "接下来", "好的，我先")
    if content and any(content.startswith(p) or content.startswith("**" + p) for p in _THINKING_PATTERNS):
        yield sse_json("status", {"content": "正在生成最终报告..."})
        messages.append({"role": "user", "content": "请基于以上所有工具调用结果，用中文给用户一份完整、清晰的分析报告。格式清晰，包含数据表格和结论。如果有异常问题请明确指出。"})
        llm_task = asyncio.create_task(_call_llm_task(provider, messages, None))
        while not llm_task.done():
            done, _ = await asyncio.wait([llm_task], timeout=3)
            if not done:
                yield sse_json("keepalive", {"content": "正在生成最终报告..."})
        final_response = llm_task.result()
        if "error" not in final_response:
            final_choice = final_response.get("choices", [{}])[0]
            content = final_choice.get("message", {}).get("content") or content
        messages.pop()  # remove the summary prompt

    cleaned = _strip_text_tool_call_tags(content) if (
        "<invoke" in content or "<parameter" in content) else content or "分析完成。"

    # 把 steps 结构化信息附加到 tool_results（供历史回放渲染任务卡片）
    tool_calls_with_steps = tool_results[:]
    for i, s in enumerate(steps):
        if i < len(tool_calls_with_steps):
            tool_calls_with_steps[i] = {**tool_calls_with_steps[i], "step": s}

    assistant_msg = add_message(db, session.id, "assistant", cleaned,
                              tool_calls=tool_calls_with_steps if tool_calls_with_steps else None)
    session.last_message_at = datetime.now()
    db.commit()

    # 记录 Agent 评估数据（遥测管道接入）
    try:
        from app.services.agent_eval_service import record_evaluation
        _HALLUCINATION_KEYWORDS = [
            "已提议", "已提交", "已提交安装", "已提交请求",
            "请点击确认", "点击确认", "确认按钮",
            "请确认是否执行", "确认执行",
            "操作已提交", "执行中，请稍候", "待确认",
        ]
        token_usage = response.get("usage", {}) if isinstance(response, dict) else {}
        total_latency = int((time.time() - start) * 1000)
        _has_hallucination = bool(cleaned and any(kw in cleaned for kw in _HALLUCINATION_KEYWORDS)
                                  and not any(s.get("tool_name") == "propose_action" and s.get("status") == "success"
                                              for s in steps))
        _is_success = bool(cleaned) and not _has_hallucination
        _task_type = "general"
        if steps:
            _tool_names = {s.get("tool_name", "") for s in steps}
            if "propose_action" in _tool_names:
                _task_type = "action_proposal"
            elif "query_alerts" in _tool_names or "get_alert_detail" in _tool_names:
                _task_type = "alert_analysis"
            elif "analyze_incident_rca" in _tool_names or "query_correlation_analysis" in _tool_names:
                _task_type = "incident_analysis"
            elif "query_assets" in _tool_names:
                _task_type = "asset_query"
            elif "query_logs" in _tool_names:
                _task_type = "log_analysis"
            elif "query_metrics" in _tool_names:
                _task_type = "metric_query"
        record_evaluation(
            db,
            session_id=session.id,
            provider_id=provider.id if provider else None,
            model_name=provider.default_model if provider else "",
            prompt_tokens=token_usage.get("prompt_tokens", 0),
            completion_tokens=token_usage.get("completion_tokens", 0),
            total_tokens=token_usage.get("total_tokens", 0),
            latency_ms=total_latency,
            round_count=(round_idx + 1) if "round_idx" in locals() else 0,
            tool_call_count=len(steps),
            success=_is_success,
            has_hallucination=_has_hallucination,
            completion_rate=1.0 if _is_success else 0.0,
            feedback="",
        )
        db.commit()
    except Exception:
        pass

    yield sse_json("done", {
        "session_id": session.id,
        "reply": cleaned,
        "pending_actions": pending_actions,
        "steps": steps,
        "urgency": urgency,
        "total_steps": len(steps),
        "completed_steps": len(steps),
    })

    try:
        await ws_manager.broadcast(f"agent_{session.id}", {
            "type": "chat_update", "session_id": session.id,
            "reply": cleaned, "pending_actions": pending_actions,
            "steps": steps,
        })
    except Exception:
        pass


@router.get("/chat/stream")
async def chat_stream(request: Request, db: Session = Depends(get_db)):
    """SSE 流式推送 AI 响应过程"""
    user_id = _get_user_id(request)
    if not user_id:
        return StreamingResponse(
            iter([f"event: error\ndata: {json.dumps({'content': '未登录'}, ensure_ascii=False)}\n\n"]),
            media_type="text/event-stream"
        )
    session_id = request.query_params.get("session_id")
    message = request.query_params.get("message", "")
    if not message:
        return StreamingResponse(
            iter([f"event: error\ndata: {json.dumps({'content': '消息不能为空'}, ensure_ascii=False)}\n\n"]),
            media_type="text/event-stream"
        )
    return StreamingResponse(
        _stream_chat(user_id, session_id, message, "default", db),
        media_type="text/event-stream",
        headers={"Cache-Control": "no-cache", "X-Accel-Buffering": "no"}
    )
