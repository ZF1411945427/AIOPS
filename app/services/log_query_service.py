"""
LogQueryService — 多日志源查询引擎

设计原则：每种日志源一个 Adapter，注册到全局字典，零侵入扩展。
当前支持：Elasticsearch
待支持：Loki / ClickHouse / Splunk / Elastic（多集群）
"""

import re
from abc import ABC, abstractmethod
from datetime import datetime, timedelta
from typing import Any, Dict, List, Optional, Tuple


class LogQueryAdapter(ABC):
    """日志源适配器抽象基类"""

    @property
    @abstractmethod
    def source_type(self) -> str:
        """返回 DataSource.type 对应的标识符"""
        pass

    @abstractmethod
    def query(
        self,
        endpoint: str,
        auth_config: Dict[str, Any],
        mapping_config: Dict[str, Any],
        query: str,
        time_range: str,
        level: str,
        host: str,
        limit: int,
    ) -> Tuple[List[Dict], int, str]:
        """
        查询日志，返回 (logs, total_count, error_msg)
        logs 每条: {timestamp, level, host, service, message, source}
        error_msg 为空表示成功
        """
        pass


# ─── Elasticsearch Adapter ─────────────────────────────────────────

class ElasticsearchAdapter(LogQueryAdapter):
    source_type = "elasticsearch"

    def query(
        self,
        endpoint: str,
        auth_config: Dict[str, Any],
        mapping_config: Dict[str, Any],
        query: str,
        time_range: str,
        level: str,
        host: str,
        limit: int,
    ) -> Tuple[List[Dict], int, str]:
        try:
            from elasticsearch import Elasticsearch
        except ImportError:
            return [], 0, "elasticsearch Python 库未安装"

        username = auth_config.get("username", "")
        password = auth_config.get("password", "")
        api_key = auth_config.get("api_key", "")

        if api_key:
            es = Elasticsearch(endpoint, api_key=api_key, request_timeout=15)
        elif username and password:
            es = Elasticsearch(endpoint, basic_auth=(username, password), request_timeout=15)
        else:
            es = Elasticsearch(endpoint, request_timeout=15)

        index_pattern = mapping_config.get("index_pattern", "aiops-logs")
        time_field = mapping_config.get("time_field", "@timestamp")

        since = self._parse_time_range(time_range)
        es_query: Dict[str, Any] = {"bool": {"must": []}}

        if query and query != "*":
            es_query["bool"]["must"].append({
                "multi_match": {
                    "query": query,
                    "fields": ["message", "host", "service", "level"],
                    "type": "phrase",
                }
            })

        if level:
            es_query["bool"]["must"].append({"term": {"level": level}})

        if host:
            es_query["bool"]["must"].append({"term": {"host": host}})

        if not es_query["bool"]["must"]:
            es_query = {"match_all": {}}

        es_query = {
            "bool": {
                "must": es_query["bool"]["must"] if es_query.get("bool", {}).get("must") else [{"match_all": {}}],
                "filter": [{"range": {time_field: {"gte": since.isoformat(), "lte": datetime.now().isoformat()}}}],
            }
        }

        body = {
            "query": es_query,
            "sort": [{time_field: {"order": "desc"}}],
            "size": limit,
        }

        # 捕获 ES 连接/查询异常，转成 (logs=[], total=0, error_msg) 三元组，
        # 让上层 mcp_tools.query_logs 看到 error 字符串后 raise ValueError，
        # 由 call_mcp_tool 包装成 {"status": "error", ...}（而非误判为 success）。
        # 这样 LLM 能看到清晰的失败原因，不会把"ES 不可达"当成"日志查询成功但无结果"
        try:
            resp = es.search(index=index_pattern, body=body)
        except Exception as e:
            err_type = type(e).__name__
            err_msg = str(e)
            # 友好提示：连接超时/拒绝时建议改用其他可观测性工具
            if any(kw in err_msg.lower() for kw in ("timed out", "timeout", "connection", "refused", "unreachable")):
                hint = (
                    f"Elasticsearch 不可达（{err_type}: {err_msg}）。"
                    f"请稍后重试，或改用 query_k8s_events / query_traces / query_metrics 等其他可观测性工具。"
                )
            else:
                hint = f"Elasticsearch 查询失败（{err_type}: {err_msg}）"
            return [], 0, hint
        finally:
            try:
                es.close()
            except Exception:
                pass

        total = resp.get("hits", {}).get("total", {})
        if isinstance(total, dict):
            total = total.get("value", 0)

        logs = []
        for hit in resp.get("hits", {}).get("hits", []):
            src = hit.get("_source", {})
            logs.append({
                "timestamp": src.get(time_field, src.get("@timestamp", "")),
                "level": src.get("level", src.get("severity", "info")),
                "host": src.get("host", src.get("hostname", "")),
                "service": src.get("service", src.get("service_name", "")),
                "message": src.get("message", src.get("log", "")),
            })

        return logs, total, ""

    def _parse_time_range(self, time_range: str) -> datetime:
        """解析时间范围字符串"""
        patterns = [
            (r"^(\d+)m$", lambda m: datetime.now() - timedelta(minutes=int(m.group(1)))),
            (r"^(\d+)h$", lambda m: datetime.now() - timedelta(hours=int(m.group(1)))),
            (r"^(\d+)d$", lambda m: datetime.now() - timedelta(days=int(m.group(1)))),
        ]
        for pat, fn in patterns:
            m = re.match(pat, time_range.strip())
            if m:
                return fn(m)
        return datetime.now() - timedelta(hours=1)


# ─── 适配器注册表 ─────────────────────────────────────────────────

_ADAPTERS: Dict[str, LogQueryAdapter] = {}


def register_adapter(adapter: LogQueryAdapter):
    _ADAPTERS[adapter.source_type] = adapter


def get_adapter(source_type: str) -> Optional[LogQueryAdapter]:
    return _ADAPTERS.get(source_type)


def query_logs(
    source_id: int,
    query: str = "*",
    time_range: str = "1h",
    level: str = "",
    host: str = "",
    limit: int = 20,
) -> Tuple[List[Dict], int, str]:
    """
    统一入口，根据 source_id 路由到对应适配器。
    返回 (logs, total, error)
    """
    from app.database import get_session_for, get_db_mode
    from app.models import DataSource

    db = get_session_for(get_db_mode())()
    try:
        source = db.query(DataSource).filter(DataSource.id == source_id).first()
        if not source:
            return [], 0, f"数据源 {source_id} 不存在"

        if not source.enabled:
            return [], 0, f"数据源 {source.name} 已禁用"

        adapter = get_adapter(source.type)
        if not adapter:
            return [], 0, f"不支持的数据源类型: {source.type}，当前支持: {', '.join(_ADAPTERS.keys())}"

        import json
        auth_config = {}
        if source.auth_config:
            try:
                auth_config = json.loads(source.auth_config)
            except Exception:
                pass

        mapping_config = {}
        if source.mapping_config:
            try:
                mapping_config = json.loads(source.mapping_config)
            except Exception:
                pass

        return adapter.query(
            endpoint=source.endpoint or "",
            auth_config=auth_config,
            mapping_config=mapping_config,
            query=query,
            time_range=time_range,
            level=level,
            host=host,
            limit=min(limit, 200),
        )
    finally:
        db.close()


# 注册内置适配器
register_adapter(ElasticsearchAdapter())
