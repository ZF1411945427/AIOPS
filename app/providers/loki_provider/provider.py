from dataclasses import dataclass, field

from app.providers.base import BaseProvider, BaseAuthConfig, ProviderMeta, ProviderCategory


@dataclass
class LokiAuthConfig(BaseAuthConfig):
    endpoint: str = field(default="", metadata={"required": True, "description": "Loki HTTP 地址(如 http://10.0.0.1:3100)"})
    username: str = field(default="", metadata={"description": "Basic Auth 用户名"})
    password: str = field(default="", metadata={"sensitive": True, "description": "Basic Auth 密码"})
    org_id: str = field(default="", metadata={"description": "X-Scope-OrgID 多租户标识"})


class LokiProvider(BaseProvider):
    PROVIDER_META = ProviderMeta(
        name="loki",
        display_name="Grafana Loki",
        category=ProviderCategory.LOGGING,
        description="对接 Grafana Loki 查询日志数据(LogQL)",
        tags=["loki", "logs", "grafana", "logging"],
        icon="📋",
        docs_url="https://grafana.com/docs/loki",
        auth_config_class=LokiAuthConfig,
    )

    def test_connection(self) -> tuple[bool, str]:
        try:
            import requests
        except ImportError:
            return False, "缺少 requests Python 包"
        try:
            base = (self.auth_config.endpoint or self.endpoint or "").rstrip("/")
            if not base:
                return False, "Loki endpoint 未配置"
            headers = {"Accept": "application/json"}
            if self.auth_config.org_id:
                headers["X-Scope-OrgID"] = str(self.auth_config.org_id)
            auth = None
            if self.auth_config.username and self.auth_config.password:
                auth = (self.auth_config.username, self.auth_config.password)
            resp = requests.get(f"{base}/loki/api/v1/labels", headers=headers, auth=auth, timeout=10)
            if resp.status_code == 200:
                data = resp.json()
                labels = data.get("data", [])
                return True, f"Loki 连接成功, 发现 {len(labels)} 个标签"
            return False, f"Loki 连接失败（HTTP {resp.status_code}）: {resp.text[:200]}"
        except Exception as e:
            return False, f"Loki 连接失败: {e}"

    def scrape(self, db=None) -> list[dict]:
        return []