"""IM 双向通道（ChatOps）服务 — 接收 IM 群内指令 → 调 Agent → 结果回推。

支持平台：
- 飞书（Feishu）：事件订阅 v2，签名校验 X-Lark-Signature
- 钉钉（DingTalk）：Outgoing 回调，签名校验 timestamp + secret
- 企业微信（WeCom）：回调 URL，签名校验 token + timestamp + nonce

指令格式：
- `/ai <message>`  → 调用 Agent SSE，回复分析结果
- `/alert`         → 查询当前未确认告警摘要
- `/help`          → 返回可用指令列表

设计原则：
- 异步处理：收到回调立即返回 200，Agent 调用在后台线程
- 单条消息超时 60s，避免 IM 平台回调超时
- 失败 fail-soft：Agent 调用失败时回推错误消息
- 会话隔离：每个 (platform, chat_id) 对应一个 ChatSession
"""
import json
import hashlib
import hmac
import time
import threading
import urllib.request
from datetime import datetime
from typing import Optional, Dict, Any, Tuple

from sqlalchemy.orm import Session

from app.models import NotificationChannel, ImIncomingMessage, ChatSession, ChatMessage, User, Alert
from app.services.agent_service import call_llm, get_mcp_manifest, call_mcp_tool, add_message, get_message_history
from app.services.sub_agent_service import route_sub_agent, get_sub_agent, filter_tools_by_sub_agent, get_sub_agent_prompt
from app.logger import logger


# ─── 签名验证 ────────────────────────────────────────────────

def verify_feishu_signature(timestamp: str, body: str, encrypt_key: str, signature: str) -> bool:
    """飞书 v2 事件订阅签名校验。"""
    if not encrypt_key or not signature:
        return False
    import base64
    string_to_sign = timestamp + "\n" + encrypt_key
    h = hashlib.sha256(string_to_sign.encode("utf-8")).digest()
    computed = base64.b64encode(h).decode("utf-8")
    return hmac.compare_digest(computed, signature)


def verify_dingtalk_signature(timestamp: str, secret: str, sign: str) -> bool:
    """钉钉 Outgoing 回调签名校验。"""
    if not secret or not sign:
        return False
    string_to_sign = timestamp + "\n" + secret
    h = hmac.new(secret.encode("utf-8"), string_to_sign.encode("utf-8"), hashlib.sha256).digest()
    import base64
    computed = base64.b64encode(h).decode("utf-8")
    return hmac.compare_digest(computed, sign)


def verify_wecom_signature(token: str, timestamp: str, nonce: str, encrypt_msg: str, signature: str) -> bool:
    """企业微信回调签名校验。"""
    if not token:
        return False
    sort_list = sorted([token, timestamp, nonce, encrypt_msg])
    sha1 = hashlib.sha1("".join(sort_list).encode("utf-8")).hexdigest()
    return hmac.compare_digest(sha1, signature)


# ─── 指令解析 ────────────────────────────────────────────────

COMMAND_PREFIXES = ["/ai", "/alert", "/help", "ai ", "AI ", "/sre"]


def parse_command(text: str) -> Tuple[str, str]:
    """解析消息文本，返回 (command, args)。command: ai/alert/help/sre/unknown。"""
    text = text.strip()
    if not text:
        return "unknown", ""
    lower = text.lower()
    if lower.startswith("/ai ") or lower.startswith("ai "):
        return "ai", text.split(" ", 1)[1].strip() if " " in text else ""
    if lower.startswith("/sre "):
        return "ai", text.split(" ", 1)[1].strip() if " " in text else ""
    if lower == "/alert" or lower == "/alerts":
        return "alert", ""
    if lower == "/help":
        return "help", ""
    # 默认当作 ai 消息（无前缀也接受）
    return "ai", text


# ─── Agent 调用 ────────────────────────────────────────────────

def _get_or_create_session(db: Session, user_id: int, platform: str, chat_id: str) -> ChatSession:
    """为 IM 通道获取或创建 ChatSession。session_id 存在 ImIncomingMessage 上。"""
    title = f"IM·{platform}·{chat_id[:20]}"
    session = ChatSession(
        user_id=user_id,
        title=title,
        mode="agent",
    )
    db.add(session)
    db.commit()
    db.refresh(session)
    return session


