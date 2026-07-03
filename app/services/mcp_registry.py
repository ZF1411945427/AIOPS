import json
from dataclasses import dataclass, field
from typing import Any, Callable, Dict, List, Optional


@dataclass
class MCPToolDef:
    name: str
    description: str
    input_schema: Dict[str, Any]
    handler: Callable
    risk_level: str = "read_only"
    expose_to_llm: bool = True


_MCP_TOOLS: Dict[str, MCPToolDef] = {}


def register_mcp_tool(
    name: str,
    description: str,
    input_schema: Optional[Dict[str, Any]] = None,
    risk_level: str = "read_only",
    expose_to_llm: bool = True,
):
    def decorator(func):
        _MCP_TOOLS[name] = MCPToolDef(
            name=name,
            description=description,
            input_schema=input_schema or {"type": "object", "properties": {}},
            handler=func,
            risk_level=risk_level,
            expose_to_llm=expose_to_llm,
        )
        return func

    return decorator


def get_mcp_manifest() -> List[Dict[str, Any]]:
    return [
        {
            "name": t.name,
            "description": t.description,
            "input_schema": t.input_schema,
            "risk_level": t.risk_level,
        }
        for t in _MCP_TOOLS.values()
        if t.expose_to_llm
    ]


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
) -> Dict[str, Any]:
    tool = get_mcp_tool(name)
    if not tool:
        return {"status": "error", "message": f"Tool '{name}' not found"}
    # 安全防护：非暴露给 LLM 的工具（如 execute_*）仅允许内部确认路径调用，
    # 阻止 LLM 在 tool_call 中构造名称直调，绕过 PendingAction 确认闭环
    if not tool.expose_to_llm and not allow_internal:
        return {"status": "error", "message": f"Tool '{name}' is internal-only and cannot be called directly"}
    try:
        result = tool.handler(db=db, user_id=user_id, **arguments)
        return {"status": "success", "result": result}
    except Exception as e:
        return {"status": "error", "message": str(e)}


def init_builtin_mcp_tools():
    """Initialize tools that are registered via decorator on import."""
    pass
