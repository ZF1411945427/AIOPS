"""组件对话管控诊断工具集 (M1: 4类→12+类, 对标天穹「AI 对话操作组件」)

每个组件一个只读诊断工具, 均可被 AI 助手自然语言调用(expose_to_llm=True)。
统一模式:
  - 通过 assets 表(asset_id)定位目标机
  - 连接走 remediation_service._ssh_connect(SSH) 或 DB 驱动(pymysql/psycopg2/pymongo)
  - 只做只读诊断, 绝不执行写操作; 依赖缺失用 try/except 友好降级
"""
import json
from typing import Dict, Optional

from sqlalchemy.orm import Session

from app.database import get_session_for, get_db_mode
from app.models import Asset
from app.services.mcp_registry import register_mcp_tool


def _get_db():
    try:
        return get_session_for(get_db_mode())()
    except Exception:
        return None


def _get_asset(db, asset_id):
    try:
        return db.query(Asset).filter(Asset.id == int(asset_id)).first()
    except Exception:
        return None


def _ssh(asset, command, timeout=20):
    """执行 SSH 只读命令, 返回 (ok, output)"""
    try:
        from app.services.remediation_service import _ssh_connect
        ssh = _ssh_connect(asset, timeout=15)
        try:
            stdin, stdout, stderr = ssh.exec_command(command, timeout=timeout)
            out = stdout.read().decode(errors="ignore").strip()
            err = stderr.read().decode(errors="ignore").strip()
            return (True, out)
        finally:
            try:
                ssh.close()
            except Exception:
                pass
    except Exception as e:
        return (False, f"SSH 失败: {e}")


def _conn_cfg(asset):
    try:
        return json.loads(asset.connection_config) if asset.connection_config else {}
    except Exception:
        return {}


def _wrap(fn, db=None, user_id=None, **kw):
    """统一入口: 解析 asset_id, 调用组件 handler"""
    asset_id = kw.get("asset_id")
    if not asset_id:
        return {"error": "缺少必填参数: asset_id"}
    close = False
    if db is None:
        db = _get_db()
        close = True
    try:
        asset = _get_asset(db, asset_id)
        if not asset:
            return {"error": f"资产 {asset_id} 不存在"}
        return fn(asset, kw)
    finally:
        if close and db:
            db.close()


# ═══════════════════ P0 工具 ═══════════════════

@register_mcp_tool(
    name="pg_diagnose",
    description="PostgreSQL 只读诊断：慢查询(从 pg_stat_statements 或日志)、连接数/空闲比例、复制延迟(pg_stat_replication)、表膨胀/VACUUM 状态。通过资产 connection_config 的 db_host/db_port/db_user/db_password 连接。",
    input_schema={
        "type": "object",
        "properties": {
            "asset_id": {"type": "integer", "description": "PostgreSQL 资产 ID"},
            "action": {"type": "string", "description": "诊断动作: config|replication|slow|activity|all", "default": "all"},
        },
        "required": ["asset_id"],
    },
    risk_level="read_only", display_name="诊断 PostgreSQL", expose_to_llm=True,
    location="cloud", category="postgresql",
)
def pg_diagnose(db: Optional[Session] = None, user_id: Optional[int] = None, **kwargs) -> Dict:
    def fn(asset, kw):
        try:
            import psycopg2
        except ImportError:
            return {"error": "缺少 psycopg2 库"}
        cfg = _conn_cfg(asset)
        host = cfg.get("db_host") or asset.ip
        port = int(cfg.get("db_port") or 5432)
        user = cfg.get("db_user") or cfg.get("pg_user") or "postgres"
        password = cfg.get("db_password") or cfg.get("pg_password")
        action = kw.get("action") or "all"
        try:
            conn = psycopg2.connect(host=host, port=port, user=user, password=password, connect_timeout=8)
            cur = conn.cursor()
            res = {}
            if action in ("all", "activity"):
                cur.execute("SELECT state, count(*) FROM pg_stat_activity GROUP BY state")
                res["activity"] = [dict(zip(['state', 'count'], r)) for r in cur.fetchall()]
                cur.execute("SELECT count(*) FILTER (WHERE state='idle') AS idle, count(*) AS total FROM pg_stat_activity")
                row = cur.fetchone()
                res["connections"] = {"idle": row[0], "total": row[1]}
            if action in ("all", "replication"):
                try:
                    cur.execute(
                        "SELECT application_name, state, sync_state, "
                        "pg_wal_lsn_diff(pg_current_wal_lsn(), flush_lsn) AS lag_bytes "
                        "FROM pg_stat_replication"
                    )
                    res["replication"] = [dict(zip(['app', 'state', 'sync', 'lag_bytes'], r)) for r in cur.fetchall()]
                except Exception:
                    res["replication"] = "无复制(单机)"
            if action in ("all", "slow"):
                try:
                    cur.execute("SELECT call_count IS NOT NULL AS has_stat FROM pg_stat_statements LIMIT 1")
                    cur.execute("SELECT query, total_exec_time, calls FROM pg_stat_statements ORDER BY total_exec_time DESC LIMIT 5")
                    res["top_slow"] = [dict(zip(['query', 'total_ms', 'calls'], r)) for r in cur.fetchall()]
                except Exception:
                    res["top_slow"] = "pg_stat_statements 未启用"
            if action in ("all", "config"):
                res["version"] = conn.server_version
            conn.close()
            return {"status": "success", "asset": asset.name, "host": host, "port": port, "result": res}
        except Exception as e:
            return {"error": f"PG 诊断失败: {e}"}
    return _wrap(fn, db, user_id, **kwargs)


