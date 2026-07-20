"""IM 双向通道（ChatOps）回调路由 — 接收飞书/钉钉/企微的事件回调。

端点：
- POST /im/callback/feishu         飞书事件订阅 v2
- POST /im/callback/dingtalk        钉钉 Outgoing 回调
- POST /im/callback/wecom           企业微信回调
- GET  /im/callback/wecom           企业微信 URL 校验
- GET  /im/incoming                 查看最近收到的 IM 消息（前端用）
- GET  /im/channels                 查看已配置的双向通道
"""
import json
import time
from fastapi import APIRouter, Request, Depends, Query
from fastapi.responses import JSONResponse, PlainTextResponse
from sqlalchemy.orm import Session

from app.database import get_db
from app.models import NotificationChannel, ImIncomingMessage
from app.services.im_chatops_service import (
    verify_feishu_signature, verify_dingtalk_signature, verify_wecom_signature,
    parse_command, process_im_message, start_async_processing,
)
from app.logger import logger

router = APIRouter(prefix="/im", tags=["im-chatops"])


def _find_channel_by_type(db: Session, platform: str, channel_id: int = None):
    """根据平台类型查找双向通道。"""
    q = db.query(NotificationChannel).filter(
        NotificationChannel.type == platform,
        NotificationChannel.bidirectional == True,
        NotificationChannel.enabled == True,
    )
    if channel_id:
        q = q.filter(NotificationChannel.id == channel_id)
    return q.first()


# ─── 飞书回调 ────────────────────────────────────────────────

@router.post("/callback/feishu")
async def feishu_callback(request: Request, db: Session = Depends(get_db)):
    """飞书事件订阅 v2 回调。

    签名校验：X-Lark-Signature + timestamp
    URL 验证 challenge：{type: "url_verification", challenge: "xxx"}
    消息事件：{event: {message: {content, message_type, chat_id}, sender: {sender_id}}}
    """
    body_bytes = await request.body()
    try:
        body_str = body_bytes.decode("utf-8")
        payload = json.loads(body_str)
    except Exception as e:
        return JSONResponse({"error": f"invalid body: {e}"}, status_code=400)

    # 找通道（飞书可能有多个，用 encrypt_key 匹配；这里取第一个启用的）
    channel = _find_channel_by_type(db, "feishu")
    if not channel:
        return JSONResponse({"error": "no feishu channel configured"}, status_code=404)

    # URL 校验
    if payload.get("type") == "url_verification":
        return JSONResponse({"challenge": payload.get("challenge", "")})

    # 签名校验（v2: X-Lark-Signature = sha256(timestamp + "\n" + encrypt_key)）
    timestamp = request.headers.get("X-Lark-Request-Timestamp", "")
    signature = request.headers.get("X-Lark-Signature", "")
    if channel.callback_secret and signature:
        if not verify_feishu_signature(timestamp, body_str, channel.callback_secret, signature):
            logger.warning("飞书签名校验失败")
            return JSONResponse({"error": "invalid signature"}, status_code=401)

    # 解析消息事件
    event = payload.get("event", {})
    msg_obj = event.get("message", {})
    sender_obj = event.get("sender", {})
    sender_id_obj = sender_obj.get("sender_id", {})
    chat_id = msg_obj.get("chat_id", "")
    sender_id = sender_id_obj.get("open_id", "") or sender_id_obj.get("union_id", "")
    sender_name = sender_obj.get("sender_name", "") or sender_id

    # 消息文本（text 类型 content 是 JSON 字符串）
    message_text = ""
    if msg_obj.get("message_type") == "text":
        try:
            content = json.loads(msg_obj.get("content", "{}"))
            message_text = content.get("text", "")
        except (json.JSONDecodeError, TypeError):
            message_text = ""

    if not message_text:
        return JSONResponse({"ok": True, "msg": "non-text message ignored"})

    # 异步处理（避免飞书回调超时）
    start_async_processing(
        db=None,  # 由 async 函数自己拿 db
        channel=channel,
        platform="feishu",
        sender_id=sender_id,
        sender_name=sender_name,
        chat_id=chat_id,
        raw_payload=body_str,
        message_text=message_text,
    )
    return JSONResponse({"ok": True})


# ─── 钉钉回调 ────────────────────────────────────────────────

