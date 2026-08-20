from dataclasses import dataclass, field
from typing import Any

import requests

from app.providers.base import BaseProvider, BaseAuthConfig, ProviderMeta, ProviderCategory


@dataclass
class SlackAuthConfig(BaseAuthConfig):
    webhook_url: str = field(default="", metadata={"required": True, "sensitive": True, "description": "Slack Webhook URL"})
    bot_token: str = field(default="", metadata={"required": False, "sensitive": True, "description": "Slack Bot Token"})
    channel: str = field(default="", metadata={"required": True, "sensitive": False, "description": "目标频道"})

    def __post_init__(self):
        self.webhook_url = self.webhook_url or ""
        self.bot_token = self.bot_token or ""
        self.channel = self.channel or ""


class SlackProvider(BaseProvider):
    PROVIDER_META = ProviderMeta(
        name="slack",
        display_name="Slack",
        category=ProviderCategory.NOTIFICATION,
        description="Slack 通知集成，通过 Webhook 或 Bot Token 发送消息",
        tags=["notification", "slack", "messaging"],
        icon="slack",
        auth_config_class=SlackAuthConfig,
    )

    def validate_config(self, auth_config: dict) -> SlackAuthConfig:
        return SlackAuthConfig.from_dict(auth_config)

    def test_connection(self) -> tuple[bool, str]:
        cfg = self.auth_config
        if not cfg.webhook_url:
            return False, "Webhook URL 未配置"
        try:
            resp = requests.post(
                cfg.webhook_url,
                json={"text": "Slack 连接测试 - 来自 AIOps"},
                timeout=15,
                headers={"Content-Type": "application/json"},
            )
            if resp.status_code == 200:
                return True, "Slack 连接正常"
            return False, f"Slack 返回异常状态码: {resp.status_code}, {resp.text[:200]}"
        except requests.RequestException as e:
            return False, f"Slack 连接失败: {e}"

    def notify(self, alert: dict, **kwargs) -> dict:
        cfg = self.auth_config
        title = alert.get("title", "无标题")
        message = alert.get("message", alert.get("description", ""))
        severity = alert.get("severity", "info")
        color_map = {"critical": "danger", "warning": "warning", "info": "good"}
        color = color_map.get(severity, "good")

        blocks = [
            {"type": "header", "text": {"type": "plain_text", "text": f"⚠️ {title}"}},
            {"type": "section", "text": {"type": "mrkdwn", "text": message}},
            {"type": "context", "elements": [{"type": "mrkdwn", "text": f"级别: *{severity}* | 来源: AIOps"}]},
        ]

        payload = {"text": title, "blocks": blocks}
        if cfg.channel:
            payload["channel"] = cfg.channel

        try:
            resp = requests.post(
                cfg.webhook_url,
                json=payload,
                timeout=15,
                headers={"Content-Type": "application/json"},
            )
            if resp.status_code == 200:
                return {"success": True, "message": "Slack 通知已发送"}
            return {"success": False, "message": f"发送失败: {resp.status_code} {resp.text[:200]}"}
        except requests.RequestException as e:
            return {"success": False, "message": f"Slack 通知异常: {e}"}

    def dispose(self):
        pass