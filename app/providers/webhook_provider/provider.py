import json
from dataclasses import dataclass, field
from typing import Any

import requests

from app.providers.base import BaseProvider, BaseAuthConfig, ProviderMeta, ProviderCategory


@dataclass
class WebhookAuthConfig(BaseAuthConfig):
    webhook_url: str = field(default="", metadata={"required": True, "sensitive": False, "description": "Webhook URL"})
    method: str = field(default="POST", metadata={"required": False, "sensitive": False, "description": "请求方法"})
    headers: dict = field(default_factory=dict, metadata={"required": False, "sensitive": False, "description": "自定义请求头"})
    auth_type: str = field(default="", metadata={"required": False, "sensitive": False, "description": "认证类型（bearer/basic）"})
    auth_token: str = field(default="", metadata={"required": False, "sensitive": True, "description": "认证 Token"})

    def __post_init__(self):
        self.webhook_url = self.webhook_url or ""
        self.method = self.method.upper() if self.method else "POST"
        self.headers = self.headers or {}
        self.auth_type = self.auth_type or ""
        self.auth_token = self.auth_token or ""


class WebhookProvider(BaseProvider):
    PROVIDER_META = ProviderMeta(
        name="webhook",
        display_name="Webhook",
        category=ProviderCategory.NOTIFICATION,
        description="自定义 Webhook 通知集成，支持任意 HTTP 端点",
        tags=["notification", "webhook", "http", "integration"],
        icon="webhook",
        auth_config_class=WebhookAuthConfig,
    )

    def validate_config(self, auth_config: dict) -> WebhookAuthConfig:
        return WebhookAuthConfig.from_dict(auth_config)

    def _build_request_kwargs(self, payload: dict) -> dict:
        cfg = self.auth_config
        headers = dict(cfg.headers)
        kwargs = {"url": cfg.webhook_url, "timeout": 15, "headers": headers}

        if cfg.auth_type == "bearer" and cfg.auth_token:
            headers["Authorization"] = f"Bearer {cfg.auth_token}"
        elif cfg.auth_type == "basic" and cfg.auth_token:
            headers["Authorization"] = f"Basic {cfg.auth_token}"

        method = cfg.method
        if method in ("POST", "PUT", "PATCH"):
            kwargs["json"] = payload
            if "Content-Type" not in {k.lower() for k in headers}:
                headers["Content-Type"] = "application/json"
        elif method == "GET":
            kwargs["params"] = payload
        else:
            kwargs["data"] = json.dumps(payload)

        return kwargs

    def test_connection(self) -> tuple[bool, str]:
        cfg = self.auth_config
        if not cfg.webhook_url:
            return False, "Webhook URL 未配置"
        try:
            kwargs = self._build_request_kwargs({"test": True, "message": "AIOps 连接测试"})
            method = cfg.method
            resp = requests.request(method, **kwargs)
            if 200 <= resp.status_code < 300:
                return True, f"Webhook 连接正常（{resp.status_code}）"
            return False, f"Webhook 返回异常: {resp.status_code} {resp.text[:200]}"
        except requests.RequestException as e:
            return False, f"Webhook 连接失败: {e}"

    def notify(self, alert: dict, **kwargs) -> dict:
        cfg = self.auth_config
        if not cfg.webhook_url:
            return {"success": False, "message": "Webhook URL 未配置"}

        payload = {
            "event": "alert",
            "source": "aiops",
            "title": alert.get("title", "无标题"),
            "message": alert.get("message", alert.get("description", "")),
            "severity": alert.get("severity", "info"),
            "timestamp": alert.get("timestamp", ""),
            "tags": alert.get("tags", {}),
            "metadata": alert.get("metadata", {}),
        }

        try:
            kwargs = self._build_request_kwargs(payload)
            method = cfg.method
            resp = requests.request(method, **kwargs)
            if 200 <= resp.status_code < 300:
                return {"success": True, "message": f"Webhook 通知已发送（{resp.status_code}）"}
            return {"success": False, "message": f"发送失败: {resp.status_code} {resp.text[:200]}"}
        except requests.RequestException as e:
            return {"success": False, "message": f"Webhook 通知异常: {e}"}

    def dispose(self):
        pass