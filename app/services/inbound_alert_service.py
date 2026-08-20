"""第二十三章：外部告警入站集成服务。

填补"无外部入站告警集成"缺口，对接：
- Prometheus Alertmanager webhook（POST）
- Prometheus remote_write（POST, protobuf/snappy 或 JSON 兜底）
- 通用 JSON webhook（POST）
- 处置状态回写（acknowledged/resolved 同步到源系统 webhook）

核心：把外部事件标准化为内部 Alert 落库 + 可选自动建 AlertRule，
处置后通过 status_webhook_url 回写源系统，形成双向闭环。
"""
import json
import secrets
from datetime import datetime
from typing import Any, Dict, List, Optional

from sqlalchemy.orm import Session

from app.logger import logger
from app.models import Alert, AlertRule, InboundSource


# ── 入站源 CRUD ─────────────────────────────────────────────
def _source_to_dict(s: InboundSource) -> Dict[str, Any]:
    return {
        "id": s.id,
        "name": s.name,
        "source_type": s.source_type,
        "endpoint_token": s.endpoint_token,
        "has_token": bool(s.endpoint_token),
        "labels": s.get_labels(),
        "metrics_to_rules": s.get_metrics_to_rules(),
        "auto_create_rule": bool(s.auto_create_rule),
        "status_webhook_url": s.status_webhook_url or "",
        "enabled": bool(s.enabled),
        "created_at": s.created_at.strftime("%Y-%m-%d %H:%M:%S") if s.created_at else None,
    }


def list_sources(db: Session) -> List[Dict[str, Any]]:
    rows = db.query(InboundSource).order_by(InboundSource.id.desc()).all()
    return [_source_to_dict(s) for s in rows]


def get_source(db: Session, source_id: int) -> Optional[InboundSource]:
    return db.query(InboundSource).filter(InboundSource.id == source_id).first()


def create_source(db: Session, data: Dict[str, Any]) -> InboundSource:
    token = data.get("endpoint_token") or secrets.token_urlsafe(24)
    s = InboundSource(
        name=data.get("name", ""),
        source_type=data.get("source_type", "alertmanager"),
        endpoint_token=token,
        labels_json=json.dumps(data.get("labels") or {}, ensure_ascii=False),
        metrics_to_rules=json.dumps(data.get("metrics_to_rules") or {}, ensure_ascii=False),
        auto_create_rule=bool(data.get("auto_create_rule", False)),
        status_webhook_url=data.get("status_webhook_url", ""),
        enabled=bool(data.get("enabled", True)),
    )
    db.add(s)
    db.commit()
    db.refresh(s)
    return s


def update_source(db: Session, source_id: int, data: Dict[str, Any]) -> Optional[InboundSource]:
    s = get_source(db, source_id)
    if not s:
        return None
    for field in ["name", "source_type", "auto_create_rule", "status_webhook_url", "enabled"]:
        if field in data:
            setattr(s, field, data[field])
    if "labels" in data:
        s.labels_json = json.dumps(data["labels"] or {}, ensure_ascii=False)
    if "metrics_to_rules" in data:
        s.metrics_to_rules = json.dumps(data["metrics_to_rules"] or {}, ensure_ascii=False)
    if "endpoint_token" in data and data["endpoint_token"]:
        s.endpoint_token = data["endpoint_token"]
    db.commit()
    db.refresh(s)
    return s


def delete_source(db: Session, source_id: int) -> bool:
    s = get_source(db, source_id)
    if not s:
        return False
    db.delete(s)
    db.commit()
    return True


def verify_token(source: InboundSource, token: Optional[str]) -> bool:
    """校验入站 token：Bearer 或 query 形式。"""
    if not token:
        return False
    return secrets.compare_digest((source.endpoint_token or ""), token)


# ── 告警落库辅助 ───────────────────────────────────────────
_SEVERITY_MAP = {
    "critical": "critical", "warning": "warning", "info": "info",
    "high": "critical", "medium": "warning", "low": "info", "error": "critical",
    "warn": "warning", "page": "critical", "ticket": "warning",
}
_DEFAULT_SEVERITY = "warning"


