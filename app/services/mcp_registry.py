import json
import threading
import time
from collections import deque
from concurrent.futures import ThreadPoolExecutor, TimeoutError as FutureTimeout
from dataclasses import dataclass, field
from typing import Any, Callable, Dict, List, Optional


# 默认工具级超时（秒）。未显式声明 timeout_seconds 的工具也受此兜底，防 Agent 卡死
DEFAULT_TOOL_TIMEOUT = 30


@dataclass
class MCPToolDef:
    name: str
    description: str
    input_schema: Dict[str, Any]
    handler: Callable
    risk_level: str = "read_only"
    expose_to_llm: bool = True
    display_name: Optional[str] = None  # 中文简写名，用于前端展示和对话进度卡片
    # ─── Capability Metadata（对齐 Ongrid，工具安全/运行位置/分类元数据）───
    location: str = "cloud"  # cloud=云端 / edge=设备端 / hybrid=混合
    category: str = "general"  # 工具分类：alert/asset/metric/incident/change/knowledge/k8s/rca/execute_host/workflow/task/propose/log/trace/mysql/general
    # ─── 装饰器横切链元数据（对齐 Ongrid tools/decorators）───
    timeout_seconds: Optional[int] = None  # 工具级超时（秒），None=使用 DEFAULT_TOOL_TIMEOUT
    ratelimit_per_minute: Optional[int] = None  # 每分钟最大调用次数，None=不限流
    audit_enabled: bool = False  # 每次调用写 AuditLog
    review_gate: bool = False  # 写操作审查门：需经 reviewer/审批后执行

    @property
    def read_only(self) -> bool:
        """是否只读工具（不可变更系统状态）。read_only/low 视为只读。"""
        return self.risk_level in ("read_only", "low")

    @property
    def safe(self) -> bool:
        """是否安全工具（可由 Agent 直接调用，无需特殊审批）。read_only/low/advisory 视为安全。"""
        return self.risk_level in ("read_only", "low", "advisory")

    @property
    def ai_only(self) -> bool:
        """是否仅 AI 调用（expose_to_llm=True 即 LLM 可见，False 即内部工具）。"""
        return self.expose_to_llm

    @property
    def timeout(self) -> int:
        """生效超时秒数。"""
        return self.timeout_seconds or DEFAULT_TOOL_TIMEOUT


_MCP_TOOLS: Dict[str, MCPToolDef] = {}

# ─── 外部 MCP 工具(P1-5): 启动时/CRUD 后由 mcp_external.reload 填充 ───
_EXTERNAL_TOOLS: Dict[str, Dict[str, Any]] = {}  # name -> manifest dict
_EXTERNAL_TARGET: Dict[str, str] = {}            # name -> server.name


def clear_external_tools():
    _EXTERNAL_TOOLS.clear()
    _EXTERNAL_TARGET.clear()


def register_external_tool(manifest_entry: Dict[str, Any], server_name: str):
    name = manifest_entry.get("name")
    if not name:
        return
    _EXTERNAL_TOOLS[name] = manifest_entry
    _EXTERNAL_TARGET[name] = server_name


def get_external_manifest() -> List[Dict[str, Any]]:
    return list(_EXTERNAL_TOOLS.values())

# ─── 限流状态（进程内滑动窗口，按工具名隔离）───
_ratelimit_lock = threading.Lock()
_ratelimit_windows: Dict[str, deque] = {}


def _ratelimit_allow(tool_name: str, per_minute: Optional[int]) -> bool:
    """滑动窗口限流：返回是否允许本次调用。"""
    if not per_minute or per_minute <= 0:
        return True
    now = time.time()
    with _ratelimit_lock:
        win = _ratelimit_windows.setdefault(tool_name, deque())
        # 清理 60s 外的调用记录
        while win and now - win[0] >= 60:
            win.popleft()
        if len(win) >= per_minute:
            return False
        win.append(now)
        return True


def _write_tool_audit(tool_name: str, arguments: Dict, result: Any, user_id: Optional[int], db=None):
    """工具审计：写 AuditLog（一次调用一条），失败静默。

    始终用独立 session 写入并提交，避免污染调用方的未提交事务状态。
    """
    try:
        from app.database import get_session_for, get_db_mode
        from app.models import AuditLog
        session = get_session_for(get_db_mode())()
        try:
            session.add(AuditLog(
                user_id=user_id,
                username="",
                method="TOOL",
                path=f"tool://{tool_name}",
                route_path="",
                action="tool_execute",
                target_type="tool",
                target_id=tool_name,
                status_code=0,
                request_body=json.dumps(arguments, ensure_ascii=False)[:4000],
                response_summary=json.dumps(result, ensure_ascii=False)[:500]
                if not isinstance(result, str) else result[:500],
            ))
            session.commit()
        finally:
            session.close()
    except Exception:
        pass


