import json
import re
from datetime import datetime, timedelta
from sqlalchemy import func
from app.models import Asset, Alert, AssetRelation
from app.database import get_session_for, get_db_mode


HEALTH_GREEN = "green"
HEALTH_GRAY = "gray"
HEALTH_RED = "red"

DOMAIN_DEFAULT = "默认"

# ── 分层健康判断阈值 ──
API_ERROR_RATE_THRESHOLD = 0.05
API_LATENCY_THRESHOLD_MS = 1000
INFRA_CPU_THRESHOLD = 90
INFRA_MEMORY_THRESHOLD = 90
INFRA_DISK_THRESHOLD = 85
HEALTH_WINDOW_MINUTES = 5

# ── 可观测信号 → 层级映射 ──
# 每个层级只关联对应的可观测信号类型，不混搭
ALERT_SIGNAL_MAP = {
    # Trace（链路）→ 功能接口
    "trace": [
        "api_error_rate", "api_latency", "api_p99", "api_throughput",
        "trace_error", "trace_latency",
    ],
    # Log（日志）→ 微服务
    "log": [
        "k8s_event", "pod_anomaly", "log_anomaly",
        "log_error", "log_exception", "container_restart",
    ],
    # Metric（指标）→ 基础设施
    "metric": [
        "cpu_usage", "memory_usage", "disk_usage", "disk_iowait",
        "network_latency", "network_in", "network_out",
        "process_count", "connections", "open_files",
        "swap_usage", "tcp_established", "ssh_connections",
        "loadavg", "uptime",
    ],
    # 中间件指标 → 中间件
    "middleware_metric": [
        "mysql_slow_queries", "redis_memory", "redis_connections",
        "kafka_lag", "mongodb_connections", "es_health",
        "svc_up",
    ],
}

# 层级 → 可观测信号类型
LAYER_SIGNALS = {
    "1": ["trace"],
    "2": ["log"],
    "3-db": ["log", "middleware_metric"],
    "3-mq": ["log", "middleware_metric"],
    "4": ["metric"],
}


def _get_alert_signal(metric_name: str) -> str:
    """根据 metric_name 判断告警属于哪种可观测信号"""
    name_lower = (metric_name or "").lower()
    for signal, patterns in ALERT_SIGNAL_MAP.items():
        for p in patterns:
            if name_lower.startswith(p) or name_lower == p:
                return signal
    return "other"


def _is_alert_for_layer(metric_name: str, layer: str) -> bool:
    """判断告警是否属于该层级（按可观测信号匹配）"""
    signal = _get_alert_signal(metric_name)
    return signal in LAYER_SIGNALS.get(layer, [])

# 实体分层映射 ci_type -> layer key (新值 1/2/3/4)
LAYER_MAP = {
    "api_service": "1",
    "api_gateway": "1",
    "api": "1",
    "deployment": "2",
    "service": "2",
    "pod": "2",
    "container": "2",
    "statefulset": "2",
    "daemonset": "2",
    "business_app": "2",
    "middleware": "3-mq",
    "database": "3-db",
    "redis": "3-db",
    "mysql": "3-db",
    "postgresql": "3-db",
    "kafka": "3-mq",
    "rabbitmq": "3-mq",
    "rocketmq": "3-mq",
    "mongodb": "3-db",
    "elasticsearch": "3-db",
    "server": "4",
    "host": "4",
    "vm": "4",
    "virtual_machine": "4",
    "node": "4",
    "kubernetes_cluster": "4",
    "namespace": "4",
    "network_device": "4",
    "switch": "4",
    "router": "4",
    "firewall": "4",
    "loadbalancer": "4",
    "storage": "4",
}

LAYER_LABELS = {
    "1": "接入层",
    "2": "应用层",
    "3-db": "数据库",
    "3-mq": "中间件",
    "4": "基础设施层",
}

LAYER_ORDER = ["1", "2", "3-db", "3-mq", "4"]


