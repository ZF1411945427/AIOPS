"""
SSE 实时推送端点 /agent/chat/stream
StreamingResponse 逐步推送 AI 处理状态，前端 EventSource 实时显示
"""
import json
import asyncio
import time
import base64
import uuid
import re
import urllib.request
import urllib.error
from datetime import datetime
from difflib import SequenceMatcher
from fastapi import APIRouter, Request, Depends, HTTPException
from fastapi.responses import StreamingResponse, JSONResponse
from pydantic import BaseModel
from sqlalchemy.orm import Session
from app.database import get_db
from app.models import AIProvider
from app.services.agent_service import call_llm, get_mcp_manifest, call_mcp_tool
from app.services.agent_service import add_message, _parse_text_tool_calls, _strip_text_tool_call_tags
from app.services.mcp_registry import get_mcp_tool
from app.services.sub_agent_service import (
    route_sub_agent, get_sub_agent, filter_tools_by_sub_agent, get_sub_agent_prompt
)
from app.services.ws_manager import ws_manager

router = APIRouter(prefix="/agent", tags=["agent_sse"])

# ── 取消令牌：前端 STOP 时设置，生成器定期检查 ──
_CANCEL_TOKENS: dict = {}  # session_id -> True 表示取消

# ⚠️ 强制中文回复（作为用户消息前的最后一条 system，优先级最高）
_LANG_SYSTEM_HINT = (
    "## 🌐 语言要求（最高优先级）\n"
    "无论用户使用什么语言提问，你都必须用中文回复（用户明确要求其他语言除外）。"
    "请使用自然、专业的中文组织回复内容。"
)


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


def _clean_key_point(value: str, max_len: int) -> str:
    """清理 LLM 输出的要点字段: 去空白/孤立标点, 超长时在词/标点边界截断, 不截半句。"""
    import re as _re
    v = (value or "").strip()
    # 去掉首尾孤立标点(逗号/句号/分号/顿号/冒号/省略号)
    v = _re.sub(r"^[\s,，。;；、：:：.…]+", "", v)
    v = _re.sub(r"[\s,，。;；、：:：.…]+$", "", v)
    if len(v) <= max_len:
        return v
    # 超长: 优先在中文/英文标点处断开, 避免截半句
    cut = v[:max_len]
    last_punct = max(cut.rfind("。"), cut.rfind("；"), cut.rfind(";"),
                     cut.rfind("，"), cut.rfind(","), cut.rfind("、"))
    idx = last_punct + 1 if last_punct > max_len * 0.5 else max_len
    return _clean_key_point(v[:idx], max_len)