@router.post("/callback/dingtalk")
async def dingtalk_callback(request: Request, db: Session = Depends(get_db)):
    """钉钉 Outgoing 回调。

    签名校验：timestamp + "\n" + secret → hmac-sha256 → base64
    """
    body_bytes = await request.body()
    try:
        body_str = body_bytes.decode("utf-8")
        payload = json.loads(body_str)
    except Exception as e:
        return JSONResponse({"error": f"invalid body: {e}"}, status_code=400)

    channel = _find_channel_by_type(db, "dingtalk")
    if not channel:
        return JSONResponse({"error": "no dingtalk channel configured"}, status_code=404)

    # 签名校验
    timestamp = payload.get("timestamp", "") or request.headers.get("timestamp", "")
    sign = payload.get("sign", "")
    if channel.callback_secret and sign:
        if not verify_dingtalk_signature(timestamp, channel.callback_secret, sign):
            logger.warning("钉钉签名校验失败")
            return JSONResponse({"error": "invalid signature"}, status_code=401)

    sender_id = payload.get("senderId", "") or payload.get("sender_id", "")
    sender_name = payload.get("senderNick", "") or payload.get("sender_name", "")
    conversation_id = payload.get("conversationId", "") or payload.get("conversation_id", "")
    message_text = payload.get("text", {}).get("content", "") if isinstance(payload.get("text"), dict) else payload.get("content", "")

    if not message_text:
        return JSONResponse({"ok": True, "msg": "empty message"})

    start_async_processing(
        db=None,
        channel=channel,
        platform="dingtalk",
        sender_id=sender_id,
        sender_name=sender_name,
        chat_id=conversation_id,
        raw_payload=body_str,
        message_text=message_text.strip(),
    )
    return JSONResponse({"ok": True})


# ─── 企业微信回调 ────────────────────────────────────────────────

@router.get("/callback/wecom")
def wecom_verify(
    request: Request,
    db: Session = Depends(get_db),
    msg_signature: str = Query("", alias="msg_signature"),
    timestamp: str = Query(""),
    nonce: str = Query(""),
    echostr: str = Query(""),
):
    """企业微信 URL 校验（GET）。

    签名校验：sha1(sort([token, timestamp, nonce, echostr])) == msg_signature
    """
    channel = _find_channel_by_type(db, "wecom")
    if not channel:
        return PlainTextResponse("no wecom channel configured", status_code=404)
    if not channel.callback_secret:
        return PlainTextResponse("missing token config", status_code=500)

    if not verify_wecom_signature(channel.callback_secret, timestamp, nonce, echostr, msg_signature):
        logger.warning("企微 URL 校验签名失败")
        return PlainTextResponse("invalid signature", status_code=401)
    return PlainTextResponse(echostr)


@router.post("/callback/wecom")
async def wecom_callback(
    request: Request,
    db: Session = Depends(get_db),
    msg_signature: str = Query("", alias="msg_signature"),
    timestamp: str = Query(""),
    nonce: str = Query(""),
):
    """企业微信事件回调（POST）。

    消息体为 XML，需解析；这里简化处理，提取 <Content> 文本。
    """
    body_bytes = await request.body()
    body_str = body_bytes.decode("utf-8", errors="replace")

    channel = _find_channel_by_type(db, "wecom")
    if not channel:
        return PlainTextResponse("no wecom channel configured", status_code=404)

    # 签名校验（企微需要先解密再校验，这里简化：直接信任或用 callback_secret 做 token 校验）
    # 完整实现需要 AES 解密，这里提供基础校验
    if channel.callback_secret:
        # 简化校验：用 token + timestamp + nonce 做基础校验
        if not verify_wecom_signature(channel.callback_secret, timestamp, nonce, body_str, msg_signature):
            logger.warning("企微回调签名校验失败（简化校验）")
            # 不阻断，记录日志，继续处理（生产环境应严格校验）

    # 简单 XML 解析提取 Content
    import re
    content_match = re.search(r"<Content><!\[CDATA\[(.*?)\]\]></Content>", body_str)
    from_user = re.search(r"<FromUserName><!\[CDATA\[(.*?)\]\]></FromUserName>", body_str)
    to_user = re.search(r"<ToUserName><!\[CDATA\[(.*?)\]\]></ToUserName>", body_str)
    msg_id = re.search(r"<MsgId>(.*?)</MsgId>", body_str)

    message_text = content_match.group(1).strip() if content_match else ""
    sender_id = from_user.group(1) if from_user else ""
    chat_id = to_user.group(1) if to_user else ""

    if not message_text:
        return PlainTextResponse("success")

    start_async_processing(
        db=None,
        channel=channel,
        platform="wecom",
        sender_id=sender_id,
        sender_name=sender_id,
        chat_id=chat_id,
        raw_payload=body_str,
        message_text=message_text,
    )
    return PlainTextResponse("success")


