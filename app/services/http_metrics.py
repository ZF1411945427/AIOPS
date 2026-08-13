"""应用级 HTTP 请求指标(D2 增强): 内存计数器 + Prometheus text 输出。

提供 HttpMetricsMiddleware(记录按 path 的请求总数/错误数/延迟累计/并发)
与 render_http_metrics()(输出 Prometheus exposition 文本)。
零外部依赖;内存字典计数(非线程安全临界由 GIL 保护)。
"""
import threading
import time
from collections import defaultdict

_lock = threading.Lock()
# path -> dict(request_count, error_count, latency_sum, configured)
_counts = defaultdict(lambda: {"request_count": 0, "error_count": 0, "latency_sum": 0.0, "configured": 0})

_SKIP_PATHS = {"/metrics", "/healthz", "/readyz"}


class HttpMetricsMiddleware:
    """包裹每个请求, 记录耗时/是否错误。注册在最外层(最先执行)。"""

    def __init__(self, app):
        self.app = app

    async def __call__(self, scope, receive, send):
        if scope["type"] != "http":
            return await self.app(scope, receive, send)
        path = scope.get("path", "")
        if path in _SKIP_PATHS:
            return await self.app(scope, receive, send)
        start = time.perf_counter()
        status = [200]

        async def _send_wrapper(message):
            if message["type"] == "http.response.start":
                status[0] = message.get("status", 200)
            await send(message)

        try:
            await self.app(scope, receive, _send_wrapper)
        finally:
            dur = (time.perf_counter() - start) * 1000  # ms
            with _lock:
                c = _counts[path]
                c["request_count"] += 1
                c["latency_sum"] += dur
                if status[0] >= 500 or status[0] == 0:
                    c["error_count"] += 1


def _metrics_dict() -> dict:
    with _lock:
        return {p: dict(c) for p, c in _counts.items()}


def render_http_metrics(lines: list) -> list:
    """把 HTTP 指标已追加进 Prometheus 文本行列表。"""
    data = _metrics_dict()
    # 拓扑: 按归一化 path(去动态 id) 聚合 —— 直接用原始 path, 避免过度聚合丢失语义
    total_req = sum(c["request_count"] for c in data.values())
    total_err = sum(c["error_count"] for c in data.values())
    total_lat = sum(c["latency_sum"] for c in data.values())

    lines.append("# HELP aiops_http_request_count Total HTTP requests processed")
    lines.append("# TYPE aiops_http_request_count counter")
    lines.append(f"aiops_http_request_count {total_req}")
    lines.append("# HELP aiops_http_error_count HTTP 5xx/unknown errors")
    lines.append("# TYPE aiops_http_error_count counter")
    lines.append(f"aiops_http_error_count {total_err}")
    lines.append("# HELP aiops_http_latency_ms_total Accumulated latency in ms across all requests")
    lines.append("# TYPE aiops_http_latency_ms_total counter")
    lines.append(f"aiops_http_latency_ms_total {total_lat:.0f}")
    if total_req:
        lines.append("# HELP aiops_http_avg_latency_ms Average request latency in ms")
        lines.append("# TYPE aiops_http_avg_latency_ms gauge")
        lines.append(f"aiops_http_avg_latency_ms {(total_lat / total_req):.2f}")
        lines.append("# HELP aiops_http_error_ratio Ratio of failed requests")
        lines.append("# TYPE aiops_http_error_ratio gauge")
        lines.append(f"aiops_http_error_ratio {(total_err / total_req):.4f}")
    return lines