def _generate_key_points(provider, cleaned: str, steps: list) -> dict:
    """基于最终回复与工具步骤，生成统一三要素要点总结(根因/方案/影响)。

    返回 {"root_cause": str, "solution": str, "impact": str}；任何失败返回空 dict
    （调用方据此决定是否展示要点块，不影响主流程）。
    """
    try:
        step_lines = []
        for s in (steps or [])[:12]:
            name = s.get("display_name") or s.get("tool_name") or ""
            if s.get("summary"):
                step_lines.append(f"- {name}: {str(s['summary'])[:120]}")
        step_text = "\n".join(step_lines) if step_lines else "（无工具步骤）"

        sys_prompt = (
            "你是 SRE 运维要点提炼专家。根据 AI 分析的最终回复和工具执行步骤，"
            "提炼一份「直击要害」的要点总结，供运维一眼看懂。\n"
            "只输出一个 JSON 对象，不要输出其他任何文字或 markdown：\n"
            '{"root_cause": "根因是什么(≤60字，说清因为什么导致)", '
            '"solution": "怎么解决(≤80字，可直接照做的处理方向)", '
            '"impact": "影响(≤60字，影响范围/资产/严重度)"}\n'
            "若没有异常或无需处置，root_cause/solution 写'无需处置'。"
        )
        user = f"## AI 最终回复\n{cleaned[:3000]}\n\n## 工具执行步骤\n{step_text}"
        resp = call_llm(provider, [
            {"role": "system", "content": sys_prompt},
            {"role": "user", "content": user},
        ], timeout_override=60)
        if "error" in resp:
            return {}
        content = (resp.get("choices", [{}])[0].get("message", {}).get("content") or "").strip()
        start, end = content.find("{"), content.rfind("}")
        if start == -1 or end == -1:
            return {}
        data = json.loads(content[start:end + 1])
        return {
            "root_cause": _clean_key_point(data.get("root_cause", ""), 100),
            "solution": _clean_key_point(data.get("solution", ""), 160),
            "impact": _clean_key_point(data.get("impact", ""), 100),
        }
    except Exception:
        logger.warning("[except:pass] generate_key_points failed", exc_info=True)
        return {}


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
    from app.models import AgentConfig, PendingAction
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

    # ─── P1-1: 子专家分派（Multi-Agent Orchestration）──────────────
    # session.sub_agent 取值: auto/sre/network/database/middleware/k8s/general
    # auto = 根据用户消息关键词自动路由; 其他 = 手动指定子专家
    sub_agent_name = getattr(session, "sub_agent", None) or "auto"
    sub_agent_obj = None
    if sub_agent_name == "auto":
        sub_agent_name = route_sub_agent(user_message, db)
    if sub_agent_name and sub_agent_name != "general":
        sub_agent_obj = get_sub_agent(db, sub_agent_name)

    _sa = sub_agent_name if sub_agent_name != "auto" else ""
    user_msg = add_message(db, session.id, "user", user_message, sub_agent=_sa)
    if session.title == "新会话":
        session.title = user_message[:64]
        db.commit()

    system_prompt = config.system_prompt or _svc.DEFAULT_SYSTEM_PROMPT
    # 构建消息列表：先不加用户消息，把系统提示放在前面
    messages = _svc.get_message_history(db, session, config, sub_agent=_sa)

    # ⚠️ 插入主系统提示词（DEFAULT_SYSTEM_PROMPT 或用户自定义配置）
    messages.insert(0, {"role": "system", "content": system_prompt})

    # 注入子专家 system_prompt（在 config system_prompt 之后，用户消息之前）
    sub_prompt = get_sub_agent_prompt(sub_agent_obj)
    if sub_prompt:
        # 子专家提示词追加到主系统提示词之后（合并到第一条 system）
        if messages and messages[0].get("role") == "system":
            messages[0]["content"] = messages[0]["content"] + "\n\n## 当前子专家身份\n" + sub_prompt
        else:
            messages.insert(0, {"role": "system", "content": sub_prompt})

    # ⚠️ 强制中文回复（追加在用户消息之前的最后一条 system，优先级最高）
    messages.append({"role": "system", "content": _LANG_SYSTEM_HINT})
    # 最后追加用户消息
    messages.append({"role": "user", "content": user_message})
    # 推送子专家切换事件（前端显示当前子专家标签）
    if sub_agent_obj or sub_agent_name == "general":
        if sub_agent_obj:
            yield sse_json("sub_agent", {
                "name": sub_agent_obj.name, "display_name": sub_agent_obj.display_name,
                "domain": sub_agent_obj.domain, "icon": sub_agent_obj.icon, "color": sub_agent_obj.color,
            })
        else:
            yield sse_json("sub_agent", {
                "name": "general", "display_name": "通用助手",
                "domain": "general", "icon": "🤖", "color": "#64748b",
            })

    mcp_tools = get_mcp_manifest() if not is_chat_mode else []
    # 按子专家工具白名单过滤
    if mcp_tools and sub_agent_obj:
        mcp_tools = filter_tools_by_sub_agent(mcp_tools, sub_agent_obj)
    openai_tools = [{
        "type": "function", "function": {
            "name": t["name"], "description": t["description"], "parameters": t["input_schema"]
        }
    } for t in mcp_tools] if mcp_tools else []

    yield sse_json("status", {"content": "思考中..."})

    async def _call_llm_task(p, msgs, tools):
        loop = asyncio.get_running_loop()
        return await loop.run_in_executor(None, call_llm, p, msgs, tools)

    async def _stream_llm_first(p, msgs, tools):
        """真流式第一次 LLM 调用: 逐 token yield 'token' SSE, 累积后返回兼容的 response dict。
        若流式失败降级为阻塞 call_llm(回归安全)。"""
        from app.services.agent_service import stream_llm
        loop = asyncio.get_running_loop()
        full_text = []
        tool_calls = []
        has_error = [None]
        try:

            def _iter():
                out = []
                for item in stream_llm(p, msgs, tools if tools else None):
                    out.append(item)
                return out

            items = await loop.run_in_executor(None, _iter)
            for item in items:
                if "token" in item:
                    tok = item["token"]
                    full_text.append(tok)
                    yield sse_json("token", {"token": tok})
                elif "error" in item:
                    has_error[0] = item["error"]
                    return
                elif "complete" in item:
                    c = item["complete"]
                    full_text.append(c.get("content") or "")
                    tool_calls = c.get("tool_calls") or []
        except Exception as e:
            has_error[0] = str(e)
            return
        if has_error[0] is not None:
            # 降级阻塞
            blocking = await loop.run_in_executor(None, call_llm, p, msgs, tools)
            if "error" in blocking and not full_text:
                has_error[0] = blocking["error"]
                return
            resp = blocking
        else:
            content = "".join(full_text).strip()
            resp = {"choices": [{"message": {"role": "assistant", "content": content, "tool_calls": tool_calls or None}}], "usage": {}}
        if tool_calls:
            # 有工具: 已流式回显文本后, 给前端一个 done 前的分隔提示
            pass
        yield {"__response": resp, "__has_error": has_error[0]}

    start = time.time()
    first_gen = _stream_llm_first(provider, messages, openai_tools if openai_tools else None)
    first_capture = None
    async for chunk in first_gen:
        if "token" in chunk:
            yield chunk  # token SSE
        elif "__response" in chunk:
            first_capture = chunk
    # ── 取消检查点 1：首轮 LLM 后 ──
    if _CANCEL_TOKENS.get(str(session.id)):
        yield sse_json("done", {"content": "", "reply": "", "cancelled": True})
        return
    if first_capture is None:
        response = {"choices": [{"message": {"role": "assistant", "content": "分析完成。"}}]}
    else:
        if first_capture.get("__has_error"):
            err = f"LLM 调用失败: {first_capture['__has_error']}"
            yield sse_json("error", {"content": err})
            add_message(db, session.id, "assistant", err, message_type="error")
            return
        response = first_capture["__response"]
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
        # ── 取消检查点 2：每轮工具执行前 ──
        if _CANCEL_TOKENS.get(str(session.id)):
            break
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

        # hoisting: 归一化 tool_calls(补稳定id/去重/参数JSON兜底), 保证回填协议合规
        from app.services.agent_service import _hoist_tool_calls
        tool_calls_raw = _hoist_tool_calls(msg)

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
                # A3: 子智能体切换
                if isinstance(result_data, dict) and result_data.get("_switch_sub_agent"):
                    _new_sa = result_data["_switch_sub_agent"]
                    session.sub_agent = _new_sa
                    db.commit()
                    yield sse_json("sub_agent_switch", {
                        "sub_agent": _new_sa,
                        "message": result_data.get("message", ""),
                    })

        # hoisting 回填: 按 id(退化按 name)把工具结果挂到 assistant tool_calls 后, 协议合规
        from app.services.agent_service import _append_tool_results
        _append_tool_results(messages, msg, tool_results, name_key="tool_name")

        # ── 取消检查点 3：工具执行后、LLM 重调前 ──
        if _CANCEL_TOKENS.get(str(session.id)):
            break

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
        # ── 取消检查点 4：最终总结前 ──
        if _CANCEL_TOKENS.get(str(session.id)):
            yield sse_json("done", {"content": "", "reply": "", "cancelled": True})
            return
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
                              tool_calls=tool_calls_with_steps if tool_calls_with_steps else None,
                              sub_agent=_sa)
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
    except Exception as _exc:
        logger.warning("[except:pass] Exception: %s", _exc, exc_info=True)

    deep_links = _extract_deep_links(cleaned, steps)

    # ── 生成统一要点总结(根因/方案/影响)，挂在 done 事件末尾；失败返回空 → 前端不渲染 ──
    key_points = {}
    try:
        _loop = asyncio.get_running_loop()
        key_points = await _loop.run_in_executor(
            None, _generate_key_points, provider, cleaned, steps
        )
    except Exception:
        logger.warning("[except:pass] key_points gen failed", exc_info=True)
        key_points = {}
    logger.info("[KeyPoints] session=%s reply_len=%d key_points=%s",
                session.id, len(cleaned), json.dumps(key_points, ensure_ascii=False)[:200])

    yield sse_json("done", {
        "session_id": session.id,
        "reply": cleaned,
        "summary": key_points if (key_points.get("root_cause") or key_points.get("solution")) else None,
        "pending_actions": pending_actions,
        "steps": steps,
        "urgency": urgency,
        "total_steps": len(steps),
        "completed_steps": len(steps),
        "deep_links": deep_links,
    })

    try:
        await ws_manager.broadcast(f"agent_{session.id}", {
            "type": "chat_update", "session_id": session.id,
            "reply": cleaned, "pending_actions": pending_actions,
            "steps": steps,
        })
    except Exception as _exc1:
        logger.warning("[except:pass] Exception: %s", _exc1, exc_info=True)


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
    # 清除该会话的旧取消标记
    _CANCEL_TOKENS.pop(str(session_id), None)
    return StreamingResponse(
        _stream_chat(user_id, session_id, message, "default", db),
        media_type="text/event-stream",
        headers={"Cache-Control": "no-cache", "X-Accel-Buffering": "no"}
    )