def _norm_severity(sev: Optional[str]) -> str:
    if not sev:
        return _DEFAULT_SEVERITY
    return _SEVERITY_MAP.get(str(sev).strip().lower(), _DEFAULT_SEVERITY)


def _find_or_create_rule(
    db: Session,
    source: InboundSource,
    metric_name: str,
    severity: str,
    labels: Dict[str, Any],
) -> Optional[int]:
    """按 metric_name（或 labels.rule_name）匹配已有规则，无则按需自动创建。"""
    # 先按 metric_name 匹配
    rule = db.query(AlertRule).filter(AlertRule.metric_name == metric_name).order_by(AlertRule.id.desc()).first()
    if rule:
        return rule.id
    # 按 labels.rule_name 匹配
    rule_name = labels.get("rule_name") or labels.get("alertname")
    if rule_name:
        rule = db.query(AlertRule).filter(AlertRule.name == str(rule_name)).order_by(AlertRule.id.desc()).first()
        if rule:
            return rule.id
    if not source.auto_create_rule:
        return None
    # 自动创建规则（入站来源专用，enabled=False 避免重复触发内部评估）
    rr = AlertRule(
        name=str(rule_name or f"inbound-{metric_name or 'node'}-{source.name}"),
        kind="metric_raw",
        metric_name=metric_name or "inbound_node",
        condition=">",
        threshold=0.0,
        config_json=json.dumps({"source": source.name, "labels": labels}, ensure_ascii=False),
        severity=severity,
        enabled=False,
    )
    db.add(rr)
    db.flush()
    return rr.id


def _ingest_alert(
    db: Session,
    source: InboundSource,
    *,
    title: str,
    severity: str,
    metric_name: Optional[str],
    message: str,
    labels: Optional[Dict[str, Any]] = None,
    asset_id: Optional[int] = None,
    actual_value: float = 0.0,
    threshold: float = 0.0,
    fired: bool = True,
) -> Optional[Alert]:
    """统一落库一条入站告警（或按 fingerprint 去重）。返回 Alert。"""
    labels = labels or {}
    _labels = {**source.get_labels(), **labels}
    sev = _norm_severity(severity)
    metric = metric_name or str(_labels.get("metric") or _labels.get("alertname") or "inbound_node")
    rule_id = _find_or_create_rule(db, source, metric, sev, _labels)
    _msg = title or str(_labels.get("summary") or message or f"{source.name} 入站告警")

    if not fired:
        # resolved: 关闭该 source+metric 的活跃告警
        active = db.query(Alert).filter(
            Alert.metric_name == metric,
            Alert.source == source.name,
            Alert.status.in_(["triggered", "acknowledged"]),
        ).order_by(Alert.id.desc()).first()
        if active:
            active.status = "resolved"
            active.resolved_at = datetime.now()
            db.commit()
            return active
        return None

    # 去重：同 source+metric+关键标签的活跃告警不重复建（仅命中后合并）
    active = db.query(Alert).filter(
        Alert.metric_name == metric,
        Alert.source == source.name,
        Alert.status.in_(["triggered", "acknowledged"]),
    ).order_by(Alert.id.desc()).first()
    if active:
        if _labels.get("fingerprint"):
            active.message = _msg
            db.commit()
        return active

    alert = Alert(
        rule_id=rule_id,
        asset_id=asset_id,
        metric_name=metric,
        actual_value=float(actual_value or 0.0),
        threshold=float(threshold or 0.0),
        severity=sev,
        status="triggered",
        source=source.name,
        message=_msg,
    )
    db.add(alert)
    db.commit()
    db.refresh(alert)
    return alert


def _notify_alert(db: Session, alert: Alert) -> None:
    """入站告警后置：通知 + webhook + WS 推送。"""
    try:
        from app.services import notification_service
        notification_service.notify_new_alerts(db, [alert])
    except Exception as e:
        logger.warning(f"[inbound] 通知告警#{alert.id} 异常: {e}")
    try:
        from app.routers.alert_webhooks import call_alert_webhooks
        call_alert_webhooks(db, alert)
    except Exception as e:
        logger.warning(f"[inbound] webhook 告警#{alert.id} 异常: {e}")

    try:  # noqa: E303
        import asyncio
        from app.services.alert_service import _serialize_alert, _ws_publish_async
        _ws_publish_async([_serialize_alert(alert)])
    except Exception as e:
        logger.warning(f"[inbound] WS 推送告警#{alert.id} 异常: {e}")


