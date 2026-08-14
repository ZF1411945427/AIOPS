"""ToolBag 二级延迟加载逻辑单测: 核心工具全量 / 专业工具降级 / 按需搜索。"""
import json
import os

from app.services import mcp_registry as mr


def _load_all_tools():
    import app.services.mcp_tools  # noqa: F401 — 触发全部内置工具注册
    import app.services.toolbag_mcp_tools  # noqa: F401


def test_toolbag_disabled_default_is_full():
    _load_all_tools()
    os.environ.pop("AIOPS_TOOLBAG", None)
    manifest = mr.get_mcp_manifest()
    assert len(manifest) > 30
    assert all("input_schema" in t for t in manifest if not t.get("external"))
    assert not any(t.get("deferred") for t in manifest)


def test_toolbag_env_enables_defer():
    _load_all_tools()
    os.environ["AIOPS_TOOLBAG"] = "1"
    try:
        manifest = mr.get_mcp_manifest()
    finally:
        os.environ.pop("AIOPS_TOOLBAG", None)
    assert any(t.get("deferred") for t in manifest)


def test_core_tools_stay_full_schema():
    _load_all_tools()
    os.environ["AIOPS_TOOLBAG"] = "1"
    try:
        manifest = mr.get_mcp_manifest()
    finally:
        os.environ.pop("AIOPS_TOOLBAG", None)
    core = [t for t in manifest if not t.get("deferred")]
    assert core, "核心工具不应被降级"
    assert all("input_schema" in t for t in core)
    names = {t["name"] for t in manifest}
    assert "query_assets" in names


def test_deferred_payload_is_smaller():
    _load_all_tools()
    full = mr.get_mcp_manifest(defer=False)
    deferred = mr.get_mcp_manifest(defer=True)
    full_bytes = len(json.dumps(full, ensure_ascii=False))
    defer_bytes = len(json.dumps(deferred, ensure_ascii=False))
    assert defer_bytes < full_bytes


def test_search_tools_returns_full_schema():
    _load_all_tools()
    results = mr.search_tools("alert")
    assert results, "搜索 alert 应有结果"
    for t in results:
        assert "input_schema" in t
        assert "name" in t


def test_search_tools_name_boost():
    _load_all_tools()
    os.environ["AIOPS_TOOLBAG"] = "1"
    try:
        results = mr.search_tools("query_assets")
    finally:
        os.environ.pop("AIOPS_TOOLBAG", None)
    assert results[0]["name"] == "query_assets"


def test_get_deferred_tool_schema():
    _load_all_tools()
    schema = mr.get_deferred_tool_schema("query_alerts")
    assert schema is not None
    assert schema["name"] == "query_alerts"
    assert "input_schema" in schema
    assert mr.get_deferred_tool_schema("nonexistent_tool_xyz") is None


def test_load_tool_schema_mcp_tool_registered():
    _load_all_tools()
    names = {t["name"] for t in mr.get_mcp_manifest()}
    assert "search_tools" in names
    assert "load_tool_schema" in names
