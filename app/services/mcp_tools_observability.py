import re
from datetime import datetime, timedelta
from typing import Dict, Optional

from sqlalchemy.orm import Session

from app.database import get_session_for, get_db_mode
from app.models import Alert, Asset, MetricRecord, K8sEvent, Incident, KnowledgeBase
from app.services.mcp_registry import register_mcp_tool, get_internal_tools, get_mcp_tool
from app.services import remediation_service, alert_service, incident_service, asset_service, rag_service
from app.services.promql_parser import parse_promql, promql_to_dict


import logging
logger = logging.getLogger(__name__)

def _get_db():
    return get_session_for(get_db_mode())()

# ─── 日志查询 Tool ──────────────────────────────────────────────

@register_mcp_tool(
    name="query_logs",
    description="查询日志（支持多日志源：Elasticsearch 等），根据关键词/主机/级别/时间范围过滤日志",
    input_schema={
        "type": "object",
        "properties": {
            "source_id": {"type": "integer", "description": "数据源 ID（从 query_log_sources 查询可用数据源）"},
            "query": {"type": "string", "description": "搜索关键词（支持多字段匹配 message/host/service/level），如 error / nginx / 192.168.1"},
            "time_range": {"type": "string", "description": "时间范围: 15m / 1h / 6h / 24h / 7d，默认 1h"},
            "level": {"type": "string", "description": "日志级别过滤: error / warning / info（可选）"},
            "host": {"type": "string", "description": "主机名过滤（如 web-server-01）"},
            "service": {"type": "string", "description": "服务过滤（Loki 源对应 job，如 kubernetes-pods / docker-containers / mall-bare）"},
            "limit": {"type": "integer", "description": "返回条数，默认 20，最大 200"},
        },
        "required": ["source_id"],
    },
    risk_level="read_only",
    display_name="查询日志",
    expose_to_llm=True,
    location="cloud",
    category="log",
)
def query_logs(db: Optional[Session] = None, user_id: Optional[int] = None, **kwargs) -> Dict:
    from app.services.log_query_service import query_logs as _query_logs
    source_id = kwargs.get("source_id")
    query_str = kwargs.get("query", "*")
    time_range = kwargs.get("time_range", "1h")
    level = kwargs.get("level", "")
    host = kwargs.get("host", "")
    service = kwargs.get("service", "")
    limit = kwargs.get("limit", 20)

    if not source_id:
        raise ValueError("缺少必填参数: source_id（请先调用 query_log_sources 获取可用数据源）")

    try:
        logs, total, error = _query_logs(
            source_id=int(source_id),
            query=query_str,
            time_range=time_range,
            level=level,
            host=host,
            limit=limit,
            service=service,
        )
    except Exception as e:
        raise ValueError(f"日志数据源 {source_id} 查询失败: {str(e)}（请检查数据源配置/网络连通性）")

    if error:
        # 错误路径必须 raise，让 call_mcp_tool 包装成 {"status":"error","message":...}
        # 否则返回 dict 会被外层当成 success，LLM 误以为查询成功但无日志
        # （真实场景：ES 不可达时 LLM 看到"成功但 logs=[]"，会下结论"无错误日志"，
        #  实际上是查询本身失败，可能误导根因分析）
        raise ValueError(error)

    return {
        "logs": logs,
        "total": total,
        "query": query_str,
        "time_range": time_range,
        "level": level,
        "host": host,
        "service": service,
    }


@register_mcp_tool(
    name="query_log_sources",
    description="查询当前系统已配置的所有日志数据源，返回 id / name / type / endpoint，用于后续 query_logs 查询",
    input_schema={
        "type": "object",
        "properties": {},
    },
    risk_level="read_only",
    display_name="日志数据源",
    expose_to_llm=True,
    location="cloud",
    category="log",
)
def query_log_sources(db: Optional[Session] = None, user_id: Optional[int] = None, **kwargs) -> Dict:
    from app.models import DataSource
    close_db = False
    if db is None:
        db = _get_db()
        close_db = True
    try:
        sources = db.query(DataSource).filter(
            DataSource.type.in_(["elasticsearch", "loki"])
        ).all()
        return {
            "sources": [
                {
                    "id": s.id,
                    "name": s.name,
                    "type": s.type,
                    "endpoint": s.endpoint or "",
                    "enabled": bool(s.enabled),
                }
                for s in sources
            ],
            "count": len(sources),
        }
    finally:
        if close_db:
            db.close()
