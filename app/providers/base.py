import abc
import json
from dataclasses import dataclass, field, fields
from typing import Any, ClassVar, Optional
from sqlalchemy.orm import Session


class ProviderCategory:
    MONITORING = "monitoring"
    LOGGING = "logging"
    TRACING = "tracing"
    NOTIFICATION = "notification"
    INCIDENT_MANAGEMENT = "incident_management"
    TICKETING = "ticketing"
    COLLABORATION = "collaboration"
    CLOUD_INFRA = "cloud_infra"
    SECURITY = "security"
    DATABASE = "database"
    CUSTOM = "custom"
    CONTAINER = "container"
    DATA_SOURCE = "data_source"

    ALL = [
        MONITORING, LOGGING, TRACING, NOTIFICATION,
        INCIDENT_MANAGEMENT, TICKETING, COLLABORATION,
        CLOUD_INFRA, SECURITY, DATABASE, CUSTOM, CONTAINER, DATA_SOURCE,
    ]


@dataclass
class BaseAuthConfig:
    @classmethod
    def field_metadata(cls) -> dict:
        result = {}
        for f in fields(cls):
            meta = dict(f.metadata)
            meta.setdefault("required", False)
            meta.setdefault("sensitive", False)
            meta.setdefault("hidden", False)
            meta.setdefault("description", f.name)
            result[f.name] = meta
        return result

    @classmethod
    def from_dict(cls, data: dict):
        filtered = {k: v for k, v in data.items() if k in {f.name for f in fields(cls)}}
        return cls(**filtered)


class ProviderMeta:
    def __init__(
        self,
        name: str,
        display_name: str,
        category: str,
        description: str = "",
        tags: list[str] = None,
        icon: str = "",
        docs_url: str = "",
        auth_config_class: type = None,
        webhook_required: bool = False,
        coming_soon: bool = False,
    ):
        self.name = name
        self.display_name = display_name
        self.category = category
        self.description = description
        self.tags = tags or []
        self.icon = icon
        self.docs_url = docs_url
        self.auth_config_class = auth_config_class
        self.webhook_required = webhook_required
        self.coming_soon = coming_soon


class BaseProvider(abc.ABC):
    PROVIDER_META: ClassVar[ProviderMeta] = None

    def __init__(self, source_id: int, auth_config: dict, db: Session = None, endpoint: str = ""):
        self.source_id = source_id
        self.endpoint = endpoint
        self.db = db
        self.auth_config = self.validate_config(auth_config)

    def validate_config(self, auth_config: dict) -> Any:
        if self.PROVIDER_META and self.PROVIDER_META.auth_config_class:
            return self.PROVIDER_META.auth_config_class.from_dict(auth_config)
        return auth_config

    def test_connection(self) -> tuple[bool, str]:
        return True, f"{self.PROVIDER_META.display_name} 连接正常" if self.PROVIDER_META else (True, "连接正常")

    def scrape(self, db: Session = None) -> list[dict]:
        return []

    def notify(self, alert: dict, **kwargs) -> dict:
        raise NotImplementedError(f"{self.__class__.__name__} 不支持 notify")

    def query(self, **kwargs) -> list[dict]:
        raise NotImplementedError(f"{self.__class__.__name__} 不支持 query")

    def dispose(self):
        pass

    def to_dict(self) -> dict:
        meta = self.PROVIDER_META
        return {
            "type": meta.name if meta else "",
            "display_name": meta.display_name if meta else "",
            "category": meta.category if meta else "",
            "description": meta.description if meta else "",
            "tags": meta.tags if meta else [],
            "icon": meta.icon if meta else "",
            "docs_url": meta.docs_url if meta else "",
            "webhook_required": meta.webhook_required if meta else False,
            "coming_soon": meta.coming_soon if meta else False,
            "auth_config_schema": self.get_auth_config_schema(),
            "capabilities": self.get_capabilities(),
        }

    def get_auth_config_schema(self) -> dict:
        if self.PROVIDER_META and self.PROVIDER_META.auth_config_class:
            return self.PROVIDER_META.auth_config_class.field_metadata()
        return {}

    def get_capabilities(self) -> list[str]:
        caps = []
        if self._has_impl("test_connection"):
            caps.append("test_connection")
        if self._has_impl("scrape"):
            caps.append("scrape")
        if self._has_impl("notify"):
            caps.append("notify")
        if self._has_impl("query"):
            caps.append("query")
        return caps

    def _has_impl(self, method_name: str) -> bool:
        method = getattr(self.__class__, method_name, None)
        if method is None:
            return False
        return method.__code__.co_code != BaseProvider.__dict__[method_name].__code__.co_code