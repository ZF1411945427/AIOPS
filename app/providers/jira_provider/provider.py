from base64 import b64encode
from dataclasses import dataclass, field
from typing import Any

import requests

from app.providers.base import BaseProvider, BaseAuthConfig, ProviderMeta, ProviderCategory


@dataclass
class JiraAuthConfig(BaseAuthConfig):
    endpoint: str = field(default="", metadata={"required": True, "sensitive": False, "description": "Jira 实例地址"})
    username: str = field(default="", metadata={"required": True, "sensitive": False, "description": "Jira 用户名"})
    api_token: str = field(default="", metadata={"required": True, "sensitive": True, "description": "Jira API Token"})
    project_key: str = field(default="", metadata={"required": True, "sensitive": False, "description": "项目 Key"})

    def __post_init__(self):
        self.endpoint = self.endpoint.rstrip("/") if self.endpoint else ""
        self.username = self.username or ""
        self.api_token = self.api_token or ""
        self.project_key = self.project_key or ""


class JiraProvider(BaseProvider):
    PROVIDER_META = ProviderMeta(
        name="jira",
        display_name="Jira",
        category=ProviderCategory.TICKETING,
        description="Jira 工单系统集成，支持从告警自动创建 Issue",
        tags=["ticketing", "jira", "issue", "workflow"],
        icon="jira",
        auth_config_class=JiraAuthConfig,
    )

    def _auth_header(self) -> dict:
        cfg = self.auth_config
        token = b64encode(f"{cfg.username}:{cfg.api_token}".encode()).decode()
        return {"Authorization": f"Basic {token}", "Content-Type": "application/json"}

    def validate_config(self, auth_config: dict) -> JiraAuthConfig:
        return JiraAuthConfig.from_dict(auth_config)

    def test_connection(self) -> tuple[bool, str]:
        cfg = self.auth_config
        if not cfg.endpoint or not cfg.username or not cfg.api_token:
            return False, "Jira 配置不完整（endpoint / username / api_token）"
        try:
            url = f"{cfg.endpoint}/rest/api/2/project"
            resp = requests.get(url, headers=self._auth_header(), timeout=15)
            if resp.status_code == 200:
                projects = resp.json()
                match = [p for p in projects if p.get("key") == cfg.project_key]
                if match:
                    return True, f"Jira 连接正常，项目 {cfg.project_key} 存在"
                keys = [p.get("key") for p in projects]
                return True, f"Jira 连接正常，但项目 {cfg.project_key} 未找到（可用: {', '.join(keys[:5])}）"
            return False, f"Jira 返回异常: {resp.status_code} {resp.text[:200]}"
        except requests.RequestException as e:
            return False, f"Jira 连接失败: {e}"

    def notify(self, alert: dict, **kwargs) -> dict:
        cfg = self.auth_config
        if not cfg.project_key:
            return {"success": False, "message": "Project Key 未配置"}

        title = alert.get("title", "AIOps 告警")
        message = alert.get("message", alert.get("description", ""))
        severity = alert.get("severity", "info")
        priority_map = {"critical": "Highest", "warning": "High", "info": "Medium"}
        priority_name = priority_map.get(severity, "Medium")

        issue_data = {
            "fields": {
                "project": {"key": cfg.project_key},
                "summary": f"[AIOps] {title}",
                "description": {
                    "type": "doc",
                    "version": 1,
                    "content": [
                        {"type": "paragraph", "content": [{"type": "text", "text": message}]},
                        {"type": "paragraph", "content": [{"type": "text", "text": f"级别: {severity}"}]},
                    ],
                },
                "issuetype": {"name": "Task"},
                "priority": {"name": priority_name},
            }
        }

        try:
            url = f"{cfg.endpoint}/rest/api/2/issue"
            resp = requests.post(url, json=issue_data, headers=self._auth_header(), timeout=15)
            if resp.status_code == 201:
                key = resp.json().get("key", "")
                return {"success": True, "message": f"Jira Issue {key} 已创建", "issue_key": key}
            return {"success": False, "message": f"创建 Issue 失败: {resp.status_code} {resp.text[:300]}"}
        except requests.RequestException as e:
            return {"success": False, "message": f"Jira 通知异常: {e}"}

    def dispose(self):
        pass