# ─── 链路追踪 Tool ─────────────────────────────────────

@register_mcp_tool(
    name="query_traces",
    description="查询分布式链路追踪（Trace），返回调用链路树，包含每个 Span 的服务/操作/耗时/状态，用于定位慢链路和错误根因",
    input_schema={
        "type": "object",
        "properties": {
            "trace_id": {"type": "string", "description": "链路 ID（可选，精确查单条）"},
            "service": {"type": "string", "description": "服务名过滤（如 api-gateway / payment-service）"},
            "status": {"type": "string", "description": "状态过滤: OK / ERROR / WARN"},
            "time_range": {"type": "string", "description": "时间范围: 15m / 1h / 6h / 24h / 7d，默认 1h"},
            "limit": {"type": "integer", "description": "返回条数，默认 20"},
        },
    },
    risk_level="read_only",
    display_name="查询链路",
    expose_to_llm=True,
    location="cloud",
    category="trace",
)
def query_traces(db: Optional[Session] = None, user_id: Optional[int] = None, **kwargs) -> Dict:
    import json as _json
    from datetime import timedelta as _td
    from app.models import Span as _Span
    from sqlalchemy import func as _func, desc as _desc

    trace_id = kwargs.get("trace_id", "")
    service = kwargs.get("service", "")
    status_filter = kwargs.get("status", "")
    time_range = kwargs.get("time_range", "1h")
    limit = min(kwargs.get("limit", 20), 100)

    # 解析时间范围
    now = datetime.now()
    m = re.match(r"^(\d+)([mhd])$", time_range.strip())
    if m:
        num, unit = int(m.group(1)), m.group(2)
        delta = _td(minutes=num) if unit == "m" else (_td(hours=num) if unit == "h" else _td(days=num))
        since = now - delta
    else:
        since = now - _td(hours=1)

    close_db = False
    if db is None:
        db = _get_db()
        close_db = True
    try:
        # 构造子查询：每个 trace_id 最小的 start_time
        subq = (
            db.query(
                _Span.trace_id,
                _func.min(_Span.started_at).label("min_start")
            )
            .filter(_Span.started_at >= since)
            .group_by(_Span.trace_id)
            .subquery()
        )
        root_q = (
            db.query(_Span)
            .join(subq, _Span.trace_id == subq.c.trace_id)
            .filter(_Span.started_at == subq.c.min_start)
        )
        if trace_id:
            root_q = root_q.filter(_Span.trace_id == trace_id)
        if service:
            root_q = root_q.filter(_Span.service_name.ilike(f"%{service}%"))
        if status_filter:
            root_q = root_q.filter(_Span.status == status_filter)
        root_q = root_q.order_by(_desc(_Span.started_at)).limit(limit)

        traces = []
        for root in root_q.all():
            all_spans = (
                db.query(_Span)
                .filter(_Span.trace_id == root.trace_id)
                .order_by(_Span.started_at)
                .all()
            )
            spans_data = []
            for s in all_spans:
                tags = {}
                try:
                    tags = _json.loads(s.tags or "{}")
                except Exception as _exc4:
                    logger.warning("[except:pass] Exception: %s", _exc4, exc_info=True)
                spans_data.append({
                    "span_id": s.span_id or "",
                    "service": s.service_name or "",
                    "operation": s.operation_name or "",
                    "duration_ms": s.duration_ms or 0,
                    "status": s.status or "OK",
                    "parent_span_id": s.parent_span_id or "",
                    "start_time": s.started_at.isoformat() if s.started_at else "",
                })
            root_durations = [sp["duration_ms"] for sp in spans_data]
            root_duration = max(root_durations) if root_durations else 0
            traces.append({
                "trace_id": root.trace_id or "",
                "root_service": root.service_name or "",
                "root_operation": root.operation_name or "",
                "root_duration_ms": root_duration,
                "root_status": root.status or "OK",
                "root_start": root.started_at.isoformat() if root.started_at else "",
                "spans_count": len(all_spans),
                "spans": spans_data,
            })

        return {"traces": traces, "count": len(traces), "time_range": time_range}
    finally:
        if close_db:
            db.close()
# ─── MySQL Query Tool ─────────────────────────────────────

