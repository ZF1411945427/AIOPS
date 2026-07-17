import json
from datetime import datetime

from fastapi import APIRouter, Depends, Request, Body
from sqlalchemy.orm import Session

from app.database import get_db
from app.models import AIProvider, AgentConfig
from app.services.agent_service import call_llm

router = APIRouter(prefix="/ai", tags=["ai"])


@router.post("/providers/{provider_id}/test")
def test_provider(provider_id: int, db: Session = Depends(get_db)):
    provider = db.query(AIProvider).filter(AIProvider.id == provider_id).first()
    if not provider:
        return {"status": "error", "message": "Provider not found"}

    test_messages = [{"role": "user", "content": "ping"}]
    result = call_llm(provider, test_messages, timeout_override=10, max_tokens_override=10)

    if "error" in result:
        return {"status": "error", "message": result["error"]}
    return {"status": "success", "message": "连接成功"}


@router.get("/api/providers")
def api_providers_list(db: Session = Depends(get_db)):
    providers = db.query(AIProvider).all()
    configs = db.query(AgentConfig).all()
    return {
        "providers": [
            {
                "id": p.id, "name": p.name, "provider_type": p.provider_type,
                "base_url": p.base_url, "default_model": p.default_model,
                "temperature": p.temperature, "max_tokens": p.max_tokens,
                "timeout_seconds": p.timeout_seconds, "is_enabled": p.is_enabled,
                "has_api_key": bool(p.api_key_encrypted),
                "created_at": p.created_at.isoformat() if p.created_at else None,
            }
            for p in providers
        ],
        "configs": [
            {
                "id": c.id, "name": c.name, "default_provider_id": c.default_provider_id,
                "system_prompt": c.system_prompt, "welcome_message": c.welcome_message,
                "suggested_questions": c.suggested_questions,
                "allow_action_execution": c.allow_action_execution,
                "require_confirmation": c.require_confirmation,
                "max_history_messages": c.max_history_messages,
                "is_enabled": c.is_enabled,
            }
            for c in configs
        ],
    }


@router.post("/api/providers/create")
def api_provider_create(payload: dict = Body(...), db: Session = Depends(get_db)):
    provider = AIProvider(
        name=payload.get("name", ""), base_url=payload.get("base_url", ""),
        default_model=payload.get("default_model", ""),
        temperature=float(payload.get("temperature", 0.2) or 0.2),
        max_tokens=int(payload.get("max_tokens", 10000) or 10000),
        timeout_seconds=int(payload.get("timeout_seconds", 30) or 30))
    if payload.get("api_key"):
        provider.set_api_key(payload["api_key"])
    db.add(provider)
    db.commit()
    db.refresh(provider)
    return {"status": "ok", "id": provider.id}


@router.put("/api/providers/{provider_id}/edit")
def api_provider_edit(provider_id: int, payload: dict = Body(...), db: Session = Depends(get_db)):
    provider = db.query(AIProvider).filter(AIProvider.id == provider_id).first()
    if not provider:
        return {"status": "error", "message": "Provider not found"}
    provider.name = payload.get("name", provider.name)
    provider.base_url = payload.get("base_url", provider.base_url)
    provider.default_model = payload.get("default_model", provider.default_model)
    provider.temperature = float(payload.get("temperature", provider.temperature) or 0.2)
    provider.max_tokens = int(payload.get("max_tokens", provider.max_tokens) or 10000)
    provider.timeout_seconds = int(payload.get("timeout_seconds", provider.timeout_seconds) or 30)
    if payload.get("api_key"):
        provider.set_api_key(payload["api_key"])
    provider.updated_at = datetime.now()
    db.commit()
    return {"status": "ok"}


@router.post("/api/providers/{provider_id}/toggle")
def api_provider_toggle(provider_id: int, db: Session = Depends(get_db)):
    provider = db.query(AIProvider).filter(AIProvider.id == provider_id).first()
    if provider:
        provider.is_enabled = not provider.is_enabled
        db.commit()
    return {"status": "ok", "enabled": provider.is_enabled if provider else None}


@router.delete("/api/providers/{provider_id}/delete")
def api_provider_delete(provider_id: int, db: Session = Depends(get_db)):
    provider = db.query(AIProvider).filter(AIProvider.id == provider_id).first()
    if provider:
        db.delete(provider)
        db.commit()
    return {"status": "ok"}


@router.post("/api/configs/create")
def api_config_create(payload: dict = Body(...), db: Session = Depends(get_db)):
    config = AgentConfig(
        name=payload.get("name", "default"),
        default_provider_id=payload.get("default_provider_id") or None,
        system_prompt=payload.get("system_prompt", ""),
        welcome_message=payload.get("welcome_message", ""),
        suggested_questions=payload.get("suggested_questions", "[]") or "[]",
        allow_action_execution=bool(payload.get("allow_action_execution", False)),
        require_confirmation=bool(payload.get("require_confirmation", True)),
        max_history_messages=int(payload.get("max_history_messages", 12) or 12))
    db.add(config)
    db.commit()
    db.refresh(config)
    return {"status": "ok", "id": config.id}


@router.put("/api/configs/{config_id}/edit")
def api_config_edit(config_id: int, payload: dict = Body(...), db: Session = Depends(get_db)):
    config = db.query(AgentConfig).filter(AgentConfig.id == config_id).first()
    if not config:
        return {"status": "error", "message": "Config not found"}
    config.name = payload.get("name", config.name)
    config.default_provider_id = payload.get("default_provider_id") or None
    config.system_prompt = payload.get("system_prompt", config.system_prompt)
    config.welcome_message = payload.get("welcome_message", config.welcome_message)
    config.suggested_questions = payload.get("suggested_questions", config.suggested_questions) or "[]"
    config.allow_action_execution = bool(payload.get("allow_action_execution", False))
    config.require_confirmation = bool(payload.get("require_confirmation", True))
    config.max_history_messages = int(payload.get("max_history_messages", 12) or 12)
    config.updated_at = datetime.now()
    db.commit()
    return {"status": "ok"}
