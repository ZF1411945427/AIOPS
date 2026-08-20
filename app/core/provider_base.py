"""
统一 Provider 抽象基类 + 注册表 + 适配器。

三类 Provider:
  - AI: LLM 模型提供商 (OpenAI-compatible)
  - Notification: 通知渠道 (email/webhook/IM)
  - DataSource: 数据采集源 (ES/Loki/Prometheus)

用法:
  registry = ProviderRegistry()
  registry.register("my-provider", MyAdapter(instance))
  for p in registry.list():
      ok, msg = p.health_check()
"""
from abc import ABC, abstractmethod
from typing import Any, Dict, List, Optional, Tuple


class BaseProvider(ABC):
    """统一 Provider 抽象基类."""

    CATEGORY: str = ""  # 子类覆盖: "ai" / "notification" / "datasource"

    @property
    @abstractmethod
    def provider_id(self) -> int:
        ...

    @property
    @abstractmethod
    def provider_name(self) -> str:
        ...

    @abstractmethod
    def health_check(self) -> Tuple[bool, str]:
        """返回 (is_healthy, message)"""
        ...

    @abstractmethod
    def to_dict(self) -> Dict[str, Any]:
        ...


class ProviderRegistry:
    """Provider 注册表 — 单例."""

    def __init__(self):
        self._providers: Dict[str, BaseProvider] = {}

    def register(self, key: str, provider: BaseProvider):
        self._providers[key] = provider

    def unregister(self, key: str):
        self._providers.pop(key, None)

    def get(self, key: str) -> Optional[BaseProvider]:
        return self._providers.get(key)

    def list(self, category: str = "") -> List[BaseProvider]:
        if category:
            return [p for p in self._providers.values() if p.CATEGORY == category]
        return list(self._providers.values())

    def list_by_ids(self, ids: List[int], category: str = "") -> List[BaseProvider]:
        return [p for p in self.list(category) if p.provider_id in ids]

    def health_snapshot(self, category: str = "") -> List[Dict[str, Any]]:
        results = []
        for p in self.list(category):
            ok, msg = p.health_check()
            d = p.to_dict()
            d["health_ok"] = ok
            d["health_message"] = msg
            results.append(d)
        return results


# 全局注册表单例
registry = ProviderRegistry()


# ── AI Provider 适配器 ──────────────────────────────────

class AIProviderAdapter(BaseProvider):
    CATEGORY = "ai"

    def __init__(self, provider, db=None):
        from app.models.agent import AIProvider
        self._p = provider
        self._db = db

    @property
    def provider_id(self) -> int:
        return self._p.id

    @property
    def provider_name(self) -> str:
        return self._p.name

    def health_check(self) -> Tuple[bool, str]:
        return self._test_llm_connection()

    def _test_llm_connection(self) -> Tuple[bool, str]:
        api_key = self._p.get_api_key()
        if not api_key:
            return False, "API Key 未配置"
        try:
            import requests
            headers = {
                "Authorization": f"Bearer {api_key}",
                "Content-Type": "application/json",
            }
            payload = {
                "model": self._p.default_model or "gpt-3.5-turbo",
                "messages": [{"role": "user", "content": "ping"}],
                "max_tokens": 5,
            }
            r = requests.post(
                f"{self._p.base_url.rstrip('/')}/chat/completions",
                headers=headers,
                json=payload,
                timeout=self._p.timeout_seconds or 10,
            )
            if r.status_code == 200:
                return True, "OK"
            return False, f"HTTP {r.status_code}: {r.text[:100]}"
        except Exception as e:
            return False, str(e)

    def to_dict(self) -> Dict[str, Any]:
        return {
            "id": self._p.id,
            "name": self._p.name,
            "category": self.CATEGORY,
            "type": self._p.provider_type,
            "model": self._p.default_model,
            "base_url": self._p.base_url,
            "enabled": self._p.is_enabled,
            "temperature": self._p.temperature,
            "max_tokens": self._p.max_tokens,
            "timeout": self._p.timeout_seconds,
        }


# ── Notification Channel 适配器 ─────────────────────────

