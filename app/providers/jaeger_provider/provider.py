import json
import urllib.request
from dataclasses import dataclass, field

from app.providers.base import BaseProvider, BaseAuthConfig, ProviderMeta, ProviderCategory


@dataclass
class JaegerAuthConfig(BaseAuthConfig):
    endpoint: str = field(default="", metadata={"required": True, "description": "Jaeger HTTP 地址(如 http://10.0.0.1:16686)"})


class JaegerProvider(BaseProvider):
    PROVIDER_META = ProviderMeta(
        name="jaeger",
        display_name="Jaeger 链路追踪",
        category=ProviderCategory.TRACING,
        description="对接 Jaeger 后端，拉取分布式调用链 Span 数据",
        tags=["jaeger", "tracing", "distributed-tracing"],
        icon="🔗",
        docs_url="https://www.jaegertracing.io/docs",
        auth_config_class=JaegerAuthConfig,
    )

    def test_connection(self) -> tuple[bool, str]:
        try:
            base = (self.auth_config.endpoint or self.endpoint or "").rstrip("/")
            if not base:
                return False, "Jaeger endpoint 未配置"
            url = f"{base}/api/services"
            req = urllib.request.Request(url, headers={"Accept": "application/json"})
            with urllib.request.urlopen(req, timeout=10) as resp:
                data = json.loads(resp.read().decode("utf-8"))
            services = data.get("data", [])
            return True, f"Jaeger 连接成功, 发现 {len(services)} 个服务"
        except Exception as e:
            return False, f"Jaeger 连接失败: {e}"

    def scrape(self, db=None) -> list[dict]:
        return []