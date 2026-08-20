from dataclasses import dataclass, field
from typing import Any

import requests

from app.providers.base import BaseProvider, BaseAuthConfig, ProviderMeta, ProviderCategory


@dataclass
class DynatraceAuthConfig(BaseAuthConfig):
    environment_id: str = field(default="", metadata={"required": True, "sensitive": False, "description": "Dynatrace Environment ID"})
    api_token: str = field(default="", metadata={"required": True, "sensitive": True, "description": "Dynatrace API Token"})

    def __post_init__(self):
        self.environment_id = self.environment_id or ""
        self.api_token = self.api_token or ""


class DynatraceProvider(BaseProvider):
    PROVIDER_META = ProviderMeta(
        name="dynatrace",
        display_name="Dynatrace",
        category=ProviderCategory.MONITORING,
        description="Dynatrace 可观测性平台集成，拉取问题(Problems)事件",
        tags=["monitoring", "dynatrace", "apm", "problems"],
        icon="dynatrace",
        auth_config_class=DynatraceAuthConfig,
    )

    _SEVERITIES_MAP = {
        "AVAILABILITY": "high",
        "ERROR": "critical",
        "PERFORMANCE": "warning",
        "RESOURCE": "warning",
        "CUSTOM": "info",
    }

    def validate_config(self, auth_config: dict) -> DynatraceAuthConfig:
        return DynatraceAuthConfig.from_dict(auth_config)

    def _base_url(self) -> str:
        return f"https://{self.auth_config.environment_id}.live.dynatrace.com"

    def _headers(self) -> dict:
        return {"Authorization": f"Api-Token {self.auth_config.api_token}"}

    def test_connection(self) -> tuple[bool, str]:
        cfg = self.auth_config
        if not cfg.environment_id or not cfg.api_token:
            return False, "Environment ID 或 API Token 未配置"
        try:
            url = f"{self._base_url()}/api/v2/problems"
            resp = requests.get(url, headers=self._headers(), timeout=15)
            if resp.status_code == 200:
                problems = resp.json().get("problems", [])
                return True, f"Dynatrace 连接正常（{len(problems)} 个问题）"
            if resp.status_code == 401:
                return False, "Dynatrace 鉴权失败（401）：API Token 无效或缺少权限"
            if resp.status_code == 404:
                return False, "Dynatrace 环境不存在（404）：请检查 Environment ID"
            return False, f"Dynatrace 返回异常: {resp.status_code} {resp.text[:200]}"
        except requests.RequestException as e:
            return False, f"Dynatrace 连接失败: {e}"

    def _scrape_problems(self) -> list[dict]:
        alerts = []
        try:
            url = f"{self._base_url()}/api/v2/problems"
            resp = requests.get(url, headers=self._headers(), timeout=30)
            if resp.status_code == 200:
                for p in resp.json().get("problems", []):
                    status = p.get("status", "OPEN")
                    if status.upper() != "OPEN":
                        continue
                    title = p.get("title", "")
                    impact = p.get("impactLevel", "CUSTOM")
                    severity = self._SEVERITIES_MAP.get(impact.upper(), "info")
                    alerts.append({
                        "id": str(p.get("problemId", "")),
                        "source": "dynatrace",
                        "name": title,
                        "message": p.get("problemDetails", ""),
                        "status": "firing",
                        "severity": severity,
                        "impact": impact,
                        "tags": p.get("tags", []),
                        "url": p.get("problemUrl", ""),
                        "timestamp": p.get("startTime"),
                    })
            else:
                alerts.append({"source": "dynatrace", "error": f"拉取问题失败: {resp.status_code} {resp.text[:200]}"})
        except requests.RequestException as e:
            alerts.append({"source": "dynatrace", "error": f"拉取问题异常: {e}"})
        return alerts

    def scrape(self, db=None) -> list[dict]:
        return self._scrape_problems()

    def query(self, **kwargs) -> list[dict]:
        problem_id = kwargs.get("problem_id", "")
        if not problem_id:
            return self._scrape_problems()
        try:
            url = f"{self._base_url()}/api/v2/problems/{problem_id}"
            resp = requests.get(url, headers=self._headers(), timeout=15)
            return resp.json() if resp.status_code == 200 else [{"error": f"查询失败: {resp.status_code}"}]
        except requests.RequestException as e:
            return [{"error": f"Dynatrace 查询异常: {e}"}]

    def dispose(self):
        pass