# ── Alertmanager webhook ───────────────────────────────────
def handle_alertmanager(db: Session, source: InboundSource, payload: Dict[str, Any]) -> Dict[str, Any]:
    """解析 Alertmanager webhook payload：{alerts:[{labels,annotations,status,...}]}"""
    alerts = payload.get("alerts") or []
    created = 0
    resolved = 0
    for item in alerts:
        if not isinstance(item, dict):
            continue
        labels = item.get("labels") or {}
        annotations = item.get("annotations") or {}
        status = (item.get("status") or item.get("state") or "").lower()
        fired = status not in ("resolved", "inactive", "suppressed")
        title = (
            str(annotations.get("summary") or annotations.get("description")
                or labels.get("alertname") or "alert")
        )
        message_parts = []
        if annotations.get("description"):
            message_parts.append(str(annotations["description"]))
        if labels:
            message_parts.append("labels=" + json.dumps(labels, ensure_ascii=False))
        metric = str(labels.get("metric") or labels.get("alertname") or "")
        alert = _ingest_alert(
            db, source,
            title=title,
            severity=str(labels.get("severity") or annotations.get("severity")),
            metric_name=metric,
            message="; ".join(message_parts) if message_parts else title,
            labels=labels,
            actual_value=float(labels.get("value") or 0.0),
            fired=fired,
        )
        if alert:
            if fired:
                created += 1
                _notify_alert(db, alert)
            else:
                resolved += 1
    return {"received": len(alerts), "created": created, "resolved": resolved}


# ── Prometheus remote_write ────────────────────────────────
def handle_remote_write(db: Session, source: InboundSource, raw_body: bytes) -> Dict[str, Any]:
    """解码 Prometheus remote_write。优先 protobuf/snappy；退化为 JSON。

    metrics_to_rules 把指标名映射到内部规则评估；有 metric 数据时写入 MetricRecord。
    """
    samples = _decode_remote_write(raw_body)
    total = 0
    written = 0
    for series in samples:
        total += 1
        metric_name = series.get("name", "")
        labels = series.get("labels", {})
        value = float(series.get("value") or 0.0)
        if not metric_name:
            continue
        # 收集到 MetricRecord（供内部规则评估）
        try:
            from app.models import MetricRecord
            mr = MetricRecord(
                name=metric_name,
                asset_id=None,
                value=value,
                timestamp=datetime.now(),
            )
            db.add(mr)
            written += 1
        except Exception as e:
            logger.warning(f"[inbound] remote_write 落库指标异常: {e}")
        # 若该指标被映射为规则监控指标 → 直接进告警
        mapping = source.get_metrics_to_rules()
        if metric_name in mapping and value is not None:
            alert = _ingest_alert(
                db, source,
                title=f"{metric_name} = {value}",
                severity=str(labels.get("severity") or "warning"),
                metric_name=str(mapping[metric_name]),
                message=f"remote_write {metric_name}={value}",
                labels={**labels, "metric": metric_name},
                actual_value=value,
            )
            if alert:
                _notify_alert(db, alert)
    db.commit()
    return {"series": total, "metric_records_written": written}


def _decode_remote_write(raw_body: bytes) -> List[Dict[str, Any]]:
    """尝试 protobuf 解码 remote_write；失败则尝试 JSON。"""
    # JSON 兜底优先：很多测试/工具用 JSON 提交流
    try:
        data = json.loads(raw_body)
        if isinstance(data, dict) and ("timeseries" in data or "samples" in data):
            return _json_remote_write_to_series(data)
    except Exception:
        pass
    # protobuf/snappy
    try:
        import snappy
        import google.protobuf  # noqa: F401
        from prometheus_pb2 import WriteRequest
        decompressed = snappy.decompress(raw_body)
        req = WriteRequest()
        req.ParseFromString(decompressed)
        series = []
        for ts in req.timeseries:
            labels = {lp.name: lp.value for lp in ts.labels}
            name = labels.pop("__name__", "")
            for s in ts.samples:
                series.append({"name": name, "labels": labels, "value": s.value})
        return series
    except Exception as e:
        logger.warning(f"[inbound] remote_write 解码失败（需 snappy+protobuf 且 JSON 兜底未命中）: {e}")
        return []


