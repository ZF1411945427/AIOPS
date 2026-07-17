"""
多租户上下文 — 请求级 TLS 存储
默认单租户，tenant_mode=OFF 时完全静默，不影响任何现有逻辑
"""
import threading
from typing import Optional

_thread_locals = threading.local()

def set_current_tenant(tenant_id: Optional[int]):
    _thread_locals.tenant_id = tenant_id

def get_current_tenant() -> Optional[int]:
    return getattr(_thread_locals, 'tenant_id', None)

def clear_current_tenant():
    _thread_locals.tenant_id = None