def register_mcp_tool(
    name: str,
    description: str,
    input_schema: Optional[Dict[str, Any]] = None,
    risk_level: str = "read_only",
    expose_to_llm: bool = True,
    display_name: Optional[str] = None,
    location: str = "cloud",
    category: str = "general",
    # 装饰器横切链参数（对齐 Ongrid tools/decorators）
    timeout_seconds: Optional[int] = None,
    ratelimit_per_minute: Optional[int] = None,
    audit_enabled: bool = False,
    review_gate: bool = False,
):
    def decorator(func):
        # 兼容 tool_registry.py 装饰器在函数上附加的元数据（装饰器在 @register_mcp_tool 之下时生效）
        _MCP_TOOLS[name] = MCPToolDef(
            name=name,
            description=description,
            input_schema=input_schema or {"type": "object", "properties": {}},
            handler=func,
            risk_level=risk_level,
            expose_to_llm=expose_to_llm,
            display_name=display_name,
            location=location,
            category=category,
            timeout_seconds=timeout_seconds if timeout_seconds is not None else getattr(func, "_tool_timeout", None),
            ratelimit_per_minute=ratelimit_per_minute if ratelimit_per_minute is not None else getattr(func, "_tool_ratelimit_per_minute", None),
            audit_enabled=audit_enabled or bool(getattr(func, "_tool_audit", False)),
            review_gate=review_gate or bool(getattr(func, "_tool_review_gate", False)),
        )
        return func

    return decorator


def get_mcp_manifest() -> List[Dict[str, Any]]:
    return [
        {
            "name": t.name,
            "display_name": t.display_name or t.name,
            "description": t.description,
            "input_schema": t.input_schema,
            "risk_level": t.risk_level,
            "location": t.location,
            "category": t.category,
            "safe": t.safe,
            "read_only": t.read_only,
            "ai_only": t.ai_only,
            "timeout_seconds": t.timeout_seconds,
            "ratelimit_per_minute": t.ratelimit_per_minute,
            "audit_enabled": t.audit_enabled,
            "review_gate": t.review_gate,
        }
        for t in _MCP_TOOLS.values()
        if t.expose_to_llm
    ] + get_external_manifest()


def get_mcp_tool(name: str) -> Optional[MCPToolDef]:
    return _MCP_TOOLS.get(name)


def get_internal_tools() -> List[MCPToolDef]:
    """返回所有不暴露给 LLM 的内部工具 (expose_to_llm=False), 如 execute_* 执行工具.
    供 list_executable_actions 等建议工具枚举可提议的运维动作清单."""
    return [t for t in _MCP_TOOLS.values() if not t.expose_to_llm]


def call_mcp_tool(
    name: str,
    arguments: Dict[str, Any],
    db=None,
    user_id: int = None,
    allow_internal: bool = False,
    timeout_override: Optional[int] = None,
) -> Dict[str, Any]:
    tool = get_mcp_tool(name)
    if not tool:
        # 外部 MCP 工具回退
        server_name = _EXTERNAL_TARGET.get(name)
        if server_name:
            try:
                from app.database import get_session_for, get_db_mode
                from app.models import MCPServer
                session = get_session_for(get_db_mode())()
                srv = session.query(MCPServer).filter(MCPServer.name == server_name).first()
                try:
                    from app.services import mcp_external
                    tool_name = name.split(":", 1)[1] if ":" in name else name
                    result = mcp_external.call_external_tool(srv, tool_name, arguments)
                    return {"status": "success", "result": result, "external": True}
                finally:
                    session.close()
            except Exception as e:
                return {"status": "error", "message": f"外部工具 {name} 调用失败: {e}"}
        return {"status": "error", "message": f"Tool '{name}' not found"}
    # 安全防护：非暴露给 LLM 的工具（如 execute_*）仅允许内部确认路径调用，
    # 阻止 LLM 在 tool_call 中构造名称直调，绕过 PendingAction 确认闭环
    if not tool.expose_to_llm and not allow_internal:
        return {"status": "error", "message": f"Tool '{name}' is internal-only and cannot be called directly"}

    # ── 限流（滑动窗口）──
    if not _ratelimit_allow(name, tool.ratelimit_per_minute):
        return {"status": "error", "message": f"Tool '{name}' 触发限流（>={tool.ratelimit_per_minute}/min）"}

    timeout = timeout_override or tool.timeout

    def _run():
        # 超时路径在独立线程中执行，为线程安全给工具一个独立的 DB session：
        # SQLAlchemy Session 非线程安全，不能跨线程共享调用方 session。
        # 传 db=None 时工具内部会自建 session 并自管关闭；否则需在此自建并关闭。
        session = db
        close_session = False
        if db is not None:
            from app.database import get_session_for, get_db_mode
            try:
                session = get_session_for(get_db_mode())()
                close_session = True
            except Exception:
                session = db
        try:
            return tool.handler(db=session, user_id=user_id, **arguments)
        finally:
            if close_session:
                try:
                    session.close()
                except Exception:
                    pass

    if timeout and timeout > 0:
        # ── 工具级超时（对齐 Ongrid agent.go:631 15s 超时）──
        executor = ThreadPoolExecutor(max_workers=1, thread_name_prefix=f"tool_{name}")
        future = executor.submit(_run)
        try:
            result = future.result(timeout=timeout)
        except FutureTimeout:
            executor.shutdown(wait=False)
            return {
                "status": "error",
                "message": f"Tool '{name}' 执行超时（>{timeout}s）",
                "timeout": True,
                "tool_name": name,
            }
        except Exception as e:
            executor.shutdown(wait=False)
            return {"status": "error", "message": str(e)}
        finally:
            executor.shutdown(wait=False)
    else:
        try:
            result = _run()
        except Exception as e:
            return {"status": "error", "message": str(e)}

    # ── 工具审计（audit decorator）──
    if tool.audit_enabled:
        _write_tool_audit(name, arguments, result, user_id, db)

    return {"status": "success", "result": result}


def init_builtin_mcp_tools():
    """Initialize tools that are registered via decorator on import."""
    pass
