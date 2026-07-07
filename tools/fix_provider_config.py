import sys
sys.path.insert(0, '.')
from app.database import get_session_for, get_db_mode
from app.models import AgentConfig

SessionLocal = get_session_for(get_db_mode())
db = SessionLocal()
try:
    config = db.query(AgentConfig).filter(AgentConfig.name == 'default').first()
    if config:
        print(f'Before: default_provider_id={config.default_provider_id}')
        config.default_provider_id = 4
        db.commit()
        print(f'After: default_provider_id={config.default_provider_id}')
        print('Fixed: default provider now points to DeepSeek (provider 4)')
    else:
        print('No default config found')
finally:
    db.close()