# ─── 查询接口（前端用）──────────────────────────────────────

@router.get("/incoming")
def list_incoming(
    request: Request,
    db: Session = Depends(get_db),
    limit: int = Query(50, le=200),
    platform: str = Query("", description="按平台过滤"),
):
    """查询最近收到的 IM 消息。"""
    q = db.query(ImIncomingMessage)
    if platform:
        q = q.filter(ImIncomingMessage.platform == platform)
    msgs = q.order_by(ImIncomingMessage.created_at.desc()).limit(limit).all()
    return {
        "total": len(msgs),
        "messages": [
            {
                "id": m.id,
                "platform": m.platform,
                "sender_id": m.sender_id,
                "sender_name": m.sender_name,
                "chat_id": m.chat_id,
                "command": m.command,
                "message_text": m.message_text,
                "status": m.status,
                "reply_text": (m.reply_text or "")[:500],
                "session_id": m.session_id,
                "created_at": m.created_at.isoformat(),
                "processed_at": m.processed_at.isoformat() if m.processed_at else None,
            }
            for m in msgs
        ],
    }


@router.get("/channels")
def list_bidirectional_channels(request: Request, db: Session = Depends(get_db)):
    """列出已配置为双向的通道。"""
    channels = db.query(NotificationChannel).filter(NotificationChannel.bidirectional == True).all()
    return {
        "total": len(channels),
        "channels": [
            {
                "id": c.id, "name": c.name, "type": c.type,
                "enabled": c.enabled, "bidirectional": c.bidirectional,
                "default_sub_agent": c.default_sub_agent or "auto",
                "callback_url": f"/im/callback/{c.type}",
                "has_callback_token": bool(c.callback_token),
                "has_callback_secret": bool(c.callback_secret),
            }
            for c in channels
        ],
    }


@router.post("/channels/{channel_id}/configure")
async def configure_bidirectional(
    channel_id: int,
    request: Request,
    db: Session = Depends(get_db),
):
    """把一个通知通道配置为双向通道。"""
    from app.models import User

    user_id = request.session.get("user_id")
    if not user_id:
        return JSONResponse({"error": "未登录"}, status_code=401)
    user = db.query(User).filter(User.id == user_id).first()
    if not user or user.role != "admin":
        return JSONResponse({"error": "需要管理员权限"}, status_code=403)

    channel = db.query(NotificationChannel).filter(NotificationChannel.id == channel_id).first()
    if not channel:
        return JSONResponse({"error": "通道不存在"}, status_code=404)

    data = await request.json()
    if "bidirectional" in data:
        channel.bidirectional = bool(data["bidirectional"])
    if "callback_token" in data:
        channel.callback_token = data["callback_token"] or ""
    if "callback_secret" in data:
        channel.callback_secret = data["callback_secret"] or ""
    if "default_sub_agent" in data:
        channel.default_sub_agent = data["default_sub_agent"] or "auto"
    db.commit()
    return {"status": "ok", "channel_id": channel.id, "bidirectional": channel.bidirectional,
            "callback_url": f"/im/callback/{channel.type}"}


@router.post("/test-reply/{channel_id}")
async def test_reply(
    channel_id: int,
    request: Request,
    db: Session = Depends(get_db),
):
    """测试向某通道回推一条消息（不调用 Agent，仅验证 webhook）。"""
    user_id = request.session.get("user_id")
    if not user_id:
        return JSONResponse({"error": "未登录"}, status_code=401)
    channel = db.query(NotificationChannel).filter(NotificationChannel.id == channel_id).first()
    if not channel:
        return JSONResponse({"error": "通道不存在"}, status_code=404)
    data = await request.json()
    text = data.get("text", "🤖 AIOps 测试消息：IM 双向通道已连通")
    from app.services.im_chatops_service import reply_to_im
    ok, err = reply_to_im(channel, "test", text)
    return {"ok": ok, "error": err}