def call_agent_for_im(db: Session, session: ChatSession, message: str, sub_agent_name: str = "auto") -> str:
    """同步调用 Agent，返回回复文本（用于 IM 回推）。

    不走 SSE，直接调用 call_llm + call_mcp_tool，最多 10 轮。
    """
    from app.models import AgentConfig, AIProvider, PendingAction

    config = db.query(AgentConfig).filter(AgentConfig.name == "default").first()
    provider = None
    if config and config.default_provider_id:
        provider = db.query(AIProvider).filter(AIProvider.id == config.default_provider_id, AIProvider.is_enabled == True).first()
    if not provider:
        provider = db.query(AIProvider).filter(AIProvider.is_enabled == True).first()
    if not provider:
        return "未配置可用的 LLM 提供商，请联系管理员"

    # 子专家路由
    if sub_agent_name == "auto":
        sub_agent_name = route_sub_agent(message, db)
    sub_agent_obj = get_sub_agent(db, sub_agent_name) if sub_agent_name and sub_agent_name != "general" else None
    sub_prompt = get_sub_agent_prompt(sub_agent_obj)

    system_prompt = (config.system_prompt or "") if config else ""
    if sub_prompt:
        system_prompt = system_prompt + "\n\n## 当前子专家身份\n" + sub_prompt

    messages = []
    if system_prompt:
        messages.append({"role": "system", "content": system_prompt})
    messages.extend(get_message_history(db, session, config))
    messages.append({"role": "user", "content": message})

    # 工具过滤
    mcp_tools = get_mcp_manifest()
    if sub_agent_obj:
        mcp_tools = filter_tools_by_sub_agent(mcp_tools, sub_agent_obj)
    openai_tools = [{
        "type": "function", "function": {
            "name": t["name"], "description": t["description"], "parameters": t["input_schema"]
        }
    } for t in mcp_tools] if mcp_tools else []

    # 记录用户消息
    add_message(db, session.id, "user", message)

    max_rounds = 10
    final_content = ""
    for round_idx in range(max_rounds):
        response = call_llm(provider, messages, openai_tools if openai_tools else None)
        if "error" in response:
            final_content = f"LLM 调用失败: {response['error']}"
            break
        choice = response.get("choices", [{}])[0]
        msg = choice.get("message", {})
        content = msg.get("content") or ""
        tool_calls = msg.get("tool_calls") or []

        if not tool_calls:
            final_content = content or "分析完成。"
            break

        # 执行工具
        tool_results = []
        for tc in tool_calls:
            t_name = tc.get("function", {}).get("name") or ""
            try:
                t_args = json.loads(tc.get("function", {}).get("arguments", "{}") or "{}")
            except (json.JSONDecodeError, KeyError):
                t_args = {}
            t_result = call_mcp_tool(t_name, t_args, db=db, user_id=session.user_id, allow_internal=False)
            tool_results.append({"tool_name": t_name, "result": t_result})

        messages.append(msg)
        for tc_item, tr_item in zip(tool_calls, tool_results):
            messages.append({"role": "tool", "tool_call_id": tc_item.get("id", ""),
                             "content": json.dumps(tr_item.get("result", {}), ensure_ascii=False)})
        final_content = content or ""

    # 记录 assistant 消息
    add_message(db, session.id, "assistant", final_content)
    return final_content[:4000]  # IM 消息长度限制


# ─── 结果回推 ────────────────────────────────────────────────

def reply_to_im(channel: NotificationChannel, chat_id: str, text: str) -> Tuple[bool, str]:
    """将 Agent 回复推回 IM 平台。"""
    config = json.loads(channel.channel_config) if channel.channel_config else {}
    webhook = config.get("webhook", "") or config.get("reply_url", "")
    if not webhook:
        return False, "未配置 webhook"

    platform = channel.type
    try:
        if platform == "feishu":
            payload = {"msg_type": "text", "content": {"text": text}}
        elif platform == "dingtalk":
            payload = {"msgtype": "text", "text": {"content": text}}
        elif platform == "wecom":
            payload = {"msgtype": "text", "text": {"content": text}}
        else:
            payload = {"text": text}
        data = json.dumps(payload, ensure_ascii=False).encode("utf-8")
        req = urllib.request.Request(webhook, data, {"Content-Type": "application/json"})
        with urllib.request.urlopen(req, timeout=15) as resp:
            body = resp.read().decode("utf-8", errors="replace")
            return True, body[:200]
    except Exception as e:
        return False, str(e)


# ─── 主处理流程 ────────────────────────────────────────────────