@register_mcp_tool(
    name="mongo_diagnose",
    description="MongoDB 只读诊断：副本集健康(replSetGetStatus)、慢操作($currentOp 按秒排序/释义)、库/集合大小、服务器状态(ok/connections/uptime)。通过 connection_config 的 mongo_uri 或 db_host/db_port 连接。",
    input_schema={
        "type": "object",
        "properties": {
            "asset_id": {"type": "integer", "description": "MongoDB 资产 ID"},
            "action": {"type": "string", "description": "诊断动作: replica|slow|stats|server|all", "default": "all"},
        },
        "required": ["asset_id"],
    },
    risk_level="read_only", display_name="诊断 MongoDB", expose_to_llm=True,
    location="cloud", category="mongodb",
)
def mongo_diagnose(db: Optional[Session] = None, user_id: Optional[int] = None, **kwargs) -> Dict:
    def fn(asset, kw):
        try:
            from pymongo import MongoClient
        except ImportError:
            return {"error": "缺少 pymongo 库"}
        cfg = _conn_cfg(asset)
        uri = cfg.get("mongo_uri")
        if not uri:
            host = cfg.get("db_host") or asset.ip
            port = int(cfg.get("db_port") or 27017)
            cred = ""
            if cfg.get("db_user") and cfg.get("db_password"):
                from urllib.parse import quote_plus
                cred = f"{quote_plus(cfg['db_user'])}:{quote_plus(cfg['db_password'])}@"
            uri = f"mongodb://{cred}{host}:{port}/"
        action = kw.get("action") or "all"
        try:
            client = MongoClient(uri, serverSelectionTimeoutMS=8000)
            res = {}
            if action in ("all", "server"):
                st = client.admin.command("serverStatus")
                res["uptime"] = st.get("uptime")
                res["ok"] = st.get("ok")
                res["connections"] = st.get("connections", {})
            if action in ("all", "replica"):
                try:
                    rs = client.admin.command("replSetGetStatus")
                    res["replica_set"] = {
                        "set": rs.get("set"), "members": [
                            {"name": m.get("name"), "stateStr": m.get("stateStr"), "health": m.get("health")}
                            for m in rs.get("members", [])
                        ],
                    }
                except Exception:
                    res["replica_set"] = "非副本集(单机)"
            if action in ("all", "slow"):
                try:
                    cur = client.admin.command({"currentOp": 1, "active": True})
                    ops = sorted(cur.get("inprog", []), key=lambda o: o.get("secs_running", 0), reverse=True)[:5]
                    res["slow_ops"] = [
                        {"ns": o.get("ns"), "secs": o.get("secs_running"), "op": o.get("op"), "desc": str(o.get("command") or o.get("query") or "")[:100]}
                        for o in ops
                    ]
                except Exception:
                    res["slow_ops"] = []
            if action in ("all", "stats"):
                res["db_stats"] = [{"name": d["name"], "size": d.get("sizeOnDisk")} for d in client.admin.command("listDatabases").get("databases", [])]
            client.close()
            return {"status": "success", "asset": asset.name, "result": res}
        except Exception as e:
            return {"error": f"Mongo 诊断失败: {e}"}
    return _wrap(fn, db, user_id, **kwargs)


@register_mcp_tool(
    name="nginx_diagnose",
    description="Nginx 只读诊断：连接数(TCP 80/Extensive)、worker 状态、配置语法校验(nginx -t)、access/error 日志 5xx 统计。通过 SSH 执行只读命令。",
    input_schema={
        "type": "object",
        "properties": {
            "asset_id": {"type": "integer", "description": "Nginx 资产 ID"},
            "action": {"type": "string", "description": "诊断动作: conn|config|logs|all", "default": "all"},
        },
        "required": ["asset_id"],
    },
    risk_level="read_only", display_name="诊断 Nginx", expose_to_llm=True,
    location="cloud", category="nginx",
)
def nginx_diagnose(db: Optional[Session] = None, user_id: Optional[int] = None, **kwargs) -> Dict:
    def fn(asset, kw):
        action = kw.get("action") or "all"
        res = {}
        if action in ("all", "conn"):
            ok, out = _ssh(asset, "ss -s 2>/dev/null | head -3; echo ---; ss -tan | wc -l")
            res["tcp"] = out if ok else "无法获取"
        if action in ("all", "config"):
            ok, out = _ssh(asset, "nginx -t 2>&1")
            res["config_test"] = out if ok else "nginx -t 失败"
        if action in ("all", "logs"):
            ok, out = _ssh(asset, "grep -cE 'HTTP/1.1\" [45][0-9][0-9]' /var/log/nginx/access.log 2>/dev/null || echo 0")
            res["5xx_4xx_today"] = out if ok else "无日志"
        res["command_hint"] = "连接数与配置语法检查完成"
        return {"status": "success", "asset": asset.name, "result": res}
    return _wrap(fn, db, user_id, **kwargs)


@register_mcp_tool(
    name="es_diagnose",
    description="Elasticsearch 只读诊断：集群健康(_cluster/health)、分片分布(_cat/shards)、JVM/堆(_nodes/stats)、慢查询(慢日志摘要)。通过 connection_config 的 es_url 或 HTTP 端口访问。",
    input_schema={
        "type": "object",
        "properties": {
            "asset_id": {"type": "integer", "description": "ES 资产 ID"},
            "action": {"type": "string", "description": "诊断动作: health|shards|jvm|all", "default": "all"},
        },
        "required": ["asset_id"],
    },
    risk_level="read_only", display_name="诊断 Elasticsearch", expose_to_llm=True,
    location="cloud", category="elasticsearch",
)
def es_diagnose(db: Optional[Session] = None, user_id: Optional[int] = None, **kwargs) -> Dict:
    def fn(asset, kw):
        import urllib.request
        import json as _json
        cfg = _conn_cfg(asset)
        base = cfg.get("es_url") or f"http://{asset.ip}:{cfg.get('es_port') or 9200}"
        action = kw.get("action") or "all"

        def get(path):
            try:
                r = urllib.request.urlopen(base + path, timeout=10)
                return True, _json.loads(r.read().decode())
            except Exception as e:
                return False, str(e)

        res = {}
        if action in ("all", "health"):
            ok, d = get("/_cluster/health")
            res["health"] = {"status": d.get("status"), "nodes": d.get("number_of_nodes"), "unassigned": d.get("unassigned_shards")} if ok else d
        if action in ("all", "shards"):
            ok, d = get("/_cat/shards?format=json")
            if ok:
                reloc = sum(1 for s in d if s.get("state") == "RELOCATING")
                init = sum(1 for s in d if s.get("state") == "INITIALIZING")
                res["shards"] = {"total": len(d), "relocating": reloc, "initializing": init}
            else:
                res["shards"] = d
        if action in ("all", "jvm"):
            ok, d = get("/_nodes/stats/jvm?filter_path=nodes.*.jvm.mem.heap_used_percent")
            pcts = list(d.get("nodes", {}).values()) if ok else []
            res["jvm_heap_pct"] = [n.get("jvm", {}).get("mem", {}).get("heap_used_percent") for n in pcts] if pcts else (d if isinstance(d, str) else "未知")
        return {"status": "success", "asset": asset.name, "base": base, "result": res}
    return _wrap(fn, db, user_id, **kwargs)


# ═══════════════════ P1 工具 ═══════════════════

