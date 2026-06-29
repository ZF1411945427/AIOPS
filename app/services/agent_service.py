import json
import time
import hashlib
import requests
from datetime import datetime
from typing import Dict, List, Optional, Any

from sqlalchemy.orm import Session

from app.models import (
    AIProvider, AgentConfig, ChatSession, ChatMessage,
    PendingAction, ToolInvocation, MCPServer,
)
from app.services.mcp_registry import get_mcp_manifest, call_mcp_tool


DEFAULT_SYSTEM_PROMPT = """你是一个 AIOps 智能运维助手。你能够帮助用户：

1. **查询资源**：查看资产列表、告警、指标、日志、K8s 资源等
2. **分析问题**：分析告警根因、异常检测结果、调用链等
3. **生成任务**：生成运维任务（脚本执行、巡检等）
4. **提供建议**：基于平台数据给出运维建议

你可以使用平台提供的工具来获取信息。对于任何有风险的操作（创建、修改、删除、执行），你必须生成待确认动作，等待用户确认后才能执行。

回答格式要求：
1. 先给出结论
2. 列出证据（引用数据来源）
3. 分析风险（如果有操作建议）
4. 给出具体建议或下一步操作"""


def call_llm(provider: AIProvider, messages: List[Dict], tools: Optional[List[Dict]] = None) -> Dict:
    """Call OpenAI-compatible API"""
    if not provider or not provider.is_enabled:
        return {"error": "Provider not available"}

    api_key = provider.get_api_key()
    base_url = provider.base_url.rstrip("/")
    model = provider.default_model or "gpt-4o"

    headers = {
        "Content-Type": "application/json",
        "Authorization": f"Bearer {api_key}",
    }

    payload = {
        "model": model,
        "messages": messages,
        "temperature": provider.temperature,
        "max_tokens": provider.max_tokens,
    }

    if tools:
        payload["tools"] = tools

    try:
        resp = requests.post(
            f"{base_url}/chat/completions",
            headers=headers,
            json=payload,
            timeout=provider.timeout_seconds,
        )
        resp.raise_for_status()
        return resp.json()
    except requests.RequestException as e:
        return {"error": str(e)}


def get_or_create_session(db: Session, user_id: int, session_id: Optional[int] = None) -> ChatSession:
    if session_id:
        session = db.query(ChatSession).filter(
            ChatSession.id == session_id,
            ChatSession.user_id == user_id,
        ).first()
        if session:
            return session

    session = ChatSession(user_id=user_id, title="新会话")
    db.add(session)
    db.commit()
    db.refresh(session)
    return session


def get_message_history(db: Session, session: ChatSession, config: AgentConfig) -> List[Dict]:
    messages = (
        db.query(ChatMessage)
        .filter(ChatMessage.session_id == session.id)
        .order_by(ChatMessage.created_at.asc())
        .all()
    )

    max_msgs = config.max_history_messages if config else 12
    if len(messages) > max_msgs:
        messages = messages[-max_msgs:]

    result = []
    for msg in messages:
        result.append({"role": msg.role, "content": msg.content or ""})
    return result


def add_message(
    db: Session, session_id: int, role: str, content: str,
    message_type: str = "text", citations: Optional[List] = None,
    tool_calls: Optional[List] = None,
) -> ChatMessage:
    msg = ChatMessage(
        session_id=session_id,
        role=role,
        message_type=message_type,
        content=content or "",
        citations=json.dumps(citations or [], ensure_ascii=False),
        tool_calls=json.dumps(tool_calls or [], ensure_ascii=False),
    )
    db.add(msg)
    session = db.query(ChatSession).filter(ChatSession.id == session_id).first()
    if session:
        session.last_message_at = datetime.now()
    db.commit()
    db.refresh(msg)
    return msg


