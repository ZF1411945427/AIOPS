"""域模型: notify (H2 models 拆分) - 各域模型, 无跨文件循环引用(全字符串FK)。"""

import json

from datetime import datetime, timezone

from sqlalchemy import Column, Integer, String, Float, Boolean, DateTime, ForeignKey, Text, UniqueConstraint

from app.database import Base


class NotificationChannel(Base):
    __tablename__ = "notification_channels"

    id = Column(Integer, primary_key=True, index=True)
    name = Column(String(64), nullable=False)
    type = Column(String(32), nullable=False)
    channel_config = Column(Text, default="")
    enabled = Column(Boolean, default=True)
    created_at = Column(DateTime, default=lambda: datetime.now())
    # P1-2: IM 双向通道字段
    bidirectional = Column(Boolean, default=False)        # 是否双向（支持指令回传）
    callback_token = Column(String(128), default="")      # IM 平台回调校验 token / Verify Token / Signing Key
    callback_secret = Column(String(128), default="")     # 飞书 Encrypt Key / 钉钉 Secret / 企微 Token
    default_sub_agent = Column(String(64), default="auto")  # 该通道默认使用的子专家


class ImIncomingMessage(Base):
    """IM 双向通道收到的指令消息（ChatOps 闭环）。"""
    __tablename__ = "im_incoming_messages"

    STATUS_PENDING = "pending"
    STATUS_PROCESSING = "processing"
    STATUS_REPLIED = "replied"
    STATUS_FAILED = "failed"

    id = Column(Integer, primary_key=True, index=True)
    channel_id = Column(Integer, ForeignKey("notification_channels.id"), nullable=True)
    platform = Column(String(32), nullable=False)         # feishu / dingtalk / wecom
    sender_id = Column(String(128), default="")           # 发送者 ID（open_id / userid / userid）
    sender_name = Column(String(128), default="")         # 发送者名称
    chat_id = Column(String(128), default="")             # 群/会话 ID
    raw_payload = Column(Text, default="")                # 原始回调 payload
    command = Column(String(64), default="")              # 指令名：ai / alert / help
    message_text = Column(Text, default="")               # 消息文本
    status = Column(String(32), default=STATUS_PENDING)
    reply_text = Column(Text, default="")                 # Agent 回复内容
    session_id = Column(Integer, nullable=True)           # 关联的 ChatSession.id
    created_at = Column(DateTime, default=lambda: datetime.now())
    processed_at = Column(DateTime, nullable=True)


class NotificationLog(Base):
    __tablename__ = "notification_logs"

    id = Column(Integer, primary_key=True, index=True)
    alert_id = Column(Integer, ForeignKey("alerts.id"), nullable=True)
    channel_id = Column(Integer, ForeignKey("notification_channels.id"), nullable=True)
    channel_type = Column(String(32), nullable=False)
    recipient = Column(String(256), default="")
    title = Column(String(256), default="")
    notification_content = Column(Text, default="")
    is_success = Column(Boolean, default=False)
    error_message = Column(Text, default="")
    created_at = Column(DateTime, default=lambda: datetime.now())


class NotificationTemplate(Base):
    __tablename__ = "notification_templates"

    id = Column(Integer, primary_key=True, index=True)
    name = Column(String(128), nullable=False)
    channel_type = Column(String(32), default="")
    title_template = Column(Text, default="")
    body_template = Column(Text, default="")
    severity = Column(String(32), default="warning")
    enabled = Column(Boolean, default=True)
    created_at = Column(DateTime, default=lambda: datetime.now())