def _extract_domains(asset: Asset) -> list:
    """提取资产所属业务域列表(支持多域,逗号分隔)。一个中间件可同时属于多个业务域。"""
    domains = []
    try:
        attrs = json.loads(asset.ci_attributes or "{}")
        raw = attrs.get("domain") or attrs.get("business_domain") or attrs.get("biz")
        if raw:
            if isinstance(raw, list):
                domains = [str(d).strip() for d in raw if str(d).strip()]
            else:
                domains = [d.strip() for d in str(raw).split(",") if d.strip()]
    except (json.JSONDecodeError, TypeError):
        pass
    if domains:
        return domains
    tags_str = (asset.tags or "").strip()
    if tags_str:
        for tag in tags_str.split(","):
            tag = tag.strip()
            if tag and tag not in ("", "0"):
                domains.append(tag)
    return domains if domains else [DOMAIN_DEFAULT]


def _extract_domain(asset: Asset) -> str:
    """兼容旧调用,返回首个业务域"""
    return _extract_domains(asset)[0]


def get_layer(asset: Asset) -> str:
    try:
        attrs = json.loads(asset.ci_attributes or "{}")
        explicit = attrs.get("layer")
        if explicit and str(explicit) in LAYER_ORDER:
            return str(explicit)
    except (json.JSONDecodeError, TypeError):
        pass
    ct = (asset.ci_type or "").strip().lower()
    layer = LAYER_MAP.get(ct)
    if layer:
        return layer
    tags_lower = (asset.tags or "").lower()
    if "microservice" in tags_lower or "service" in tags_lower:
        return "2"
    return "4"


# ── Asset.name → Span.service_name 模糊匹配 ──

def _normalize_service_name(name: str) -> str:
    cleaned = re.sub(r'^(prod|staging|dev|test)/', '', name)
    cleaned = re.sub(r'-[a-f0-9]{5,}$', '', cleaned)
    cleaned = re.sub(r'-(deploy|svc|service|app|server)$', '', cleaned)
    return cleaned.strip().lower()


def _match_asset_to_services(asset: Asset, db_session) -> list:
    from app.models import Span
    normalized = _normalize_service_name(asset.name)
    if not normalized:
        return []
    spans = (
        db_session.query(Span.service_name)
        .filter(Span.service_name.ilike(f"%{normalized}%"))
        .distinct()
        .all()
    )
    matched = [s[0] for s in spans if s[0]]
    if not matched:
        name_lower = asset.name.lower()
        spans2 = (
            db_session.query(Span.service_name)
            .filter(Span.service_name.ilike(f"%{name_lower}%"))
            .distinct()
            .all()
        )
        matched = [s[0] for s in spans2 if s[0]]
    return matched


# ── 分层健康计算 ──

def _compute_api_health(asset: Asset, db_session) -> str:
    from app.models import Span
    service_names = _match_asset_to_services(asset, db_session)
    if not service_names:
        return _compute_middleware_health(asset, db_session)

    cutoff = datetime.now() - timedelta(minutes=HEALTH_WINDOW_MINUTES)
    spans = (
        db_session.query(Span)
        .filter(
            Span.service_name.in_(service_names),
            Span.started_at >= cutoff,
        )
        .all()
    )
    if not spans:
        return HEALTH_GREEN

    total = len(spans)
    error_count = sum(1 for s in spans if s.status and s.status.upper() == "ERROR")
    error_rate = error_count / total if total > 0 else 0

    durations = sorted([s.duration_ms for s in spans if s.duration_ms is not None and s.duration_ms > 0])
    p99 = durations[int(len(durations) * 0.99)] if len(durations) > 1 else (durations[0] if durations else 0)

    if error_rate > API_ERROR_RATE_THRESHOLD or p99 > API_LATENCY_THRESHOLD_MS:
        return HEALTH_RED
    return HEALTH_GREEN