@router.post("/chat/cancel/{session_id}")
async def chat_cancel(session_id: int, request: Request):
    """取消指定会话的流式处理（前端 STOP 按钮调用）"""
    user_id = _get_user_id(request)
    if not user_id:
        return {"ok": False, "message": "未登录"}
    _CANCEL_TOKENS[str(session_id)] = True
    return {"ok": True, "message": "取消中"}


import logging
logger = logging.getLogger(__name__)


def _extract_deep_links(reply: str, steps: list) -> list:
    """从回复文本和步骤中提取可跳转的深度链接。"""
    links = []
    seen = set()

    # 1. 从步骤结果中提取实体
    for s in steps:
        raw = s.get("raw_output", "")
        if not raw:
            continue
        try:
            result = json.loads(raw) if isinstance(raw, str) else raw
            if isinstance(result, dict):
                result = result.get("result", result)
            if isinstance(result, dict):
                # 资产 ID
                asset_id = result.get("asset_id") or result.get("id")
                asset_name = result.get("asset_name") or result.get("name")
                if asset_id and asset_name and ("asset" not in seen):
                    seen.add("asset")
                    links.append({"label": f"📦 {asset_name}", "type": "asset", "key": "asset-list", "params": {"id": asset_id}})
                # 告警 ID
                alert_id = result.get("alert_id")
                if alert_id and ("alert" not in seen):
                    seen.add("alert")
                    links.append({"label": f"🚨 告警 #{alert_id}", "type": "alert", "key": "alerts", "params": {"id": alert_id}})
                # 故障单 ID
                incident_id = result.get("incident_id")
                if incident_id and ("incident" not in seen):
                    seen.add("incident")
                    links.append({"label": f"📋 故障单 #{incident_id}", "type": "incident", "key": "incident", "params": {"id": incident_id}})
        except (json.JSONDecodeError, TypeError):
            pass

    # 2. 从回复文本中提取引用
    if reply:
        # 告警 #数字
        for m in re.finditer(r'(?:告警|alert)\s*#?\s*(\d+)', reply, re.IGNORECASE):
            aid = m.group(1)
            key = f"alert_{aid}"
            if key not in seen:
                seen.add(key)
                links.append({"label": f"🚨 告警 #{aid}", "type": "alert", "key": "alerts", "params": {"id": aid}})
        # 故障单 #数字
        for m in re.finditer(r'(?:故障单|incident)\s*#?\s*(\d+)', reply, re.IGNORECASE):
            iid = m.group(1)
            key = f"incident_{iid}"
            if key not in seen:
                seen.add(key)
                links.append({"label": f"📋 故障单 #{iid}", "type": "incident", "key": "incident", "params": {"id": iid}})
        # 资产名称（在引号或括号中）
        for m in re.finditer(r'[「『【\[]\s*([^」』】\]]{2,24}?)\s*[」』】\]](?:\s*资产|\s*主机|\s*节点)?', reply):
            name = m.group(1)
            key = f"asset_name_{name}"
            if key not in seen:
                seen.add(key)
                links.append({"label": f"📦 {name}", "type": "asset", "key": "asset-list", "params": {"name": name}})

    return links[:6]  # 最多6个


