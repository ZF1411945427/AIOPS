import importlib
import inspect
import os
import pkgutil
from pathlib import Path
from typing import Optional, Type
from sqlalchemy.orm import Session

from app.providers.base import BaseProvider, ProviderCategory


class ProviderFactory:
    _registry: dict[str, Type[BaseProvider]] = {}
    _loaded = False

    @classmethod
    def discover_providers(cls, force: bool = False):
        if cls._loaded and not force:
            return
        cls._registry.clear()
        providers_dir = Path(__file__).parent
        for entry in providers_dir.iterdir():
            if not entry.is_dir():
                continue
            if entry.name.startswith("_") or entry.name.startswith("."):
                continue
            if not entry.name.endswith("_provider"):
                continue
            provider_module_name = f"app.providers.{entry.name}.provider"
            try:
                module = importlib.import_module(provider_module_name)
            except (ImportError, ModuleNotFoundError):
                continue
            for name in dir(module):
                obj = getattr(module, name, None)
                if (isinstance(obj, type) and issubclass(obj, BaseProvider)
                        and obj is not BaseProvider and obj.PROVIDER_META is not None):
                    cls._registry[obj.PROVIDER_META.name] = obj
        cls._loaded = True

    @classmethod
    def get_provider_class(cls, provider_type: str) -> Optional[Type[BaseProvider]]:
        cls.discover_providers()
        return cls._registry.get(provider_type)

    @classmethod
    def get_provider(
        cls,
        provider_type: str,
        source_id: int = 0,
        auth_config: dict = None,
        db: Session = None,
        endpoint: str = "",
    ) -> Optional[BaseProvider]:
        provider_class = cls.get_provider_class(provider_type)
        if not provider_class:
            return None
        return provider_class(
            source_id=source_id,
            auth_config=auth_config or {},
            db=db,
            endpoint=endpoint,
        )

    @classmethod
    def list_providers(cls) -> list[dict]:
        cls.discover_providers()
        results = []
        for provider_type, provider_class in cls._registry.items():
            meta = provider_class.PROVIDER_META
            dummy = provider_class(source_id=0, auth_config={})
            results.append({
                "type": provider_type,
                "display_name": meta.display_name,
                "category": meta.category,
                "description": meta.description,
                "tags": meta.tags,
                "icon": meta.icon or "",
                "docs_url": meta.docs_url or "",
                "webhook_required": meta.webhook_required,
                "coming_soon": meta.coming_soon,
                "auth_config_schema": dummy.get_auth_config_schema(),
                "capabilities": dummy.get_capabilities(),
            })
        return results

    @classmethod
    def get_providers_by_category(cls) -> dict[str, list[dict]]:
        providers = cls.list_providers()
        grouped = {}
        for p in providers:
            cat = p["category"]
            if cat not in grouped:
                grouped[cat] = []
            grouped[cat].append(p)
        return grouped

    @classmethod
    def get_registered_types(cls) -> list[str]:
        cls.discover_providers()
        return list(cls._registry.keys())