def _compute_microservice_health(asset: Asset, db_session) -> str:
    """微服务层：基于 Log（日志）信号判断健康"""
    if asset.status == "offline":
        return HEALTH_GRAY
    if asset.last_checked_at is None:
        return HEALTH_GREEN
    cutoff = datetime.now() - timedelta(minutes=HEALTH_WINDOW_MINUTES)
    if asset.last_checked_at < cutoff:
        return HEALTH_GRAY

    # 只查 Log 类告警（k8s_event / pod_anomaly / log_anomaly）
    active_alerts = (
        db_session.query(Alert)
        .filter(
            Alert.asset_id == asset.id,
            Alert.status.in_(["triggered", "acknowledged", "firing"]),
        )
        .all()
    )
    log_alerts = [a for a in active_alerts if _is_alert_for_layer(a.metric_name, "microservice")]
    if log_alerts:
        return HEALTH_RED
    return HEALTH_GREEN


def _compute_middleware_health(asset: Asset, db_session) -> str:
    """中间件层：基于 Log + 中间件指标信号判断健康"""
    if asset.status == "offline":
        return HEALTH_GRAY
    if asset.last_checked_at is None:
        return HEALTH_GREEN
    cutoff = datetime.now() - timedelta(minutes=HEALTH_WINDOW_MINUTES)
    if asset.last_checked_at < cutoff:
        return HEALTH_GRAY

    # 查 Log + 中间件指标告警
    active_alerts = (
        db_session.query(Alert)
        .filter(
            Alert.asset_id == asset.id,
            Alert.status.in_(["triggered", "acknowledged", "firing"]),
        )
        .all()
    )
    mw_alerts = [a for a in active_alerts if _is_alert_for_layer(a.metric_name, "middleware")]
    if mw_alerts:
        return HEALTH_RED
    return HEALTH_GREEN


def _compute_infra_health(asset: Asset, db_session) -> str:
    if asset.status == "offline":
        return HEALTH_GRAY
    if asset.last_checked_at is None:
        return HEALTH_GREEN
    cutoff = datetime.now() - timedelta(minutes=HEALTH_WINDOW_MINUTES)
    if asset.last_checked_at < cutoff:
        return HEALTH_GRAY

    from app.models import MetricRecord
    check_metrics = ["cpu_usage", "memory_usage", "disk_usage"]
    rows = (
        db_session.query(MetricRecord.name, MetricRecord.value)
        .filter(
            MetricRecord.asset_id == asset.id,
            MetricRecord.name.in_(check_metrics),
        )
        .order_by(MetricRecord.timestamp.desc())
        .all()
    )
    latest = {}
    for name, value in rows:
        if name not in latest:
            latest[name] = value

    if latest.get("cpu_usage", 0) > INFRA_CPU_THRESHOLD:
        return HEALTH_RED
    if latest.get("memory_usage", 0) > INFRA_MEMORY_THRESHOLD:
        return HEALTH_RED
    if latest.get("disk_usage", 0) > INFRA_DISK_THRESHOLD:
        return HEALTH_RED

    active_alerts = (
        db_session.query(Alert)
        .filter(
            Alert.asset_id == asset.id,
            Alert.status.in_(["triggered", "acknowledged"]),
        )
        .all()
    )
    if active_alerts:
        return HEALTH_RED
    return HEALTH_GREEN


_LAYER_TO_COMPUTE = {
    "1": "_compute_api_health",
    "2": "_compute_microservice_health",
    "3-db": "_compute_middleware_health",
    "3-mq": "_compute_middleware_health",
    "4": "_compute_infra_health",
}

def compute_health(asset: Asset, active_alerts: list, db_session=None, layer: str = None) -> str:
    if layer is None:
        layer = get_layer(asset)

    func_name = _LAYER_TO_COMPUTE.get(layer, "_compute_infra_health")
    if db_session is not None:
        func = globals().get(func_name)
        if func:
            return func(asset, db_session)
    return _compute_middleware_fallback(asset)


def _compute_middleware_fallback(asset: Asset) -> str:
    if asset.status == "offline":
        return HEALTH_GRAY
    if asset.last_checked_at is None:
        return HEALTH_GREEN
    cutoff = datetime.now() - timedelta(minutes=HEALTH_WINDOW_MINUTES)
    if asset.last_checked_at < cutoff:
        return HEALTH_GRAY
    return HEALTH_GREEN