# ── TTS 语音合成端点（云端分发，已移除本地 VITS，2026-08-19） ──
# 引擎分发(见 CONTRACT.md 26.6, voice_service.py): 云 TTS(阿里/百度/腾讯) → edge-tts(免费云端) 逐级降级。
# 单角色=小智(jarvis)。edge-tts 音色: 云健(磁性男声)。

@router.get("/tts")
async def agent_tts(text: str, voice: str = "jarvis", engine: str = "", request: Request = None, db: Session = Depends(get_db)):
    """将文本合成为指定角色音色的 MP3 音频流。

    引擎分发(见 CONTRACT.md 26.6, voice_service.py):
    已配置云 TTS(阿里/百度/腾讯)则调用云端, 否则/失败回退 edge-tts(微软免费)。
    engine=edge-tts 时强制固定云健男声(zh-CN-YunjianNeural), 不走已配置的云 TTS。
    实现: 本地磁盘缓存(按 text+voice+engine 哈希) + 云端调用。
    """
    user_id = _get_user_id(request)
    if not user_id:
        return JSONResponse({"error": "未登录"}, status_code=401)
    if not text or not text.strip():
        return JSONResponse({"error": "文本不能为空"}, status_code=400)

    import hashlib
    from pathlib import Path
    cache_dir = Path(__file__).resolve().parent.parent.parent / "storage" / "tts_cache"

    # 通过 voice_service 分发合成(云 TTS → edge-tts)；engine=edge-tts 时强制云健男声。
    # 合成函数内部可能用 asyncio.run(edge-tts)，不能在 FastAPI 事件循环里直接调，
    # 故放到线程池去跑，线程内无运行中的事件循环，asyncio.run 可正常工作。
    from app.services import voice_service
    loop = asyncio.get_running_loop()
    if engine == "edge-tts":
        data, media_type, engine_used = await loop.run_in_executor(
            None, voice_service._edge_tts, text, voice
        )
    else:
        data, media_type, engine_used = await loop.run_in_executor(
            None, voice_service.synthesize, db, text, voice
        )

    if not data:
        return JSONResponse({"error": "TTS 合成失败，请稍后重试"}, status_code=500)

    # 本地磁盘缓存(按文本+引擎哈希)
    ext = "mp3" if engine_used in ("aliyun", "baidu", "tencent", "edge-tts") else "mp3"
    try:
        cache_key = hashlib.md5(f"{engine_used}|{voice}|{text}".encode()).hexdigest()
        cache_dir.mkdir(parents=True, exist_ok=True)
        cache_file = cache_dir / f"{cache_key}.{ext}"
        cache_file.write_bytes(data)
    except Exception as e:
        logger.warning("TTS 缓存写入失败: %s", e)

    headers = {
        "Cache-Control": "public, max-age=86400",
        "Content-Disposition": "inline",
        "X-TTS-Engine": engine_used,
    }
    return StreamingResponse(iter([data]), media_type=media_type, headers=headers)


