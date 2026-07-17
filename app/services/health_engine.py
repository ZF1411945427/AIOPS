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
    ],
}

# 层级 → 可观测信号类型
LAYER_SIGNALS = {
    "api": ["trace"],
    "microservice": ["log"],
    "middleware": ["log", "middleware_metric"],
    "infra": ["metric"],
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

# 实体分层映射 ci_type -> layer key
LAYER_MAP = {
    "api_service": "api",
    "api_gateway": "api",
    "api": "api",
    "deployment": "microservice",
    "service": "microservice",
    "pod": "microservice",
    "container": "microservice",
    "statefulset": "microservice",
    "daemonset": "microservice",
    "middleware": "middleware",
    "database": "middleware",
    "redis": "middleware",
    "mysql": "middleware",
    "postgresql": "middleware",
    "kafka": "middleware",
    "rabbitmq": "middleware",
    "rocketmq": "middleware",
    "mongodb": "middleware",
    "elasticsearch": "middleware",
    "server": "infra",
    "host": "infra",
    "vm": "infra",
    "network_device": "infra",
    "switch": "infra",
    "router": "infra",
    "firewall": "infra",
    "loadbalancer": "infra",
    "storage": "infra",
}

LAYER_LABELS = {
    "api": "功能接口",
    "microservice": "微服务",
    "middleware": "中间件",
    "infra": "基础设施",
}

LAYER_ORDER = ["api", "microservice", "middleware", "infra"]


def _extract_domain(asset: Asset) -> str:
    try:
        attrs = json.loads(asset.ci_attributes or "{}")
        domain = attrs.get("domain") or attrs.get("business_domain") or attrs.get("biz")
        if domain:
            return str(domain).strip()
    except (json.JSONDecodeError, TypeError):
        pass
    tags_str = (asset.tags or "").strip()
    if tags_str:
        for tag in tags_str.split(","):
            tag = tag.strip()
            if tag and tag not in ("", "0"):
                return tag
    return DOMAIN_DEFAULT


def get_layer(asset: Asset) -> str:
    ct = (asset.ci_type or "").strip().lower()
    layer = LAYER_MAP.get(ct)
    if layer:
        return layer
    tags_lower = (asset.tags or "").lower()
    if "microservice" in tags_lower or "service" in tags_lower:
        return "microservice"
    return "infra"


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
        return HEALTH_GRAY
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
        return HEALTH_GRAY
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
        return HEALTH_GRAY
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


def compute_health(asset: Asset, active_alerts: list, db_session=None, layer: str = None) -> str:
    if layer is None:
        layer = get_layer(asset)

    if layer == "api":
        if db_session is not None:
            return _compute_api_health(asset, db_session)
        return _compute_middleware_fallback(asset)

    elif layer == "microservice":
        if db_session is not None:
            return _compute_microservice_health(asset, db_session)
        return _compute_middleware_fallback(asset)

    elif layer == "middleware":
        if db_session is not None:
            return _compute_middleware_health(asset, db_session)
        return _compute_middleware_fallback(asset)

    else:
        if db_session is not None:
            return _compute_infra_health(asset, db_session)
        return _compute_middleware_fallback(asset)


def _compute_middleware_fallback(asset: Asset) -> str:
    if asset.status == "offline":
        return HEALTH_GRAY
    if asset.last_checked_at is None:
        return HEALTH_GRAY
    cutoff = datetime.now() - timedelta(minutes=HEALTH_WINDOW_MINUTES)
    if asset.last_checked_at < cutoff:
        return HEALTH_GRAY
    return HEALTH_GREEN


# ── 业务域总览 ──

def fetch_domains(db_session=None):
    close_db = False
    if db_session is None:
        db_session = get_session_for(get_db_mode())()
        close_db = True
    try:
        assets = db_session.query(Asset).all()

        domain_map = {}
        for asset in assets:
            domain = _extract_domain(asset)
            if domain not in domain_map:
                domain_map[domain] = {"total": 0, HEALTH_GREEN: 0, HEALTH_GRAY: 0, HEALTH_RED: 0, "entities": []}
            status = compute_health(asset, [], db_session=db_session)
            domain_map[domain]["entities"].append({
                "id": asset.id,
                "name": asset.name,
                "ci_type": asset.ci_type or "",
                "health_status": status,
                "alert_count": 0,
            })
            domain_map[domain]["total"] += 1
            domain_map[domain][status] += 1

        result = []
        for name, d in sorted(domain_map.items(), key=lambda x: -x[1]["total"]):
            alert_count = sum(
                1 for e in d["entities"] if e["health_status"] == HEALTH_RED
            )
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


# ── 分层概览 ──

def fetch_overview(db_session=None, domain: str = None):
    close_db = False
    if db_session is None:
        db_session = get_session_for(get_db_mode())()
        close_db = True
    try:
        assets = db_session.query(Asset).all()
        if domain:
            assets = [a for a in assets if _extract_domain(a) == domain]

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

        result_layers = []
        for k in LAYER_ORDER:
            entities = layers[k]
            if not entities:
                continue
            result_layers.append({
                "name": LAYER_LABELS.get(k, k),
                "key": k,
                "count": len(entities),
                "healthy": sum(1 for e in entities if e["health_status"] == HEALTH_GREEN),
                "fault": sum(1 for e in entities if e["health_status"] == HEALTH_RED),
                "offline": sum(1 for e in entities if e["health_status"] == HEALTH_GRAY),
                "entities": entities,
            })

        return {"stats": stats, "layers": result_layers}
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
                parent = {"id": p.id, "name": p.name, "ci_type": p.ci_type}

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
                rel_assets = db_session.query(Asset).filter(Asset.id.in_(child_ids)).all()
                for c in rel_assets:
                    c_layer = get_layer(c)
                    children.append({
                        "id": c.id,
                        "name": c.name,
                        "ci_type": c.ci_type,
                        "health_status": compute_health(c, [], db_session=db_session, layer=c_layer),
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

        if layer == "api":
            result["trace_info"] = _build_trace_info(asset, db_session)

        if layer == "infra":
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