@register_mcp_tool(
    name="query_mysql",
    description="连接 MySQL 数据库执行 SQL 查询（仅支持 SELECT/DESC/SHOW 语句），返回查询结果。连接信息从资产 connection_config 中读取。",
    input_schema={
        "type": "object",
        "properties": {
            "asset_id": {"type": "integer", "description": "资产 ID（从 assets 表）"},
            "sql": {"type": "string", "description": "SQL 查询语句（仅支持读操作：SELECT/SHOW/DESC/DESCRIBE）"},
            "limit": {"type": "integer", "description": "最大返回行数，默认 100"},
        },
        "required": ["asset_id", "sql"],
    },
    risk_level="medium",
    display_name="查询 MySQL",
    expose_to_llm=True,
    location="cloud",
    category="mysql",
)
def query_mysql(db: Optional[Session] = None, user_id: Optional[int] = None, **kwargs) -> Dict:
    import pymysql
    import json as _json

    asset_id = kwargs.get("asset_id")
    sql = kwargs.get("sql", "").strip()
    limit = min(kwargs.get("limit", 100), 1000)

    if not asset_id:
        return {"error": "缺少必填参数: asset_id"}
    if not sql:
        return {"error": "缺少必填参数: sql"}

    # 只允许读操作
    safe_sql = sql.upper()
    allowed = ["SELECT", "SHOW", "DESC", "DESCRIBE", "EXPLAIN"]
    if not any(safe_sql.startswith(a) for a in allowed):
        return {"error": "只允许 SELECT/SHOW/DESC/DESCRIBE/EXPLAIN 语句"}

    close_db = False
    if db is None:
        db = _get_db()
        close_db = True

    try:
        asset = db.query(Asset).filter(Asset.id == int(asset_id)).first()
        if not asset:
            return {"error": f"资产 {asset_id} 不存在"}

        cfg = _json.loads(asset.connection_config) if asset.connection_config else {}
        host = cfg.get("db_host") or cfg.get("mysql_host") or asset.ip
        port = int(cfg.get("db_port") or cfg.get("mysql_port") or 3306)
        user = cfg.get("db_user") or cfg.get("mysql_user") or "root"
        password = cfg.get("db_password") or cfg.get("mysql_password") or ""
        database = cfg.get("db_name") or cfg.get("mysql_database") or ""

        try:
            conn = pymysql.connect(
                host=host, port=port, user=user, password=password,
                database=database, charset="utf8mb4",
                connect_timeout=10, read_timeout=30
            )
        except pymysql.Error as e:
            return {"error": f"MySQL 连接失败: {e}", "host": host, "port": port, "user": user}

        try:
            cur = conn.cursor()
            cur.execute(sql + (" LIMIT %d" % limit if limit else ""))
            rows = cur.fetchall()
            cols = [d[0] for d in cur.description] if cur.description else []
            return {
                "columns": cols,
                "rows": [list(r) for r in rows],
                "row_count": len(rows),
                "sql": sql,
                "asset": {"id": asset.id, "name": asset.name, "ip": asset.ip},
            }
        finally:
            conn.close()
    finally:
        if close_db:
            db.close()
# ─── MySQL 权限安全检测 ─────────────────────────────────

