from typing import Optional
from datetime import datetime


class ProviderInstallDTO:
    def __init__(
        self,
        type: str,
        name: str,
        endpoint: str = "",
        auth_config: dict = None,
        scrape_interval: int = 60,
        mapping_config: dict = None,
        enabled: bool = True,
    ):
        self.type = type
        self.name = name
        self.endpoint = endpoint
        self.auth_config = auth_config or {}
        self.scrape_interval = scrape_interval
        self.mapping_config = mapping_config or {}
        self.enabled = enabled

    @classmethod
    def from_dict(cls, data: dict):
        return cls(
            type=data.get("type", ""),
            name=data.get("name", ""),
            endpoint=data.get("endpoint", ""),
            auth_config=data.get("auth_config", {}),
            scrape_interval=data.get("scrape_interval", 60),
            mapping_config=data.get("mapping_config", {}),
            enabled=data.get("enabled", True),
        )


class ProviderStatusDTO:
    def __init__(
        self,
        id: int,
        name: str,
        type: str,
        display_name: str = "",
        endpoint: str = "",
        enabled: bool = True,
        last_status: str = "unknown",
        last_error: str = "",
        last_scraped_at: Optional[str] = None,
        created_at: Optional[str] = None,
        auth_config: dict = None,
        category: str = "",
    ):
        self.id = id
        self.name = name
        self.type = type
        self.display_name = display_name
        self.endpoint = endpoint
        self.enabled = enabled
        self.last_status = last_status
        self.last_error = last_error
        self.last_scraped_at = last_scraped_at
        self.created_at = created_at
        self.auth_config = auth_config or {}
        self.category = category

    def to_dict(self) -> dict:
        return {
            "id": self.id,
            "name": self.name,
            "type": self.type,
            "display_name": self.display_name,
            "endpoint": self.endpoint,
            "enabled": self.enabled,
            "last_status": self.last_status,
            "last_error": self.last_error,
            "last_scraped_at": self.last_scraped_at,
            "created_at": self.created_at,
            "auth_config": self.auth_config,
            "category": self.category,
        }