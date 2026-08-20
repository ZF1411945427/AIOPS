"""
LogQueryService — 多日志源查询引擎

设计原则：每种日志源一个 Adapter，注册到全局字典，零侵入扩展。
当前支持：Elasticsearch / Loki
待支持：ClickHouse / Splunk / Elastic（多集群）
"""

import re
import time
from abc import ABC, abstractmethod
from datetime import datetime, timedelta
from typing import Any, Dict, List, Optional, Tuple


import logging
logger = logging.getLogger(__name__)

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
        service: str = "",
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
        service: str = "",
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

        if service:
            es_query["bool"]["must"].append({"match_phrase": {"service": service}})

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
            except Exception as _exc:
                logger.warning("[except:pass] Exception: %s", _exc, exc_info=True)

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


# ─── Loki 服务名解析工具 ────────────────────────────────────────

_K8S_POD_RE = re.compile(r"/var/log/pods/(?P<ns>[^_]+)_(?P<pod>[^_]+?)_(?P<uid>[a-f0-9-]+)/(?P<container>[^/]+)/\d+\.log$")
_K8S_POD_HASH_RE = re.compile(r"^(?P<name>.+?)-[0-9a-z]{9,10}-[a-z0-9]{5}$")
_DOCKER_LOG_RE = re.compile(r"/var/lib/docker/containers/(?P<id>[a-f0-9]{12,64})/")
_BARE_LOG_RE = re.compile(r"\.log$")

# Loki 使用 RE2 正则,不支持 Python 的 \w \d 等别名外的部分转义(如 \-)。
# 只转义 RE2 定义的特殊字符,避免 re.escape 把普通字符(如 -)也转义。
_RE2_SPECIAL = re.compile(r'([\\\.\+\*\?\(\)\|\[\]\{\}\^\$])')


def _re2_escape(s: str) -> str:
    return _RE2_SPECIAL.sub(r"\\\1", s)


def _has_positive_matcher(filters: List[str]) -> bool:
    """判断 selector 是否含"正向非空"匹配器.

    Loki 要求 LogQL selector 至少有一个正则/等值匹配器且其值非空兼容
    (如 job=~".+", host="x"), 排除式(level!~"..." / level!="x")不计入。
    否则查询报 HTTP 400 "queries require at least one regexp or equality matcher..."
    """
    for f in filters:
        if "!=" in f or "!~" in f:
            continue
        if "=" in f:
            return True
    return False

_docker_map_cache = {"ts": 0.0, "data": {}}


def _load_docker_container_map(max_age: float = 300.0) -> Dict[str, str]:
    """查询 132 上 docker 容器 id→name 映射(带缓存,5 分钟内不重复 SSH)."""
    now = time.time()
    if now - _docker_map_cache["ts"] < max_age:
        return _docker_map_cache["data"]
    mapping: Dict[str, str] = {}
    try:
        from app.services.ssh_helper import connect_ssh
        c = connect_ssh("11.0.1.132", port=22, username="root", password="123456", timeout=8)
        _, stdout, stderr = c.exec_command(
            "docker ps --format '{{.ID}}|{{.Names}}'", timeout=10)
        out = stdout.read().decode("utf-8", "ignore")
        err = stderr.read().decode("utf-8", "ignore")
        c.close()
        if err.strip():
            raise RuntimeError(err.strip()[:200])
        for line in out.splitlines():
            line = line.strip()
            if "|" in line:
                cid, name = line.split("|", 1)
                mapping[cid.lower()] = name.strip()
    except Exception:
        mapping = {}
    _docker_map_cache["ts"] = now
    _docker_map_cache["data"] = mapping
    return mapping


def parse_loki_service_name(filename: str) -> str:
    """从 Loki filename 标签解析服务名.

    - k8s pod 路径: /var/log/pods/<ns>_<pod>_<uid>/<container>/<n>.log
      → 取 deployment 名(去 rs/pod hash 后缀),如 adservice-845cd8755b-rrfr4 → adservice
    - docker 路径: /var/lib/docker/containers/<id>/<id>-json.log
      → 通过容器 id 映射为容器名,如 mall-search
    - 裸机路径: /data/mall/logs/<name>.log → <name>
    - 其它: 返回空串
    """
    if not filename:
        return ""
    m = _K8S_POD_RE.search(filename)
    if m:
        pod = m.group("pod")
        hm = _K8S_POD_HASH_RE.match(pod)
        return hm.group("name") if hm else pod
    m = _DOCKER_LOG_RE.search(filename)
    if m:
        cid = m.group("id")[:12]
        mapping = _load_docker_container_map()
        return mapping.get(cid.lower(), cid)
    if _BARE_LOG_RE.search(filename):
        name = filename.rsplit("/", 1)[-1]
        return name[:-4] if name.endswith(".log") else name
    return ""


# ─── Loki Adapter ────────────────────────────────────────────────

