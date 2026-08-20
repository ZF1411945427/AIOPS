from dataclasses import dataclass, field
from typing import Any

import requests

from app.providers.base import BaseProvider, BaseAuthConfig, ProviderMeta, ProviderCategory


@dataclass
class PagerDutyAuthConfig(BaseAuthConfig):
    api_key: str = field(default="", metadata={"required": True, "sensitive": True, "description": "PagerDuty API Key"})
    routing_key: str = field(default="", metadata={"required": True, "sensitive": True, "description": "Events API v2 Routing Key"})
    service_id: str = field(default="", metadata={"required": False, "sensitive": False, "description": "服务 ID"})

    def __post_init__(self):
        self.api_key = self.api_key or ""
        self.routing_key = self.routing_key or ""
        self.service_id = self.service_id or ""


class PagerDutyProvider(BaseProvider):
    PROVIDER_META = ProviderMeta(
        name="pagerduty",
        display_name="PagerDuty",
        category=ProviderCategory.INCIDENT_MANAGEMENT,
        description="PagerDuty 事件管理集成，支持告警通知和事件触发",
        tags=["incident", "pagerduty", "alerting", "oncall"],
        icon="pagerduty",
        auth_config_class=PagerDutyAuthConfig,
    )

    def validate_config(self, auth_config: dict) -> PagerDutyAuthConfig:
        return PagerDutyAuthConfig.from_dict(auth_config)

    def test_connection(self) -> tuple[bool, str]:
        cfg = self.auth_config
        if not cfg.api_key:
            return False, "API Key 未配置"
        try:
            headers = {
                "Authorization": f"Token token={cfg.api_key}",
                "Accept": "application/vnd.pagerduty+json;version=2",
            }
            resp = requests.get("https://api.pagerduty.com/services", headers=headers, timeout=15)
            if resp.status_code == 200:
                services = resp.json().get("services", [])
                return True, f"PagerDuty 连接正常，共 {len(services)} 个服务"
            return False, f"PagerDuty 返回异常: {resp.status_code} {resp.text[:200]}"
        except requests.RequestException as e:
            return False, f"PagerDuty 连接失败: {e}"

    def notify(self, alert: dict, **kwargs) -> dict:
        cfg = self.auth_config
        routing_key = cfg.routing_key
        if not routing_key:
            return {"success": False, "message": "Routing Key 未配置"}

        title = alert.get("title", "AIOps 告警")
        message = alert.get("message", alert.get("description", ""))
        severity = alert.get("severity", "info")
        pd_severity = severity if severity in ("critical", "warning", "error", "info") else "info"
        source = alert.get("source", "aiops")
        alert_key = alert.get("alert_key", f"aiops-{hash(str(alert))}")

        payload = {
            "routing_key": routing_key,
            "event_action": "trigger",
            "dedup_key": alert_key,
            "payload": {
                "summary": title[:1024],
                "source": source,
                "severity": pd_severity,
                "custom_details": {"message": message, "alert": alert},
            },
        }

        try:
            resp = requests.post(
                "https://events.pagerduty.com/v2/enqueue",
                json=payload,
                timeout=15,
                headers={"Content-Type": "application/json"},
            )
            if resp.status_code == 202:
                data = resp.json()
                return {"success": True, "message": "PagerDuty 事件已触发", "dedup_key": data.get("dedup_key", alert_key)}
            return {"success": False, "message": f"触发失败: {resp.status_code} {resp.text[:200]}"}
        except requests.RequestException as e:
            return {"success": False, "message": f"PagerDuty 通知异常: {e}"}

    def dispose(self):
        pass