from collections import defaultdict
from datetime import datetime, timedelta
import math
import json
import time
from fastapi import APIRouter, Depends, Query
from fastapi.responses import JSONResponse
from sqlalchemy.orm import Session
from sqlalchemy import desc
from app.database import get_db
from app.models import Span, Alert, MetricRecord, Asset, LogAnomalyRule, K8sEvent, AssetChangeLog
from app.logger import logger

router = APIRouter(prefix="/observability", tags=["observability-correlation"])
logger.info("[ObservabilityCorrelation] Router loaded, prefix=/observability")

_cache = {}
_CACHE_TTL = 10

def _cached(key: str, ttl: int = _CACHE_TTL):
    entry = _cache.get(key)
    if entry and time.time() - entry["ts"] < ttl:
        return entry["data"]
    return None

def _set_cache(key: str, data):
    _cache[key] = {"data": data, "ts": time.time()}


def _get_time_range(hours: int):
    return datetime.now() - timedelta(hours=hours)


def _bucket_minutes(hours: int) -> int:
    if hours <= 2:
        return 1
    if hours <= 8:
        return 5
    if hours <= 24:
        return 15
    return 60


def _floor_ts(dt: datetime, bucket_minutes: int) -> str:
    bucket_seconds = bucket_minutes * 60
    ts = dt.timestamp()
    floored = math.floor(ts / bucket_seconds) * bucket_seconds
    return datetime.fromtimestamp(floored).isoformat()


def _detect_k8s_log_anomalies(db: Session, since: datetime, asset_id: int = 0, service: str = "") -> list:
    q = db.query(K8sEvent).filter(K8sEvent.last_seen_at >= since)
    if asset_id > 0:
        asset = db.query(Asset).filter(Asset.id == asset_id).first()
        if asset and asset.k8s_cluster:
            q = q.filter(K8sEvent.cluster == asset.k8s_cluster)
    if service:
        q = q.filter(K8sEvent.namespace.ilike(f"%{service}%"))
    events = q.order_by(desc(K8sEvent.last_seen_at)).limit(500).all()

    reason_groups = defaultdict(list)
    for e in events:
        reason_groups[e.reason].append(e)

    result = []
    for reason, evts in reason_groups.items():
        severity = evts[0].severity or "info"
        total_count = sum(e.count or 1 for e in evts)
        if severity not in ("ERROR", "Warning") and total_count < 10:
            continue
        result.append({
            "reason": reason,
            "count": total_count,
            "severity": severity,
            "kind": evts[0].kind or "",
            "namespace": evts[0].namespace or "",
            "message_sample": evts[0].message[:200] if evts[0].message else "",
            "last_seen_at": evts[0].last_seen_at.isoformat() if evts[0].last_seen_at else "",
            "cluster": evts[0].cluster or "",
        })
    return result


def _generate_rca(alerts: list, metric_anomalies: list, log_anomalies: list, trace_data: dict) -> list:
    suggestions = []

    metric_asset_ids = set(ma.get("asset_id") for ma in metric_anomalies if ma.get("asset_id"))
    alert_asset_ids = defaultdict(list)
    for a in alerts:
        aid = a.get("asset_id")
        if aid:
            alert_asset_ids[aid].append(a)

    trace_error_rate = trace_data.get("error_rate_pct", 0)
    slow_traces = trace_data.get("slow_traces", [])
    error_traces = trace_data.get("error_traces", [])
    high_error_services = trace_data.get("high_error_services", [])

    if len(metric_anomalies) >= 3 and trace_error_rate > 5:
        affected = list(set(
            ma.get("metric_name", "").split("_")[0]
            for ma in metric_anomalies[:10] if ma.get("metric_name")
        ))
        suggestions.append({
            "type": "application",
            "confidence": "high",
            "message": f"检测到 {len(metric_anomalies)} 个指标异常，同时调用链错误率 {trace_error_rate}% 超过 5% 阈值，疑似应用层故障",
            "affected_services": affected,
        })

    for aid, alist in alert_asset_ids.items():
        if len(alist) >= 3:
            suggestions.append({
                "type": "infrastructure",
                "confidence": "medium",
                "message": f"资产 #{aid} 触发了 {len(alist)} 条告警，可能为基础设施问题",
                "affected_services": [],
            })

    if slow_traces and log_anomalies:
        suggestions.append({
            "type": "code_issue",
            "confidence": "medium",
            "message": f"检测到 {len(slow_traces)} 条慢调用链和 {len(log_anomalies)} 个日志异常并发，可能为代码缺陷（慢查询/死锁/异常逻辑）",
            "affected_services": [s.get("service_name", "") for s in slow_traces[:5]],
        })

    if error_traces:
        suggestions.append({
            "type": "application",
            "confidence": "low",
            "message": f"检测到 {len(error_traces)} 条错误调用链，建议检查相关服务的错误日志",
            "affected_services": [s.get("service_name", "") for s in error_traces[:5]],
        })

    return suggestions