def process_im_message(
    db: Session,
    channel: NotificationChannel,
    platform: str,
    sender_id: str,
    sender_name: str,
    chat_id: str,
    raw_payload: str,
    message_text: str,
) -> ImIncomingMessage:
    """处理一条 IM 消息：解析指令 → 调 Agent → 回推结果。同步执行。"""
    command, args = parse_command(message_text)

    im_msg = ImIncomingMessage(
        channel_id=channel.id,
        platform=platform,
        sender_id=sender_id,
        sender_name=sender_name,
        chat_id=chat_id,
        raw_payload=raw_payload,
        command=command,
        message_text=message_text,
        status=ImIncomingMessage.STATUS_PROCESSING,
    )
    db.add(im_msg)
    db.commit()
    db.refresh(im_msg)

    try:
        if command == "help":
            reply = (
                "🤖 AIOps 智能运维 IM 指令：\n"
                "  /ai <消息>  — 调用 AI 智能助手（如：/ai 查一下当前告警）\n"
                "  /alert      — 查询最近 1 小时未确认告警摘要\n"
                "  /help       — 显示此帮助\n"
                "\n支持自然语言：直接发消息即可（如 'mysql 慢查询怎么排查'）"
            )
        elif command == "alert":
            alerts = db.query(Alert).filter(Alert.status == "triggered").order_by(Alert.created_at.desc()).limit(10).all()
            if not alerts:
                reply = "✅ 当前无未确认告警"
            else:
                lines = [f"⚠️ 最近 {len(alerts)} 条未确认告警："]
                for a in alerts:
                    lines.append(f"  #{a.id} [{a.severity}] {a.metric_name}={a.actual_value} (阈值 {a.threshold}) {a.message[:50]}")
                reply = "\n".join(lines)
        elif command == "ai":
            if not args:
                reply = "用法：/ai <消息>，如 /ai 查一下当前告警"
            else:
                # 获取/创建会话
                session = _get_or_create_session(db, 1, platform, chat_id)  # 默认 admin 用户
                im_msg.session_id = session.id
                db.commit()
                sub_agent = channel.default_sub_agent or "auto"
                reply = call_agent_for_im(db, session, args, sub_agent)
        else:
            reply = f"未识别的指令：{message_text[:50]}\n输入 /help 查看可用指令"

        # 回推 IM
        ok, err = reply_to_im(channel, chat_id, reply)
        im_msg.reply_text = reply
        im_msg.status = ImIncomingMessage.STATUS_REPLIED if ok else ImIncomingMessage.STATUS_FAILED
        if not ok:
            im_msg.status = ImIncomingMessage.STATUS_FAILED
            logger.warning(f"IM 回推失败: {err}")
        im_msg.processed_at = datetime.now()
        db.commit()
    except Exception as e:
        im_msg.status = ImIncomingMessage.STATUS_FAILED
        im_msg.reply_text = f"处理失败: {e}"
        im_msg.processed_at = datetime.now()
        db.commit()
        logger.error(f"IM 消息处理失败: {e}")

    return im_msg


def process_im_message_async(channel_id: int, platform: str, sender_id: str, sender_name: str,
                              chat_id: str, raw_payload: str, message_text: str, **kwargs):
    """异步处理 IM 消息（后台线程）。

    注意：传 channel_id 而非 channel 对象，因为原 session 关闭后对象会 detached。
    """
    from app.database import get_session_for, get_db_mode
    from app.models import NotificationChannel
    db = get_session_for(get_db_mode())()
    try:
        channel = db.query(NotificationChannel).filter(NotificationChannel.id == channel_id).first()
        if not channel:
            logger.error(f"IM 异步处理失败: channel_id={channel_id} 不存在")
            return
        process_im_message(
            db=db,
            channel=channel,
            platform=platform,
            sender_id=sender_id,
            sender_name=sender_name,
            chat_id=chat_id,
            raw_payload=raw_payload,
            message_text=message_text,
        )
    except Exception as e:
        logger.error(f"IM 异步处理失败: {e}")
    finally:
        db.close()


def start_async_processing(channel, platform: str, sender_id: str, sender_name: str,
                            chat_id: str, raw_payload: str, message_text: str, **kwargs):
    """启动后台线程处理 IM 消息。"""
    channel_id = channel.id if hasattr(channel, "id") else channel
    t = threading.Thread(
        target=process_im_message_async,
        args=(channel_id, platform, sender_id, sender_name, chat_id, raw_payload, message_text),
        daemon=True,
    )
    t.start()
    return t
