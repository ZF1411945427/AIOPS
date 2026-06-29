import json
from datetime import datetime

from fastapi import APIRouter, Depends, Request, Form
from fastapi.responses import RedirectResponse
from sqlalchemy.orm import Session

from app.database import get_db
from app.models import AIProvider, AgentConfig
from app.template_utils import get_templates
from app.services.agent_service import call_llm

router = APIRouter(prefix="/ai", tags=["ai"])
templates = get_templates()


@router.get("/providers")
def list_providers(request: Request, db: Session = Depends(get_db)):
    providers = db.query(AIProvider).all()
    configs = db.query(AgentConfig).all()
    return templates.TemplateResponse("ai_providers.html", {
        "request": request,
        "providers": providers,
        "configs": configs,
    })


@router.get("/providers/create")
def create_provider_form(request: Request):
    return templates.TemplateResponse("ai_provider_form.html", {
        "request": request,
        "provider": None,
    })


@router.post("/providers/create")
def create_provider(
    request: Request,
    name: str = Form(...),
    base_url: str = Form(""),
    default_model: str = Form(""),
    api_key: str = Form(""),
    temperature: float = Form(0.2),
    max_tokens: int = Form(10000),
    timeout_seconds: int = Form(30),
    db: Session = Depends(get_db),
):
    provider = AIProvider(
        name=name,
        base_url=base_url,
        default_model=default_model,
        temperature=temperature,
        max_tokens=max_tokens,
        timeout_seconds=timeout_seconds,
    )
    provider.set_api_key(api_key)
    db.add(provider)
    db.commit()
    return RedirectResponse(url="/ai/providers", status_code=303)


@router.get("/providers/{provider_id}/edit")
def edit_provider_form(request: Request, provider_id: int, db: Session = Depends(get_db)):
    provider = db.query(AIProvider).filter(AIProvider.id == provider_id).first()
    return templates.TemplateResponse("ai_provider_form.html", {
        "request": request,
        "provider": provider,
    })


@router.post("/providers/{provider_id}/edit")
def edit_provider(
    request: Request,
    provider_id: int,
    name: str = Form(...),
    base_url: str = Form(""),
    default_model: str = Form(""),
    api_key: str = Form(""),
    temperature: float = Form(0.2),
    max_tokens: int = Form(10000),
    timeout_seconds: int = Form(30),
    db: Session = Depends(get_db),
):
    provider = db.query(AIProvider).filter(AIProvider.id == provider_id).first()
    if provider:
        provider.name = name
        provider.base_url = base_url
        provider.default_model = default_model
        provider.temperature = temperature
        provider.max_tokens = max_tokens
        provider.timeout_seconds = timeout_seconds
        if api_key:
            provider.set_api_key(api_key)
        provider.updated_at = datetime.now()
        db.commit()
    return RedirectResponse(url="/ai/providers", status_code=303)


@router.post("/providers/{provider_id}/toggle")
def toggle_provider(provider_id: int, db: Session = Depends(get_db)):
    provider = db.query(AIProvider).filter(AIProvider.id == provider_id).first()
    if provider:
        provider.is_enabled = not provider.is_enabled
        db.commit()
    return RedirectResponse(url="/ai/providers", status_code=303)


@router.post("/providers/{provider_id}/delete")
def delete_provider(provider_id: int, db: Session = Depends(get_db)):
    provider = db.query(AIProvider).filter(AIProvider.id == provider_id).first()
    if provider:
        db.delete(provider)
        db.commit()
    return RedirectResponse(url="/ai/providers", status_code=303)


@router.post("/providers/{provider_id}/test")
def test_provider(provider_id: int, db: Session = Depends(get_db)):
    provider = db.query(AIProvider).filter(AIProvider.id == provider_id).first()
    if not provider:
        return {"status": "error", "message": "Provider not found"}

    test_messages = [{"role": "user", "content": "ping"}]
    result = call_llm(provider, test_messages)

    if "error" in result:
        return {"status": "error", "message": result["error"]}
    return {"status": "success", "message": "连接成功"}


@router.get("/configs/create")
def create_config_form(request: Request, db: Session = Depends(get_db)):
    providers = db.query(AIProvider).filter(AIProvider.is_enabled == True).all()
    return templates.TemplateResponse("agent_config_form.html", {
        "request": request,
        "config": None,
        "providers": providers,
    })


@router.post("/configs/create")
def create_config(
    request: Request,
    name: str = Form("default"),
    default_provider_id: int = Form(0),
    system_prompt: str = Form(""),
    welcome_message: str = Form(""),
    suggested_questions: str = Form("[]"),
    allow_action_execution: bool = Form(False),
    require_confirmation: bool = Form(True),
    max_history_messages: int = Form(12),
    db: Session = Depends(get_db),
):
    config = AgentConfig(
        name=name,
        default_provider_id=default_provider_id if default_provider_id else None,
        system_prompt=system_prompt,
        welcome_message=welcome_message,
        suggested_questions=suggested_questions,
        allow_action_execution=allow_action_execution,
        require_confirmation=require_confirmation,
        max_history_messages=max_history_messages,
    )
    db.add(config)
    db.commit()
    return RedirectResponse(url="/ai/providers", status_code=303)


@router.get("/configs/{config_id}/edit")
def edit_config_form(request: Request, config_id: int, db: Session = Depends(get_db)):
    config = db.query(AgentConfig).filter(AgentConfig.id == config_id).first()
    providers = db.query(AIProvider).filter(AIProvider.is_enabled == True).all()
    return templates.TemplateResponse("agent_config_form.html", {
        "request": request,
        "config": config,
        "providers": providers,
    })


@router.post("/configs/{config_id}/edit")
def edit_config(
    request: Request,
    config_id: int,
    name: str = Form("default"),
    default_provider_id: int = Form(0),
    system_prompt: str = Form(""),
    welcome_message: str = Form(""),
    suggested_questions: str = Form("[]"),
    allow_action_execution: bool = Form(False),
    require_confirmation: bool = Form(True),
    max_history_messages: int = Form(12),
    db: Session = Depends(get_db),
):
    config = db.query(AgentConfig).filter(AgentConfig.id == config_id).first()
    if config:
        config.name = name
        config.default_provider_id = default_provider_id if default_provider_id else None
        config.system_prompt = system_prompt
        config.welcome_message = welcome_message
        config.suggested_questions = suggested_questions
        config.allow_action_execution = allow_action_execution
        config.require_confirmation = require_confirmation
        config.max_history_messages = max_history_messages
        config.updated_at = datetime.now()
        db.commit()
    return RedirectResponse(url="/ai/providers", status_code=303)
