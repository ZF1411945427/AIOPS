from dataclasses import dataclass, field
from typing import Any

import requests

from app.providers.base import BaseProvider, BaseAuthConfig, ProviderMeta, ProviderCategory


@dataclass
class GrafanaAuthConfig(BaseAuthConfig):
    endpoint: str = field(default="", metadata={"required": True, "sensitive": False, "description": "Grafana 实例地址"})
    api_token: str = field(default="", metadata={"required": True, "sensitive": True, "description": "Grafana API Token"})

    def __post_init__(self):
        self.endpoint = self.endpoint.rstrip("/") if self.endpoint else ""
        self.api_token = self.api_token or ""


class GrafanaProvider(BaseProvider):
    PROVIDER_META = ProviderMeta(
        name="grafana",
        display_name="Grafana",
        category=ProviderCategory.MONITORING,
        description="Grafana 监控集成，支持告警注解和数据查询",
        tags=["monitoring", "grafana", "dashboard", "alerting"],
        icon="grafana",
        auth_config_class=GrafanaAuthConfig,
    )

    def validate_config(self, auth_config: dict) -> GrafanaAuthConfig:
        return GrafanaAuthConfig.from_dict(auth_config)

    def _headers(self) -> dict:
        return {
            "Authorization": f"Bearer {self.auth_config.api_token}",
            "Content-Type": "application/json",
        }

    def test_connection(self) -> tuple[bool, str]:
        cfg = self.auth_config
        if not cfg.endpoint or not cfg.api_token:
            return False, "Endpoint 或 API Token 未配置"
        try:
            url = f"{cfg.endpoint}/api/org"
            resp = requests.get(url, headers=self._headers(), timeout=15)
            if resp.status_code == 200:
                org = resp.json()
                return True, f"Grafana 连接正常（组织: {org.get('name', 'N/A')}）"
            return False, f"Grafana 返回异常: {resp.status_code} {resp.text[:200]}"
        except requests.RequestException as e:
            return False, f"Grafana 连接失败: {e}"

    def _scrape_alerts(self) -> list[dict]:
        """拉取 Grafana 活跃告警（Percona/legacy + 新版 alerting），参考 KeepHQ 逻辑"""
        alerts = []
        cfg = self.auth_config
        try:
            # 1. 活跃告警列表（legacy & unified alerting）
            url = f"{cfg.endpoint}/api/prometheus/grafana/api/v1/rules"
            resp = requests.get(url, headers=self._headers(), timeout=15)
            if resp.status_code == 200:
                for group in resp.json().get("data", {}).get("groups", []):
                    for rule in group.get("rules", []):
                        if not rule.get("alerts"):
                            continue
                        cur = rule.get("state", "firing")
                        if cur not in ("firing", "alerting"):
                            continue
                        for a in rule.get("alerts", []):
                            labels = {k: v for k, v in a.get("labels", {}).items()}
                            sev = labels.get("severity", "warning")
                            alerts.append({
                                "id": a.get("fingerprint") or rule.get("name"),
                                "source": "grafana",
                                "name": rule.get("name"),
                                "message": a.get("annotations", {}).get("summary", rule.get("name", "")),
                                "status": "firing",
                                "severity": sev,
                                "labels": labels,
                                "timestamp": a.get("activeAt"),
                                "url": f"{cfg.endpoint}/alerting",
                            })
            # 2. 备用: 注解类型告警
            if resp.status_code != 200:
                ann_url = f"{cfg.endpoint}/api/annotations?type=alert"
                aresp = requests.get(ann_url, headers=self._headers(), timeout=15)
                if aresp.status_code == 200:
                    for ann in aresp.json() or []:
                        alerts.append({
                            "id": str(ann.get("id")),
                            "source": "grafana",
                            "name": ann.get("text", ""),
                            "message": ann.get("text", ""),
                            "status": "firing",
                            "severity": "warning",
                            "timestamp": ann.get("time"),
                            "url": f"{cfg.endpoint}/dashboard",
                        })
        except requests.RequestException as e:
            alerts.append({"source": "grafana", "error": f"拉取告警异常: {e}"})
        return alerts

    def scrape(self, db=None) -> list[dict]:
        return self._scrape_alerts()

    def get_dashboards(self) -> list[dict]:
        try:
            url = f"{self.auth_config.endpoint}/api/search?type=dash-db"
            resp = requests.get(url, headers=self._headers(), timeout=15)
            return resp.json() if resp.status_code == 200 else [{"error": f"查询失败: {resp.status_code}"}]
        except requests.RequestException as e:
            return [{"error": f"Grafana 查询异常: {e}"}]

    def notify(self, alert: dict, **kwargs) -> dict:
        cfg = self.auth_config
        title = alert.get("title", "AIOps 告警")
        message = alert.get("message", alert.get("description", ""))
        severity = alert.get("severity", "info")
        tags = alert.get("tags", [])
        panel_id = kwargs.get("panel_id", 0)
        dashboard_id = kwargs.get("dashboard_id", 0)

        annotation = {
            "text": f"{title}\n{message}",
            "tags": ["aiops", f"severity:{severity}"] + ([f"{k}:{v}" for k, v in tags.items()] if isinstance(tags, dict) else tags),
        }
        if panel_id:
            annotation["panelId"] = panel_id
        if dashboard_id:
            annotation["dashboardId"] = dashboard_id

        try:
            url = f"{cfg.endpoint}/api/annotations"
            resp = requests.post(url, json=annotation, headers=self._headers(), timeout=15)
            if resp.status_code == 200:
                ann_id = resp.json().get("id", "")
                return {"success": True, "message": "Grafana 注解已创建", "annotation_id": ann_id}
            return {"success": False, "message": f"创建注解失败: {resp.status_code} {resp.text[:200]}"}
        except requests.RequestException as e:
            return {"success": False, "message": f"Grafana 通知异常: {e}"}

    def dispose(self):
        pass