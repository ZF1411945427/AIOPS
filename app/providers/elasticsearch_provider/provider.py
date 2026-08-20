import json
from dataclasses import dataclass, field
from datetime import datetime
from typing import Any

from app.providers.base import BaseProvider, BaseAuthConfig, ProviderMeta, ProviderCategory


@dataclass
class ElasticsearchAuthConfig(BaseAuthConfig):
    endpoint: str = field(default="", metadata={"required": True, "description": "Elasticsearch HTTP 地址(如 http://10.0.0.1:9200)"})
    username: str = field(default="", metadata={"description": "ES 用户名"})
    password: str = field(default="", metadata={"sensitive": True, "description": "ES 密码"})
    api_key: str = field(default="", metadata={"sensitive": True, "description": "ES API Key(base64)"})


class ElasticsearchProvider(BaseProvider):
    PROVIDER_META = ProviderMeta(
        name="elasticsearch",
        display_name="Elasticsearch",
        category=ProviderCategory.DATA_SOURCE,
        description="对接 Elasticsearch 采集集群健康、索引统计、分片信息等指标",
        tags=["elasticsearch", "search", "logs", "metrics"],
        icon="📊",
        docs_url="https://www.elastic.co/guide/en/elasticsearch/reference/current",
        auth_config_class=ElasticsearchAuthConfig,
    )

    def test_connection(self) -> tuple[bool, str]:
        try:
            from elasticsearch import Elasticsearch
        except ImportError:
            return False, "缺少 elasticsearch Python 包"
        try:
            es = self._build_client()
            info = es.info()
            es.close()
            version = info.get("version", {}).get("number", "?")
            cluster_name = info.get("cluster_name", "?")
            return True, f"ES 连接成功, version={version}, cluster={cluster_name}"
        except Exception as e:
            return False, f"ES 连接失败: {e}"

    def scrape(self, db: Any = None) -> list[dict]:
        try:
            from elasticsearch import Elasticsearch
        except ImportError:
            return []
        results = []
        now = datetime.now()
        es = None
        try:
            es = self._build_client()
            info = es.info()
            cluster_uuid = info.get("cluster_uuid", "")
            cluster_name = info.get("cluster_name", "")

            results.extend(self._save_metric(db, cluster_name, "es_cluster_nodes", float(info.get("number_of_nodes", 0)), "nodes", now))
            results.extend(self._save_metric(db, cluster_name, "es_cluster_data_nodes", float(info.get("number_of_data_nodes", 0)), "nodes", now))

            indices = es.cat.indices(format="json")
            total_docs = 0
            total_size = 0
            index_count = len(indices)
            for idx in indices:
                total_docs += int(idx.get("docs.count", 0) or 0)
                store_size = idx.get("store.size", "0b")
                total_size += self._parse_size(store_size)
            results.extend(self._save_metric(db, cluster_name, "es_indices", float(index_count), "indices", now))
            results.extend(self._save_metric(db, cluster_name, "es_docs_total", float(total_docs), "docs", now))
            results.extend(self._save_metric(db, cluster_name, "es_store_size_bytes", float(total_size), "bytes", now))

            health = es.cluster.health()
            health_val = {"green": 2, "yellow": 1, "red": 0}.get(health.get("status", ""), 0)
            results.extend(self._save_metric(db, cluster_name, "es_health_status", float(health_val), "", now))
            results.extend(self._save_metric(db, cluster_name, "es_active_shards", float(health.get("active_shards", 0)), "shards", now))
            results.extend(self._save_metric(db, cluster_name, "es_relocating_shards", float(health.get("relocating_shards", 0)), "shards", now))
            results.extend(self._save_metric(db, cluster_name, "es_unassigned_shards", float(health.get("unassigned_shards", 0)), "shards", now))

            results.append({
                "kind": "summary",
                "cluster": cluster_name,
                "cluster_uuid": cluster_uuid,
                "indices": index_count,
                "docs": total_docs,
                "health": health.get("status", "?"),
                "timestamp": now,
            })
        finally:
            if es:
                try:
                    es.close()
                except Exception:
                    pass
        return results

    def _build_client(self):
        from elasticsearch import Elasticsearch
        endpoint = self.auth_config.endpoint or self.endpoint or ""
        if not endpoint:
            raise ValueError("ES endpoint 未配置")
        if self.auth_config.api_key:
            return Elasticsearch(endpoint, api_key=self.auth_config.api_key, request_timeout=30)
        if self.auth_config.username and self.auth_config.password:
            return Elasticsearch(endpoint, basic_auth=(self.auth_config.username, self.auth_config.password), request_timeout=30)
        return Elasticsearch(endpoint, request_timeout=30)

    def _save_metric(self, db: Any, host: str, name: str, value: float, unit: str, timestamp: datetime) -> list[dict]:
        record = {
            "kind": "metric",
            "name": name,
            "value": value,
            "unit": unit,
            "labels": {"host": host},
            "timestamp": timestamp,
        }
        if db is not None:
            from app.models import MetricRecord
            db.add(MetricRecord(
                name=name, value=value, unit=unit,
                timestamp=timestamp, labels=json.dumps({"host": host}, ensure_ascii=False),
            ))
        return [record]

    def _parse_size(self, val: str) -> float:
        val = val.strip()
        if val.endswith("tb") or val.endswith("Tb"):
            return float(val[:-2]) * 1024 ** 4
        if val.endswith("gb") or val.endswith("Gb"):
            return float(val[:-2]) * 1024 ** 3
        if val.endswith("mb") or val.endswith("Mb"):
            return float(val[:-2]) * 1024 ** 2
        if val.endswith("kb") or val.endswith("Kb"):
            return float(val[:-2]) * 1024
        if val.endswith("b"):
            return float(val[:-1])
        try:
            return float(val)
        except ValueError:
            return 0