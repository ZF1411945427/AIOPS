"""外部 MCP 服务器客户端(P1-5) - HTTP JSON-RPC / SSE, 把外部工具并入 Agent。

契约: CONTRACT.md(见外部 MCP 节)。支持 MCP(Model Context Protocol)标准的
`tools/list` 与 `tools/call` 方法(HTTP transport + 可选 SSE)。零外部依赖(urllib)。
外部工具名以 `<server>:<tool>` 前缀隔离,避免与内置工具冲突。
"""
import json
import urllib.request
from typing import Any, Dict, List

from app.models import MCPServer

_DEFAULT_TIMEOUT = 15


def _auth_headers(server: MCPServer) -> Dict[str, str]:
    """从 auth_config 派生认证头(支持 api_key / bearer)。"""
    h: Dict[str, str] = {"Content-Type": "application/json"}
    try:
        cfg = json.loads(server.auth_config) if server.auth_config else {}
    except Exception:
        cfg = {}
    if not isinstance(cfg, dict):
        cfg = {}
    if cfg.get("super_secret_value"):
        from app.services.secret_vault import resolve_secret_refs
        v = resolve_secret_refs(cfg["super_secret_value"], None)
    else:
        v = None
    key = v or cfg.get("api_key") or cfg.get("token") or cfg.get("bearer")
    if key:
        h["Authorization"] = f"Bearer {key}"
    return h


def _rpc_call(server: MCPServer, method: str, params: dict, timeout: int = _DEFAULT_TIMEOUT) -> dict:
    """向 MCP http endpoint 发 JSON-RPC 请求。返回 result 或抛 ValueError。"""
    endpoint = (server.endpoint or "").strip()
    if not endpoint:
        raise ValueError(f"服务器 {server.name} 未配置 endpoint")
    body = json.dumps({"jsonrpc": "2.0", "id": 1, "method": method, "params": params}).encode()
    req = urllib.request.Request(endpoint, data=body, method="POST", headers=_auth_headers(server))
    try:
        with urllib.request.urlopen(req, timeout=timeout) as resp:
            data = json.loads(resp.read().decode("utf-8", "replace"))
    except Exception as e:
        raise ValueError(f"调用外部 MCP {server.name} 失败: {e}")
    if data.get("error"):
        raise ValueError(f"MCP 错误: {data['error']}")
    return data.get("result") or {}


def server_tools(server: MCPServer) -> List[Dict[str, Any]]:
    """获取单台服务器工具清单。"""
    result = _rpc_call(server, "tools/list", {})
    tools = result.get("tools") or []
    try:
        wl = json.loads(server.tool_whitelist) if server.tool_whitelist else []
    except Exception:
        wl = []
    if wl:
        tools = [t for t in tools if t.get("name") in wl]
    return tools


def fetch_external_manifest(server: MCPServer) -> List[Dict[str, Any]]:
    """把外部工具转成与 get_mcp_manifest 兼容的 manifest 条目(带前缀)。"""
    out = []
    for t in server_tools(server):
        schema = t.get("inputSchema") or {}
        out.append({
            "name": f"{server.name}:{t.get('name')}",
            "display_name": t.get("name"),
            "description": f"[外部MCP/{server.name}] {t.get('description') or ''}",
            "input_schema": schema,
            "risk_level": "read_only",  # 外部工具默认只读视角, 实际风险由 server 端承担
            "location": "cloud",
            "category": "mcp_external",
            "safe": True,
            "read_only": True,
            "ai_only": True,
            "external": True,
        })
    return out


def call_external_tool(server: MCPServer, tool_name: str, arguments: dict) -> Dict[str, Any]:
    """调用外部工具。返回 MCP result(通常含 content 数组)。"""
    result = _rpc_call(server, "tools/call", {"name": tool_name, "arguments": arguments or {}})
    return result


# ─── 聚合: 供 get_mcp_manifest / call_mcp_tool 钩子使用 ───────────
_cache_lock_cache: Dict[str, Any] = {}


def external_manifests(db=None) -> Dict[str, List[Dict[str, Any]]]:
    """返回 {server_name: [manifest条目]}，仅启用且非 builtin 的外部服务器。"""
    if db is None:
        return {}
    out: Dict[str, List[Dict[str, Any]]] = {}
    servers = db.query(MCPServer).filter(
        MCPServer.is_enabled == True, MCPServer.is_builtin == False,       # noqa: E712
        MCPServer.server_type == MCPServer.TYPE_HTTP).all()
    for s in servers:
        try:
            out[s.name] = fetch_external_manifest(s)
        except Exception:
            continue  # 单台失败不影响其他
    return out


def flatten_external_manifest(external: Dict[str, List[Dict[str, Any]]]) -> List[Dict[str, Any]]:
    flat = []
    for _, items in external.items():
        flat.extend(items)
    return flat


def reload_external_tools(db=None):
    """清空并重载所有启用的外部 MCP 工具到 mcp_registry(启动/CRUD 后调用)。"""
    from app.services import mcp_registry
    mcp_registry.clear_external_tools()
    if db is None:
        return 0
    servers = db.query(MCPServer).filter(
        MCPServer.is_enabled == True, MCPServer.is_builtin == False,       # noqa: E712
        MCPServer.server_type == MCPServer.TYPE_HTTP).all()
    count = 0
    for s in servers:
        try:
            for entry in fetch_external_manifest(s):
                mcp_registry.register_external_tool(entry, s.name)
                count += 1
        except Exception:
            continue
    return count
