"""Tempo 查询代理 — 从 Tempo Query Frontend 拉取 trace 数据, 转成本系统前端期望的格式。

配置 AIOPS_TEMPO_QUERY_URL(如 http://tempo:3200) 后启用。
Traces API 优先从 Tempo 查询, 失败/未配置时回退 SQLite。

Tempo Query Frontend API(Tempo 2.x /api/*):
  - GET /api/search?limit=..&service=..  -> {"traces":[{traceID,rootServiceName,rootTraceName,startTimeUnixNano,durationMs}], "metrics":{...}}
  - GET /api/traces/{traceID}            -> {"batches":[{resource, scopeSpans:[{spans:[...]}]}]}
这里把 Tempo 结构映射成本系统前端期望的列表/详情格式。
"""
import base64
import os
from datetime import datetime, timezone, timedelta

_TEMPO_QUERY_URL = os.environ.get("AIOPS_TEMPO_QUERY_URL", "").strip()


def _epoch_ms_to_str(ms: int) -> str:
    if not ms:
        return ""
    try:
        dt = datetime.fromtimestamp(ms / 1000.0, tz=timezone(timedelta(hours=8)))
        return dt.strftime("%Y-%m-%d %H:%M:%S.%f")[:-3]
    except Exception:
        return ""


def _b64_decode_to_hex(b: str) -> str:
    try:
        return base64.b64decode(b).hex()
    except Exception:
        return b or ""


def _otlp_attr_to_pair(attr) -> tuple:
    """OTLP attribute dict -> (key, value)。"""
    try:
        key = attr.get("key", "")
        v = attr.get("value", {})
        if not isinstance(v, dict):
            return key, v
        for f in ("stringValue", "intValue", "doubleValue", "boolValue"):
            if f in v:
                return key, v[f]
        return key, ""
    except Exception:
        return "", ""


def is_tempo_enabled() -> bool:
    return bool(_TEMPO_QUERY_URL)


def search_traces(query_url: str, service: str = "", limit: int = 50, operation: str = "",
                  status: str = "", min_dur: float = 0, max_dur: float = 0) -> dict:
    """从 Tempo /api/search 拉取 trace 列表, 转成前端 trace 列表格式。"""
    import requests
    params = {"limit": min(int(limit), 1000)}
    if service:
        params["service"] = service
    resp = requests.get(f"{query_url}/api/search", params=params, timeout=10)
    resp.raise_for_status()
    data = (resp.json().get("traces") or []) or (resp.json().get("data") or [])

    traces = []
    for t in data:
        try:
            dur_ms = float(t.get("durationMs", 0) or 0)
            if t.get("durationNano"):
                dur_ms = float(t["durationNano"]) / 1e6
            if min_dur > 0 and dur_ms < min_dur:
                continue
            if max_dur > 0 and dur_ms > max_dur:
                continue
            start_ns = int(t.get("startTimeUnixNano", 0) or 0)
            traces.append({
                "trace_id": t.get("traceID", ""),
                "span_count": 1,
                "total_duration_ms": round(dur_ms, 1),
                "root_service": t.get("rootServiceName", ""),
                "root_operation": t.get("rootTraceName", ""),
                "started_at": _epoch_ms_to_str(int(start_ns / 1e6)) if start_ns else "",
                "worst_status": "OK",
            })
        except Exception:
            continue

    services = []
    try:
        ser = requests.get(f"{query_url}/api/services", timeout=5)
        services = [s for s in (ser.json().get("data") or []) if s]
    except Exception:
        pass

    return {"traces": traces, "services": services, "total": len(traces)}


