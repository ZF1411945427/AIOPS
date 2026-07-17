"""
Synthetic Monitoring — 主动拨测服务
定期检查核心系统端点，将结果写入 VictoriaMetrics，用于 Grafana 级别监控看板展示。
"""
import time
import requests
from datetime import datetime
from typing import Optional

from app.services.metric_v2_service import write_metrics_batch, is_vm_available

_PROBE_TIMEOUT = 10
_SESSION = requests.Session()
_SESSION.timeout = _PROBE_TIMEOUT

# 拨测目标：系统核心端点
_PROBE_TARGETS = [
    {"name": "api_healthz", "url": "http://127.0.0.1:8000/healthz", "method": "GET"},
    {"name": "api_readyz", "url": "http://127.0.0.1:8000/readyz", "method": "GET"},
    {"name": "victoria_metrics", "url": "http://127.0.0.1:8428/health", "method": "GET"},
]


def run_synthetic_probes():
    """执行一轮拨测，将结果写入 VM."""
    if not is_vm_available():
        return

    now = datetime.now()
    batch = []
    for target in _PROBE_TARGETS:
        name = target["name"]
        url = target["url"]
        method = target.get("method", "GET")
        start = time.time()
        status = 0
        latency_ms = 0
        try:
            if method == "GET":
                resp = _SESSION.get(url)
            else:
                resp = _SESSION.post(url)
            status = resp.status_code
            latency_ms = round((time.time() - start) * 1000, 1)
        except Exception:
            status = 0
            latency_ms = round((time.time() - start) * 1000, 1)

        is_up = 1 if (200 <= status < 400) else 0
        batch.append({"name": f"synthetic_{name}_latency_ms", "value": latency_ms, "timestamp": now, "labels": {"target": name, "method": method}})
        batch.append({"name": f"synthetic_{name}_up", "value": is_up, "timestamp": now, "labels": {"target": name, "method": method}})
        batch.append({"name": f"synthetic_{name}_status", "value": status, "timestamp": now, "labels": {"target": name, "method": method}})

    if batch:
        write_metrics_batch(batch)


def check_all_synthetics(db=None):
    """供后台循环调用的入口."""
    run_synthetic_probes()