# ── 业务域总览 ──

def _prefetch_spans_by_service(db_session, all_service_names: list[str], cutoff) -> dict:
    """一次性查出窗口内 span，按 service_name 分组，返回 {name: {durations, error_count}}"""
    from app.models import Span
    if not all_service_names:
        return {}
    rows = (
        db_session.query(Span.service_name, Span.status, Span.duration_ms)
        .filter(Span.service_name.in_(all_service_names), Span.started_at >= cutoff)
        .all()
    )
    grouped = {}
    for sn, status, dur in rows:
        g = grouped.setdefault(sn, {"durations": [], "error_count": 0})
        if dur is not None and dur > 0:
            g["durations"].append(dur)
        if status and status.upper() == "ERROR":
            g["error_count"] += 1
    return grouped


def _match_service_names_in_memory(asset_name: str, all_service_names: list[str]) -> list[str]:
    """内存匹配 asset.name → service_name，替代逐条 ILIKE"""
    normalized = _normalize_service_name(asset_name)
    if not normalized:
        return []
    matched = [s for s in all_service_names if normalized in s.lower()]
    if not matched:
        name_lower = asset_name.lower()
        matched = [s for s in all_service_names if name_lower in s.lower()]
    return matched


def fetch_domains(db_session=None):
    close_db = False
    if db_session is None:
        db_session = get_session_for(get_db_mode())()
        close_db = True
    try:
        from app.models import MetricRecord, Span
        all_service_names = [r[0] for r in db_session.query(Span.service_name).distinct().all() if r[0]]
        assets = db_session.query(Asset).all()
        asset_ids = [a.id for a in assets]
        cutoff = datetime.now() - timedelta(minutes=HEALTH_WINDOW_MINUTES)

        # 一次性预取活跃告警
        alerts_by_asset = {}
        if asset_ids:
            for a in db_session.query(Alert).filter(
                Alert.asset_id.in_(asset_ids),
                Alert.status.in_(["triggered", "acknowledged", "firing"]),
            ).all():
                alerts_by_asset.setdefault(a.asset_id, []).append(a)

        # 一次性预取指标（每个 asset 取最新值）
        check_metrics = ["cpu_usage", "memory_usage", "disk_usage"]
        metrics_by_asset = {}
        if asset_ids:
            rows = db_session.query(MetricRecord.asset_id, MetricRecord.name, MetricRecord.value).filter(
                MetricRecord.asset_id.in_(asset_ids),
                MetricRecord.name.in_(check_metrics),
            ).order_by(MetricRecord.timestamp.desc()).all()
            for aid, name, value in rows:
                m = metrics_by_asset.setdefault(aid, {})
                if name not in m:
                    m[name] = value

        # 预计算所有资产的 layer（避免重复计算）
        asset_layers = {a.id: get_layer(a) for a in assets}

        # 收集 layer=1 的资产，批量匹配 service_name 并预取 span 统计
        api_asset_ids = [a.id for a in assets if asset_layers.get(a.id) == "1"]
        service_names_by_asset = {}
        spans_by_service = {}
        if api_asset_ids:
            all_svc = all_service_names
            for a in assets:
                if a.id in api_asset_ids:
                    matched = _match_service_names_in_memory(a.name, all_svc)
                    if matched:
                        service_names_by_asset[a.id] = matched
            all_matched = list(set(s for svcs in service_names_by_asset.values() for svcs in svcs))
            if all_matched:
                spans_by_service = _prefetch_spans_by_service(db_session, all_matched, cutoff)

        domain_map = {}
        for asset in assets:
            domains = _extract_domains(asset)
            layer = asset_layers.get(asset.id, "4")
            status = _compute_health_bulk(asset, layer, alerts_by_asset, metrics_by_asset,
                                          service_names_by_asset, spans_by_service)
            entity = {
                "id": asset.id,
                "name": asset.name,
                "ci_type": asset.ci_type or "",
                "health_status": status,
                "alert_count": 0,
            }
            for domain in domains:
                if domain not in domain_map:
                    domain_map[domain] = {"total": 0, HEALTH_GREEN: 0, HEALTH_GRAY: 0, HEALTH_RED: 0, "entities": []}
                domain_map[domain]["entities"].append(entity)
                domain_map[domain]["total"] += 1
                domain_map[domain][status] += 1

        result = []
        for name, d in sorted(domain_map.items(), key=lambda x: -x[1]["total"]):
            result.append({
                "name": name,
                "total": d["total"],
                "healthy": d[HEALTH_GREEN],
                "fault": d[HEALTH_RED],
                "offline": d[HEALTH_GRAY],
            })
        return result
    finally:
        if close_db:
            db_session.close()