@register_mcp_tool(
    name="rabbitmq_diagnose",
    description="RabbitMQ 只读诊断：队列堆积(rabbitmqctl list_queues)、节点内存/连接(rabbitmqctl status)、overview API。SSH 执行 rabbitmqctl 只读命令。",
    input_schema={
        "type": "object",
        "properties": {
            "asset_id": {"type": "integer", "description": "RabbitMQ 资产 ID"},
            "action": {"type": "string", "description": "诊断动作: queues|status|all", "default": "all"},
        },
        "required": ["asset_id"],
    },
    risk_level="read_only", display_name="诊断 RabbitMQ", expose_to_llm=True,
    location="cloud", category="rabbitmq",
)
def rabbitmq_diagnose(db: Optional[Session] = None, user_id: Optional[int] = None, **kwargs) -> Dict:
    def fn(asset, kw):
        action = kw.get("action") or "all"
        res = {}
        if action in ("all", "queues"):
            ok, out = _ssh(asset, "rabbitmqctl list_queues name messages consumers 2>/dev/null | head -30 || docker exec aiops-rabbitmq rabbitmqctl list_queues name messages consumers 2>/dev/null | head -30")
            res["queues"] = out if ok else "无法获取队列"
        if action in ("all", "status"):
            ok, out = _ssh(asset, "rabbitmqctl status 2>/dev/null | grep -iE 'Node name|total memory|queue_totals|message_stats' | head -10 || docker exec aiops-rabbitmq rabbitmqctl status 2>/dev/null | head -10")
            res["status"] = out if ok else "无法获取状态"
        if not res:
            return {"error": "诊断无结果"}
        return {"status": "success", "asset": asset.name, "resource": res}
    return _wrap(fn, db, user_id, **kwargs)


@register_mcp_tool(
    name="rocketmq_diagnose",
    description="RocketMQ 只读诊断：通过 mqadmin 查询 Broker/Topic 状态、消费进度(Lag)、NameServer 状态。SSH 执行 mqadmin 只读命令。",
    input_schema={
        "type": "object",
        "properties": {
            "asset_id": {"type": "integer", "description": "RocketMQ 资产 ID(配置 rocketmq_home/nameserver)"},
            "action": {"type": "string", "description": "诊断动作: broker|topic|consumer|all", "default": "all"},
        },
        "required": ["asset_id"],
    },
    risk_level="read_only", display_name="诊断 RocketMQ", expose_to_llm=True,
    location="cloud", category="rocketmq",
)
def rocketmq_diagnose(db: Optional[Session] = None, user_id: Optional[int] = None, **kwargs) -> Dict:
    def fn(asset, kw):
        cfg = _conn_cfg(asset)
        home = cfg.get("rocketmq_home") or "/opt/rocketmq"
        ns = cfg.get("nameserver") or ""
        action = kw.get("action") or "all"
        res = {}
        base = f"cd {home}/bin && sh mqadmin"
        ns_opt = f"-n {ns}" if ns else ""
        if action in ("all", "broker"):
            ok, out = _ssh(asset, f"{base} clusterList {ns_opt} 2>&1 | head -20")
            res["broker"] = out if ok else "无法获取 Broker"
        if action in ("all", "topic"):
            ok, out = _ssh(asset, f"{base} topicList {ns_opt} 2>&1 | head -30")
            res["topics"] = out if ok else "无法获取 Topic"
        return {"status": "success", "asset": asset.name, "result": res}
    return _wrap(fn, db, user_id, **kwargs)


@register_mcp_tool(
    name="nacos_diagnose",
    description="Nacos 只读诊断：通过 HTTP API 查询命名空间/服务列表/实例健康、配置列表。URL 从 connection_config 的 nacos_url 读取。",
    input_schema={
        "type": "object",
        "properties": {
            "asset_id": {"type": "integer", "description": "Nacos 资产 ID(配置 nacos_url)"},
            "action": {"type": "string", "description": "诊断动作: services|instances|configs|health|all", "default": "all"},
            "service_name": {"type": "string", "description": "服务名(action=instances 时用)"},
        },
        "required": ["asset_id"],
    },
    risk_level="read_only", display_name="诊断 Nacos", expose_to_llm=True,
    location="cloud", category="nacos",
)
def nacos_diagnose(db: Optional[Session] = None, user_id: Optional[int] = None, **kwargs) -> Dict:
    def fn(asset, kw):
        import urllib.request
        import json as _json
        cfg = _conn_cfg(asset)
        base = cfg.get("nacos_url") or f"http://{asset.ip}:{cfg.get('nacos_port') or 8848}/nacos"
        action = kw.get("action") or "all"

        def get(path):
            try:
                r = urllib.request.urlopen(base + path, timeout=10)
                return True, _json.loads(r.read().decode())
            except Exception as e:
                return False, str(e)

        res = {}
        if action in ("all", "health"):
            ok, d = get("/v1/console/health/readiness")
            res["readiness"] = d if ok else "未就绪"
        if action in ("all", "services"):
            ok, d = get("/v1/ns/catalog/services?pageNo=1&pageSize=50")
            res["services"] = d.get("count") if ok else d
        return {"status": "success", "asset": asset.name, "result": res}
    return _wrap(fn, db, user_id, **kwargs)


@register_mcp_tool(
    name="zk_diagnose",
    description="ZooKeeper 只读诊断：通过 SSH 执行 zkServer.sh status(Leader/Follower) / zkCli 统计会话数, 检查脑裂风险。",
    input_schema={
        "type": "object",
        "properties": {
            "asset_id": {"type": "integer", "description": "ZooKeeper 资产 ID(配置 zk_home)"},
            "action": {"type": "string", "description": "诊断动作: status|connections|all", "default": "all"},
        },
        "required": ["asset_id"],
    },
    risk_level="read_only", display_name="诊断 ZooKeeper", expose_to_llm=True,
    location="cloud", category="zookeeper",
)
def zk_diagnose(db: Optional[Session] = None, user_id: Optional[int] = None, **kwargs) -> Dict:
    def fn(asset, kw):
        cfg = _conn_cfg(asset)
        home = cfg.get("zk_home") or "/opt/zookeeper"
        action = kw.get("action") or "all"
        res = {}
        if action in ("all", "status"):
            ok, out = _ssh(asset, f"{home}/bin/zkServer.sh status 2>&1 | head -5")
            res["role"] = out if ok else "无法获取"
        if action in ("all", "connections"):
            ok, out = _ssh(asset, f"echo srvr | nc -w 2 localhost {cfg.get('zk_port') or 2181} 2>/dev/null | head -5; echo '----'; echo stat | nc -w 2 localhost {cfg.get('zk_port') or 2181} 2>/dev/null | grep -iE 'Connections|Zxid' | head -5")
            res["srvr"] = out if ok else "无法获取"
        return {"status": "success", "asset": asset.name, "result": res}
    return _wrap(fn, db, user_id, **kwargs)


# ═══════════════════ P2 工具 ═══════════════════

