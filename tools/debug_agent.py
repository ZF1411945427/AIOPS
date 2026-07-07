import sys, traceback
sys.path.insert(0, '.')
from app.database import get_session_for, get_db_mode
from app.models import AIProvider, AgentConfig
from app.services.agent_service import process_chat_message

SessionLocal = get_session_for(get_db_mode())
db = SessionLocal()
try:
    config = db.query(AgentConfig).filter(AgentConfig.name == 'default').first()
    print(f'Config: default_provider_id={config.default_provider_id}')

    provider = None
    if config.default_provider_id:
        p = db.query(AIProvider).filter(
            AIProvider.id == config.default_provider_id,
            AIProvider.is_enabled == True
        ).first()
        if p:
            print(f'Default provider (enabled): {p.name} -> {p.base_url} / {p.default_model}')
        else:
            print(f'Default provider {config.default_provider_id} is disabled or missing')
    
    if not provider:
        provider = db.query(AIProvider).filter(AIProvider.is_enabled == True).first()
    
    if provider:
        print(f'Using provider: {provider.name} / {provider.default_model}')
        print(f'Base URL: {provider.base_url}')
        print(f'Has API key: {bool(provider.api_key_encrypted)}')
    
    result = process_chat_message(db, 1, None, 'ping')
    print(f'\nResult: {result}')
except Exception as e:
    traceback.print_exc()
finally:
    db.close()