def _json_remote_write_to_series(data: Dict[str, Any]) -> List[Dict[str, Any]]:
    series = []
    items = data.get("timeseries") or data.get("samples") or []
    for ts in items:
        if not isinstance(ts, dict):
            continue
        labels = dict(ts.get("labels") or {})
        name = labels.pop("__name__", "") or ts.get("name", "")
        if "value" in ts:
            series.append({"name": name, "labels": labels, "value": ts["value"]})
        else:
            samples = ts.get("samples") or []
            for s in samples:
                series.append({"name": name, "labels": labels, "value": s.get("value")})
    return series


# ── 通用 webhook ───────────────────────────────────────────
def handle_webhook(db: Session, source: InboundSource, payload: Dict[str, Any]) -> Dict[str, Any]:
    """通用 JSON webhook: {title,severity,status,metric_name?,message?,labels?}"""
    status = str(payload.get("status") or "firing").lower()
    fired = status not in ("resolved", "closed", "inactive")
    alert = _ingest_alert(
        db, source,
        title=str(payload.get("title") or payload.get("summary") or "webhook alert"),
        severity=str(payload.get("severity") or "warning"),
        metric_name=payload.get("metric_name") or payload.get("metric"),
        message=str(payload.get("message") or ""),
        labels=payload.get("labels") or {},
        actual_value=float(payload.get("actual_value") or 0.0),
        threshold=float(payload.get("threshold") or 0.0),
        fired=fired,
    )
    if alert and fired:
        _notify_alert(db, alert)
    return {"handled": True, "alert_id": alert.id if alert else None, "fired": fired}


# ── 状态回写 ───────────────────────────────────────────────
def callback_status(db: Session, source: InboundSource, payload: Dict[str, Any]) -> Dict[str, Any]:
    """接收本项目侧状态变更请求（告警 acknowledge/resolve），回写源系统 webhook。"""
    alert_id = payload.get("alert_id")
    status = str(payload.get("status") or "").lower()
    if alert_id:
        from app.models import Alert
        alert = db.query(Alert).filter(Alert.id == int(alert_id)).first()
        if alert:
            if status in ("acknowledge", "acknowledged"):
                alert.status = "acknowledged"
                alert.acknowledged_at = datetime.now()
                db.commit()
            elif status in ("resolve", "resolved"):
                alert.status = "resolved"
                alert.resolved_at = datetime.now()
                db.commit()
    # 回写源系统
    if source.status_webhook_url:
        _post_webhook(source.status_webhook_url, {
            "event": "alert_status",
            "source": source.name,
            "alert_id": alert_id,
            "status": status,
            "time": datetime.now().isoformat(timespec="seconds"),
        })
    return {"ok": True, "source": source.name, "status": status}


def _post_webhook(url: str, payload: Dict[str, Any]) -> None:
    import urllib.request
    from app.security import validate_url_scheme
    ok, _ = validate_url_scheme(url or "")
    if not ok:
        logger.warning(f"[inbound] 回写 URL 校验失败: {url}")
        return
    try:
        data = json.dumps(payload, ensure_ascii=False).encode("utf-8")
        req = urllib.request.Request(url, data, {"Content-Type": "application/json"}, method="POST")
        urllib.request.urlopen(req, timeout=10)
    except Exception as e:
        logger.warning(f"[inbound] 回写 webhook 失败: {e}")


def sync_status_outbound(db: Session, source_name: str, alert_id: int, status: str) -> None:
    """供内部（告警处置）调用：把本项目告警处置状态回写源系统。"""
    src = db.query(InboundSource).filter(
        InboundSource.name == source_name,
        InboundSource.enabled == True,
    ).first()
    if src and src.status_webhook_url:
        _post_webhook(src.status_webhook_url, {
            "event": "alert_status",
            "source": src.name,
            "alert_id": alert_id,
            "status": status,
            "time": datetime.now().isoformat(timespec="seconds"),
        })