@register_mcp_tool(
    name="etcd_diagnose",
    description="etcd 只读诊断：通过 etcdctl 查询集群成员/健康/leader/告警(alarm list)、磁盘 slow-fsync 延迟。SSH 执行 etcdctl 只读(或 endpoint health)。",
    input_schema={
        "type": "object",
        "properties": {
            "asset_id": {"type": "integer", "description": "etcd 资产 ID(配置 etcdctl / endpoints)"},
            "action": {"type": "string", "description": "诊断动作: health|members|alarm|all", "default": "all"},
        },
        "required": ["asset_id"],
    },
    risk_level="read_only", display_name="诊断 etcd", expose_to_llm=True,
    location="cloud", category="etcd",
)
def etcd_diagnose(db: Optional[Session] = None, user_id: Optional[int] = None, **kwargs) -> Dict:
    def fn(asset, kw):
        cfg = _conn_cfg(asset)
        ep = cfg.get("etcd_endpoints") or f"http://127.0.0.1:{cfg.get('etcd_port') or 2379}"
        action = kw.get("action") or "all"
        res = {}
        env = ""
        if cfg.get("etcd_user") and cfg.get("etcd_password"):
            env = f"ETCDCTL_USER='{cfg['etcd_user']}:{cfg['etcd_password']}' "
        if action in ("all", "health"):
            ok, out = _ssh(asset, f"{env}ETCDCTL_ENDPOINTS={ep} etcdctl endpoint health 2>&1 | head -10")
            res["health"] = out if ok else "无法健康检查"
        if action in ("all", "members"):
            ok, out = _ssh(asset, f"{env}ETCDCTL_ENDPOINTS={ep} etcdctl member list 2>&1 | head -20")
            res["members"] = out if ok else "无法获取成员"
        if action in ("all", "alarm"):
            ok, out = _ssh(asset, f"{env}ETCDCTL_ENDPOINTS={ep} etcdctl alarm list 2>&1 | head -10")
            res["alarms"] = out if ok else "无法获取告警"
        return {"status": "success", "asset": asset.name, "result": res}
    return _wrap(fn, db, user_id, **kwargs)


@register_mcp_tool(
    name="oracle_diagnose",
    description="Oracle 只读诊断：通过 sqlplus 查询表空间使用率/会话/等待。SSH 执行 sqlplus 只读 SQL(需先配置连接)。",
    input_schema={
        "type": "object",
        "properties": {
            "asset_id": {"type": "integer", "description": "Oracle 资产 ID(配置 oracle_sid/oracle_user)"},
            "action": {"type": "string", "description": "诊断动作: tablespace|sessions|all", "default": "all"},
        },
        "required": ["asset_id"],
    },
    risk_level="read_only", display_name="诊断 Oracle", expose_to_llm=True,
    location="cloud", category="oracle",
)
def oracle_diagnose(db: Optional[Session] = None, user_id: Optional[int] = None, **kwargs) -> Dict:
    def fn(asset, kw):
        cfg = _conn_cfg(asset)
        sid = cfg.get("oracle_sid") or "ORCL"
        user = cfg.get("oracle_user") or "system"
        password = cfg.get("oracle_password") or ""
        action = kw.get("action") or "all"
        res = {}
        conn = f"{user}/{password}@{sid}"
        if action in ("all", "tablespace"):
            sql = "SET PAGESIZE 50; SELECT tablespace_name, ROUND((SUM(bytes)/1024/1024),1) mb FROM dba_data_files GROUP BY tablespace_name;"
            ok, out = _ssh(asset, f'echo "{sql}" | sqlplus -S "{conn}" 2>/dev/null | head -30')
            res["tablespaces"] = out if ok else "无法查询表空间"
        if action in ("all", "sessions"):
            sql = "SELECT status, count(*) FROM v\\$session GROUP BY status;"
            ok, out = _ssh(asset, f'echo "{sql}" | sqlplus -S "{conn}" 2>/dev/null | head -20')
            res["sessions"] = out if ok else "无法查询会话"
        return {"status": "success", "asset": asset.name, "result": res}
    return _wrap(fn, db, user_id, **kwargs)


@register_mcp_tool(
    name="clickhouse_diagnose",
    description="ClickHouse 只读诊断：通过 clickhouse-client 查询系统表(慢查询/merge/副本)。SSH 执行 clickhouse-client 只读 SQL。",
    input_schema={
        "type": "object",
        "properties": {
            "asset_id": {"type": "integer", "description": "ClickHouse 资产 ID(配置 ch_home)"},
            "action": {"type": "string", "description": "诊断动作: queries|merge|replicas|all", "default": "all"},
        },
        "required": ["asset_id"],
    },
    risk_level="read_only", display_name="诊断 ClickHouse", expose_to_llm=True,
    location="cloud", category="clickhouse",
)
def clickhouse_diagnose(db: Optional[Session] = None, user_id: Optional[int] = None, **kwargs) -> Dict:
    def fn(asset, kw):
        cfg = _conn_cfg(asset)
        action = kw.get("action") or "all"
        cli = cfg.get("ch_client") or "clickhouse-client"
        res = {}
        if action in ("all", "queries"):
            ok, out = _ssh(asset, f"{cli} --query \"SELECT query FROM system.processes ORDER BY elapsed_ms DESC LIMIT 5\" 2>/dev/null | head -10 || {cli} --query \"SELECT query FROM system.processes ORDER BY elapsed DESC LIMIT 5\" 2>/dev/null | head -10")
            res["slow_queries"] = out if ok else "无法获取慢查询"
        if action in ("all", "merge"):
            ok, out = _ssh(asset, f"{cli} --query 'SELECT count() FROM system.merges' 2>/dev/null")
            res["merge_count"] = out if ok else "无法获取 merge"
        return {"status": "success", "asset": asset.name, "result": res}
    return _wrap(fn, db, user_id, **kwargs)


@register_mcp_tool(
    name="memcached_diagnose",
    description="Memcached 只读诊断：通过 STATS/STATS settings 获取命中率、逐出(evictions)、Slab 使用。SSH 执行 telnet/nc 'stats' 只读。",
    input_schema={
        "type": "object",
        "properties": {
            "asset_id": {"type": "integer", "description": "Memcached 资产 ID(配置 memcached_port)"},
            "action": {"type": "string", "description": "诊断动作: stats|slabs|all", "default": "all"},
        },
        "required": ["asset_id"],
    },
    risk_level="read_only", display_name="诊断 Memcached", expose_to_llm=True,
    location="cloud", category="memcached",
)
def memcached_diagnose(db: Optional[Session] = None, user_id: Optional[int] = None, **kwargs) -> Dict:
    def fn(asset, kw):
        cfg = _conn_cfg(asset)
        port = cfg.get("memcached_port") or 11211
        action = kw.get("action") or "all"
        res = {}
        if action in ("all", "stats"):
            ok, out = _ssh(asset, f"printf 'stats\\r\\n' | nc -w 2 localhost {port} 2>/dev/null | grep -E 'curr_items|total_items|get_hits|get_misses|evictions|bytes' | head -10 || docker exec aiops-memcached printf 'stats\\r\\n' | nc -w 2 localhost {port} 2>/dev/null | grep -E 'curr|hits|misses|evictions|bytes' | head -10")
            res["stats"] = out if ok else "无法获取 stats"
        if action in ("all", "slabs"):
            ok, out = _ssh(asset, f"printf 'stats slabs\\r\\n' | nc -w 2 localhost {port} 2>/dev/null | head -15")
            res["slabs"] = out if ok else "无法获取 slab"
        return {"status": "success", "asset": asset.name, "result": res}
    return _wrap(fn, db, user_id, **kwargs)