@register_mcp_tool(
    name="check_mysql_permissions",
    description="检测 MySQL 账号的权限等级，评估 AI 连接该数据库的安全风险。用于新增数据库资产时自动检测，辅助判断是否允许 AI 使用。",
    input_schema={
        "type": "object",
        "properties": {
            "asset_id": {"type": "integer", "description": "数据库资产 ID"},
        },
        "required": ["asset_id"],
    },
    risk_level="read_only",
    display_name="检查 MySQL 权限",
    expose_to_llm=True,
    location="cloud",
    category="mysql",
)
def check_mysql_permissions(db: Optional[Session] = None, user_id: Optional[int] = None, **kwargs) -> Dict:
    import pymysql
    import json as _json

    asset_id = kwargs.get("asset_id")
    if not asset_id:
        return {"error": "缺少必填参数: asset_id"}

    close_db = False
    if db is None:
        db = _get_db()
        close_db = True

    try:
        asset = db.query(Asset).filter(Asset.id == int(asset_id)).first()
        if not asset:
            return {"error": f"资产 {asset_id} 不存在"}

        cfg = _json.loads(asset.connection_config) if asset.connection_config else {}
        host = cfg.get("db_host") or cfg.get("mysql_host") or asset.ip
        port = int(cfg.get("db_port") or cfg.get("mysql_port") or 3306)
        user = cfg.get("db_user") or cfg.get("mysql_user") or "root"
        password = cfg.get("db_password") or cfg.get("mysql_password") or ""
        database = cfg.get("db_name") or ""

        try:
            conn = pymysql.connect(
                host=host, port=port, user=user, password=password,
                database=database, charset="utf8mb4",
                connect_timeout=10, read_timeout=30
            )
        except pymysql.Error as e:
            return {"error": f"MySQL 连接失败: {e}", "host": host, "port": port, "user": user}

        try:
            cur = conn.cursor()
            cur.execute("SELECT * FROM mysql.user WHERE User=%s AND Host=%s", (user, "%" if user != "root" else "%"))
            privs = []
            is_super = False
            if cur.description:
                cols = [d[0] for d in cur.description]
                for row in cur.fetchall():
                    priv_map = dict(zip(cols, row))
                    for col, val in priv_map.items():
                        if val in (True, 1, "Y", "y"):
                            privs.append(col)

            if conn and database:
                try:
                    # SHOW GRANTS 不支持参数化绑定，先对用户名做白名单校验防注入
                    import re as _re
                    if not _re.match(r"^[A-Za-z0-9_\-.@ ]{1,64}$", user or ""):
                        grants = []
                    else:
                        _safe_user = (user or "").replace("'", "''")
                        cur.execute(f"SHOW GRANTS FOR '{_safe_user}'@'%'")
                        grants = [r[0] for r in cur.fetchall()]
                except Exception:
                    grants = []
            else:
                grants = []

            ddl_privs = [p for p in privs if p in ("Drop_priv", "Alter_priv", "Create_priv", "Index_priv", "References_priv")]
            dml_privs = [p for p in privs if p in ("Insert_priv", "Update_priv", "Delete_priv", "Execute_priv")]
            dcl_privs = [p for p in privs if p in ("Grant_priv", "Super_priv", "Shutdown_priv", "Process_priv", "File_priv")]
            read_privs = [p for p in privs if p in ("Select_priv", "Show_db_priv", "Show_view_priv", "Lock_tables_priv")]

            has_grant_option = "Grant_priv" in privs or any("GRANT OPTION" in g for g in grants)
            is_super_user = "Super_priv" in privs

            if has_grant_option or is_super_user or ddl_privs or "File_priv" in privs:
                risk_level = "high"
                risk_label = "🔴 高危"
                risk_desc = "该账号拥有极高危权限（DCL/DDL/文件操作/授权），AI 可能导致数据丢失或权限失控"
            elif dml_privs:
                risk_level = "medium"
                risk_label = "⚠️ 警告"
                risk_desc = "该账号拥有 DML 权限（INSERT/UPDATE/DELETE），AI 可修改业务数据"
            elif read_privs and not dml_privs and not ddl_privs:
                risk_level = "safe"
                risk_label = "✅ 安全"
                risk_desc = "该账号仅有读权限，AI 仅能查询无法修改数据"
            else:
                risk_level = "unknown"
                risk_label = "❓ 未知"
                risk_desc = "无法明确判定权限等级，建议人工确认"

            return {
                "asset_id": asset_id,
                "asset_name": asset.name,
                "asset_ip": host,
                "mysql_user": user,
                "risk_level": risk_level,
                "risk_label": risk_label,
                "risk_desc": risk_desc,
                "privileges": {
                    "read": read_privs,
                    "dml": dml_privs,
                    "ddl": ddl_privs,
                    "dcl": dcl_privs,
                },
                "has_grant_option": has_grant_option,
                "is_super_user": is_super_user,
                "grants": grants,
                "recommendation": "仅【✅ 安全】权限的数据库建议接入 AI 助手；其他权限等级请评估风险后决定",
            }
        finally:
            conn.close()
    finally:
        if close_db:
            db.close()
# ─── MySQL Write Tool ─────────────────────────────────────