# ── STT 语音识别端点（本地 sherpa-onnx ASR） ──
# 前端 MediaRecorder 录音 → base64 上传 → 本地 sherpa-onnx 流式 Zipformer 识别转文字。
# 完全本地推理（中英双语，~190MB），不依赖任何外部远程服务，替换旧 whisper-small（~967MB）。
# 前端 `_flushRecording()` 用 Web Audio 解码 → 重采样 16kHz → 编码 WAV → 上传本端点。

class VoiceTranscribeReq(BaseModel):
    audio_base64: str
    format: str = "webm"  # webm/mp3/wav


@router.post("/voice/transcribe")
def agent_voice_transcribe(req: VoiceTranscribeReq, request: Request, db: Session = Depends(get_db)):
    """接收前端录音 base64，走 voice_service 引擎分发(云 STT 或本地 sherpa-onnx)。"""
    user_id = _get_user_id(request)
    if not user_id:
        return JSONResponse({"error": "未登录"}, status_code=401)

    try:
        audio_bytes = base64.b64decode(req.audio_base64)
    except Exception:
        raise HTTPException(status_code=400, detail="音频数据解码失败")

    if len(audio_bytes) < 500:
        raise HTTPException(status_code=400, detail="音频太短，请说话至少1秒")

    # 引擎分发: 配置了云 STT 则调用云端, 否则本地 sherpa-onnx(两者都容错)
    from app.services import voice_service
    text, provider = voice_service.transcribe_audio_file(
        db, audio_bytes, sample_rate=16000, audio_format=req.format or "wav"
    )
    logger.info("[voice] transcribe user=%s provider=%s text=%r", user_id, provider, text or "(empty)")
    if not text:
        raise HTTPException(status_code=422, detail="语音识别返回空结果")
    return {"text": text, "provider": provider}

# ── 唤醒词检测端点（云端 ASR 识别 + 文本匹配，已移除本地 KWS/VAD，2026-08-19） ──
# 唤醒流程：录音 → 云端 STT(voice_service 分发) → 整句识别 → 文本匹配唤醒词。
# 命中即唤醒；未命中返回识别文本便于调试。
# 前端 WAKE_WORDS 含 ['小智','唤醒']，需与后端词表一致。

_WAKE_WORDS = ['小智', '唤醒']


def _smart_wake_match(text, wake_word, threshold=0.5):
    """智能模糊匹配唤醒词（自适应同音/近音/错别字，无需维护词表）。

    思路：把识别文本滑窗切成与唤醒词等长的窗口，用 difflib.SequenceMatcher
    计算字符级相似度，超过阈值即命中。同音字(智/志/之/只)、近字(学/鞋)都自动覆盖。
    """
    text = text.lower()
    wake_word = wake_word.lower()
    n = len(wake_word)
    if len(text) < n:
        return False
    for i in range(len(text) - n + 1):
        window = text[i:i + n]
        if SequenceMatcher(None, window, wake_word).ratio() >= threshold:
            return True
    return False


class WakeCheckReq(BaseModel):
    audio_base64: str   # 16kHz 单声道 16bit PCM 的 WAV base64
    format: str = "wav"