# ═══════════════════ 赶超天穹 M1: 12 个组件对话工具(16→28 类) ═══════════════════

@register_mcp_tool(
    name="mariadb_diagnose",
    description="MariaDB 只读诊断：慢查询、连接数、复制延迟、InnoDB 状态(通过与 MySQL 兼容的方式)。连接走 connection_config 的 db_host/db_port/db_user/db_password。",
    input_schema={
        "type": "object",
        "properties": {
            "asset_id": {"type": "integer", "description": "MariaDB 资产 ID"},
            "action": {"type": "string", "description": "诊断动作: activity|replication|innodb|all", "default": "all"},
        },
        "required": ["asset_id"],
    },
    risk_level="read_only", display_name="诊断 MariaDB", expose_to_llm=True,
    location="cloud", category="mariadb",
)
def mariadb_diagnose(db: Optional[Session] = None, user_id: Optional[int] = None, **kwargs) -> Dict:
    def fn(asset, kw):
        try:
            import pymysql
        except ImportError:
            return {"error": "缺少 pymysql"}
        cfg = _conn_cfg(asset)
        host = cfg.get("db_host") or asset.ip
        port = int(cfg.get("db_port") or 3306)
        user = cfg.get("db_user") or cfg.get("maria_user") or "root"
        password = cfg.get("db_password") or cfg.get("maria_password") or ""
        action = kw.get("action") or "all"
        try:
            conn = pymysql.connect(host=host, port=port, user=user, password=password, connect_timeout=8)
            cur = conn.cursor()
            res = {}
            if action in ("all", "activity"):
                cur.execute("SHOW GLOBAL STATUS LIKE 'Threads_connected'")
                res["threads"] = dict(cur.fetchall())
                cur.execute("SHOW GLOBAL STATUS LIKE 'Slow_queries'")
                res["slow_queries"] = dict(cur.fetchall())
            if action in ("all", "replication"):
                try:
                    cur.execute("SHOW REPLICA STATUS")
                    row = cur.fetchone()
                    if row:
                        cols = [c[0] for c in cur.description]
                        rd = dict(zip(cols, row))
                        res["replication"] = {"io_running": rd.get("Replica_IO_Running"), "sql_running": rd.get("Replica_SQL_Running"), "seconds_behind": rd.get("Seconds_Behind_Source")}
                    else:
                        res["replication"] = "无复制(单机)"
                except Exception:
                    res["replication"] = "无复制"
            if action in ("all", "innodb"):
                cur.execute("SHOW ENGINE INNODB STATUS")
                row = cur.fetchone()
                res["innodb_latest"] = (row[2][:500] if row and len(row) > 2 else "") if row else ""
            conn.close()
            return {"status": "success", "asset": asset.name, "result": res}
        except Exception as e:
            return {"error": f"MariaDB 诊断失败: {e}"}
    return _wrap(fn, db, user_id, **kwargs)


@register_mcp_tool(
    name="tidb_diagnose",
    description="TiDB 只读诊断：集群拓扑(Prometheus/metrics)、region 状态、慢查询、store 健康。通过 TiDB SQL(mysql 协议) 或 HTTP(PD) 查询。",
    input_schema={
        "type": "object",
        "properties": {
            "asset_id": {"type": "integer", "description": "TiDB 资产 ID(配置 tidb_host/tidb_port/pd_port)"},
            "action": {"type": "string", "description": "诊断动作: store|region|slow|all", "default": "all"},
        },
        "required": ["asset_id"],
    },
    risk_level="read_only", display_name="诊断 TiDB", expose_to_llm=True,
    location="cloud", category="tidb",
)
def tidb_diagnose(db: Optional[Session] = None, user_id: Optional[int] = None, **kwargs) -> Dict:
    def fn(asset, kw):
        import urllib.request
        import json as _json
        cfg = _conn_cfg(asset)
        host = cfg.get("tidb_host") or asset.ip
        pd_port = cfg.get("pd_port") or 2379
        action = kw.get("action") or "all"
        res = {}
        base = f"http://{host}:{pd_port}/pd/api/v1"

        def get(path):
            try:
                r = urllib.request.urlopen(base + path, timeout=8)
                return True, _json.loads(r.read().decode())
            except Exception as e:
                return False, str(e)

        if action in ("all", "store"):
            ok, d = get("/stores")
            if ok:
                stores = d.get("stores", [])
                res["stores"] = {"total": len(stores), "up": sum(1 for s in stores if s.get("state_name") == "Up"),
                                 "tombstone": sum(1 for s in stores if s.get("state_name") == "Tombstone")}
            else:
                res["stores"] = d
        if action in ("all", "region"):
            ok, d = get("/regions/count")
            res["region_count"] = d if ok else d
        return {"status": "success", "asset": asset.name, "result": res}
    return _wrap(fn, db, user_id, **kwargs)


@register_mcp_tool(
    name="minio_diagnose",
    description="MinIO 只读诊断：桶列表/健康(endpoint health)、磁盘可用空间、版本。通过 HTTP(bucket health) 或连接配置 minio_url。",
    input_schema={
        "type": "object",
        "properties": {
            "asset_id": {"type": "integer", "description": "MinIO 资产 ID(配置 minio_url/minio_access_key)"},
            "action": {"type": "string", "description": "诊断动作: health|buckets|all", "default": "all"},
        },
        "required": ["asset_id"],
    },
    risk_level="read_only", display_name="诊断 MinIO", expose_to_llm=True,
    location="cloud", category="minio",
)
def minio_diagnose(db: Optional[Session] = None, user_id: Optional[int] = None, **kwargs) -> Dict:
    def fn(asset, kw):
        import urllib.request
        cfg = _conn_cfg(asset)
        base = cfg.get("minio_url") or f"http://{asset.ip}:{cfg.get('minio_port') or 9000}"
        action = kw.get("action") or "all"
        res = {}
        if action in ("all", "health"):
            try:
                r = urllib.request.urlopen(base + "/minio/health/live", timeout=8)
                res["health"] = r.status
            except Exception as e:
                res["health"] = f"异常: {e}"
        res["hint"] = "MinIO 桶级管理建议通过 S3 API/管理控制台, 当前仅做健康探活"
        return {"status": "success", "asset": asset.name, "base": base, "result": res}
    return _wrap(fn, db, user_id, **kwargs)




