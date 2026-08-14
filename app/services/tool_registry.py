"""工具注册表装饰器横切链（对齐 Ongrid tools/decorators）。

在 `@register_mcp_tool` 之下、目标函数之上叠加横切装饰器，为工具附加
audit / ratelimit / timeout / review_gate 元数据，
由 `mcp_registry.call_mcp_tool` 统一强制执行：

```python
@register_mcp_tool(name="query_assets", ...)
@tool_timeout(10)
@tool_ratelimit(60)
def query_assets(db=None, user_id=None, **kwargs):
    ...
```

装饰器只把元数据写到函数属性上，`register_mcp_tool` 读取并落进 MCPToolDef。
使用方式二：直接在 `@register_mcp_tool(...)` 里传 timeout_seconds / ratelimit_per_minute /
audit_enabled / review_gate（两者等价）。
"""
from typing import Optional


def tool_timeout(seconds: int):
    """工具级超时（秒）：超过即返回 timeout 错误，防止 Agent 卡死。"""
    def decorator(func):
        func._tool_timeout = int(seconds)
        return func
    return decorator


def tool_ratelimit(per_minute: int):
    """工具级限流：每分钟最多调用 per_minute 次，超过返回限流错误。"""
    def decorator(func):
        func._tool_ratelimit_per_minute = int(per_minute)
        return func
    return decorator


def tool_audit(enabled: bool = True):
    """工具审计：每次调用写一条 AuditLog（action=tool_execute）。"""
    def decorator(func):
        func._tool_audit = bool(enabled)
        return func
    return decorator


def tool_review_gate(enabled: bool = True):
    """写操作审查门：标记该工具需经 reviewer 二签后才能执行（write gate）。

    当前 enforce 层：内部写工具本身 expose_to_llm=False，仅确认路径可调；
    该标记用于未来 reviewer 子代理自动审查。落位 MCPToolDef.review_gate。
    """
    def decorator(func):
        func._tool_review_gate = bool(enabled)
        return func
    return decorator


def tool_metric(enabled: bool = True):
    """工具指标：标记该工具的调用数/错误/延迟进 /metrics(tool_metrics.py)。

    对齐 on-grid tools/decorators/metric.go: 每次调用记录 call/latency/error，
    在 call_mcp_tool 内强制执行。落位 MCPToolDef.metric_enabled。
    """
    def decorator(func):
        func._tool_metric = bool(enabled)
        return func
    return decorator


def tool_tenant_bind(note: str = ""):
    """租户绑定(声明式标记)：标记该工具应在当前租户上下文内执行。

    对齐 on-grid tools/decorators/tenant_bind.go。当前 enforce 层：
    call_mcp_tool 会把调用线程的 tenant id 传播进执行线程。落位 MCPToolDef.tenant_bind。
    """
    def decorator(func):
        func._tool_tenant_bind = True
        return func
    return decorator


def apply_decorator_meta(func, **meta):
    """程序化附加装饰器元数据（等价于叠装饰器），供动态注册工具使用。"""
    for key, value in meta.items():
        setattr(func, f"_tool_{key}", value)
    return func


__all__ = [
    "tool_timeout", "tool_ratelimit", "tool_audit",
    "tool_review_gate", "tool_metric", "tool_tenant_bind", "apply_decorator_meta",
]