@register_mcp_tool(
    name="execute_mysql",
    description="通过资产记录的 MySQL 连接信息执行 SQL 语句（支持 DDL/DML：CREATE/ALTER/DROP/INSERT/UPDATE/DELETE/TRUNCATE 等写操作），必须经用户确认后才执行。适用于创建数据库、建表、插入数据等操作。",
    input_schema={
        "type": "object",
        "properties": {
            "asset_id": {"type": "integer", "description": "MySQL 数据库资产 ID"},
            "sql": {"type": "string", "description": "要执行的 SQL 语句（支持 CREATE/ALTER/DROP/INSERT/UPDATE/DELETE 等写操作）"},
        },
        "required": ["asset_id", "sql"],
    },
    risk_level="high",
    display_name="执行 MySQL",
    expose_to_llm=False,
    review_gate=True,  # 高危写操作, 需审批
    location="cloud",
    category="mysql",
)
def execute_mysql(db: Optional[Session] = None, user_id: Optional[int] = None, **kwargs) -> Dict:
    import pymysql
    import json as _json

    asset_id = kwargs.get("asset_id")
    sql = kwargs.get("sql", "").strip()

    if not asset_id:
        return {"error": "缺少必填参数: asset_id"}
    if not sql:
        return {"error": "缺少必填参数: sql"}

    close_db = False
    if db is None:
        db = _get_db()
        close_db = True

    try:
        asset = db.query(Asset).filter(Asset.id == int(asset_id)).first()
        if not asset:
            return {"error": f"资产 {asset_id} 不存在"}

        # 生产只读铁闸: read-only 资产禁止执行任何写 SQL
        from app.services.asset_service import assert_ai_writable
        _ro_deny = assert_ai_writable(db, {"asset_id": asset_id})
        if _ro_deny:
            return {"error": _ro_deny, "_read_only_denied": True}

        cfg = _json.loads(asset.connection_config) if asset.connection_config else {}
        host = cfg.get("db_host") or cfg.get("mysql_host") or asset.ip
        port = int(cfg.get("db_port") or cfg.get("mysql_port") or 3306)
        user = cfg.get("db_user") or cfg.get("mysql_user") or "root"
        password = cfg.get("db_password") or cfg.get("mysql_password") or ""
        database = cfg.get("db_name") or cfg.get("mysql_database") or ""

        try:
            conn = pymysql.connect(
                host=host, port=port, user=user, password=password,
                database=database, charset="utf8mb4",
                connect_timeout=10, read_timeout=60
            )
        except pymysql.Error as e:
            return {"error": f"MySQL 连接失败: {e}", "host": host, "port": port, "user": user}

        try:
            cur = conn.cursor()
            cur.execute(sql)
            conn.commit()
            affected = cur.rowcount
            return {
                "status": "success",
                "message": f"SQL 执行成功，影响行数: {affected}",
                "affected_rows": affected,
                "sql": sql,
                "asset": {"id": asset.id, "name": asset.name, "ip": asset.ip},
            }
        except pymysql.Error as e:
            conn.rollback()
            return {"error": f"SQL 执行失败: {e}", "sql": sql}
        finally:
            conn.close()
    finally:
        if close_db:
            db.close()
# ─── Redis Monitor Tool ─────────────────────────────────────