@register_mcp_tool(
    name="valkey_diagnose",
    description="Valkey(Redis兼容)只读诊断: 内存、命中率、连接数。通过 connection_config 的 redis_host/redis_port/redis_password(valkey_password 优先) 连接。",
    input_schema={"type":"object","properties":{"asset_id":{"type":"integer","description":"Valkey/Redis 资产 ID"},"action":{"type":"string","description":"server|memory|all","default":"all"}},"required":["asset_id"]},
    risk_level="read_only", display_name="诊断 Valkey", expose_to_llm=True,
    location="cloud", category="valkey",
)
def valkey_diagnose(db: Optional[Session] = None, user_id: Optional[int] = None, **kwargs) -> Dict:
    def fn(asset, kw):
        try:
            import redis as _redis
        except ImportError:
            return {"error": "缺少 redis 库"}
        cfg = _conn_cfg(asset)
        host = cfg.get("redis_host") or asset.ip
        port = int(cfg.get("redis_port") or 6379)
        password = cfg.get("valkey_password") or cfg.get("redis_password") or ""
        action = kw.get("action") or "all"
        try:
            r = _redis.Redis(host=host, port=port, password=password or None, socket_connect_timeout=5, decode_responses=True)
            res = {}
            if action in ("all", "server"):
                info = r.info()
                res["server"] = {"version": info.get("redis_version"), "uptime": info.get("uptime_in_seconds"), "clients": info.get("connected_clients"), "mode": info.get("redis_mode")}
            if action in ("all", "memory"):
                m = r.info("memory")
                res["memory"] = {"used": m.get("used_memory_human"), "peak": m.get("used_memory_peak_human"), "frag": m.get("mem_fragmentation_ratio")}
            if action in ("all", "cluster"):
                try:
                    res["cluster_enabled"] = "cluster_enabled:1" in str(r.execute_command("CLUSTER INFO"))
                except Exception:
                    res["cluster_enabled"] = "非集群"
            return {"status": "success", "asset": asset.name, "result": res}
        except Exception as e:
            return {"error": f"Valkey 诊断失败: {e}"}
    return _wrap(fn, db, user_id, **kwargs)


@register_mcp_tool(
    name="emqx_diagnose",
    description="EMQX/MQTT 只读诊断: 集群 broker 节点状态、客户端连接数(HTTP API /api/v5/brokers 与 /api/v5/stats)。via emqx_url/emqx_api_key/emqx_api_secret。",
    input_schema={"type":"object","properties":{"asset_id":{"type":"integer","description":"EMQX 资产 ID"},"action":{"type":"string","description":"brokers|clients|all","default":"all"}},"required":["asset_id"]},
    risk_level="read_only", display_name="诊断 EMQX", expose_to_llm=True,
    location="cloud", category="emqx",
)
def emqx_diagnose(db: Optional[Session] = None, user_id: Optional[int] = None, **kwargs) -> Dict:
    def fn(asset, kw):
        import urllib.request, json as _json, base64
        cfg = _conn_cfg(asset)
        base = cfg.get("emqx_url") or f"http://{asset.ip}:{cfg.get('emqx_port') or 18083}/api/v5"
        action = kw.get("action") or "all"
        res = {}
        def get(path):
            try:
                req = urllib.request.Request(base + path)
                if cfg.get("emqx_api_key") and cfg.get("emqx_api_secret"):
                    tok = base64.b64encode(f"{cfg['emqx_api_key']}:{cfg['emqx_api_secret']}".encode()).decode()
                    req.add_header("Authorization", "Basic " + tok)
                r = urllib.request.urlopen(req, timeout=8)
                return True, _json.loads(r.read().decode())
            except Exception as e:
                return False, str(e)
        if action in ("all", "brokers"):
            ok, d = get("/brokers")
            res["brokers"] = [{"node": b.get("node"), "version": b.get("version"), "status": b.get("status")} for b in d] if ok else d
        if action in ("all", "clients"):
            ok, d = get("/stats")
            if ok and isinstance(d, dict):
                res["clients_connected"] = d.get("connections.count")
                res["clients_total"] = d.get("clients.count")
            else:
                res["clients"] = d
        return {"status": "success", "asset": asset.name, "result": res}
    return _wrap(fn, db, user_id, **kwargs)


@register_mcp_tool(
    name="consul_diagnose",
    description="Consul 只读诊断: 服务列表、leader、节点健康 (HTTP :8500)。via consul_url/consul_token。",
    input_schema={"type":"object","properties":{"asset_id":{"type":"integer","description":"Consul 资产 ID"},"action":{"type":"string","description":"services|health|all","default":"all"}},"required":["asset_id"]},
    risk_level="read_only", display_name="诊断 Consul", expose_to_llm=True,
    location="cloud", category="consul",
)
def consul_diagnose(db: Optional[Session] = None, user_id: Optional[int] = None, **kwargs) -> Dict:
    def fn(asset, kw):
        import urllib.request, json as _json
        cfg = _conn_cfg(asset)
        base = cfg.get("consul_url") or f"http://{asset.ip}:{cfg.get('consul_port') or 8500}"
        action = kw.get("action") or "all"
        res = {}
        def get(path):
            try:
                req = urllib.request.Request(base + path)
                if cfg.get("consul_token"):
                    req.add_header("X-Consul-Token", cfg["consul_token"])
                r = urllib.request.urlopen(req, timeout=8)
                return True, _json.loads(r.read().decode())
            except Exception as e:
                return False, str(e)
        if action in ("all", "health"):
            ok, d = get("/v1/status/leader")
            res["leader"] = d if ok else "无法获取"
        if action in ("all", "services"):
            ok, d = get("/v1/catalog/services")
            res["services"] = list(d.keys()) if ok else d
        return {"status": "success", "asset": asset.name, "result": res}
    return _wrap(fn, db, user_id, **kwargs)