class NotificationChannelAdapter(BaseProvider):
    CATEGORY = "notification"

    def __init__(self, channel):
        self._c = channel

    @property
    def provider_id(self) -> int:
        return self._c.id

    @property
    def provider_name(self) -> str:
        return self._c.name

    def health_check(self) -> Tuple[bool, str]:
        return self._test()

    def _test(self) -> Tuple[bool, str]:
        import json
        cfg = {}
        try:
            cfg = json.loads(self._c.channel_config) if self._c.channel_config else {}
        except Exception:
            pass
        ct = self._c.type
        if ct == "email":
            return self._test_email(cfg)
        elif ct == "webhook":
            return self._test_webhook(cfg)
        elif ct in ("dingtalk", "wecom", "feishu"):
            return self._test_im_webhook(cfg)
        return True, f"type={ct} 无需测试"

    def _test_email(self, cfg: dict) -> Tuple[bool, str]:
        import smtplib
        try:
            host = cfg.get("host", "")
            port = int(cfg.get("port", 25))
            with smtplib.SMTP(host=host, port=port, timeout=5) as smtp:
                return True, "SMTP 连通"
        except Exception as e:
            return False, str(e)

    def _test_webhook(self, cfg: dict) -> Tuple[bool, str]:
        import requests
        url = cfg.get("url", "")
        if not url:
            return False, "Webhook URL 为空"
        try:
            r = requests.get(url, timeout=5)
            return True, f"HTTP {r.status_code}"
        except Exception as e:
            return False, str(e)

    def _test_im_webhook(self, cfg: dict) -> Tuple[bool, str]:
        return self._test_webhook(cfg)

    def send(self, title: str, content: str) -> Tuple[bool, str]:
        from app.services.notification_service import send_notification as _send
        if hasattr(self._c, "__tablename__"):
            return True, "delegated"
        return False, "unsupported"

    def to_dict(self) -> Dict[str, Any]:
        return {
            "id": self._c.id,
            "name": self._c.name,
            "category": self.CATEGORY,
            "type": self._c.type,
            "enabled": self._c.enabled,
            "bidirectional": getattr(self._c, "bidirectional", False),
        }


# ── DataSource 适配器 ──────────────────────────────────

# 数据源类型 -> 专用健康探测路径(拼在 endpoint 后); 命中即按 HTTP 状态判定
_DS_PROBE_PATH = {
    "prometheus": "/api/v1/status/buildinfo",
    "grafana": "/api/health",
    "loki": "/loki/api/v1/ready",
    "elasticsearch": "/",
    "jaeger": "/api/services",
    "tempo": "/ready",
    "alertmanager": "/-/ready",
    "thanos": "/-/ready",
    "kafka": "/",
}


class DataSourceAdapter(BaseProvider):
    CATEGORY = "datasource"

    def __init__(self, ds):
        self._ds = ds

    @property
    def provider_id(self) -> int:
        return self._ds.id

    @property
    def provider_name(self) -> str:
        return self._ds.name

    def health_check(self) -> Tuple[bool, str]:
        return self._probe()

    def _probe(self) -> Tuple[bool, str]:
        endpoint = self._ds.endpoint or ""
        if not endpoint:
            return False, "Endpoint 为空"
        import requests
        probe_url = endpoint.rstrip("/")
        # 已含路径的 endpoint(如 /prometheus)不再重复拼接
        dspath = _DS_PROBE_PATH.get(self._ds.type or "", "")
        if dspath and not endpoint.rstrip("/").endswith(dspath):
            probe_url += dspath
        headers: Dict[str, str] = {}
        try:
            auth_cfg = {}
            if self._ds.auth_config:
                import json as _json
                auth_cfg = _json.loads(self._ds.auth_config) if isinstance(self._ds.auth_config, str) else (self._ds.auth_config or {})
        except Exception:
            auth_cfg = {}
        token = auth_cfg.get("token") or auth_cfg.get("api_key") or auth_cfg.get("apikey")
        if token:
            headers["Authorization"] = f"Bearer {token}"
        elif auth_cfg.get("basic_auth"):
            ba = auth_cfg.get("basic_auth")
            if isinstance(ba, dict) and ba.get("username") is not None and ba.get("password") is not None:
                from requests.auth import HTTPBasicAuth
                import base64
                raw = f"{ba.get('username')}:{ba.get('password')}".encode()
                headers["Authorization"] = "Basic " + base64.b64encode(raw).decode()
        try:
            r = requests.get(probe_url, headers=headers, timeout=5)
            ok = r.status_code < 500
            return (True, f"HTTP {r.status_code} {self._ds.type or ''}") if ok else (
                False, f"HTTP {r.status_code} {r.text[:120]}")
        except Exception as e:
            return False, str(e)

    def to_dict(self) -> Dict[str, Any]:
        return {
            "id": self._ds.id,
            "name": self._ds.name,
            "category": self.CATEGORY,
            "type": self._ds.type,
            "endpoint": self._ds.endpoint,
            "enabled": self._ds.enabled,
            "last_status": self._ds.last_status,
            "last_scraped_at": str(self._ds.last_scraped_at) if self._ds.last_scraped_at else None,
            "probe_path": _DS_PROBE_PATH.get(self._ds.type or "", ""),
        }



# ── 工厂函数 ────────────────────────────────────────────

def register_all_providers(db) -> int:
    """从数据库加载所有 Provider 并注册到全局注册表。返回注册数。"""
    from sqlalchemy.orm import Session
    count = 0
    # AI Provider
    try:
        from app.models.agent import AIProvider
        for p in db.query(AIProvider).all():
            registry.register(f"ai_{p.id}", AIProviderAdapter(p, db))
            count += 1
    except Exception:
        pass
    # Notification Channel
    try:
        from app.models.notify import NotificationChannel
        for c in db.query(NotificationChannel).all():
            registry.register(f"notif_{c.id}", NotificationChannelAdapter(c))
            count += 1
    except Exception:
        pass
    # DataSource
    try:
        from app.models.asset import DataSource
        for ds in db.query(DataSource).all():
            registry.register(f"ds_{ds.id}", DataSourceAdapter(ds))
            count += 1
    except Exception:
        pass
    return count