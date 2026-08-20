import json
import urllib.parse
import urllib.request
from dataclasses import dataclass, field
from datetime import datetime
from typing import Any

from app.providers.base import BaseProvider, BaseAuthConfig, ProviderMeta, ProviderCategory


@dataclass
class PrometheusAuthConfig(BaseAuthConfig):
    endpoint: str = field(default="", metadata={"required": True, "description": "Prometheus API 地址(如 http://10.0.0.1:9090)"})
    auth_type: str = field(default="none", metadata={"description": "认证方式(none/basic/bearer)"})
    api_token: str = field(default="", metadata={"sensitive": True, "description": "API Token(Bearer)"})


class PrometheusProvider(BaseProvider):
    PROVIDER_META = ProviderMeta(
        name="prometheus",
        display_name="Prometheus",
        category=ProviderCategory.MONITORING,
        description="对接 Prometheus 拉取节点 CPU/内存/磁盘等监控指标",
        tags=["prometheus", "monitoring", "metrics"],
        icon="🔥",
        docs_url="https://prometheus.io/docs",
        auth_config_class=PrometheusAuthConfig,
    )

    _QUERIES = {
        "cpu_usage": "100 - (avg(rate(node_cpu_seconds_total{mode=\"idle\"}[5m])) * 100)",
        "memory_usage": "100 * (1 - node_memory_MemAvailable_bytes / node_memory_MemTotal_bytes)",
        "disk_usage": "100 * (1 - node_filesystem_avail_bytes{mountpoint=\"/\"} / node_filesystem_size_bytes{mountpoint=\"/\"})",
    }

    def test_connection(self) -> tuple[bool, str]:
        try:
            endpoint = (self.auth_config.endpoint or self.endpoint or "").rstrip("/")
            if not endpoint:
                return False, "Prometheus endpoint 未配置"
            url = f"{endpoint}/api/v1/query?query=" + urllib.parse.quote("up")
            req = urllib.request.Request(url, headers=self._headers())
            with urllib.request.urlopen(req, timeout=10) as resp:
                data = json.loads(resp.read().decode("utf-8"))
            if data.get("status") != "success":
                return False, f"Prometheus 响应异常: {data.get('warning') or data.get('error') or 'unknown'}"
            results = data.get("data", {}).get("result", [])
            return True, f"Prometheus 连接正常, 检测到 {len(results)} 个 up 目标"
        except Exception as e:
            return False, f"Prometheus 连接失败: {e}"

    def scrape(self, db: Any = None) -> list[dict]:
        results = []
        endpoint = (self.auth_config.endpoint or self.endpoint or "").rstrip("/")
        if not endpoint:
            return results
        now = datetime.now()
        for name, query in self._QUERIES.items():
            try:
                url = f"{endpoint}/api/v1/query?query=" + urllib.parse.quote(query)
                req = urllib.request.Request(url, headers=self._headers())
                with urllib.request.urlopen(req, timeout=10) as resp:
                    data = json.loads(resp.read().decode("utf-8"))
                for r in data.get("data", {}).get("result", []):
                    value = float(r.get("value", [0, "0"])[1])
                    labels = r.get("metric", {})
                    record = {
                        "name": name,
                        "value": value,
                        "unit": "%",
                        "labels": {"host": labels.get("instance", ""), "job": labels.get("job", "")},
                        "timestamp": now,
                    }
                    results.append(record)
                    self._save_metric(db, labels.get("instance", self.source_id), name, value, "%", now)
            except Exception as e:
                import logging
                logging.getLogger(__name__).warning("[providers.prometheus] query %s failed: %s", name, e)
        return results

    def _headers(self) -> dict:
        headers = {"Accept": "application/json"}
        if self.auth_config.api_token:
            headers["Authorization"] = f"Bearer {self.auth_config.api_token}"
        return headers

    def _save_metric(self, db: Any, host: str, name: str, value: float, unit: str, timestamp: datetime):
        if db is None:
            return
        from app.models import MetricRecord
        db.add(MetricRecord(
            name=name, value=value, unit=unit,
            timestamp=timestamp, labels=json.dumps({"host": host}, ensure_ascii=False),
        ))