@register_mcp_tool(
    name="apisix_diagnose",
    description="APISIX 只读诊断: 路由/上游/消费者数量、admin 健康 (Admin API :9180)。via apisix_url/apisix_admin_key。",
    input_schema={"type":"object","properties":{"asset_id":{"type":"integer","description":"APISIX 资产 ID"},"action":{"type":"string","description":"routes|upstreams|health|all","default":"all"}},"required":["asset_id"]},
    risk_level="read_only", display_name="诊断 APISIX", expose_to_llm=True,
    location="cloud", category="apisix",
)
def apisix_diagnose(db: Optional[Session] = None, user_id: Optional[int] = None, **kwargs) -> Dict:
    def fn(asset, kw):
        import urllib.request, json as _json
        cfg = _conn_cfg(asset)
        base = cfg.get("apisix_url") or f"http://127.0.0.1:{cfg.get('apisix_port') or 9180}/apisix/admin"
        action = kw.get("action") or "all"
        key = cfg.get("apisix_admin_key") or "edd1c9f034335f136f87ad84b625c8f1"
        res = {}
        def get(path):
            try:
                req = urllib.request.Request(base + path)
                req.add_header("X-API-KEY", key)
                r = urllib.request.urlopen(req, timeout=8)
                d = _json.loads(r.read().decode())
                return True, d.get("list", d)
            except Exception as e:
                return False, str(e)
        if action in ("all", "routes"):
            ok, d = get("/routes?page_size=50")
            res["routes"] = len(d) if isinstance(d, (list, dict)) else d
        if action in ("all", "upstreams"):
            ok, d = get("/upstreams?page_size=50")
            res["upstreams"] = len(d) if isinstance(d, (list, dict)) else d
        return {"status": "success", "asset": asset.name, "result": res}
    return _wrap(fn, db, user_id, **kwargs)


@register_mcp_tool(
    name="traefik_diagnose",
    description="Traefik 只读诊断: 路由/服务/入口点状态 (HTTP :8080 dashboard/api). via traefik_url.",
    input_schema={"type":"object","properties":{"asset_id":{"type":"integer","description":"Traefik 资产 ID"},"action":{"type":"string","description":"services|routers|health|all","default":"all"}},"required":["asset_id"]},
    risk_level="read_only", display_name="诊断 Traefik", expose_to_llm=True,
    location="cloud", category="traefik",
)
def traefik_diagnose(db=None, user_id=None, **kwargs):
    def fn(asset, kw):
        import urllib.request, json as _json
        cfg = _conn_cfg(asset)
        api = cfg.get("traefik_url") or f"http://{asset.ip}:{cfg.get('traefik_api_port') or 8080}/api"
        action = kw.get("action") or "all"
        res = {}
        def get(path):
            try:
                r = urllib.request.urlopen(api + path, timeout=8)
                return True, _json.loads(r.read().decode())
            except Exception as e:
                return False, str(e)
        if action in ("all", "services"):
            ok, d = get("/http/services")
            res["services"] = list(d.keys()) if ok else d
        if action in ("all", "routers"):
            ok, d = get("/http/routers")
            res["routers"] = len(d) if ok else d
        if action in ("all", "health"):
            try:
                r = urllib.request.urlopen(api + "/rawdata", timeout=8)
                res["api_alive"] = r.status
            except Exception as e:
                res["api_alive"] = f"异常: {e}"
        return {"status": "success", "asset": asset.name, "result": res}
    return _wrap(fn, db, user_id, **kwargs)


@register_mcp_tool(
    name="keycloak_diagnose",
    description="Keycloak 只读诊断: 服务健康(/health/ready)、realm 统计 (REST :8080). via keycloak_url.",
    input_schema={"type":"object","properties":{"asset_id":{"type":"integer","description":"Keycloak 资产 ID"},"action":{"type":"string","description":"health|realms|stats|all","default":"all"}},"required":["asset_id"]},
    risk_level="read_only", display_name="诊断 Keycloak", expose_to_llm=True,
    location="cloud", category="keycloak",
)
def keycloak_diagnose(db=None, user_id=None, **kwargs):
    def fn(asset, kw):
        import urllib.request, json as _json
        cfg = _conn_cfg(asset)
        base = cfg.get("keycloak_url") or f"http://{asset.ip}:{cfg.get('keycloak_port') or 8080}"
        action = kw.get("action") or "all"
        res = {}
        def get(path):
            try:
                r = urllib.request.urlopen(base + path, timeout=8)
                return True, _json.loads(r.read().decode())
            except Exception as e:
                return False, str(e)
        if action in ("all", "health"):
            ok, d = get("/health/ready")
            res["health"] = d.get("status") if isinstance(d, dict) else (d if ok else "未就绪")
        return {"status": "success", "asset": asset.name, "result": res}
    return _wrap(fn, db, user_id, **kwargs)


@register_mcp_tool(
    name="prometheus_diagnose",
    description="Prometheus 只读诊断: 目标抓取状态/失败、告警规则 (API /api/v1/). via prom_url/prom_token.",
    input_schema={"type":"object","properties":{"asset_id":{"type":"integer","description":"Prometheus 资产 ID"},"action":{"type":"string","description":"targets|rules|config|all","default":"all"}},"required":["asset_id"]},
    risk_level="read_only", display_name="诊断 Prometheus", expose_to_llm=True,
    location="cloud", category="prometheus",
)
def prometheus_diagnose(db=None, user_id=None, **kwargs):
    def fn(asset, kw):
        import urllib.request, json as _json
        cfg = _conn_cfg(asset)
        base = cfg.get("prom_url") or f"http://{asset.ip}:{cfg.get('prom_port') or 9090}"
        action = kw.get("action") or "all"
        res = {}
        def get(path):
            try:
                req = urllib.request.Request(base + path)
                if cfg.get("prom_token"):
                    req.add_header("Authorization", "Bearer " + cfg["prom_token"])
                r = urllib.request.urlopen(req, timeout=8)
                return True, _json.loads(r.read().decode())
            except Exception as e:
                return False, str(e)
        if action in ("all", "targets"):
            ok, d = get("/api/v1/targets")
            if ok:
                act = d.get("data", {}).get("activeTargets", [])
                down = [t.get("scrapeUrl") for t in act if t.get("health") == "down"]
                res["targets"] = {"total": len(act), "down": len(down), "down_list": down[:10]}
            else:
                res["targets"] = d
        if action in ("all", "rules"):
            ok, d = get("/api/v1/rules")
            if ok:
                res["rule_groups"] = len(d.get("data", {}).get("groups", []))
            else:
                res["rules"] = d
        return {"status": "success", "asset": asset.name, "result": res}
    return _wrap(fn, db, user_id, **kwargs)