def _compute_health_bulk(asset, layer, alerts_by_asset, metrics_by_asset,
                         service_names_by_asset, spans_by_service) -> str:
    """批量预取版健康计算，不执行任何 SQL"""
    if layer == "1":
        return _compute_api_health_bulk(asset, service_names_by_asset, spans_by_service)
    if layer == "2":
        return _compute_generic_health_bulk(asset, alerts_by_asset, "microservice")
    if layer in ("3-db", "3-mq"):
        return _compute_generic_health_bulk(asset, alerts_by_asset, "middleware")
    if layer == "4":
        return _compute_infra_health_bulk(asset, alerts_by_asset, metrics_by_asset)
    return _compute_middleware_fallback(asset)


def _compute_api_health_bulk(asset, service_names_by_asset, spans_by_service) -> str:
    matched = service_names_by_asset.get(asset.id, [])
    if not matched:
        return HEALTH_GREEN
    total_error = 0
    total_span = 0
    all_durations = []
    for sn in matched:
        g = spans_by_service.get(sn)
        if not g:
            continue
        total_span += g["total"]
        total_error += g["error_count"]
        if g["durations"]:
            all_durations.extend(g["durations"])
    if total_span == 0:
        return HEALTH_GREEN
    error_rate = total_error / total_span
    sorted_durs = sorted(all_durations)
    p99 = sorted_durs[int(len(sorted_durs) * 0.99)] if len(sorted_durs) > 1 else (sorted_durs[0] if sorted_durs else 0)
    if error_rate > API_ERROR_RATE_THRESHOLD or p99 > API_LATENCY_THRESHOLD_MS:
        return HEALTH_RED
    return HEALTH_GREEN


def _compute_generic_health_bulk(asset, alerts_by_asset, layer_name) -> str:
    if asset.status == "offline":
        return HEALTH_GRAY
    if asset.last_checked_at is None:
        return HEALTH_GREEN
    cutoff = datetime.now() - timedelta(minutes=HEALTH_WINDOW_MINUTES)
    if asset.last_checked_at < cutoff:
        return HEALTH_GRAY
    active = alerts_by_asset.get(asset.id, [])
    for a in active:
        if _is_alert_for_layer(a.metric_name, layer_name):
            return HEALTH_RED
    return HEALTH_GREEN


def _compute_infra_health_bulk(asset, alerts_by_asset, metrics_by_asset) -> str:
    if asset.status == "offline":
        return HEALTH_GRAY
    if asset.last_checked_at is None:
        return HEALTH_GREEN
    cutoff = datetime.now() - timedelta(minutes=HEALTH_WINDOW_MINUTES)
    if asset.last_checked_at < cutoff:
        return HEALTH_GRAY
    m = metrics_by_asset.get(asset.id, {})
    if m.get("cpu_usage", 0) > INFRA_CPU_THRESHOLD:
        return HEALTH_RED
    if m.get("memory_usage", 0) > INFRA_MEMORY_THRESHOLD:
        return HEALTH_RED
    if m.get("disk_usage", 0) > INFRA_DISK_THRESHOLD:
        return HEALTH_RED
    active = alerts_by_asset.get(asset.id, [])
    if active:
        return HEALTH_RED
    return HEALTH_GREEN


