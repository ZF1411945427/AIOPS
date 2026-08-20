from dataclasses import dataclass, field
from typing import Any

import requests

from app.providers.base import BaseProvider, BaseAuthConfig, ProviderMeta, ProviderCategory


@dataclass
class DatadogAuthConfig(BaseAuthConfig):
    api_key: str = field(default="", metadata={"required": True, "sensitive": True, "description": "Datadog API Key"})
    app_key: str = field(default="", metadata={"required": True, "sensitive": True, "description": "Datadog Application Key"})
    site: str = field(default="datadoghq.com", metadata={"required": False, "sensitive": False, "description": "Datadog 站点"})

    def __post_init__(self):
        self.api_key = self.api_key or ""
        self.app_key = self.app_key or ""
        self.site = self.site or "datadoghq.com"


class DatadogProvider(BaseProvider):
    PROVIDER_META = ProviderMeta(
        name="datadog",
        display_name="Datadog",
        category=ProviderCategory.MONITORING,
        description="Datadog 监控数据集成，支持指标查询和事件监控",
        tags=["monitoring", "datadog", "metrics", "apm"],
        icon="datadog",
        auth_config_class=DatadogAuthConfig,
    )

    def validate_config(self, auth_config: dict) -> DatadogAuthConfig:
        return DatadogAuthConfig.from_dict(auth_config)

    def _headers(self) -> dict:
        cfg = self.auth_config
        return {
            "DD-API-KEY": cfg.api_key,
            "DD-APPLICATION-KEY": cfg.app_key,
            "Content-Type": "application/json",
        }

    def _api_base(self) -> str:
        return f"https://api.{self.auth_config.site}"

    def test_connection(self) -> tuple[bool, str]:
        cfg = self.auth_config
        if not cfg.api_key or not cfg.app_key:
            return False, "API Key 或 Application Key 未配置"
        try:
            url = f"{self._api_base()}/api/v1/validate"
            resp = requests.get(url, headers=self._headers(), timeout=15)
            if resp.status_code == 200:
                return True, "Datadog 连接正常"
            return False, f"Datadog 验证失败: {resp.status_code} {resp.text[:200]}"
        except requests.RequestException as e:
            return False, f"Datadog 连接失败: {e}"

    def query(self, **kwargs) -> list[dict]:
        query_str = kwargs.get("query", "")
        if not query_str:
            return []
        try:
            url = f"{self._api_base()}/api/v1/query"
            params = {"query": query_str, "from": kwargs.get("from_ts", 0), "to": kwargs.get("to_ts", 0)}
            resp = requests.get(url, params=params, headers=self._headers(), timeout=30)
            if resp.status_code == 200:
                return resp.json().get("series", [])
            return [{"error": f"查询失败: {resp.status_code} {resp.text[:200]}"}]
        except requests.RequestException as e:
            return [{"error": f"Datadog 查询异常: {e}"}]

    def _scrape_alerts(self) -> list[dict]:
        """拉取 Datadog 活动监控告警（monitors + events），参考 KeepHQ 逻辑"""
        alerts = []
        try:
            monitors_url = f"{self._api_base()}/api/v1/monitor"
            mresp = requests.get(
                monitors_url,
                params={"group_states": "alert,warn", "with_downtimes": True},
                headers=self._headers(),
                timeout=30,
            )
            monitors = mresp.json() if mresp.status_code == 200 else []
            for m in monitors or []:
                status = m.get("overall_state", "")
                if status not in ("Alert", "Warn"):
                    continue
                priority = m.get("priority")
                sev_map = {1: "critical", 2: "high", 3: "warning", 4: "info", 5: "info"}
                alerts.append({
                    "id": str(m.get("id")),
                    "source": "datadog",
                    "name": m.get("name"),
                    "message": m.get("message", ""),
                    "status": "firing",
                    "severity": sev_map.get((priority or 4), "info"),
                    "monitor_id": str(m.get("id")),
                    "groups": m.get("query", ""),
                    "tags": (m.get("tags") or []),
                    "url": f"{self._api_base()}/monitors/{m.get('id')}",
                    "timestamp": m.get("created"),
                })
        except requests.RequestException as e:
            alerts.append({"source": "datadog", "error": f"拉取告警异常: {e}"})
        return alerts

    def scrape(self, db=None) -> list[dict]:
        return self._scrape_alerts()

    def get_monitors(self) -> list[dict]:
        try:
            url = f"{self._api_base()}/api/v1/monitor"
            resp = requests.get(url, headers=self._headers(), timeout=30)
            return resp.json() if resp.status_code == 200 else [{"error": f"查询失败: {resp.status_code}"}]
        except requests.RequestException as e:
            return [{"error": f"Datadog 查询异常: {e}"}]

    def notify(self, alert: dict, **kwargs) -> dict:
        title = alert.get("title", "AIOps 告警")
        message = alert.get("message", alert.get("description", ""))
        severity = alert.get("severity", "info")
        alert_type = severity if severity in ("error", "warning", "info", "success") else "info"

        event_data = {
            "title": title,
            "text": message,
            "alert_type": alert_type,
            "source_tag_name": "aiops",
            "tags": ["source:aiops", f"severity:{severity}"],
        }

        try:
            url = f"{self._api_base()}/api/v1/events"
            resp = requests.post(url, json=event_data, headers=self._headers(), timeout=15)
            if resp.status_code == 202:
                event_id = resp.json().get("event", {}).get("id", "")
                return {"success": True, "message": "Datadog 事件已发送", "event_id": str(event_id)}
            return {"success": False, "message": f"发送失败: {resp.status_code} {resp.text[:200]}"}
        except requests.RequestException as e:
            return {"success": False, "message": f"Datadog 通知异常: {e}"}

    def dispose(self):
        pass