@router.post("/voice/wake-check")
def agent_voice_wake_check(req: WakeCheckReq, request: Request, db: Session = Depends(get_db)):
    """接收前端唤醒词录音 base64，云端 STT 识别后文本匹配唤醒词。

    返回 {"hit": true, "keyword": "小智", "provider": "aliyun"|"baidu"|"tencent"}；
    未命中时返回 {"hit": false, "keyword": "", "detected": "ASR识别文本"}。
    无云 STT 配置/无密钥/识别失败时 hit=false(不可唤醒)。
    """
    user_id = _get_user_id(request)
    if not user_id:
        return JSONResponse({"error": "未登录"}, status_code=401)

    try:
        audio_bytes = base64.b64decode(req.audio_base64)
    except Exception:
        raise HTTPException(status_code=400, detail="音频数据解码失败")

    if len(audio_bytes) < 100:
        raise HTTPException(status_code=400, detail="音频太短")

    # 统一交给云端 STT 整句识别(voice_service 分发 aliyun/baidu/tencent)
    from app.services import voice_service
    try:
        text, provider = voice_service.transcribe_audio_file(
            db, audio_bytes, sample_rate=16000, audio_format=req.format or "wav"
        )
    except Exception:
        text, provider = "", "none"

    text = (text or "").strip()
    if text:
        text_lower = text.lower()
        for w in _WAKE_WORDS:
            if w in text_lower or w in text:
                return {"hit": True, "keyword": w, "provider": provider or "cloud", "detected": text}
        for w in _WAKE_WORDS:
            if _smart_wake_match(text_lower, w):
                return {"hit": True, "keyword": w, "provider": provider or "cloud", "detected": text}
    return {"hit": False, "keyword": "", "provider": provider or "none", "detected": text}


# ── 语音导航意图识别（关键词/同音模糊匹配优先 + LLM 兜底） ──
# 解决常驻语音指挥里 STT 把"拓扑"识别成"简谱/点头"等近音词导致跳转失败的问题。
# 流程：文本 → ① 对全部菜单 label 做同音/近音模糊匹配 → 命中即跳转（无 LLM，快）
#       → ② 未命中再交给 LLM 判定该打开哪个菜单页面（兜底，慢一点）。

class NavIntentReq(BaseModel):
    text: str


def _load_menu_label_map() -> list:
    """读取 menu_config.json，返回 [{key, label, group_label, leaf}] 扁平列表（含嵌套）。
    leaf=True 表示真正的可导航页面叶子节点（非分组）；匹配优先级最高，避免命中间接分组 key。"""
    import os
    cfg = os.path.join(os.path.dirname(__file__), "menu_config.json")
    try:
        with open(cfg, encoding="utf-8") as f:
            menu = json.load(f)
    except Exception:
        return []
    out = []
    for g in menu:
        gkey, glabel = g.get("key", ""), g.get("label", "")
        items = g.get("items", [])
        if not items:
            out.append({"key": gkey, "label": glabel or gkey, "group": "", "leaf": True})
            continue
        for it in items:
            ikey, ilabel = it.get("key", ""), it.get("label", "")
            subs = it.get("items", [])
            if not subs:
                out.append({"key": ikey, "label": ilabel or ikey, "group": glabel, "leaf": True})
            else:
                # 分组节点(非叶子)同样收录, leaf=False, 供模糊/别名兜底; 但叶子节点优先级更高
                out.append({"key": ikey, "label": ilabel or ikey, "group": glabel, "leaf": False})
                for s in subs:
                    out.append({"key": s.get("key", ""), "label": s.get("label", ""), "group": glabel, "leaf": True})
    return [x for x in out if x["key"]]


# 语音常用别名 → 兜底映射到具体菜单 key（覆盖 STT 近音/口语化表达）
_NAV_ALIASES = [
    ("拓扑", "topology"),
    ("架构", "topology"),          # 架构拓扑
    ("监控", "monitor-view"),
    ("指标", "metrics"),
    ("告警", "alerts"),
    ("日志", "logs"),
    ("故障", "incident"),
    ("工单", "incident"),
    ("资产", "asset-list"),
    ("态势", "system-posture"),
    ("集群", "k8s-overview"),
    ("容器", "docker-list"),
    ("链路", "traces"),
    ("追踪", "traces"),
    ("预测", "prediction-models"),
    ("用户", "users"),
    ("权限", "roles-manage"),
    ("设置", "settings"),
]


def _fuzzy_match_label(text: str, label: str, threshold: float = 0.45) -> bool:
    """用 difflib 同音/近音相似度判断 text 是否命中 label（滑窗，覆盖近音错别字）。"""
    text = (text or "").lower()
    label = (label or "").lower()
    # 完整包含（加速 + 高置信）
    if label and label in text:
        return True
    n = len(label)
    if n < 2 or len(text) < n:
        return False
    for i in range(len(text) - n + 1):
        window = text[i:i + n]
        # 同音：去掉声调差异已经很接近；SequenceMatcher 对同音/近音字友好
        if SequenceMatcher(None, window, label).ratio() >= threshold:
            return True
    # 反向：label 长句里包含 text 里的候选词
    return False