# ── 分层概览 ──

def fetch_overview(db_session=None, domain: str = None):
    close_db = False
    if db_session is None:
        db_session = get_session_for(get_db_mode())()
        close_db = True
    try:
        assets = db_session.query(Asset).all()
        if domain:
            assets = [a for a in assets if domain in _extract_domains(a)]

        layers = {k: [] for k in LAYER_ORDER}
        stats = {"total": 0, HEALTH_GREEN: 0, HEALTH_GRAY: 0, HEALTH_RED: 0}

        for asset in assets:
            layer_key = get_layer(asset)
            if layer_key not in layers:
                layer_key = "infra"

            status = compute_health(asset, [], db_session=db_session, layer=layer_key)

            # 按层级过滤告警：只统计该层级对应的可观测信号告警
            all_alerts = (
                db_session.query(Alert)
                .filter(
                    Alert.asset_id == asset.id,
                    Alert.status.in_(["triggered", "acknowledged", "firing"]),
                )
                .all()
            )
            layer_alerts = [a for a in all_alerts if _is_alert_for_layer(a.metric_name, layer_key)]
            alert_count = len(layer_alerts)

            layers[layer_key].append({
                "id": asset.id,
                "name": asset.name,
                "ci_type": asset.ci_type or "",
                "health_status": status,
                "alert_count": alert_count,
                "ip": asset.ip or "",
                "status": asset.status or "",
                "last_checked_at": asset.last_checked_at.isoformat() if asset.last_checked_at else None,
                "latency_ms": asset.latency_ms,
            })
            stats["total"] += 1
            stats[status] += 1

        # 构建 entity_id -> layer_key 映射
        entity_layer_map = {}
        for k, elist in layers.items():
            for e in elist:
                entity_layer_map[e["id"]] = k

        # 为每层计算层间聚合依赖
        rels_all = []
        if domain:
            rels_all = db_session.query(AssetRelation).all()

        domain_asset_ids = {a.id for a in assets}
        # 层间聚合: 每层到其他层的依赖计数
        layer_deps = {k: {"up": {}, "down": {}} for k in LAYER_ORDER}
        for r in rels_all:
            if r.parent_id not in domain_asset_ids or r.child_id not in domain_asset_ids:
                continue
            p_layer = entity_layer_map.get(r.parent_id)
            c_layer = entity_layer_map.get(r.child_id)
            if p_layer and c_layer and p_layer != c_layer:
                # parent -> child: parent 的 down 方向, child 的 up 方向
                layer_deps[p_layer]["down"][c_layer] = layer_deps[p_layer]["down"].get(c_layer, 0) + 1
                layer_deps[c_layer]["up"][p_layer] = layer_deps[c_layer]["up"].get(p_layer, 0) + 1

        # 每个实体加上 up/down 简要信息
        for k, elist in layers.items():
            for e in elist:
                up_ids, down_ids = [], []
                for r in rels_all:
                    if r.parent_id not in domain_asset_ids or r.child_id not in domain_asset_ids:
                        continue
                    if r.child_id == e["id"]:
                        up_ids.append(r.parent_id)
                    if r.parent_id == e["id"]:
                        down_ids.append(r.child_id)
                # 找这些 id 的名字
                up_names = []
                for uid in up_ids:
                    a = next((a for a in assets if a.id == uid), None)
                    if a:
                        up_names.append(a.name)
                down_names = []
                for did in down_ids:
                    a = next((a for a in assets if a.id == did), None)
                    if a:
                        down_names.append(a.name)
                e["dep_up"] = up_names[:4]
                e["dep_down"] = down_names[:4]
                e["dep_up_count"] = len(up_ids)
                e["dep_down_count"] = len(down_ids)

        result_layers = []
        for k in LAYER_ORDER:
            entities = layers[k]
            if not entities:
                continue
            deps = layer_deps[k]
            result_layers.append({
                "name": LAYER_LABELS.get(k, k),
                "key": k,
                "count": len(entities),
                "healthy": sum(1 for e in entities if e["health_status"] == HEALTH_GREEN),
                "fault": sum(1 for e in entities if e["health_status"] == HEALTH_RED),
                "offline": sum(1 for e in entities if e["health_status"] == HEALTH_GRAY),
                "entities": entities,
                "dep_up": {LAYER_LABELS.get(lk, lk): cnt for lk, cnt in deps["up"].items()},
                "dep_down": {LAYER_LABELS.get(lk, lk): cnt for lk, cnt in deps["down"].items()},
            })

        relations = []
        if domain:
            for r in rels_all:
                if r.parent_id in domain_asset_ids and r.child_id in domain_asset_ids:
                    relations.append({
                        "from": r.parent_id,
                        "to": r.child_id,
                        "type": r.relation_type or "depends_on",
                    })

        return {"stats": stats, "layers": result_layers, "relations": relations}
    finally:
        if close_db:
            db_session.close()


