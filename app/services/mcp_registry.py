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


_MCP_TOOLS: Dict[str, MCPToolDef] = {}


def register_mcp_tool(
    name: str,
    description: str,
    input_schema: Optional[Dict[str, Any]] = None,
    risk_level: str = "read_only",
):
    def decorator(func):
        _MCP_TOOLS[name] = MCPToolDef(
            name=name,
            description=description,
            input_schema=input_schema or {"type": "object", "properties": {}},
            handler=func,
            risk_level=risk_level,
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
    ]


def get_mcp_tool(name: str) -> Optional[MCPToolDef]:
    return _MCP_TOOLS.get(name)


def call_mcp_tool(name: str, arguments: Dict[str, Any], db=None, user_id: int = None) -> Dict[str, Any]:
    tool = get_mcp_tool(name)
    if not tool:
        return {"status": "error", "message": f"Tool '{name}' not found"}
    try:
        result = tool.handler(db=db, user_id=user_id, **arguments)
        return {"status": "success", "result": result}
    except Exception as e:
        return {"status": "error", "message": str(e)}


def init_builtin_mcp_tools():
    """Initialize tools that are registered via decorator on import."""
    pass