@register_mcp_tool(
    name="redis_monitor",
    description="连接 Redis 实例执行监控类命令（INFO/CLIENT LIST/PING/CONFIG GET），返回运行状态、内存、连接数等监控信息。连接信息从资产 connection_config 中读取（redis_host/redis_port/redis_password）。",
    input_schema={
        "type": "object",
        "properties": {
            "asset_id": {"type": "integer", "description": "资产 ID（从 assets 表，需配置 redis 连接信息）"},
            "command": {"type": "string", "description": "Redis 监控命令（只读）：PING/INFO/CLIENT LIST/CONFIG GET 参数，如 'INFO server'"},
        },
        "required": ["asset_id", "command"],
    },
    risk_level="read_only",
    display_name="监控 Redis",
    expose_to_llm=True,
    location="cloud",
    category="redis",
)
def redis_monitor(db: Optional[Session] = None, user_id: Optional[int] = None, **kwargs) -> Dict:
    import json as _json
    asset_id = kwargs.get("asset_id")
    command = (kwargs.get("command") or "INFO").strip()
    if not asset_id:
        return {"error": "缺少必填参数: asset_id"}

    close_db = False
    if db is None:
        db = _get_db()
        close_db = True
    try:
        asset = db.query(Asset).filter(Asset.id == int(asset_id)).first()
        if not asset:
            return {"error": f"资产 {asset_id} 不存在"}
        cfg = _json.loads(asset.connection_config) if asset.connection_config else {}
        host = cfg.get("redis_host") or asset.ip
        port = int(cfg.get("redis_port") or 6379)
        password = cfg.get("redis_password") or ""
        allowed = ["PING", "INFO", "CLIENT LIST", "CONFIG GET", "DBSIZE", "MEMORY"]
        if not any(command.upper().startswith(a) for a in allowed):
            return {"error": "仅允许只读监控命令: PING/INFO/CLIENT LIST/CONFIG GET/DBSIZE/MEMORY"}
        try:
            import redis as _redis
        except ImportError:
            return {"error": "缺少 redis 库, 无法执行 Redis 监控"}
        try:
            r = _redis.Redis(host=host, port=port, password=password or None,
                             socket_connect_timeout=5, socket_timeout=10, decode_responses=True)
            parts = command.split(" ", 1)
            method = parts[0].lower()
            arg = parts[1] if len(parts) > 1 else None
            if method == "info":
                return {"status": "success", "result": r.info(arg or "default"), "asset": asset.name, "host": host, "port": port}
            elif method == "ping":
                return {"status": "success", "ping": r.ping()}
            elif method == "client":
                return {"status": "success", "clients": list(r.client_list())}
            elif method == "config":
                return {"status": "success", "config": r.config_get(arg or "*")}
            elif method == "dbsize":
                return {"status": "success", "dbsize": r.dbsize()}
            elif method == "memory":
                return {"status": "success", "memory": r.memory_stats() if hasattr(r, "memory_stats") else str(r.execute_command("MEMORY", "STATS"))}
            return {"status": "success", "result": str(r.execute_command(*command.split()))}
        except Exception as e:
            return {"error": f"Redis 监控失败: {e}", "host": host, "port": port}
    finally:
        if close_db:
            db.close()
# ─── Kafka Monitor Tool ─────────────────────────────────────

@register_mcp_tool(
    name="kafka_monitor",
    description="连接 Kafka 集群执行监控类查询（通过 kafka-python）：集群元数据、Topic 列表、分区状态、消费组 Lag。连接信息从资产 connection_config 中读取（kafka_bootstrap_servers）。",
    input_schema={
        "type": "object",
        "properties": {
            "asset_id": {"type": "integer", "description": "资产 ID（从 assets 表，需配置 kafka_bootstrap_servers）"},
            "action": {"type": "string", "description": "监控动作：topics / cluster / partitions / groups / lag", "default": "topics"},
            "topic": {"type": "string", "description": "指定 Topic（action=partitions 或 lag 时使用）"},
            "group": {"type": "string", "description": "指定消费组（action=lag 时使用）"},
        },
        "required": ["asset_id", "action"],
    },
    risk_level="read_only",
    display_name="监控 Kafka",
    expose_to_llm=True,
    location="cloud",
    category="kafka",
)
def kafka_monitor(db: Optional[Session] = None, user_id: Optional[int] = None, **kwargs) -> Dict:
    import json as _json
    asset_id = kwargs.get("asset_id")
    action = (kwargs.get("action") or "topics").strip()
    if not asset_id:
        return {"error": "缺少必填参数: asset_id"}
    close_db = False
    if db is None:
        db = _get_db()
        close_db = True
    try:
        asset = db.query(Asset).filter(Asset.id == int(asset_id)).first()
        if not asset:
            return {"error": f"资产 {asset_id} 不存在"}
        cfg = _json.loads(asset.connection_config) if asset.connection_config else {}
        servers = cfg.get("kafka_bootstrap_servers") or (asset.ip and f"{asset.ip}:9092") or ""
        if not servers:
            return {"error": "未配置 kafka_bootstrap_servers 连接信息"}
        try:
            from kafka import KafkaAdminClient
        except ImportError:
            return {"error": "缺少 kafka-python 库, 无法执行 Kafka 监控"}
        servers_list = [s.strip() for s in servers.split(",") if s.strip()]
        try:
            admin = KafkaAdminClient(bootstrap_servers=servers_list, request_timeout_ms=8000)
            if action == "cluster":
                return {"status": "success", "cluster": admin.describe_cluster()}
            elif action == "topics":
                topics = admin.list_topics()
                return {"status": "success", "topics": sorted(list(topics)) if not isinstance(topics, str) else topics,
                        "count": len(topics) if hasattr(topics, "__len__") else None}
            elif action == "partitions":
                if not kwargs.get("topic"):
                    return {"error": "action=partitions 需要 topic 参数"}
                tps = admin.describe_topics([kwargs.get("topic")])
                topic_meta = tps[0] if tps else {}
                partitions = topic_meta.get("partitions", [])
                return {"status": "success", "topic": kwargs.get("topic"),
                        "partitions": [{"id": p["partition"], "leader": p["leader"]} for p in partitions],
                        "count": len(partitions)}
            elif action == "groups":
                groups = admin.list_consumer_groups()
                group_ids = []
                for g in groups:
                    if isinstance(g, tuple):
                        group_ids.append(g[0])
                    elif hasattr(g, "group_id"):
                        group_ids.append(g.group_id)
                    elif isinstance(g, str):
                        group_ids.append(g)
                return {"status": "success", "consumer_groups": group_ids, "count": len(group_ids)}
            elif action == "lag":
                topic_name = kwargs.get("topic")
                group_id = kwargs.get("group")
                if not topic_name or not group_id:
                    return {"error": "action=lag 需要 topic 与 group 参数"}
                from kafka import KafkaConsumer, TopicPartition
                consumer = KafkaConsumer(topic_name, group_id=group_id, bootstrap_servers=servers_list,
                                         enable_auto_commit=False, auto_offset_reset="latest")
                partitions = consumer.partitions_for_topic(topic_name) or set()
                res = {}
                for p in sorted(partitions):
                    tp_obj = TopicPartition(topic_name, p)
                    end_off = consumer.end_offsets([tp_obj]).get(tp_obj)
                    pos = consumer.position(tp_obj) if tp_obj in consumer.assignment() else None
                    res[p] = {"end_offset": end_off, "position": pos,
                              "lag": (end_off - pos) if (end_off is not None and pos is not None) else None}
                consumer.close()
                return {"status": "success", "topic": topic_name, "group": group_id, "lag": res}
            return {"error": f"未知 action: {action}"}
        except Exception as e:
            return {"error": f"Kafka 监控失败: {e}"}
        finally:
            try:
                admin.close()
            except Exception as _exc5:
                logger.warning("[except:pass] Exception: %s", _exc5, exc_info=True)
    finally:
        if close_db:
            db.close()