def get_trace(query_url: str, trace_id: str) -> dict | None:
    """从 Tempo /api/traces/{id} 拉取单个 trace(batches 格式), 转前端详情格式。"""
    import requests
    resp = requests.get(f"{query_url}/api/traces/{trace_id}", timeout=15)
    if resp.status_code != 200:
        return None
    body = resp.json()
    batches = body.get("batches") or []
    if not batches:
        # 兼容老 Jaeger data 格式
        data = body.get("data") or []
        if data:
            return _parse_jaeger_trace(data[0], trace_id)
        return None

    span_list = []
    for batch in batches:
        resource = batch.get("resource", {}) or {}
        service_name = ""
        for attr in (resource.get("attributes") or []):
            k, v = _otlp_attr_to_pair(attr)
            if k == "service.name":
                service_name = str(v)
        for ss in (batch.get("scopeSpans") or []):
            for sp in (ss.get("spans") or []):
                dur_ns = 0
                try:
                    start_ns = int(sp.get("startTimeUnixNano", 0) or 0)
                    end_ns = int(sp.get("endTimeUnixNano", 0) or 0)
                    dur_ns = end_ns - start_ns
                except Exception:
                    start_ns = 0
                tags = {}
                for attr in (sp.get("attributes") or []):
                    k, v = _otlp_attr_to_pair(attr)
                    tags[k] = v
                status = sp.get("status", "")
                status_val = "ERROR" if "ERROR" in str(status).upper() else "OK"
                span_list.append({
                    "span_id": _b64_decode_to_hex(sp.get("spanId", "")),
                    "parent_span_id": _b64_decode_to_hex(sp.get("parentSpanId", "")),
                    "service_name": service_name,
                    "operation_name": sp.get("name", ""),
                    "started_at": _epoch_ms_to_str(start_ns / 1e6) if start_ns else "",
                    "duration_ms": round(dur_ns / 1e6, 1) if dur_ns else 0,
                    "status": status_val,
                    "tags": tags,
                })

    if not span_list:
        return None
    return _build_detail(trace_id, span_list)


def _parse_jaeger_trace(trace, trace_id: str) -> dict | None:
    """老 Jaeger data[0] 格式兼容。"""
    spans = trace.get("spans", []) or []
    span_list = []
    for s in spans:
        tags = {}
        for attr in (s.get("tags") or []):
            if isinstance(attr, dict):
                k = attr.get("key", "")
                v = attr.get("value", "")
                if isinstance(v, dict):
                    v = v.get("doubleValue") or v.get("stringValue") or v.get("boolValue") or ""
                tags[k] = v
        status = "ERROR" if _span_status_bad(s) else "OK"
        start_ns = s.get("startTime", 0) or 0
        span_list.append({
            "span_id": s.get("spanID", ""),
            "parent_span_id": s.get("parentSpanID", "") or "",
            "service_name": s.get("serviceName", ""),
            "operation_name": s.get("operationName", ""),
            "started_at": _epoch_ms_to_str(int(start_ns / 1e6)) if start_ns else "",
            "duration_ms": round((s.get("durationNano", 0) or 0) / 1e6, 1),
            "status": status,
            "tags": tags,
        })
    if not span_list:
        return None
    return _build_detail(trace_id, span_list)


def _span_status_bad(sp: dict) -> bool:
    try:
        st = sp.get("status", {}) or {}
        code = st.get("code", 0)
        msg = st.get("message", "")
        return bool(code and code != 0) or bool(msg and "error" in msg.lower())
    except Exception:
        return False


def _build_detail(trace_id: str, span_list: list) -> dict:
    services = list(dict.fromkeys(s["service_name"] for s in span_list if s["service_name"]))
    edges = []
    sid2svc = {s["span_id"]: s["service_name"] for s in span_list}
    seen = set()
    for s in span_list:
        if s["parent_span_id"]:
            psvc = sid2svc.get(s["parent_span_id"])
            if psvc and psvc != s["service_name"]:
                ek = f"{psvc}->{s['service_name']}"
                if ek not in seen:
                    seen.add(ek)
                    edges.append({"source": psvc, "target": s["service_name"]})
    root_start = ""
    root_dur = 0.0
    for s in span_list:
        if not s["parent_span_id"]:
            root_start = s["started_at"]
            root_dur = s["duration_ms"]
            break
    return {
        "trace_id": trace_id,
        "total_spans": len(span_list),
        "root_duration_ms": round(root_dur, 1),
        "root_start": root_start,
        "services": services,
        "spans": span_list,
        "topology": {"services": services, "edges": edges},
    }