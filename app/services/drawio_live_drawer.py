"""draw.io 集成服务：通过子进程驱动 node MCP server（drawio-file-utils），生成/打开/导出架构图。

原理: 启动 node server.mjs 作为子进程，通过 JSON-RPC over stdio 调用其工具。
server.mjs 来自 auto_sw_config/skills/drawio/，会在环境变量 DRAWIO_PATH 指定的路径下
找到 draw.io 桌面版并调用 drawio_open 打开文件。
"""

from __future__ import annotations

import json
import os
import subprocess
import threading
from pathlib import Path
from typing import Any, Dict

import logging
logger = logging.getLogger(__name__)

SKILLS_DRAWIO_DIR = Path(__file__).resolve().parent.parent.parent / "skills" / "drawio"
SERVER_SCRIPT = SKILLS_DRAWIO_DIR / "server.mjs"

_lock = threading.Lock()


class MCPClient:
    """极简 JSON-RPC over stdio 的 MCP 客户端，用于调用 node MCP server"""

    def __init__(self, script: Path, drawio_path: str):
        env = dict(os.environ)
        env["DRAWIO_PATH"] = drawio_path
        self.proc = subprocess.Popen(
            ["node", str(script)],
            stdin=subprocess.PIPE,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            cwd=str(script.parent),
            env=env,
            text=True,
            encoding="utf-8",
            bufsize=1,
        )
        self._id = 0
        self._lock = threading.Lock()

    def _request(self, method: str, params: dict) -> dict:
        with self._lock:
            self._id += 1
            rid = self._id
            payload = json.dumps({"jsonrpc": "2.0", "id": rid, "method": method, "params": params},
                                 ensure_ascii=False)
            self.proc.stdin.write(payload + "\n")
            self.proc.stdin.flush()
            while True:
                line = self.proc.stdout.readline()
                if not line:
                    raise RuntimeError("MCP server 已退出")
                line = line.strip()
                if not line:
                    continue
                try:
                    msg = json.loads(line)
                except json.JSONDecodeError:
                    continue
                if msg.get("id") == rid:
                    if "error" in msg:
                        raise RuntimeError(msg["error"].get("message", str(msg["error"])))
                    return msg.get("result") or {}

    def initialize(self):
        return self._request("initialize", {"protocolVersion": "2025-06-18"})

    def call_tool(self, name: str, args: dict) -> dict:
        return self._request("tools/call", {"name": name, "arguments": args})

    def close(self):
        try:
            self.proc.stdin.close()
        except Exception as _exc:
            logger.warning("[except:pass] Exception: %s", _exc, exc_info=True)
        try:
            self.proc.terminate()
        except Exception as _exc1:
            logger.warning("[except:pass] Exception: %s", _exc1, exc_info=True)


def _call_tool(name: str, args: dict, drawio_path: str) -> dict:
    """一次性调用：启动 server → 调用 → 关闭（幂等、无残留进程）"""
    client = MCPClient(SERVER_SCRIPT, drawio_path)
    try:
        client.initialize()
        result = client.call_tool(name, args)
        return _extract(result)
    finally:
        client.close()


def _extract(result: dict) -> dict:
    if isinstance(result, dict) and "structuredContent" in result:
        return result["structuredContent"] or {}
    content = result.get("content") or []
    text = "\n".join(c.get("text", "") for c in content if c.get("type") == "text")
    try:
        return json.loads(text) if text.strip().startswith("{") else {"text": text}
    except json.JSONDecodeError:
        return {"text": text}


def open_drawio(file_path: str, drawio_path: str) -> dict:
    """在 draw.io 桌面版中打开已生成的 .drawio 文件。

    返回: {"ok": True/False, "message": str}
    """
    if not Path(drawio_path).exists():
        return {"ok": False, "message": f"draw.io 路径不存在: {drawio_path}"}
    if not Path(file_path).exists():
        return {"ok": False, "message": f".drawio 文件不存在: {file_path}"}
    try:
        result = _call_tool("drawio_open", {"input_path": file_path}, drawio_path)
        return {"ok": True, "message": "已打开 draw.io", "detail": result}
    except Exception as e:
        return {"ok": False, "message": f"打开 draw.io 失败: {e}"}


def generate_and_open(drawio_path: str, domain: str, db) -> Dict[str, Any]:
    """完整流程: AI 分析 → 生成 .drawio → 打开 draw.io 桌面版。

    返回:
    {
        "ok": True/False,
        "message": str,
        "ai_analysis": str,
        "ai_suggestions": str,
        "drawio_download": str,  (可选, 文件下载 URL)
    }
    """
    from app.models import AssetRelation
    from app.services import drawio_generator as dg
    from app.services.drawio_ai_planner import ai_layout_plan, apply_ai_scores, _pick_provider

    assets = dg.collect_domain_assets(db, domain)
    relations = db.query(AssetRelation).all()

    if not assets:
        return {"ok": False, "message": f"业务域 '{domain}' 下没有资产"}

    # AI 分析
    provider = _pick_provider(db)
    ai_result = None
    ai_scores = None
    if provider:
        ai_result = ai_layout_plan(domain, assets, relations, provider=provider)
        if ai_result.get("ok"):
            ai_scores = apply_ai_scores(assets, ai_result.get("node_order", {}))

    # 生成 .drawio 文件
    xml = dg.build_drawio_xml(domain, assets, relations,
                              diagram_title=f"{domain} - 系统架构图",
                              ai_scores=ai_scores)
    safe = "".join(c if c.isalnum() or c in "_-." else "_" for c in domain) or "domain"
    drawio_file = dg.write_drawio_file(xml, f"arch-{safe}.drawio")

    result = {
        "ok": True,
        "message": f"已生成架构图: {len(assets)} 个资产, {len(relations)} 条关系",
        "drawio_download": f"/api/arch-diagram/file/{drawio_file.name}",
    }

    if ai_result and ai_result.get("ok"):
        result["ai_analysis"] = ai_result.get("analysis", "")
        result["ai_suggestions"] = ai_result.get("suggestions", "")

    # 打开 draw.io 桌面版
    open_result = open_drawio(str(drawio_file), drawio_path)
    result["live_ok"] = open_result.get("ok", False)
    result["live_message"] = open_result.get("message", "")

    return result