def run_correlation_analysis(
    db: Session,
    hours: int = 1,
    service: str = "",
    asset_id: int = 0,
) -> dict:
    """
    关联分析核心逻辑（可复用，供 AI 深度分析等场景调用）：
    在指定时间窗口内，同时查询指标异常、日志异常、链路异常，
    按资产/服务聚合，返回统一的关联分析结果。
    """
    since = _get_time_range(hours)
    result = {
        "time_range_hours": hours,
        "since": since.isoformat(),
        "service": service or "全部",
        "asset_id": asset_id,
        "summary": {
            "total_alerts": 0,
            "total_metric_anomalies": 0,
            "total_log_anomalies": 0,
            "total_trace_anomalies": 0,
            "correlated_assets": 0,
            "multi_signal_assets": 0,
            "critical_assets": 0,
        },
        "alerts": [],
        "metric_anomalies": [],
        "log_anomalies": [],
        "trace_anomalies": {
            "slow_traces": [],
            "error_traces": [],
            "high_error_services": [],
            "duration_p95_ms": 0,
            "error_rate_pct": 0,
            "total_traces": 0,
        },
        "correlated_assets": [],
        "rca_suggestions": [],
        "change_records": [],
    }

    alert_q = db.query(Alert).filter(Alert.created_at >= since)
    if asset_id > 0:
        alert_q = alert_q.filter(Alert.asset_id == asset_id)
    if service:
        alert_q = alert_q.filter(Alert.message.ilike(f"%{service}%"))
    alerts = alert_q.order_by(desc(Alert.created_at)).limit(200).all()

    alert_list = []
    for a in alerts:
        alert_list.append({
            "id": a.id,
            "asset_id": a.asset_id,
            "metric_name": a.metric_name or "",
            "severity": a.severity or "warning",
            "status": a.status or "firing",
            "message": a.message or "",
            "actual_value": a.actual_value,
            "threshold": a.threshold,
            "created_at": a.created_at.isoformat() if a.created_at else "",
        })
    result["alerts"] = alert_list
    result["summary"]["total_alerts"] = len(alert_list)

    change_logs = (
        db.query(AssetChangeLog)
        .filter(AssetChangeLog.created_at >= since)
        .order_by(desc(AssetChangeLog.created_at))
        .limit(100)
        .all()
    )
    change_record_list = []
    for cl in change_logs:
        change_record_list.append({
            "id": cl.id,
            "asset_id": cl.asset_id,
            "asset_name": cl.asset_name,
            "field": cl.field,
            "old_value": cl.old_value,
            "new_value": cl.new_value,
            "operator": cl.operator,
            "created_at": cl.created_at.isoformat() if cl.created_at else "",
        })
    result["change_records"] = change_record_list

    metric_q = db.query(MetricRecord).filter(MetricRecord.timestamp >= since)
    if asset_id > 0:
        metric_q = metric_q.filter(MetricRecord.asset_id == asset_id)
    metric_records = metric_q.order_by(desc(MetricRecord.timestamp)).limit(2000).all()

    metric_groups = defaultdict(list)
    for mr in metric_records:
        metric_groups[(mr.asset_id, mr.name)].append(mr)

    metric_anomaly_list = []
    for (aid, mname), records in metric_groups.items():
        if len(records) < 5:
            continue
        values = [r.value for r in records]
        mean = sum(values) / len(values)
        variance = sum((v - mean) ** 2 for v in values) / len(values)
        std = math.sqrt(variance) if variance > 0 else 1e-10
        for mr in records:
            z = (mr.value - mean) / std
            if abs(z) > 2.5:
                metric_anomaly_list.append({
                    "asset_id": mr.asset_id,
                    "metric_name": mr.name,
                    "value": mr.value,
                    "mean": round(mean, 4),
                    "std": round(std, 4),
                    "z_score": round(z, 2),
                    "severity": "critical" if abs(z) > 3.5 else "warning",
                    "timestamp": mr.timestamp.isoformat() if mr.timestamp else "",
                })
    result["metric_anomalies"] = metric_anomaly_list[:200]
    result["summary"]["total_metric_anomalies"] = len(metric_anomaly_list)

    k8s_logs = _detect_k8s_log_anomalies(db, since, asset_id, service)
    result["log_anomalies"] = list(k8s_logs)

    log_anomaly_rules = db.query(LogAnomalyRule).filter(LogAnomalyRule.enabled == True).all()
    log_anomaly_list = []
    for rule in log_anomaly_rules:
        matched_alerts = [
            a for a in alerts
            if a.message and rule.keyword and rule.keyword.lower() in a.message.lower()
        ]
        for a in matched_alerts:
            log_anomaly_list.append({
                "rule_id": rule.id,
                "rule_name": rule.name,
                "asset_id": a.asset_id,
                "keyword": rule.keyword or "",
                "severity": rule.severity or a.severity,
                "message": a.message,
                "created_at": a.created_at.isoformat() if a.created_at else "",
            })
    result["log_anomalies"].extend(log_anomaly_list[:100])
    result["summary"]["total_log_anomalies"] = len(result["log_anomalies"])

    span_q = db.query(Span).filter(Span.started_at >= since)
    if service:
        span_q = span_q.filter(Span.service_name.ilike(f"%{service}%"))
    spans = span_q.order_by(desc(Span.started_at)).limit(1000).all()

    durations = [s.duration_ms for s in spans if s.duration_ms is not None and s.duration_ms > 0]
    avg_dur = sum(durations) / len(durations) if durations else 0
    std_dur = (sum((d - avg_dur) ** 2 for d in durations) / len(durations)) ** 0.5 if len(durations) > 1 else 1
    dur_threshold = avg_dur + 2 * std_dur

    slow_trace_list = []
    error_trace_list = []
    slow_trace_ids = set()
    error_trace_ids = set()

    for s in spans:
        is_slow = s.duration_ms and s.duration_ms > dur_threshold
        is_error = s.status and s.status != "OK"
        entry = {
            "trace_id": s.trace_id,
            "service_name": s.service_name,
            "operation_name": s.operation_name,
            "duration_ms": s.duration_ms,
            "status": s.status,
            "is_error": is_error,
            "is_slow": is_slow,
            "z_score": round((s.duration_ms - avg_dur) / std_dur, 2) if std_dur > 0 and s.duration_ms else 0,
            "started_at": s.started_at.isoformat() if s.started_at else "",
        }
        if is_slow and s.trace_id not in slow_trace_ids:
            slow_trace_ids.add(s.trace_id)
            slow_trace_list.append(entry)
        if is_error and s.trace_id not in error_trace_ids:
            error_trace_ids.add(s.trace_id)
            error_trace_list.append(entry)

    service_errors = defaultdict(lambda: {"total": 0, "errors": 0})
    for s in spans:
        service_errors[s.service_name]["total"] += 1
        if s.status and s.status != "OK":
            service_errors[s.service_name]["errors"] += 1

    high_error_services = []
    for svc, stats in service_errors.items():
        if stats["total"] > 0:
            err_rate = stats["errors"] / stats["total"] * 100
            if err_rate > 5 or stats["errors"] > 3:
                high_error_services.append({
                    "service_name": svc,
                    "error_rate": round(err_rate, 1),
                    "error_count": stats["errors"],
                    "total_count": stats["total"],
                })

    trace_data = {
        "slow_traces": sorted(slow_trace_list, key=lambda x: -x.get("z_score", 0))[:20],
        "error_traces": sorted(error_trace_list, key=lambda x: -x.get("z_score", 0))[:20],
        "high_error_services": sorted(high_error_services, key=lambda x: -x["error_rate"])[:10],
        "duration_p95_ms": round(sorted(durations)[int(len(durations) * 0.95)] if len(durations) > 1 else avg_dur, 1),
        "error_rate_pct": round(len([s for s in spans if s.status and s.status != "OK"]) / len(spans) * 100, 1) if spans else 0,
        "total_traces": len(set(s.trace_id for s in spans)),
    }
    result["trace_anomalies"] = trace_data
    result["summary"]["total_trace_anomalies"] = len(slow_trace_ids | error_trace_ids)

    asset_scores = defaultdict(lambda: {"score": 0, "signals": set(), "alerts": 0, "metric": 0, "log": 0, "trace": 0})

    for a in alerts:
        if a.asset_id:
            asset_scores[a.asset_id]["score"] += 1
            asset_scores[a.asset_id]["alerts"] += 1
            asset_scores[a.asset_id]["signals"].add("alert")

    for ma in metric_anomaly_list:
        aid = ma.get("asset_id")
        if aid:
            asset_scores[aid]["score"] += 2
            asset_scores[aid]["metric"] += 1
            asset_scores[aid]["signals"].add("metric")

    for la in result["log_anomalies"]:
        aid = la.get("asset_id")
        if aid:
            asset_scores[aid]["score"] += 2
            asset_scores[aid]["log"] += 1
            asset_scores[aid]["signals"].add("log")

    trace_asset_map = {}
    for s in spans:
        if s.service_name and s.service_name not in trace_asset_map:
            asset_match = db.query(Asset).filter(
                Asset.name.ilike(f"%{s.service_name}%")
            ).first()
            trace_asset_map[s.service_name] = asset_match.id if asset_match else None
        aid = trace_asset_map.get(s.service_name)
        if aid:
            asset_scores[aid]["score"] += 3
            asset_scores[aid]["trace"] += 1
            asset_scores[aid]["signals"].add("trace")

    multi_signal_count = 0
    critical_count = 0
    correlated_assets = []
    for aid, counts in sorted(asset_scores.items(), key=lambda x: -x[1]["score"]):
        asset = db.query(Asset).filter(Asset.id == aid).first()
        if asset:
            signal_count = len(counts["signals"])
            correlated_assets.append({
                "asset_id": aid,
                "asset_name": asset.name,
                "ci_type": asset.ci_type or "",
                "ip": asset.ip or "",
                "alerts": counts["alerts"],
                "metric_anomalies": counts["metric"],
                "log_anomalies": counts["log"],
                "trace_anomalies": counts["trace"],
                "signal_count": signal_count,
                "signals": sorted(counts["signals"]),
                "total_score": counts["score"],
            })
            if signal_count >= 2:
                multi_signal_count += 1
            if counts["score"] >= 10:
                critical_count += 1

    result["summary"]["correlated_assets"] = len(correlated_assets)
    result["summary"]["multi_signal_assets"] = multi_signal_count
    result["summary"]["critical_assets"] = critical_count
    result["correlated_assets"] = correlated_assets[:20]

    result["rca_suggestions"] = _generate_rca(
        alert_list, metric_anomaly_list, result["log_anomalies"], trace_data
    )

    return result