def process_chat_message(
    db: Session, user_id: int, session_id: Optional[int],
    user_message: str, config_name: str = "default",
) -> Dict:
    """Main entry point for chat message processing"""
    session = get_or_create_session(db, user_id, session_id)
    config = db.query(AgentConfig).filter(
        AgentConfig.name == config_name, AgentConfig.is_enabled == True
    ).first()

    if not config:
        config = AgentConfig(name="default", is_enabled=True)

    provider = None
    if config.default_provider_id:
        provider = db.query(AIProvider).filter(
            AIProvider.id == config.default_provider_id,
            AIProvider.is_enabled == True,
        ).first()
    if not provider:
        provider = db.query(AIProvider).filter(
            AIProvider.is_enabled == True
        ).first()

    # Save user message
    user_msg = add_message(db, session.id, "user", user_message)

    # Auto-title on first message
    if session.title == "新会话":
        session.title = user_message[:64]
        db.commit()

    if not provider:
        error_text = "未配置可用的 LLM 提供商，请在 AI 设置中配置并启用一个模型提供商。"
        add_message(db, session.id, "assistant", error_text, message_type="error")
        return {"session_id": session.id, "reply": error_text, "error": True}

    # Build messages
    system_prompt = config.system_prompt or DEFAULT_SYSTEM_PROMPT
    messages = [{"role": "system", "content": system_prompt}]
    messages.extend(get_message_history(db, session, config))
    messages.append({"role": "user", "content": user_message})

    # Build MCP tools manifest for LLM
    mcp_tools = get_mcp_manifest()
    openai_tools = []
    for t in mcp_tools:
        openai_tools.append({
            "type": "function",
            "function": {
                "name": t["name"],
                "description": t["description"],
                "parameters": t["input_schema"],
            },
        })

    # Call LLM
    start = time.time()
    response = call_llm(provider, messages, openai_tools if openai_tools else None)
    latency = int((time.time() - start) * 1000)

    if "error" in response:
        error_text = f"调用 LLM 失败: {response['error']}"
        add_message(db, session.id, "assistant", error_text, message_type="error")
        return {"session_id": session.id, "reply": error_text, "error": True}

    # Process response
    choice = response.get("choices", [{}])[0]
    message = choice.get("message", {})
    content = message.get("content", "") or ""
    tool_calls_raw = message.get("tool_calls")

    tool_results = []
    pending_actions = []

    if tool_calls_raw:
        for tc in tool_calls_raw:
            tool_name = tc["function"]["name"]
            try:
                arguments = json.loads(tc["function"]["arguments"])
            except (json.JSONDecodeError, KeyError):
                arguments = {}

            # Call tool
            tool_start = time.time()
            tool_result = call_mcp_tool(tool_name, arguments, db=db, user_id=user_id)
            tool_latency = int((time.time() - tool_start) * 1000)

            # Record invocation
            invocation = ToolInvocation(
                session_id=session.id,
                message_id=user_msg.id,
                tool_name=tool_name,
                status="success" if tool_result["status"] == "success" else "failed",
                latency_ms=tool_latency,
                request_payload=json.dumps(arguments, ensure_ascii=False),
                response_summary=json.dumps(tool_result, ensure_ascii=False),
            )
            db.add(invocation)
            db.commit()

            tool_results.append({
                "tool_name": tool_name,
                "result": tool_result,
                "tool_call_id": tc.get("id", ""),
            })

            # Check for pending actions
            if tool_result.get("status") == "success":
                result_data = tool_result.get("result", {})
                if isinstance(result_data, dict) and result_data.get("_pending_action"):
                    pa_data = result_data["_pending_action"]
                    pa = PendingAction(
                        session_id=session.id,
                        message_id=user_msg.id,
                        action_type=pa_data.get("action_type", "unknown"),
                        title=pa_data.get("title", ""),
                        risk_level=pa_data.get("risk_level", "low"),
                        action_payload=json.dumps(pa_data.get("payload", {}), ensure_ascii=False),
                    )
                    db.add(pa)
                    db.commit()
                    pending_actions.append({
                        "id": pa.id,
                        "title": pa.title,
                        "risk_level": pa.risk_level,
                        "action_type": pa.action_type,
                    })

        # If there were tool calls, call LLM again with results
        if tool_results:
            tool_response_messages = list(messages)
            tool_response_messages.append(message)

            for tr in tool_results:
                tool_response_messages.append({
                    "role": "tool",
                    "tool_call_id": tr["tool_call_id"],
                    "content": json.dumps(tr["result"], ensure_ascii=False),
                })

            second_response = call_llm(provider, tool_response_messages)
            if "error" not in second_response:
                second_choice = second_response.get("choices", [{}])[0]
                second_msg = second_choice.get("message", {})
                if second_msg.get("content"):
                    content = second_msg["content"]

    # Save assistant reply
    assistant_msg = add_message(
        db, session.id, "assistant", content,
        tool_calls=tool_results if tool_results else None,
    )

    session.last_message_at = datetime.now()
    db.commit()

    result = {
        "session_id": session.id,
        "reply": content,
        "session_title": session.title,
    }

    if pending_actions:
        result["pending_actions"] = pending_actions

    return result


def confirm_pending_action(db: Session, action_id: int, user_name: str) -> bool:
    action = db.query(PendingAction).filter(PendingAction.id == action_id).first()
    if not action or action.status != PendingAction.STATUS_PENDING:
        return False

    action.status = PendingAction.STATUS_CONFIRMED
    action.confirmed_by = user_name
    action.confirmed_at = datetime.now()

    # Execute the action
    try:
        payload = json.loads(action.action_payload) if action.action_payload else {}
        tool_name = f"execute_{action.action_type}"
        result = call_mcp_tool(tool_name, payload)

        action.status = PendingAction.STATUS_EXECUTED
        action.result_payload = json.dumps(result, ensure_ascii=False)
    except Exception as e:
        action.status = PendingAction.STATUS_FAILED
        action.result_payload = json.dumps({"error": str(e)}, ensure_ascii=False)

    db.commit()
    return True


def cancel_pending_action(db: Session, action_id: int) -> bool:
    action = db.query(PendingAction).filter(PendingAction.id == action_id).first()
    if not action or action.status != PendingAction.STATUS_PENDING:
        return False

    action.status = PendingAction.STATUS_CANCELED
    db.commit()
    return True
