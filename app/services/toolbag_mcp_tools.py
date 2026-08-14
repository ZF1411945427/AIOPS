"""ToolBag 工具检索 MCP 工具(对齐 Ongrid tools/toolbag.go 的 ToolSearch)。

AIOPS_TOOLBAG=1 降级模式下, 专业工具只暴露紧凑摘要, LLM 需调用本工具
按关键词搜索并加载完整 JSON Schema 后才能正确传参。

依赖 mcp_registry: search_tools / get_deferred_tool_schema。
"""
from app.services.mcp_registry import register_mcp_tool
from app.services.mcp_registry import get_deferred_tool_schema
from app.services.mcp_registry import search_tools


@register_mcp_tool(
    name="search_tools",
    description=(
        "搜索并按需加载工具的完整调用参数(JSON Schema)。"
        "当遇到 deferred=True 的工具摘要、或不确定某个工具的确切参数时,"
        "请先调用本工具搜索工具名/功能关键词, 再按返回的 input_schema 传参。"
    ),
    input_schema={
        "type": "object",
        "properties": {
            "query": {"type": "string", "description": "搜索关键词(工具名/功能/分类, 如 'asset' 'alert' 'metrics')"},
            "limit": {"type": "integer", "description": "最多返回工具数, 默认 8"},
        },
        "required": ["query"],
    },
    risk_level="read_only",
    display_name="搜索工具",
    location="cloud",
    category="general",
)
def _search_tools(db=None, user_id=None, **kwargs):
    query = str(kwargs.get("query") or "")
    try:
        limit = int(kwargs.get("limit") or 8)
    except (TypeError, ValueError):
        limit = 8
    results = search_tools(query, limit=limit)
    return {"total": len(results), "query": query, "tools": results}


@register_mcp_tool(
    name="load_tool_schema",
    description="按工具名加载单个工具的完整调用参数(JSON Schema)。用于 ToolBag 降级模式下确认某工具确切参数后再调用。",
    input_schema={
        "type": "object",
        "properties": {
            "name": {"type": "string", "description": "工具名(与工具清单中的 name 一致)"},
        },
        "required": ["name"],
    },
    risk_level="read_only",
    display_name="加载工具参数",
    location="cloud",
    category="general",
)
def _load_tool_schema(db=None, user_id=None, **kwargs):
    name = str(kwargs.get("name") or "").strip()
    if not name:
        return {"status": "error", "message": "缺少工具名 name"}
    schema = get_deferred_tool_schema(name)
    if not schema:
        return {"status": "error", "message": f"工具 {name} 不存在或不可见"}
    return schema