def format_correlation_for_llm(data: dict) -> str:
    """将关联分析结果格式化为 LLM 友好的文本"""
    lines = []
    s = data.get("summary", {})
    lines.append("## 📊 关联分析概览")
    lines.append(f"- 分析时间范围：最近 {data.get('time_range_hours', 1)} 小时")
    lines.append(f"- 服务筛选：{data.get('service', '全部')}")
    lines.append(f"- 总告警数：{s.get('total_alerts', 0)}")
    lines.append(f"- 指标异常数：{s.get('total_metric_anomalies', 0)}")
    lines.append(f"- 日志异常数：{s.get('total_log_anomalies', 0)}")
    lines.append(f"- 链路异常数：{s.get('total_trace_anomalies', 0)}")
    lines.append(f"- 关联资产数：{s.get('correlated_assets', 0)}")
    lines.append(f"- 多信号资产数：{s.get('multi_signal_assets', 0)}")
    lines.append(f"- 严重资产数：{s.get('critical_assets', 0)}")
    lines.append("")

    alerts = data.get("alerts", [])
    if alerts:
        lines.append(f"## 🚨 告警列表（共 {len(alerts)} 条，显示前 10 条）")
        for a in alerts[:10]:
            lines.append(f"- [{a.get('severity','')}] #{a.get('id','')} {a.get('metric_name','')} = {a.get('actual_value','')} (阈值 {a.get('threshold','')}) 资产ID:{a.get('asset_id','')}")
        lines.append("")

    metrics = data.get("metric_anomalies", [])
    if metrics:
        lines.append(f"## 📈 指标异常（共 {len(metrics)} 条，显示前 10 条）")
        for m in metrics[:10]:
            lines.append(f"- {m.get('metric_name','')} 当前值={m.get('value','')} 均值={m.get('mean','')} Z-Score={m.get('z_score','')} 级别={m.get('severity','')} 资产ID:{m.get('asset_id','')}")
        lines.append("")

    logs = data.get("log_anomalies", [])
    if logs:
        lines.append(f"## 📝 日志异常（共 {len(logs)} 条，显示前 10 条）")
        for l in logs[:10]:
            lines.append(f"- [{l.get('severity','')}] {l.get('reason','')} (次数:{l.get('count','')}) 命名空间:{l.get('namespace','')}")
        lines.append("")

    traces = data.get("trace_anomalies", {})
    if traces.get("total_traces", 0) > 0:
        lines.append(f"## 🔗 链路追踪")
        lines.append(f"- 总调用链：{traces.get('total_traces', 0)} 条")
        lines.append(f"- P95 耗时：{traces.get('duration_p95_ms', 0)} ms")
        lines.append(f"- 错误率：{traces.get('error_rate_pct', 0)}%")
        slow = traces.get("slow_traces", [])
        if slow:
            lines.append(f"  - 慢调用链（前 5 条）：")
            for t in slow[:5]:
                lines.append(f"    - {t.get('service_name','')}/{t.get('operation_name','')} 耗时 {t.get('duration_ms','')}ms Z={t.get('z_score','')}")
        err = traces.get("error_traces", [])
        if err:
            lines.append(f"  - 错误调用链（前 5 条）：")
            for t in err[:5]:
                lines.append(f"    - {t.get('service_name','')}/{t.get('operation_name','')} 状态={t.get('status','')}")
        high_err = traces.get("high_error_services", [])
        if high_err:
            lines.append(f"  - 高错误率服务：")
            for t in high_err[:5]:
                lines.append(f"    - {t.get('service_name','')} 错误率={t.get('error_rate','')}% ({t.get('error_count','')}/{t.get('total_count','')})")
        lines.append("")

    assets = data.get("correlated_assets", [])
    if assets:
        lines.append(f"## 🖥️ 关联资产评分（共 {len(assets)} 个，显示前 10 个）")
        for a in assets[:10]:
            sigs = ", ".join(a.get("signals", []))
            lines.append(f"- {a.get('asset_name','')} ({a.get('ci_type','')}) IP={a.get('ip','')} 评分={a.get('total_score','')} 信号数={a.get('signal_count','')} [{sigs}]")
        lines.append("")

    rca = data.get("rca_suggestions", [])
    if rca:
        lines.append(f"## 💡 系统预判（RCA 建议）")
        for r in rca:
            lines.append(f"- [{r.get('confidence','')}] [{r.get('type','')}] {r.get('message','')}")
        lines.append("")

    changes = data.get("change_records", [])
    if changes:
        lines.append(f"## 📝 变更记录（共 {len(changes)} 条，显示前 10 条）")
        for c in changes[:10]:
            lines.append(f"- [{c.get('created_at','')}] {c.get('asset_name','')} {c.get('field','')}: {c.get('old_value','')} → {c.get('new_value','')} (操作人:{c.get('operator','')}")
        lines.append("")

    return "\n".join(lines)