@router.post("/voice/nav-intent")
def agent_voice_nav_intent(req: NavIntentReq, request: Request, db: Session = Depends(get_db)):
    """语音导航意图识别：返回 {hit, nav, label, source}；未命中 hit=false。"""
    user_id = _get_user_id(request)
    if not user_id:
        return JSONResponse({"error": "未登录"}, status_code=401)

    text = (req.text or "").strip()
    if not text:
        return {"hit": False, "nav": "", "label": "", "source": "empty"}

    items = _load_menu_label_map()
    # ① 全称/别名优先 + 同音模糊匹配（同等置信下偏好叶子节点 leaf=True，避免命中间接分组 key）
    best = None
    best_score = 0.0
    for it in items:
        label = it["label"]
        score = 0.0
        if label and label in text:
            score = 1.0
        elif label and _fuzzy_match_label(text, label, 0.5):
            score = SequenceMatcher(None, label, text).ratio()
        if score > best_score or (score == best_score and best and it.get("leaf") and not best.get("leaf")):
            best_score = score
            best = it
    if not best or best_score < 0.5:
        for alias, nav in _NAV_ALIASES:
            if _fuzzy_match_label(text, alias, 0.45):
                found = next((x for x in items if x["key"] == nav), None)
                candidate = found or {"key": nav, "label": alias, "group": ""}
                # 别名命中若置信更高则覆盖，否则保留原 best（如"打开指标监控"更贴合 metrics）
                if best is None or best_score < 0.6:
                    best = candidate
                    best_score = 0.6
                break

    # 导航意图门控：有"打开/去/看"等导航动词，或整句基本等于页面名（高置信）才跳转。
    # 避免"帮我建一张...指标卡"这类动作指令被误判为跳转到指标页。
    nav_verbs = ["打开", "去", "看", "显示", "进入", "跳转", "前往", "切到", "查看", "展示", "到"]
    has_nav_verb = any(v in text for v in nav_verbs)
    if best and best_score >= 0.5 and (has_nav_verb or best_score >= 0.85):
        return {"hit": True, "nav": best["key"], "label": best["label"], "source": "fuzzy"}

    # 动作指令门控：无导航动词，却含"建/创建/生成/做/写"等动作意图（如"帮我建指标卡"），
    # 判定为让 AI 干活而非打开页面 → 跳过 LLM 导航，交给前端发 AI 处理。
    action_verbs = ["建", "创建", "生成", "做", "写", "新增", "添加", "删除", "删掉", "帮我", "分析", "查询", "排查", "看看什么", "怎么回事", "为什么"]
    has_action = any(v in text for v in action_verbs)
    if not has_nav_verb and has_action:
        return {"hit": False, "nav": "", "label": "", "source": "action"}

    # ② LLM 兜底：让模型判定该打开哪个菜单页面
    from app.services.ai_provider_health import select_healthy_provider
    from app.models import AgentConfig
    config = db.query(AgentConfig).filter(AgentConfig.is_enabled == True).order_by(AgentConfig.id.asc()).first()
    provider = None
    if config and config.default_provider_id:
        provider = db.query(AIProvider).filter(
            AIProvider.id == config.default_provider_id, AIProvider.is_enabled == True).first()
    if not provider:
        _all = db.query(AIProvider).filter(AIProvider.is_enabled == True).all()
        provider = select_healthy_provider(_all)[0] if _all else None
    if not provider:
        return {"hit": False, "nav": "", "label": "", "source": "no-provider"}

    menu_lines = "\n".join(f"- {it['label']}({it['key']})" for it in items if it.get("leaf"))
    sys_prompt = (
        "你是智能导航助手。判断用户这句话是不是\"打开某个功能页面\"的导航意图。\n"
        "若是导航意图：从下面的菜单列表中选出最匹配的一个，只输出该菜单的 key（形如 topology）；\n"
        "若不是导航意图（例如让AI建指标卡、查数据、分析、答疑等），输出 NONE。\n"
        "只输出一个单词（key 或 NONE），不要任何其他文字、标点或解释。\n"
        f"菜单列表：\n{menu_lines}"
    )
    resp = call_llm(provider, [
        {"role": "system", "content": sys_prompt},
        {"role": "user", "content": f"用户说：{text}"},
    ], timeout_override=20, max_tokens_override=20)
    if resp.get("error"):
        return {"hit": False, "nav": "", "label": "", "source": "llm-error"}
    try:
        content = (resp["choices"][0]["message"]["content"] or "").strip().strip("`").strip()
    except Exception:
        content = ""
    nav = re.sub(r"[^a-zA-Z0-9_-]", "", content) if content else ""
    if nav and nav != "NONE":
        found = next((x for x in items if x["key"] == nav), None)
        if found:
            return {"hit": True, "nav": found["key"], "label": found["label"], "source": "llm"}
    return {"hit": False, "nav": "", "label": "", "source": "llm-none"}


# ── 语音填充表单（借鉴 form-field-extractor 模式：扫描字段 → LLM 解析语音→字段值 → 反馈缺漏） ──
# 前端把当前弹窗表单的字段 schema 传进来，后端用 LLM 把语音解析成 {fieldKey: value}，
# 并识别"保存/取消"等动作意图。字段类型支持 text/textarea/select(下拉, 自动匹配 options)。

