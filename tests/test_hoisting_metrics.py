"""Hoisting(工具重放健壮化) 与 tool_metrics(metric 装饰器) 单元测试(H3[B])。"""
import json
import os
import sys
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from app.services.agent_service import _hoist_tool_calls, _append_tool_results


def test_hoist_fills_missing_id():
    msg = {"tool_calls": [
        {"id": "", "function": {"name": "query_alerts", "arguments": "{\"limit\": 3}"}},
        {"function": {"name": "query_assets"}},  # 无 id
    ]}
    calls = _hoist_tool_calls(msg)
    assert calls[0]["id"]  # 有兜底 id
    assert calls[1]["id"]  # 补 id
    # 无 id 的补 hoist_N
    assert calls[0]["id"] != calls[1]["id"]
    # arguments 非法 JSON 兜底为 {}
    assert json.loads(calls[0]["function"]["arguments"])["limit"] == 3


def test_hoist_dedup_and_bad_arguments():
    msg = {"tool_calls": [
        {"id": "a", "function": {"name": "x", "arguments": "not-json"}},
    ]}
    calls = _hoist_tool_calls(msg)
    assert calls[0]["id"] == "a"
    assert json.loads(calls[0]["function"]["arguments"]) == {}  # 非法 JSON -> {}

def test_hoist_skips_empty_name():
    msg = {"tool_calls": [{"function": {"name": ""}}]}
    assert _hoist_tool_calls(msg) == []


def test_append_tool_results_by_id():
    assistant = {"tool_calls": [{"id": "tc1", "function": {"name": "query_alerts", "arguments": "{}"}}]}
    results = [{"tool_name": "query_alerts", "result": {"ok": True}, "tool_call_id": "tc1"}]
    msgs = []
    _append_tool_results(msgs, dict(assistant), results, name_key="tool_name")
    # msgs[0] = assistant msg, msgs[1] = tool result
    assert msgs[0]["tool_calls"][0]["id"] == "tc1"
    assert msgs[1]["role"] == "tool"
    assert msgs[1]["tool_call_id"] == "tc1"
    assert json.loads(msgs[1]["content"])["ok"] is True


def test_append_tool_results_matches_by_name_when_no_id():
    assistant = {"tool_calls": [{"id": "tc9", "function": {"name": "query_metrics", "arguments": "{}"}}]}
    results = [{"tool_name": "query_metrics", "result": {"count": 5}}]  # 无 tool_call_id
    msgs = []
    _append_tool_results(msgs, dict(assistant), results, name_key="tool_name")
    assert json.loads(msgs[1]["content"])["count"] == 5


def test_tool_metrics_record_render():
    from app.services import tool_metrics
    tool_metrics.record_tool("query_alerts", 12.5, True)
    tool_metrics.record_tool("query_alerts", 3.0, False)
    out = tool_metrics.render_tool_metrics([])
    assert any('aiops_tool_call_count{tool="query_alerts"} 2' in l for l in out)
    assert any('aiops_tool_error_count{tool="query_alerts"} 1' in l for l in out)