@router.get("/correlation/analyze")
def analyze_correlation(
    db: Session = Depends(get_db),
    hours: int = Query(1, description="分析时间范围（小时）"),
    service: str = Query("", description="服务名（可选，模糊匹配）"),
    asset_id: int = Query(0, description="资产 ID（可选）"),
):
    """关联分析核心接口（端点包装，含缓存）"""
    cache_key = f"analyze:{hours}:{service}:{asset_id}"
    cached = _cached(cache_key)
    if cached is not None:
        return cached
    result = run_correlation_analysis(db, hours, service, asset_id)
    _set_cache(cache_key, result)
    return result


@router.get("/correlation/timeline")
def correlation_timeline(
    db: Session = Depends(get_db),
    hours: int = Query(1, description="时间范围（小时）"),
    service: str = Query("", description="服务名（可选）"),
    asset_id: int = Query(0, description="资产 ID（可选）"),
):
    """
    返回按时间桶聚合的4类信号事件数，用于前端 ECharts 时间轴泳道图。
    """
    cache_key = f"timeline:{hours}:{service}:{asset_id}"
    cached = _cached(cache_key)
    if cached is not None:
        return cached

    logger.info(f"[ObservabilityCorrelation] correlation_timeline called: hours={hours}, service={service}, asset_id={asset_id}")
    since = _get_time_range(hours)
    bucket_min = _bucket_minutes(hours)
    bucket_seconds = bucket_min * 60

    now = datetime.now()
    total_seconds = int((now - since).total_seconds())
    num_buckets = max(1, math.ceil(total_seconds / bucket_seconds))
    bucket_map = {}
    for i in range(num_buckets):
        ts = int(since.timestamp()) + i * bucket_seconds
        floored = datetime.fromtimestamp(math.floor(ts / bucket_seconds) * bucket_seconds)
        key = floored.isoformat()
        bucket_map[key] = {"timestamp": key, "alerts": 0, "metrics": 0, "logs": 0, "traces": 0, "errors": 0}

    alert_q = db.query(Alert.created_at).filter(Alert.created_at >= since)
    if asset_id > 0:
        alert_q = alert_q.filter(Alert.asset_id == asset_id)
    if service:
        alert_q = alert_q.filter(Alert.message.ilike(f"%{service}%"))
    for row in alert_q.all():
        if row[0]:
            key = _floor_ts(row[0], bucket_min)
            if key in bucket_map:
                bucket_map[key]["alerts"] += 1

    metric_q = db.query(MetricRecord.timestamp).filter(MetricRecord.timestamp >= since)
    if asset_id > 0:
        metric_q = metric_q.filter(MetricRecord.asset_id == asset_id)
    for row in metric_q.all():
        if row[0]:
            key = _floor_ts(row[0], bucket_min)
            if key in bucket_map:
                bucket_map[key]["metrics"] += 1

    span_q = db.query(Span.started_at, Span.status).filter(Span.started_at >= since)
    if service:
        span_q = span_q.filter(Span.service_name.ilike(f"%{service}%"))
    for row in span_q.all():
        if row[0]:
            key = _floor_ts(row[0], bucket_min)
            if key in bucket_map:
                bucket_map[key]["traces"] += 1
                if row[1] and row[1] != "OK":
                    bucket_map[key]["errors"] += 1

    k8s_q = db.query(K8sEvent.last_seen_at).filter(K8sEvent.last_seen_at >= since)
    if asset_id > 0:
        asset = db.query(Asset).filter(Asset.id == asset_id).first()
        if asset and asset.k8s_cluster:
            k8s_q = k8s_q.filter(K8sEvent.cluster == asset.k8s_cluster)
    if service:
        k8s_q = k8s_q.filter(K8sEvent.namespace.ilike(f"%{service}%"))
    for row in k8s_q.all():
        if row[0]:
            key = _floor_ts(row[0], bucket_min)
            if key in bucket_map:
                bucket_map[key]["logs"] += 1

    log_rules = db.query(LogAnomalyRule).filter(LogAnomalyRule.enabled == True).all()
    if log_rules:
        alert_q2 = db.query(Alert.created_at, Alert.message).filter(Alert.created_at >= since)
        if asset_id > 0:
            alert_q2 = alert_q2.filter(Alert.asset_id == asset_id)
        if service:
            alert_q2 = alert_q2.filter(Alert.message.ilike(f"%{service}%"))
        for row in alert_q2.all():
            if row[0] and row[1]:
                for rule in log_rules:
                    if rule.keyword and rule.keyword.lower() in row[1].lower():
                        key = _floor_ts(row[0], bucket_min)
                        if key in bucket_map:
                            bucket_map[key]["logs"] += 1
                        break

    result = {
        "timeline": sorted(bucket_map.values(), key=lambda x: x["timestamp"]),
        "bucket_minutes": bucket_min,
    }
    _set_cache(cache_key, result)
    return result


