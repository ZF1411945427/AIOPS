import json
from datetime import datetime
from typing import Optional

from sqlalchemy.orm import Session

from app.models import DataSource
from app.providers.factory import ProviderFactory
from app.providers.models import ProviderInstallDTO, ProviderStatusDTO
from app.services.secret_vault import resolve_secret_refs
from app.template_utils import parse_json_config


_SENSITIVE_FIELDS = (
    "ssh_password", "ssh_private_key", "k8s_token", "kubeconfig",
    "db_password", "http_credential", "api_key", "access_token",
    "webhook_url", "secret", "password", "token",
)


def _mask_auth_config(auth_config) -> dict:
    if not auth_config:
        return {}
    try:
        cfg = json.loads(auth_config) if isinstance(auth_config, str) else (dict(auth_config) or {})
    except Exception:
        return {}
    masked = {}
    for k, v in cfg.items():
        if any(sen in k.lower() for sen in ("password", "secret", "token", "key", "credential")):
            masked[k] = "***"
            masked[f"has_{k}"] = bool(v)
        else:
            masked[k] = v
    return masked


def _source_to_dto(source: DataSource) -> ProviderStatusDTO:
    provider_class = ProviderFactory.get_provider_class(source.type)
    display_name = provider_class.PROVIDER_META.display_name if provider_class else source.type
    category = provider_class.PROVIDER_META.category if provider_class else ""
    return ProviderStatusDTO(
        id=source.id,
        name=source.name,
        type=source.type,
        display_name=display_name,
        endpoint=source.endpoint or "",
        enabled=bool(source.enabled),
        last_status=source.last_status or "unknown",
        last_error=source.last_error or "",
        last_scraped_at=source.last_scraped_at.strftime("%Y-%m-%d %H:%M:%S") if source.last_scraped_at else None,
        created_at=source.created_at.strftime("%Y-%m-%d %H:%M") if source.created_at else None,
        auth_config=_mask_auth_config(source.auth_config),
        category=category,
    )


class ProviderService:
    @staticmethod
    def list_installed(db: Session) -> list[dict]:
        sources = db.query(DataSource).order_by(DataSource.id.desc()).all()
        return [_source_to_dto(s).to_dict() for s in sources]

    @staticmethod
    def get_installed(db: Session, source_id: int) -> Optional[dict]:
        source = db.query(DataSource).filter(DataSource.id == source_id).first()
        if not source:
            return None
        return _source_to_dto(source).to_dict()

    @staticmethod
    def install(db: Session, data: dict) -> dict:
        dto = ProviderInstallDTO.from_dict(data)
        provider_class = ProviderFactory.get_provider_class(dto.type)
        if not provider_class:
            raise ValueError(f"不支持的 Provider 类型: {dto.type}")

        if isinstance(dto.auth_config, dict):
            auth_config_str = json.dumps(dto.auth_config, ensure_ascii=False)
        else:
            auth_config_str = str(dto.auth_config or "{}")

        mapping_str = json.dumps(dto.mapping_config, ensure_ascii=False) if dto.mapping_config else "{}"

        source = DataSource(
            name=dto.name,
            type=dto.type,
            endpoint=dto.endpoint,
            auth_type="provider",
            auth_config=auth_config_str,
            scrape_interval=dto.scrape_interval,
            mapping_config=mapping_str,
            enabled=dto.enabled,
        )
        db.add(source)
        db.commit()
        db.refresh(source)
        return _source_to_dto(source).to_dict()

    @staticmethod
    def uninstall(db: Session, source_id: int) -> bool:
        source = db.query(DataSource).filter(DataSource.id == source_id).first()
        if not source:
            return False
        db.delete(source)
        db.commit()
        return True

    @staticmethod
    def update_installed(db: Session, source_id: int, data: dict) -> Optional[dict]:
        source = db.query(DataSource).filter(DataSource.id == source_id).first()
        if not source:
            return None
        if isinstance(data.get("auth_config"), dict):
            existing = {}
            try:
                existing = json.loads(source.auth_config) if source.auth_config else {}
            except Exception:
                existing = {}
            merged = dict(existing)
            for k, v in data["auth_config"].items():
                if v in (None, "") and any(sen in k.lower() for sen in ("password", "secret", "token", "key")):
                    continue
                merged[k] = v
            data["auth_config"] = json.dumps(merged, ensure_ascii=False)
        if isinstance(data.get("mapping_config"), dict):
            data["mapping_config"] = json.dumps(data["mapping_config"], ensure_ascii=False)
        for k, v in data.items():
            if hasattr(source, k):
                setattr(source, k, v)
        db.commit()
        db.refresh(source)
        return _source_to_dto(source).to_dict()

    @staticmethod
    def test_connection(db: Session, source_id: int) -> tuple[bool, str]:
        source = db.query(DataSource).filter(DataSource.id == source_id).first()
        if not source:
            return False, "数据源不存在"
        auth = parse_json_config(source.auth_config)
        auth = resolve_secret_refs(auth, db)
        provider = ProviderFactory.get_provider(
            provider_type=source.type,
            source_id=source.id,
            auth_config=auth,
            db=db,
            endpoint=source.endpoint or "",
        )
        if not provider:
            return False, f"不支持的 Provider 类型: {source.type}"
        try:
            success, msg = provider.test_connection()
        except Exception as e:
            success, msg = False, str(e)
        source.last_status = "online" if success else "error"
        source.last_error = "" if success else msg
        source.last_scraped_at = datetime.now()
        db.commit()
        return success, msg

    @staticmethod
    def scrape(db: Session, source_id: int) -> tuple[bool, str]:
        source = db.query(DataSource).filter(DataSource.id == source_id).first()
        if not source:
            return False, "数据源不存在"
        auth = parse_json_config(source.auth_config)
        auth = resolve_secret_refs(auth, db)
        provider = ProviderFactory.get_provider(
            provider_type=source.type,
            source_id=source.id,
            auth_config=auth,
            db=db,
            endpoint=source.endpoint or "",
        )
        if not provider:
            return False, f"不支持的 Provider 类型: {source.type}"
        try:
            results = provider.scrape(db=db)
            source.last_status = "online"
            source.last_error = ""
            source.last_scraped_at = datetime.now()
            db.commit()
            return True, f"采集成功，{len(results)} 条记录"
        except Exception as e:
            source.last_status = "error"
            source.last_error = str(e)
            source.last_scraped_at = datetime.now()
            db.commit()
            return False, str(e)

    @staticmethod
    def get_provider_catalog() -> list[dict]:
        return ProviderFactory.list_providers()

    @staticmethod
    def get_providers_by_category() -> dict[str, list[dict]]:
        return ProviderFactory.get_providers_by_category()