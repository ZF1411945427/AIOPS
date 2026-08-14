"""工具级指标(H3[B] 对齐 on-grid decorators/metric): per-tool 调用数/错误/延迟。

新增 `tool_metric` 装饰器标记的工具会在 call_mcp_tool 内记录指标, 由 render_tool_metrics
输出到 /metrics(Prometheus text)。低开销内存计数, 零外部依赖。
"""
import threading
from collections import defaultdict

_lock = threading.Lock()
_counts = defaultdict(lambda: {"call_count": 0, "error_count": 0, "latency_sum": 0.0})


def record_tool(tool_name: str, latency_ms: float, ok: bool) -> None:
    with _lock:
        c = _counts[tool_name]
        c["call_count"] += 1
        c["latency_sum"] += latency_ms
        if not ok:
            c["error_count"] += 1


def render_tool_metrics(lines: list) -> list:
    with _lock:
        data = dict(_counts)
    total_calls = sum(c["call_count"] for c in data.values())
    lines.append("# HELP aiops_tool_call_count Total MCP tool invocations")
    lines.append("# TYPE aiops_tool_call_count counter")
    for name, c in sorted(data.items()):
        lines.append(f'aiops_tool_call_count{{tool="{_esc(name)}"}} {c["call_count"]}')
    lines.append("# HELP aiops_tool_error_count MCP tool errors")
    lines.append("# TYPE aiops_tool_error_count counter")
    for name, c in sorted(data.items()):
        lines.append(f'aiops_tool_error_count{{tool="{_esc(name)}"}} {c["error_count"]}')
    if total_calls:
        lines.append("# HELP aiops_tool_total_calls Sum of tool calls")
        lines.append("# TYPE aiops_tool_total_calls counter")
        lines.append(f"aiops_tool_total_calls {total_calls}")
    return lines


def _esc(s: str) -> str:
    return s.replace('"', '\\"').replace("\\", "\\\\")