@router.get("/correlation/topology")
def correlation_topology(
    db: Session = Depends(get_db),
    hours: int = Query(1, description="时间范围（小时）"),
    service: str = Query("", description="服务名（可选）"),
    asset_id: int = Query(0, description="资产 ID（可选）"),
):
    """
    返回服务拓扑依赖图，从 Span 的 parent_span_id 关系推导。
    """
    cache_key = f"topology:{hours}:{service}:{asset_id}"
    cached = _cached(cache_key)
    if cached is not None:
        return cached

    logger.info(f"[ObservabilityCorrelation] correlation_topology called: hours={hours}, service={service}, asset_id={asset_id}")
    since = _get_time_range(hours)

    span_q = db.query(Span).filter(Span.started_at >= since)
    if service:
        span_q = span_q.filter(Span.service_name.ilike(f"%{service}%"))
    spans = span_q.order_by(Span.started_at).limit(5000).all()

    trace_groups = defaultdict(list)
    for s in spans:
        trace_groups[s.trace_id].append(s)

    edge_counts = defaultdict(lambda: {"call_count": 0, "error_count": 0})
    service_stats = defaultdict(lambda: {"call_count": 0, "error_count": 0, "total_duration": 0.0})

    for tid, span_list in trace_groups.items():
        span_map = {s.span_id: s for s in span_list}
        for s in span_list:
            service_stats[s.service_name]["call_count"] += 1
            service_stats[s.service_name]["total_duration"] += (s.duration_ms or 0)
            if s.status and s.status != "OK":
                service_stats[s.service_name]["error_count"] += 1
            if s.parent_span_id and s.parent_span_id in span_map:
                parent = span_map[s.parent_span_id]
                key = (parent.service_name, s.service_name)
                edge_counts[key]["call_count"] += 1
                if s.status and s.status != "OK":
                    edge_counts[key]["error_count"] += 1

    nodes = []
    for svc, stats in service_stats.items():
        error_rate = round(stats["error_count"] / stats["call_count"] * 100, 1) if stats["call_count"] > 0 else 0
        avg_dur = round(stats["total_duration"] / stats["call_count"], 1) if stats["call_count"] > 0 else 0
        status = "error" if stats["error_count"] > 0 else ("normal" if stats["call_count"] > 0 else "unknown")
        nodes.append({
            "id": svc,
            "name": svc,
            "call_count": stats["call_count"],
            "error_count": stats["error_count"],
            "error_rate": error_rate,
            "avg_duration_ms": avg_dur,
            "status": status,
        })

    edges = []
    for (parent_svc, child_svc), counts in edge_counts.items():
        edges.append({
            "source": parent_svc,
            "target": child_svc,
            "call_count": counts["call_count"],
            "error_count": counts["error_count"],
        })

    result = {"nodes": nodes, "edges": edges}
    _set_cache(cache_key, result)
    return result


