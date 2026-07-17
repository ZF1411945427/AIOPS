"""
VictoriaMetrics 读写封装
所有指标写入 VM，查询走 VM PromQL 接口
"""
import requests
import threading
from datetime import datetime
from typing import Optional, List

VM_URL = "http://127.0.0.1:8428"
VM_WRITE_URL = f"{VM_URL}/api/v1/import/prometheus"
VM_QUERY_URL = f"{VM_URL}/api/v1/query"
VM_QUERY_RANGE_URL = f"{VM_URL}/api/v1/query_range"
VM_LABEL_URL = f"{VM_URL}/api/v1/labels"
VM_NAME_VALUES_URL = f"{VM_URL}/api/v1/label/__name__/values"
VM_SERIES_URL = f"{VM_URL}/api/v1/series"

_session = requests.Session()
_session.timeout = 5

_VM_WRITE_QUEUE: List[str] = []
_VM_WRITE_LOCK = threading.Lock()


def _build_prometheus_line(name: str, value: float, timestamp: datetime, labels: Optional[dict] = None, asset_id: Optional[int] = None) -> str:
    """构造 Prometheus exposition format 行，__name__ 是指标名约定."""
    label_parts = [f'__name__="{name}"']
    if asset_id is not None:
        label_parts.append(f'asset_id="{asset_id}"')
    if labels:
        for k, v in labels.items():
            label_parts.append(f'{k}="{v}"')
    label_str = "{" + ",".join(label_parts) + "}"
    ts_ms = int(timestamp.timestamp() * 1000)
    return f"{name}{label_str} {value} {ts_ms}\n"


def write_metric(name: str, value: float, timestamp: Optional[datetime] = None,
                 labels: Optional[dict] = None, asset_id: Optional[int] = None):
    """单条指标写入 VM（线程安全，批量写入前先排队）."""
    if timestamp is None:
        timestamp = datetime.now()
    line = _build_prometheus_line(name, value, timestamp, labels, asset_id)
    with _VM_WRITE_LOCK:
        _VM_WRITE_QUEUE.append(line)


def write_metrics_batch(metrics: List[dict]):
    """批量指标写入 VM，Prometheus 格式一次性发送，减少 HTTP 开销.

    metrics 格式: [{"name": str, "value": float, "timestamp": datetime,
                   "labels": dict, "asset_id": int}]
    """
    if not metrics:
        return
    lines = []
    for m in metrics:
        ts = m.get("timestamp") or datetime.now()
        lines.append(_build_prometheus_line(
            m["name"], m["value"], ts,
            m.get("labels"), m.get("asset_id")
        ))
    payload = "".join(lines)
    try:
        resp = _session.post(VM_WRITE_URL, data=payload.encode("utf-8"),
                             headers={"Content-Type": "application/x-protobuf"})
        if resp.status_code not in (204, 200):
            pass
    except Exception:
        pass


def query_promql(query: str, time: Optional[str] = None) -> dict:
    """执行 PromQL instant query，返回 VM 原生格式."""
    params = {"query": query}
    if time:
        params["time"] = time
    try:
        resp = _session.get(VM_QUERY_URL, params=params)
        if resp.status_code == 200:
            return resp.json()
        return {"status": "error", "error": f"HTTP {resp.status_code}"}
    except Exception as e:
        return {"status": "error", "error": str(e)}


def query_promql_range(query: str, start: int, end: int, step: str = "300s") -> dict:
    """执行 PromQL range query."""
    params = {"query": query, "start": start, "end": end, "step": step}
    try:
        resp = _session.get(VM_QUERY_RANGE_URL, params=params)
        if resp.status_code == 200:
            return resp.json()
        return {"status": "error", "error": f"HTTP {resp.status_code}"}
    except Exception as e:
        return {"status": "error", "error": str(e)}


def query_metric_names() -> List[str]:
    """查询 VM 中所有指标名."""
    try:
        resp = _session.get(VM_NAME_VALUES_URL)
        if resp.status_code == 200:
            data = resp.json()
            return data.get("data", [])
    except Exception:
        pass
    return []


def query_latest_values(asset_id: Optional[int] = None) -> dict:
    """查询最新指标值，返回格式兼容现有 SQLite 查询格式 {name: {value, unit, asset_id, timestamp}}."""
    try:
        if asset_id:
            query = f'{{asset_id="{asset_id}"}}'
        else:
            query = "{__name__=~\".+\"}"
        result = query_promql(query)
        if result.get("status") != "success":
            return {}
        out = {}
        for item in result.get("data", {}).get("result", []):
            metric = item.get("metric", {})
            name = metric.get("__name__", "")
            value = item.get("value")
            if value is not None and name:
                ts = value[0]
                out[name] = {
                    "value": float(value[1]),
                    "unit": metric.get("unit", ""),
                    "asset_id": int(metric.get("asset_id", 0)),
                    "timestamp": datetime.fromtimestamp(ts).isoformat() if ts else "",
                }
        return out
    except Exception:
        return {}


def query_range_data(asset_id: int, name: str, hours: int = 24) -> List[dict]:
    """查询指标历史范围数据，兼容 SQLite 格式 [{time, value, name, asset_id, unit}]."""
    now_s = int(datetime.now().timestamp())
    start_s = now_s - hours * 3600
    if asset_id and asset_id > 0:
        query = f'{name}{{asset_id="{asset_id}"}}'
    else:
        query = name
    result = query_promql_range(query, start_s, now_s, step="300s")
    if result.get("status") != "success":
        return []
    out = []
    for item in result.get("data", {}).get("result", []):
        metric = item.get("metric", {})
        values = item.get("values", [])
        aid = int(metric.get("asset_id", 0)) if metric.get("asset_id") else asset_id
        for ts, val in values:
            out.append({
                "time": datetime.fromtimestamp(ts).strftime("%Y-%m-%d %H:%M:%S"),
                "value": float(val),
                "name": name,
                "asset_id": aid,
                "unit": metric.get("unit", ""),
            })
    out.sort(key=lambda x: x["time"])
    return out


def is_vm_available() -> bool:
    """检查 VM 是否可达."""
    try:
        resp = _session.get(VM_URL, timeout=3)
        return resp.status_code == 200
    except Exception:
        return False