# ── 实体详情（含分层专属信息）──

def fetch_entity_detail(entity_id: int, db_session=None):
    close_db = False
    if db_session is None:
        db_session = get_session_for(get_db_mode())()
        close_db = True
    try:
        asset = db_session.query(Asset).filter(Asset.id == entity_id).first()
        if not asset:
            return None

        layer = get_layer(asset)
        health = compute_health(asset, [], db_session=db_session, layer=layer)

        # 查活跃告警，并按层级可观测信号过滤
        all_active_alerts = (
            db_session.query(Alert)
            .filter(
                Alert.asset_id == entity_id,
                Alert.status.in_(["triggered", "acknowledged", "firing"]),
            )
            .order_by(Alert.created_at.desc())
            .all()
        )
        active_alerts = [a for a in all_active_alerts if _is_alert_for_layer(a.metric_name, layer)]

        from app.models import MetricRecord
        metrics = (
            db_session.query(MetricRecord)
            .filter(MetricRecord.asset_id == entity_id)
            .order_by(MetricRecord.timestamp.desc())
            .limit(20)
            .all()
        )

        parent = None
        if asset.parent_id:
            p = db_session.query(Asset).filter(Asset.id == asset.parent_id).first()
            if p:
                parent_rel = (
                    db_session.query(AssetRelation)
                    .filter(
                        AssetRelation.child_id == entity_id,
                    )
                    .first()
                )
                parent = {
                    "id": p.id,
                    "name": p.name,
                    "ci_type": p.ci_type,
                    "relation_type": parent_rel.relation_type if parent_rel else "parent_of",
                }

        children = []
        child_assets = (
            db_session.query(Asset)
            .filter(Asset.parent_id == entity_id)
            .all()
        )
        if child_assets:
            child_ids = [c.id for c in child_assets]
            child_alerts = (
                db_session.query(Alert)
                .filter(
                    Alert.asset_id.in_(child_ids),
                    Alert.status.in_(["triggered", "acknowledged", "firing"]),
                )
                .all()
            )
            child_alert_map = {}
            for ca in child_alerts:
                child_alert_map.setdefault(ca.asset_id, []).append(ca)
        else:
            child_alert_map = {}

        for c in child_assets:
            c_layer = get_layer(c)
            children.append({
                "id": c.id,
                "name": c.name,
                "ci_type": c.ci_type,
                "health_status": compute_health(c, [], db_session=db_session, layer=c_layer),
            })
        if not children:
            child_rels = (
                db_session.query(AssetRelation)
                .filter(AssetRelation.parent_id == entity_id)
                .all()
            )
            if child_rels:
                child_ids = [r.child_id for r in child_rels]
                rel_map = {r.child_id: r.relation_type for r in child_rels}
                rel_assets = db_session.query(Asset).filter(Asset.id.in_(child_ids)).all()
                for c in rel_assets:
                    c_layer = get_layer(c)
                    children.append({
                        "id": c.id,
                        "name": c.name,
                        "ci_type": c.ci_type,
                        "health_status": compute_health(c, [], db_session=db_session, layer=c_layer),
                        "relation_type": rel_map.get(c.id, "depends_on"),
                    })

        result = {
            "id": asset.id,
            "name": asset.name,
            "ci_type": asset.ci_type or "",
            "layer": layer,
            "health_status": health,
            "ip": asset.ip or "",
            "status": asset.status or "",
            "tags": (asset.tags or "").split(",") if asset.tags else [],
            "last_checked_at": asset.last_checked_at.isoformat() if asset.last_checked_at else None,
            "latency_ms": asset.latency_ms,
            "alerts": [
                {
                    "id": a.id,
                    "severity": a.severity,
                    "status": a.status,
                    "message": a.message,
                    "metric_name": a.metric_name,
                    "actual_value": a.actual_value,
                    "threshold": a.threshold,
                    "created_at": a.created_at.isoformat() if a.created_at else None,
                }
                for a in active_alerts
            ],
            "metrics": [
                {
                    "name": m.name,
                    "value": m.value,
                    "unit": m.unit,
                    "timestamp": m.timestamp.isoformat() if m.timestamp else None,
                }
                for m in metrics
            ],
            "parent": parent,
            "children": children,
        }

        if layer in ("1", "api"):
            result["trace_info"] = _build_trace_info(asset, db_session)

        if layer in ("4", "infra"):
            result["infra_metrics"] = _build_infra_metrics(asset, db_session)

        return result
    finally:
        if close_db:
            db_session.close()


