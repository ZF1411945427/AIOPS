import json
import urllib.request
from dataclasses import dataclass, field

from app.providers.base import BaseProvider, BaseAuthConfig, ProviderMeta, ProviderCategory


@dataclass
class CustomApiAuthConfig(BaseAuthConfig):
    endpoint: str = field(default="", metadata={"required": True, "description": "外部 API 地址(完整 URL)"})
    auth_type: str = field(default="none", metadata={"description": "认证方式(none/basic/bearer/api_key)"})
    api_key: str = field(default="", metadata={"sensitive": True, "description": "API Key 或 Bearer Token"})
    headers: str = field(default="", metadata={"description": "自定义请求头(JSON 对象)"})


class CustomApiProvider(BaseProvider):
    PROVIDER_META = ProviderMeta(
        name="custom_api",
        display_name="自定义 API",
        category=ProviderCategory.CUSTOM,
        description="调用外部 REST API 获取指标数据",
        tags=["api", "rest", "custom", "integration"],
        icon="🔌",
        docs_url="",
        auth_config_class=CustomApiAuthConfig,
    )

    def test_connection(self) -> tuple[bool, str]:
        try:
            endpoint = self.auth_config.endpoint or self.endpoint or ""
            if not endpoint:
                return False, "API endpoint 未配置"
            headers = self._build_headers()
            req = urllib.request.Request(endpoint, headers=headers, method="GET")
            with urllib.request.urlopen(req, timeout=10) as resp:
                status = resp.status
                body = resp.read().decode("utf-8")[:200]
            return True, f"API 连接成功, HTTP {status}"
        except urllib.error.HTTPError as e:
            return True, f"API 可达, HTTP {e.code}"
        except Exception as e:
            return False, f"API 连接失败: {e}"

    def scrape(self, db=None) -> list[dict]:
        return []

    def _build_headers(self) -> dict:
        headers = {"Accept": "application/json", "User-Agent": "AIOPS-Provider/1.0"}
        if self.auth_config.api_key:
            if self.auth_config.auth_type == "bearer":
                headers["Authorization"] = f"Bearer {self.auth_config.api_key}"
            elif self.auth_config.auth_type == "api_key":
                headers["X-API-Key"] = self.auth_config.api_key
            else:
                headers["Authorization"] = f"Bearer {self.auth_config.api_key}"
        if self.auth_config.headers:
            try:
                extra = json.loads(self.auth_config.headers) if isinstance(self.auth_config.headers, str) else self.auth_config.headers
                if isinstance(extra, dict):
                    headers.update(extra)
            except Exception:
                pass
        return headers