# ─── Network Device Query Tool ─────────────────────────────

@register_mcp_tool(
    name="net_device_query",
    description="查询网络设备信息（通过 SSH 执行只读命令）：运行状态/接口信息/LLDP 邻居。连接信息从资产 connection_config 中读取。",
    input_schema={
        "type": "object",
        "properties": {
            "asset_id": {"type": "integer", "description": "网络设备资产 ID（从 assets 表）"},
            "command": {"type": "string", "description": "只读查询命令，如 'show version'、'show interfaces summary'、'show lldp neighbors'（网络设备 CLI）"},
        },
        "required": ["asset_id", "command"],
    },
    risk_level="read_only",
    display_name="查询网络设备",
    expose_to_llm=True,
    location="cloud",
    category="network",
)
def net_device_query(db: Optional[Session] = None, user_id: Optional[int] = None, **kwargs) -> Dict:
    import json as _json
    asset_id = kwargs.get("asset_id")
    command = (kwargs.get("command") or "show version").strip()
    if not asset_id:
        return {"error": "缺少必填参数: asset_id"}
    if not command.lower().startswith(("show", "display", "get", "ping")):
        return {"error": "仅允许只读查询命令（以 show/display/get 开头）"}
    close_db = False
    if db is None:
        db = _get_db()
        close_db = True
    try:
        asset = db.query(Asset).filter(Asset.id == int(asset_id)).first()
        if not asset:
            return {"error": f"资产 {asset_id} 不存在"}
        try:
            from app.services.remediation_service import _ssh_connect
            ssh = _ssh_connect(asset, timeout=15)
            stdin, stdout, stderr = ssh.exec_command(command, timeout=20)
            out = stdout.read().decode(errors="ignore").strip()
            err = stderr.read().decode(errors="ignore").strip()
            ssh.close()
            return {"status": "success", "command": command, "output": out,
                    "error": err, "asset": asset.name, "ip": asset.ip}
        except Exception as e:
            return {"error": f"网络设备 SSH 查询失败: {e}"}
    finally:
        if close_db:
            db.close()