def _build_trace_info(asset: Asset, db_session) -> dict:
    from app.models import Span
    service_names = _match_asset_to_services(asset, db_session)
    if not service_names:
        return {"matched_services": [], "total_spans": 0, "error_rate": 0, "p99_ms": 0}

    cutoff = datetime.now() - timedelta(minutes=HEALTH_WINDOW_MINUTES)
    spans = (
        db_session.query(Span)
        .filter(
            Span.service_name.in_(service_names),
            Span.started_at >= cutoff,
        )
        .all()
    )
    total = len(spans)
    if total == 0:
        return {"matched_services": service_names, "total_spans": 0, "error_rate": 0, "p99_ms": 0}

    error_count = sum(1 for s in spans if s.status and s.status.upper() == "ERROR")
    error_rate = round(error_count / total * 100, 2) if total > 0 else 0

    durations = sorted([s.duration_ms for s in spans if s.duration_ms is not None and s.duration_ms > 0])
    p99 = round(durations[int(len(durations) * 0.99)], 1) if len(durations) > 1 else (round(durations[0], 1) if durations else 0)
    avg_dur = round(sum(durations) / len(durations), 1) if durations else 0

    return {
        "matched_services": service_names,
        "total_spans": total,
        "error_rate": error_rate,
        "p99_ms": p99,
        "avg_latency_ms": avg_dur,
        "thresholds": {
            "error_rate": API_ERROR_RATE_THRESHOLD * 100,
            "latency_ms": API_LATENCY_THRESHOLD_MS,
        },
    }


def _build_infra_metrics(asset: Asset, db_session) -> dict:
    from app.models import MetricRecord
    check_metrics = ["cpu_usage", "memory_usage", "disk_usage", "network_latency"]
    rows = (
        db_session.query(MetricRecord.name, MetricRecord.value, MetricRecord.unit, MetricRecord.timestamp)
        .filter(
            MetricRecord.asset_id == asset.id,
            MetricRecord.name.in_(check_metrics),
        )
        .order_by(MetricRecord.timestamp.desc())
        .all()
    )
    latest = {}
    for name, value, unit, ts in rows:
        if name not in latest:
            latest[name] = {"value": value, "unit": unit, "timestamp": ts.isoformat() if ts else None}

    thresholds = {
        "cpu_usage": {"threshold": INFRA_CPU_THRESHOLD, "unit": "%"},
        "memory_usage": {"threshold": INFRA_MEMORY_THRESHOLD, "unit": "%"},
        "disk_usage": {"threshold": INFRA_DISK_THRESHOLD, "unit": "%"},
    }
    return {"latest": latest, "thresholds": thresholds}