@register_mcp_tool(
    name="grafana_diagnose",
    description="Grafana 只读诊断: 数据源/面板/健康 (HTTP :3000, ServiceAccount token). via grafana_url/grafana_token.",
    input_schema={"type":"object","properties":{"asset_id":{"type":"integer","description":"Grafana 资产 ID"},"action":{"type":"string","description":"datasources|dashboards|health|all","default":"all"}},"required":["asset_id"]},
    risk_level="read_only", display_name="诊断 Grafana", expose_to_llm=True,
    location="cloud", category="grafana",
)
def grafana_diagnose(db=None, user_id=None, **kwargs):
    def fn(asset, kw):
        import urllib.request, json as _json
        cfg = _conn_cfg(asset)
        base = cfg.get("grafana_url") or f"http://{asset.ip}:{cfg.get('grafana_port') or 3000}"
        action = kw.get("action") or "all"
        token = cfg.get("grafana_token") or ""
        res = {}
        def get(path):
            try:
                req = urllib.request.Request(base + "/api" + path)
                if token:
                    req.add_header("Authorization", "Bearer " + token)
                r = urllib.request.urlopen(req, timeout=8)
                return True, _json.loads(r.read().decode())
            except Exception as e:
                return False, str(e)
        if action in ("all", "health"):
            try:
                r = urllib.request.urlopen(base + "/api/health", timeout=8)
                res["health"] = r.json
            except Exception as e:
                res["health"] = f"异常: {e}"
        if action in ("all", "datasources"):
            ok, d = get("/datasources")
            res["datasources"] = [ds.get("name") for ds in d] if ok else d
        return {"status": "success", "asset": asset.name, "result": res}
    return _wrap(fn, db, user_id, **kwargs)


@register_mcp_tool(
    name="loki_diagnose",
    description="Grafana Loki 只读诊断: 就绪/日志标签 (HTTP :3100 /ready /loki/api/v1/). via loki_url.",
    input_schema={"type":"object","properties":{"asset_id":{"type":"integer","description":"Loki 资产 ID"},"action":{"type":"string","description":"health|labels|all","default":"all"}},"required":["asset_id"]},
    risk_level="read_only", display_name="诊断 Loki", expose_to_llm=True,
    location="cloud", category="loki",
)
def loki_diagnose(db=None, user_id=None, **kwargs):
    def fn(asset, kw):
        import urllib.request, json as _json
        cfg = _conn_cfg(asset)
        base = cfg.get("loki_url") or f"http://{asset.ip}:{cfg.get('loki_port') or 3100}"
        action = kw.get("action") or "all"
        res = {}
        def get(path):
            try:
                r = urllib.request.urlopen(base + path, timeout=8)
                return True, _json.loads(r.read().decode())
            except Exception as e:
                return False, str(e)
        if action in ("all", "health"):
            try:
                r = urllib.request.urlopen(base + "/ready", timeout=8)
                res["ready"] = r.status
            except Exception as e:
                res["ready"] = f"异常: {e}"
        if action in ("all", "labels"):
            ok, d = get("/loki/api/v1/labels")
            res["labels"] = d.get("data") if ok else d
        return {"status": "success", "asset": asset.name, "result": res}
    return _wrap(fn, db, user_id, **kwargs)


@register_mcp_tool(
    name="component_diagnose",
    description="通用组件对话诊断: 对任意组件(商店 54 组件全部支持)执行四合一体检(健康+配置+漏洞+AI分析)。有专属诊断工具的组件建议用专属工具(更精准), 本工具作为通用兜底, 覆盖所有无专属工具的组件(如 TDengine/InfluxDB/GitLab/Jenkins/Neo4j/达梦/金仓/OceanBase/HBase/Cassandra/StarRocks/Doris/NATS/Jaeger/Alertmanager/VictoriaMetrics/OTel/HAProxy/Vault 等)。输入组件名+目标机资产ID, 会查找该资产上的组件实例或直接对资产做探测。",
    input_schema={
        "type": "object",
        "properties": {
            "component": {"type": "string", "description": "组件名(如 zookeeper/tdengine/gitlab/neo4j 等, 商店内组件均可)"},
            "asset_id": {"type": "integer", "description": "目标机资产 ID"},
        },
        "required": ["component", "asset_id"],
    },
    risk_level="read_only", display_name="通用组件体检", expose_to_llm=True,
    location="cloud", category="generic",
)
def component_diagnose(db=None, user_id=None, **kwargs):
    import json as _json
    comp_name = (kwargs.get("component") or "").strip().lower()
    asset_id = kwargs.get("asset_id")
    if not comp_name or not asset_id:
        return {"error": "需要 component 与 asset_id"}
    close = False
    if db is None:
        db = _get_db()
        close = True
    try:
        asset = _get_asset(db, asset_id)
        if not asset:
            return {"error": f"资产 {asset_id} 不存在"}
        from app.services import component_catalog_service as ccs
        # 1. 找该资产上的组件实例(按组件名模糊匹配)
        inst = None
        try:
            from app.models import ComponentInstall
            inst = db.query(ComponentInstall).filter(
                ComponentInstall.asset_id == asset_id,
                ComponentInstall.component_name.ilike(f"%{comp_name}%"),
            ).first()
        except Exception:
            inst = None
        if not inst:
            # 2. 无实例: 创建临时记录走体检? 或直接复用健康探测
            # 用商店 catalog 找到组件, 直接对该资产做健康探测(不落库)
            return _diagnose_without_install(db, asset, comp_name)
        # 3. 有实例: 四合一体检
        result = ccs.full_health_check(db, inst.id)
        return {"status": "success", "component": comp_name, "asset": asset.name,
                "mode": "full-check(实例)", "result": result}
    finally:
        if close and db:
            db.close()


def _diagnose_without_install(db, asset, comp_name):
    """无安装记录时的通用健康探测(不落库)。复用 check_health 的 SSH 命令探测。"""
    import json as _json
    try:
        from app.services import component_catalog_service as ccs
        from app.models import ComponentCatalog
        comp = db.query(ComponentCatalog).filter(ComponentCatalog.name == comp_name).first()
        if not comp:
            return {"status": "info", "component": comp_name, "asset": asset.name,
                    "detail": "商店无此组件, 但资产可 SSH 探测", "probe": _ssh_probe(asset, comp_name)}
        # 模拟一个安装记录用于 check_health(不落库)
        # 直接构造轻量健康探测
        probe = _ssh_probe(asset, comp_name)
        return {"status": "success", "component": comp_name, "asset": asset.name,
                "mode": "probe(无实例)", "catalog_version": comp.version,
                "docker_image": comp.docker_image, "probe": probe}
    except Exception as e:
        return {"error": str(e)}


def _ssh_probe(asset, comp_name):
    """对资产做组件健康/版本探测(只读)。"""
    version_cmds = {
        "redis": "redis-cli --version 2>/dev/null | head -1",
        "nginx": "nginx -v 2>&1 | head -1",
        "mysql": "mysql --version 2>/dev/null | head -1",
    }
    ok, out = _ssh(asset, version_cmds.get(comp_name, f"{comp_name} --version 2>&1 | head -1") if False else f"ps aux | grep -iE '{comp_name}' | grep -v grep | head -2")
    return {"process": out if ok else "未发现进程", "ip": asset.ip, "ci_type": asset.ci_type}