class LokiAdapter(LogQueryAdapter):
    """Grafana Loki 日志适配器（HTTP API, LogQL）"""

    source_type = "loki"

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
        service: str = "",
    ) -> Tuple[List[Dict], int, str]:
        try:
            import requests
        except ImportError:
            return [], 0, "requests 库未安装"

        if not endpoint:
            return [], 0, "Loki endpoint 未配置"

        headers = {"Content-Type": "application/json"}
        org_id = auth_config.get("org_id", "")
        if org_id:
            headers["X-Scope-OrgID"] = str(org_id)

        auth = None
        if auth_config.get("username") and auth_config.get("password"):
            auth = (auth_config["username"], auth_config["password"])

        now = datetime.now()
        since = self._parse_time_range(time_range)
        start_ns = int(since.timestamp() * 1e9)
        end_ns = int(now.timestamp() * 1e9)

        # 构造 LogQL 表达式
        # 排除法:某级别 X 时,数据查询用 level!~ 排除其它明确的非 X 级别,
        # 这样 ERROR 主行 + 无 level 标签的堆栈行都能保留(多行合并可用)。
        _LEVEL_EXCLUDE = {
            "error": r"(?i)^(info|debug|warn|warning)$",
            "warning": r"(?i)^(info|debug|error)$",
            "info": r"(?i)^(error|debug|warn|warning)$",
            "debug": r"(?i)^(error|info|warn|warning)$",
        }
        base_filters = []
        if host:
            base_filters.append(f'host="{host}"')
        if service:
            base_filters.append(self._service_selector(service))
        # Loki 要求选择器至少含一个非空通配的匹配器,裸 `{}` 会 400,
        # 由 _has_positive_matcher 兜底插入 job=~".+"

        # 数据查询选择器: level 用排除法(保留目标级别+无 level 堆栈行)
        # 注意: level!~/!= 是"排除式"匹配器,Loki 校验时不会被计为有效 matcher,
        # 因此 base 无 host/service 时必须以 job=~".+" 兜底,否则 HTTP 400
        data_filters = list(base_filters)
        if not _has_positive_matcher(data_filters):
            data_filters.append('job=~".+"')
        if level:
            data_filters.append(f'level!~"{_LEVEL_EXCLUDE.get(level.lower(), r"(?i)^(info|debug)$")}"')
        data_selector = "{" + ",".join(data_filters) + "}"
        # 计数查询选择器: 正向过滤目标级别,保证 total 准确
        count_filters = list(base_filters)
        if not _has_positive_matcher(count_filters):
            count_filters.append('job=~".+"')
        if level:
            count_filters.append(f'level=~"(?i)^{re.escape(level)}$"')
        count_selector = "{" + ",".join(count_filters) + "}"

        # 数据查询
        expr = data_selector
        if query and query != "*":
            safe_query = query.replace("\\", "\\\\").replace('"', '\\"')
            expr += f'|= "{safe_query}"'
        # 计数查询
        count_expr_base = count_selector
        if query and query != "*":
            safe_query = query.replace("\\", "\\\\").replace('"', '\\"')
            count_expr_base += f'|= "{safe_query}"'

        base = endpoint.rstrip("/")

        # 先用 count_over_time 聚合出真实总数,支持前端分页。
        # 注意:query_range 的 limit 是"每个 stream"的条数,不能当全局总数;
        # 之前直接 len(logs) 会导致 totalPages 恒为 1,翻页按钮被隐藏。
        total = 0
        window = time_range.strip()
        if window and window[0].isdigit():
            count_expr = f"count_over_time({count_expr_base}[{window}])"
            try:
                cnt_resp = requests.get(
                    f"{base}/loki/api/v1/query",
                    params={"query": count_expr, "time": end_ns},
                    headers=headers,
                    auth=auth,
                    timeout=15,
                )
                if cnt_resp.status_code == 200:
                    for s in cnt_resp.json().get("data", {}).get("result", []):
                        # instant vector 返回 {"value": [ts, count]};range 返回 {"values": [[ts, count], ...]}
                        vals = s.get("values") or [s.get("value")]
                        if vals:
                            total += int(float(vals[0][1]))
            except Exception:
                total = 0

        params = {
            "query": expr,
            "start": start_ns,
            "end": end_ns,
            "limit": limit,
            "direction": "backward",
        }

        try:
            resp = requests.get(
                f"{base}/loki/api/v1/query_range",
                params=params,
                headers=headers,
                auth=auth,
                timeout=15,
            )
        except Exception as e:
            hint = (
                f"Loki 不可达（{type(e).__name__}: {e}）。"
                f"请检查 endpoint 与网络连通性，或改用 query_k8s_events / query_traces / query_metrics 等其他可观测性工具。"
            )
            return [], 0, hint

        if resp.status_code != 200:
            return [], 0, f"Loki 查询失败（HTTP {resp.status_code}）: {resp.text[:300]}"

        try:
            payload = resp.json()
        except Exception as e:
            return [], 0, f"Loki 响应解析失败: {e}"

        if payload.get("status") != "success":
            return [], 0, f"Loki 返回错误: {payload.get('error', 'unknown')}"

        logs: List[Dict] = []
        streams = payload.get("data", {}).get("result", [])
        for stream in streams:
            labels = stream.get("stream", {})
            filename = labels.get("filename", "")
            svc = parse_loki_service_name(filename) or labels.get("service", labels.get("service_name", labels.get("job", "")))
            for ts_ns, message in stream.get("values", []):
                logs.append({
                    "timestamp": self._ns_to_iso(ts_ns),
                    "level": labels.get("level", labels.get("severity", "")),
                    "host": labels.get("host", labels.get("hostname", "")),
                    "service": svc,
                    "message": message,
                    "source": "loki",
                })

        # Loki 按 stream 分组返回,stream 之间不排序;全局按时间倒序排序,
        # 保证分页切片按时间顺序准确
        logs.sort(key=lambda x: x["timestamp"], reverse=True)

        # promtail 默认按行拆分,Java 等编程语言的多行异常堆栈被拆成多条独立记录。
        # 把同一 stream 相邻的"堆栈续行"(以空白/at /Caused by: 开头)合并回主日志,
        # 还原成完整的一条异常日志。
        logs = self._merge_multiline(logs)

        # 注:level 过滤不在 LokiAdapter 层做——LogQL 里加 level 过滤会排除堆栈行,
        # 而 Python 过滤在 logs.py 的 _query_loki 中统一处理(合并后行内正则匹配)。

        return logs, total, ""

    @staticmethod
    def _is_continuation_line(msg: str) -> bool:
        """判断是否为多行日志的续行(异常堆栈特征).

        覆盖: 缩进行(\tat ...)、Caused by、... N more、Java 异常声明行(java.xxx.Exception:)
        """
        if not msg:
            return False
        if msg[:1].isspace():
            return True
        s = msg.lstrip()
        if s.startswith("at ") or s.startswith("Caused by:") or s.startswith("... more") or s.startswith("Suppressed:"):
            return True
        # 异常声明行: com.foo.BarException: message / java.net.ConnectException: message
        if re.match(r'^[a-z]+\.[a-zA-Z]', s) and re.search(r'(Exception|Error|Throwable)\b', s):
            return True
        return False

    def _merge_multiline(self, logs: List[Dict]) -> List[Dict]:
        """把相邻的堆栈续行合并回主日志,还原完整多行异常."""
        if not logs:
            return logs
        # 正序处理,便于合并
        seq = list(reversed(logs))
        merged: List[Dict] = []
        for lg in seq:
            msg = lg.get("message", "").rstrip("\r\n")
            if merged and self._is_continuation_line(msg):
                merged[-1]["message"] += "\n" + msg
            else:
                merged.append(dict(lg))
        # 清理因 Loki 条目末尾自带 \n 导致的空行
        for m in merged:
            m["message"] = m["message"].rstrip("\r\n")
        merged.reverse()
        return merged

    @staticmethod
    def _ns_to_iso(ts_ns) -> str:
        try:
            return datetime.fromtimestamp(int(ts_ns) / 1e9).isoformat()
        except Exception:
            return str(ts_ns)

    @staticmethod
    def _service_selector(service: str) -> str:
        """把业务服务名转成 filename 标签匹配的 LogQL 选择器.

        k8s pod 路径:   /var/log/pods/<ns>_<pod>_<uid>/... → 匹配 <pod> 名(带 rs/pod hash)
        docker 路径:    /var/lib/docker/containers/<id>/... → 匹配容器名
        裸机路径:       /data/mall/logs/<name>.log          → 匹配文件名
        兜底:           正则匹配任意含服务名的 filename 片段
        """
        if not service:
            return 'job=~".+"'
        # 若服务名是 docker 容器名,映射回容器 id 精确匹配
        # 注意:Loki 的 =~ 是"全字符串匹配",正则必须覆盖完整 filename(以 .* 开头)
        try:
            mapping = _load_docker_container_map()
            for cid, name in mapping.items():
                if name == service:
                    return f'filename=~".*/containers/{re.escape(cid)}[a-f0-9]*/.*"'
        except Exception as _exc1:
            logger.warning("[except:pass] Exception: %s", _exc1, exc_info=True)
        # k8s pod / 裸机文件名 / 通用片段
        escaped = _re2_escape(service)
        return f'filename=~"(?i)(/var/log/pods/[^_]+_{escaped}-[0-9]{{9,10}}-[a-z0-9]{{5}}_|/data/mall/logs/{escaped}\\\\.log|.*{escaped}.*)"'

    def _parse_time_range(self, time_range: str) -> datetime:
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
    service: str = "",
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
            except Exception as _exc2:
                logger.warning("[except:pass] Exception: %s", _exc2, exc_info=True)

        mapping_config = {}
        if source.mapping_config:
            try:
                mapping_config = json.loads(source.mapping_config)
            except Exception as _exc3:
                logger.warning("[except:pass] Exception: %s", _exc3, exc_info=True)

        return adapter.query(
            endpoint=source.endpoint or "",
            auth_config=auth_config,
            mapping_config=mapping_config,
            query=query,
            time_range=time_range,
            level=level,
            host=host,
            limit=min(limit, 200),
            service=service,
        )
    finally:
        db.close()


# 注册内置适配器
register_adapter(ElasticsearchAdapter())
register_adapter(LokiAdapter())