class FormFillField(BaseModel):
    key: str            # 字段唯一标识（v-model 的 key，如 title/promql/category/hours/w/h）
    label: str          # 字段展示名（如 卡片标题/分类/时间范围）
    type: str = "text"  # text | textarea | select
    options: list = []  # 仅 select 用：[{value, label}]，用于把语音文字匹配到具体选项值


class FormFillReq(BaseModel):
    text: str
    fields: list = []   # List[FormFillField]
    save_words: list = ["保存", "提交", "确定", "点保存", "存卡", "建卡"]
    cancel_words: list = ["取消", "关闭", "不建了", "算了"]


@router.post("/voice/form-fill")
def agent_voice_form_fill(req: FormFillReq, request: Request, db: Session = Depends(get_db)):
    """语音填充表单：返回 {action, values, missing, feedback}。action: fill|save|cancel|none|error"""
    user_id = _get_user_id(request)
    if not user_id:
        return JSONResponse({"error": "未登录"}, status_code=401)

    text = (req.text or "").strip()
    if not text:
        return {"action": "none", "values": {}, "missing": [], "feedback": ""}

    # 动作意图优先：保存 / 取消
    for w in req.save_words:
        if w in text:
            return {"action": "save", "values": {}, "missing": [], "feedback": "收到，正在保存"}
    for w in req.cancel_words:
        if w in text:
            return {"action": "cancel", "values": {}, "missing": [], "feedback": "好的，已取消"}

    # 构建字段 schema 与 LLM 提示
    fields = [f for f in req.fields if isinstance(f, dict) and f.get("key") and f.get("label")]
    if not fields:
        return {"action": "none", "values": {}, "missing": [], "feedback": ""}

    from app.models import AgentConfig
    from app.services.ai_provider_health import select_healthy_provider
    config = db.query(AgentConfig).filter(AgentConfig.is_enabled == True).order_by(AgentConfig.id.asc()).first()
    provider = None
    if config and config.default_provider_id:
        provider = db.query(AIProvider).filter(
            AIProvider.id == config.default_provider_id, AIProvider.is_enabled == True).first()
    if not provider:
        _all = db.query(AIProvider).filter(AIProvider.is_enabled == True).all()
        provider = select_healthy_provider(_all)[0] if _all else None
    if not provider:
        return {"action": "error", "values": {}, "missing": [], "feedback": "AI 服务不可用，无法解析语音填表"}

    # 组装字段说明：select 列出可选项
    lines = []
    for f in fields:
        base = f"- {f['key']}: 字段名「{f['label']}」, 类型 {f['type']}"
        if f.get('options'):
            opts = ", ".join(f"{o.get('label')}(值:{o.get('value')})" for o in f['options'])
            base += f", 可选值: {opts}"
        lines.append(base)
    field_desc = "\n".join(lines)

    sys_prompt = (
        "你是语音表单填充助手。用户说一句话，可能是给某个表单填字段，也可能是闲聊。\n"
        "请提取这句话里提到的一个或多个字段值，只返回 JSON，不要任何解释。\n"
        "JSON 格式：{\"values\": {\"<字段key>\": \"<规范化后的值>\"}}\n"
        "规则：\n"
        "1. 只包含这句话明确提到的字段；没提到的不要包含。\n"
        "2. select 字段必须把用户说的文字匹配到给定的可选值，输出对应 value；匹配不到则不要包含该字段。\n"
        "3. text/textarea 直接填用户说的内容（去掉无关的'标题是/填/叫'等引导词）。\n"
        "4. 如果这句话不是填表内容（纯闲聊，如'你好'、'嗯'、'辛苦了'），返回 {\"values\": {}}。\n"
        f"可填字段：\n{field_desc}"
    )

    try:
        resp = call_llm(provider, [
            {"role": "system", "content": sys_prompt},
            {"role": "user", "content": f"用户说：{text}"},
        ], timeout_override=25, max_tokens_override=500)
    except Exception:
        resp = {}
    if resp.get("error"):
        return {"action": "none", "values": {}, "missing": [], "feedback": ""}

    try:
        content = (resp["choices"][0]["message"]["content"] or "").strip()
        content = re.sub(r"^```(?:json)?|```$", "", content.strip(), flags=re.M).strip()
        parsed = json.loads(content)
        values = parsed.get("values", {}) or {}
    except Exception:
        values = {}

    # 过滤非法 key，严格只保留 schema 里存在的字段
    valid_keys = {f['key'] for f in fields}
    values = {k: v for k, v in values.items() if k in valid_keys and v not in (None, "")}

    if not values:
        return {"action": "none", "values": {}, "missing": [], "feedback": ""}

    filled = "、".join(next((f['label'] for f in fields if f['key'] == k), k) for k in values)
    return {"action": "fill", "values": values, "missing": [], "feedback": f"已填好：{filled}"}