@router.get("/correlation/services")
def list_services(
    db: Session = Depends(get_db),
    hours: int = Query(1, description="最近 N 小时"),
    limit: int = Query(100, description="返回条数上限"),
    offset: int = Query(0, description="分页偏移量"),
):
    """返回服务列表，优先从 Span 表读取，无数据时降级到 Asset 表"""
    logger.info(f"[ObservabilityCorrelation] list_services called: hours={hours}, limit={limit}, offset={offset}")
    since = _get_time_range(hours)
    services = set()

    # 优先从 Span 表（APM 链路数据）
    for row in db.query(Span.service_name).filter(Span.started_at >= since).distinct():
        if row[0]:
            services.add(row[0])

    # 无 Span 数据时从 Asset 表兜底
    if not services:
        for row in db.query(Asset.name).filter(
            Asset.ci_type.in_(["service", "business_app", "api_service"])
        ).distinct():
            if row[0]:
                services.add(row[0])

    sorted_list = sorted(services)
    return {"services": sorted_list[offset:offset + limit] if limit else sorted_list}


@router.get("/correlation/assets")
def list_correlatable_assets(
    db: Session = Depends(get_db),
    hours: int = Query(1, description="最近 N 小时"),
    limit: int = Query(100, description="返回条数上限"),
    offset: int = Query(0, description="分页偏移量"),
):
    """返回资产列表，优先查有告警的资产，无数据时降级到全量资产"""
    since = _get_time_range(hours)
    asset_ids = set()

    # 优先从 Alert 表查有告警的资产
    for row in db.query(Alert.asset_id).filter(
        Alert.created_at >= since, Alert.asset_id != None
    ).distinct():
        if row[0]:
            asset_ids.add(row[0])

    if asset_ids:
        assets = db.query(Asset).filter(Asset.id.in_(asset_ids)).all()
    else:
        # 无告警数据时返回全量资产
        assets = db.query(Asset).all()

    sliced = assets[offset:offset + limit] if limit else assets
    return {
        "assets": [
            {"id": a.id, "name": a.name, "ci_type": a.ci_type or ""}
            for a in sliced
        ]
    }


@router.get("/correlation/trace-detail")
def get_trace_detail(
    trace_id: str = Query(..., description="Trace ID"),
    db: Session = Depends(get_db),
):
    """获取单条 trace 的详细链路信息"""
    spans = db.query(Span).filter(Span.trace_id == trace_id).order_by(Span.started_at).all()
    if not spans:
        return JSONResponse({"spans": []})

    span_list = []
    for s in spans:
        tags = s.tags
        if isinstance(tags, str):
            try:
                tags = json.loads(tags)
            except (json.JSONDecodeError, TypeError):
                tags = {}
        span_list.append({
            "span_id": s.span_id,
            "parent_span_id": s.parent_span_id or "",
            "service_name": s.service_name,
            "operation_name": s.operation_name,
            "started_at": s.started_at.isoformat() if s.started_at else "",
            "duration_ms": s.duration_ms,
            "status": s.status,
            "tags": tags,
        })

    return {
        "trace_id": trace_id,
        "total_spans": len(spans),
        "spans": span_list,
    }
