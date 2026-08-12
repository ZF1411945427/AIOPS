"""
AI 洞察引擎 — 统一指标/日志/链路三页的 AI 能力增强

核心能力:
1. 时序趋势分析(指标): 斜率/突刺/波动检测 → 趋势分类
2. 日志聚类(日志): 按 service+level+error 模式聚合
3. 跨链路聚合(链路): 按 service 聚合 P90/错误率/瓶颈排序
4. 跨域 RCA: 指标异常 → 自动拉关联日志+链路+告警 → LLM 根因分析
5. 历史记录沉淀: 每次分析结果持久化,可回看/对比
"""
import json
import re
import logging
from datetime import datetime, timedelta
from typing import Optional
from collections import defaultdict
from sqlalchemy.orm import Session

from app.models import AIInsightRecord, AIProvider, AgentConfig, Alert, Span, DataSource
from app.services.agent_service import call_llm
from app.services.ai_provider_health import select_healthy_provider

logger = logging.getLogger(__name__)


def _get_provider(db: Session) -> Optional[AIProvider]:
    config = db.query(AgentConfig).filter(AgentConfig.is_enabled == True).order_by(AgentConfig.id.asc()).first()
    provider = None
    if config and config.default_provider_id:
        provider = db.query(AIProvider).filter(
            AIProvider.id == config.default_provider_id, AIProvider.is_enabled == True).first()
    if not provider:
        _all = db.query(AIProvider).filter(AIProvider.is_enabled == True).all()
        _sel, _cand, _skip = select_healthy_provider(_all)
        provider = _sel or (_all[0] if _all else None)
    return provider


# ═══════════════════════════════════════════════════════════════
# 1. 时序趋势分析
# ═══════════════════════════════════════════════════════════════

def analyze_trend(values: list) -> dict:
    if not values or len(values) < 3:
        return {"trend": "unknown", "direction": 0, "spike": False, "volatility": 0}
    vals = [v for v in values if v is not None]
    if len(vals) < 3:
        return {"trend": "unknown", "direction": 0, "spike": False, "volatility": 0}
    n = len(vals)
    mean_val = sum(vals) / n
    if mean_val == 0:
        mean_val = 0.001
    xs = list(range(n))
    sum_x = sum(xs)
    sum_y = sum(vals)
    sum_xy = sum(x * y for x, y in zip(xs, vals))
    sum_xx = sum(x * x for x in xs)
    slope = (n * sum_xy - sum_x * sum_y) / (n * sum_xx - sum_x * sum_x) if (n * sum_xx - sum_x * sum_x) else 0
    slope_pct = (slope / mean_val) * 100
    recent = vals[-max(3, n // 3):]
    early = vals[:max(3, n // 3)]
    recent_mean = sum(recent) / len(recent)
    early_mean = sum(early) / len(early)
    rel_change = ((recent_mean - early_mean) / mean_val) * 100
    std = (sum((v - mean_val) ** 2 for v in vals) / n) ** 0.5
    cv = std / mean_val
    spike_count = 0
    for v in vals:
        if v > mean_val + 3 * std:
            spike_count += 1
    if abs(slope_pct) < 0.1:
        trend = "steady"
    elif slope_pct > 5:
        trend = "rising"
    elif slope_pct < -5:
        trend = "falling"
    else:
        trend = "steady"
    if cv > 0.5:
        trend = "volatile"
    if spike_count >= 2:
        trend = "spike"
    return {
        "trend": trend,
        "direction": round(slope_pct, 2),
        "spike": spike_count >= 2,
        "volatility": round(cv, 3),
        "rel_change_pct": round(rel_change, 1),
        "mean": round(mean_val, 2),
        "std": round(std, 2),
    }


TREND_CN = {
    "steady": "平稳",
    "rising": "持续上升",
    "falling": "持续下降",
    "volatile": "剧烈波动",
    "spike": "频繁突刺",
    "unknown": "数据不足",
}


# ═══════════════════════════════════════════════════════════════
# 2. 日志聚类
# ═══════════════════════════════════════════════════════════════

def cluster_logs(logs: list) -> dict:
    if not logs:
        return {"clusters": [], "total": 0, "error_pct": 0}
    by_type = defaultdict(list)
    for lg in logs:
        lvl = (lg.get("level") or "info").lower()
        svc = lg.get("service") or "unknown"
        host = lg.get("host") or "unknown"
        msg = (lg.get("message") or "").strip()
        error_type = "unknown"
        if lvl in ("error", "critical", "fatal"):
            patterns = [
                (r"timeout|timed out|timed_out", "timeout"),
                (r"connection refused|connection refused|ECONNREFUSED", "connection_refused"),
                (r"out of memory|OOM|oom_kill", "oom"),
                (r"disk full|no space left", "disk_full"),
                (r"permission denied|permission_denied|EACCES", "permission_denied"),
                (r"not found|No such file|ENOENT", "not_found"),
                (r"null pointer|NullPointerException", "null_pointer"),
                (r"stack overflow|StackOverflow", "stack_overflow"),
                (r"divide by zero|DivisionByZero", "divide_by_zero"),
                (r"deadlock|deadlock detected|Deadlock", "deadlock"),
                (r"invalid|Invalid|illegal|Illegal", "invalid_argument"),
                (r"failed|Failed|FAILED|error|Error|ERROR", "general_error"),
            ]
            for pat, etype in patterns:
                if re.search(pat, msg, re.I):
                    error_type = etype
                    break
            else:
                error_type = "unknown_error"
        key = (svc, host, lvl, error_type)
        by_type[key].append(lg)
    clusters = []
    for (svc, host, lvl, etype), items in sorted(by_type.items(), key=lambda x: -len(x[1])):
        clusters.append({
            "service": svc,
            "host": host,
            "level": lvl,
            "error_type": etype if lvl in ("error", "critical", "fatal") else "",
            "count": len(items),
            "sample": items[0] if items else {},
        })
    total = len(logs)
    errors = sum(1 for lg in logs if (lg.get("level") or "").lower() in ("error", "critical", "fatal"))
    return {
        "clusters": clusters,
        "total": total,
        "error_pct": round(errors / total * 100, 1) if total else 0,
        "error_count": errors,
        "cluster_count": len(clusters),
    }


# ═══════════════════════════════════════════════════════════════
# 3. 跨链路聚合
# ═══════════════════════════════════════════════════════════════

def aggregate_traces(traces: list) -> dict:
    """跨多条调用链聚合,按服务计算 P90/错误率/瓶颈评分"""
    if not traces:
        return {"services": [], "total_traces": 0}
    svc_metrics = defaultdict(lambda: {"durations": [], "errors": 0, "total": 0, "operations": set()})
    for tr in traces:
        for s in tr.get("spans") or []:
            svc = s.get("service_name") or "unknown"
            dur = s.get("duration_ms") or 0
            svc_metrics[svc]["durations"].append(dur)
            svc_metrics[svc]["total"] += 1
            if s.get("status") == "ERROR":
                svc_metrics[svc]["errors"] += 1
            svc_metrics[svc]["operations"].add(s.get("operation_name", ""))
    services = []
    for svc, m in svc_metrics.items():
        durs = sorted(m["durations"])
        n = len(durs)
        p90 = durs[int(n * 0.9)] if n > 0 else 0
        avg = sum(durs) / n if n > 0 else 0
        max_dur = max(durs) if durs else 0
        err_rate = round(m["errors"] / m["total"] * 100, 1) if m["total"] else 0
        bottleneck_score = round(p90 * (1 + err_rate / 100) / 100, 2)
        services.append({
            "service": svc,
            "span_count": m["total"],
            "avg_duration_ms": round(avg, 1),
            "p90_duration_ms": round(p90, 1),
            "max_duration_ms": round(max_dur, 1),
            "error_rate": err_rate,
            "error_count": m["errors"],
            "bottleneck_score": bottleneck_score,
            "operations": sorted(m["operations"])[:10],
        })
    services.sort(key=lambda x: -x["bottleneck_score"])
    top_bottleneck = services[0] if services else None
    return {
        "services": services,
        "total_traces": len(traces),
        "top_bottleneck": top_bottleneck,
    }


# ═══════════════════════════════════════════════════════════════
# 4. 跨域 RCA（指标异常 → 关联日志+链路+告警）
# ═══════════════════════════════════════════════════════════════

def cross_domain_rca(db: Session, provider, metric_name: str, asset_id: int,
                     hours: int = 6, question: str = "") -> dict:
    from app.services import metric_v2_service
    # 4a. 取指标时序
    metric_data = metric_v2_service.query_range_data(asset_id=asset_id, name=metric_name, hours=hours)
    trend = analyze_trend([d.get("value") for d in metric_data if d.get("value") is not None])
    # 4b. 关联告警
    since = datetime.utcnow() - timedelta(hours=hours)
    alerts = db.query(Alert).filter(
        Alert.asset_id == asset_id,
        Alert.created_at >= since,
    ).order_by(Alert.created_at.desc()).limit(20).all()
    # 4c. 关联调用链
    from app.routers.traces_api import _span_service_names
    svc_match = None
    asset = None
    from app.models import Asset
    asset = db.query(Asset).filter(Asset.id == asset_id).first()
    if asset:
        all_svcs = _span_service_names(db)
        aname = asset.name.lower()
        for s in all_svcs:
            if aname.split(".")[0] in s.lower() or s.lower() in aname:
                svc_match = s
                break
    related_traces = []
    if svc_match:
        related_spans = db.query(Span).filter(
            Span.service_name == svc_match,
            Span.started_at >= since,
        ).order_by(Span.started_at.desc()).limit(20).all()
        if related_spans:
            traces_seen = set()
            for sp in related_spans:
                if sp.trace_id not in traces_seen and len(traces_seen) < 5:
                    traces_seen.add(sp.trace_id)
            for tid in list(traces_seen)[:3]:
                s = db.query(Span).filter(Span.trace_id == tid).first()
                if s:
                    related_traces.append({"trace_id": tid, "service": svc_match})
    # 4d. 关联日志(如果有日志源)
    related_logs = []
    log_sources = db.query(DataSource).filter(
        DataSource.type.in_(["elasticsearch", "loki"]),
        DataSource.enabled == True,
    ).limit(1).all()
    asset_name = asset.name if asset else f"asset#{asset_id}"
    # 组装 LLM 输入
    lines = [f"=== 跨域 RCA 分析 ===", f"目标资产: {asset_name} (ID={asset_id})", f"异常指标: {metric_name}", f"时间窗口: {hours}小时", f"时间: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}", ""]
    # 指标
    lines.append(f"--- 指标时序 ---")
    lines.append(f"趋势: {TREND_CN.get(trend.get('trend', ''), 'unknown')} (rel_change={trend.get('rel_change_pct', 0)}%)")
    lines.append(f"波动率: {trend.get('volatility', 0)} | 突刺: {'是' if trend.get('spike') else '否'}")
    if metric_data:
        last = metric_data[-1]
        lines.append(f"最新值: {last.get('value', '?')} {last.get('unit', '')}")
    lines.append(f"数据点: {len(metric_data)}")
    lines.append("")
    # 告警
    lines.append(f"--- 关联告警 ({len(alerts)} 条) ---")
    for a in alerts[:10]:
        lines.append(f"  [{a.severity}] {a.metric_name or '?'} = {a.actual_value} (阈值: {a.threshold}) {a.message or ''}")
    lines.append("")
    # 链路
    lines.append(f"--- 关联调用链 ({len(related_traces)} 条) ---")
    for rt in related_traces:
        lines.append(f"  trace_id={rt['trace_id']} service={rt['service']}")
    lines.append("")
    sys_prompt = (
        "你是一名资深 SRE 专家，精通跨域根因分析(RCA)。"
        "用户有一个指标异常，已自动关联了同资产同时间段的告警、调用链数据请做综合根因分析。"
        "请输出结构化分析：\n"
        "1. **指标现状**：该指标的当前状态、趋势方向、异常程度\n"
        "2. **关联信号**：告警与调用链中有哪些异常信号与指标异常存在时序关联\n"
        "3. **根因判断**：最可能的根因，按置信度排序\n"
        "4. **影响范围**：受影响的服务/资产范围\n"
        "5. **处置建议**：P0/P1/P2 优先级操作步骤"
    )
    user_prompt = "\n".join(lines)
    if question:
        user_prompt += f"\n\n用户附加诉求: {question}"
    resp = call_llm(provider, [
        {"role": "system", "content": sys_prompt},
        {"role": "user", "content": user_prompt},
    ], timeout_override=120)
    if resp.get("error"):
        return {"ok": False, "error": f"RCA 分析失败: {resp['error']}"}
    try:
        content = resp["choices"][0]["message"]["content"]
    except Exception:
        return {"ok": False, "error": "AI 返回格式异常"}
    return {
        "ok": True,
        "analysis": content or "",
        "provider": provider.default_model,
        "trend": trend,
        "alert_count": len(alerts),
        "trace_count": len(related_traces),
        "metric_name": metric_name,
        "asset_name": asset_name,
    }


# ═══════════════════════════════════════════════════════════════
# 5. 历史记录沉淀
# ═══════════════════════════════════════════════════════════════

def record_analysis(db: Session, user_id: int, source_type: str, title: str,
                    analysis: str, provider: str = "", meta_json: dict = None,
                    question: str = "", score: int = 0) -> AIInsightRecord:
    rec = AIInsightRecord(
        user_id=user_id,
        source_type=source_type,
        title=title or f"{source_type} 分析 #{datetime.now().strftime('%H%M%S')}",
        question=question or "",
        analysis=analysis or "",
        meta_json=json.dumps(meta_json or {}, ensure_ascii=False),
        provider=provider or "",
        score=score,
    )
    db.add(rec)
    db.commit()
    db.refresh(rec)
    return rec


def list_analysis(db: Session, user_id: int, source_type: str = "", limit: int = 50) -> list:
    q = db.query(AIInsightRecord).filter(AIInsightRecord.user_id == user_id)
    if source_type:
        q = q.filter(AIInsightRecord.source_type == source_type)
    rows = q.order_by(AIInsightRecord.created_at.desc()).limit(limit).all()
    return [{
        "id": r.id, "source_type": r.source_type, "title": r.title,
        "question": r.question[:100] if r.question else "",
        "analysis_preview": (r.analysis or "")[:200],
        "provider": r.provider or "",
        "meta_json": json.loads(r.meta_json or "{}"),
        "score": r.score,
        "created_at": r.created_at.strftime("%Y-%m-%d %H:%M:%S") if r.created_at else "",
    } for r in rows]


def get_analysis_detail(db: Session, record_id: int, user_id: int) -> dict:
    r = db.query(AIInsightRecord).filter(
        AIInsightRecord.id == record_id,
        AIInsightRecord.user_id == user_id,
    ).first()
    if not r:
        return None
    return {
        "id": r.id, "source_type": r.source_type, "title": r.title,
        "question": r.question or "",
        "analysis": r.analysis or "",
        "provider": r.provider or "",
        "meta_json": json.loads(r.meta_json or "{}"),
        "score": r.score,
        "created_at": r.created_at.strftime("%Y-%m-%d %H:%M:%S") if r.created_at else "",
    }


def delete_analysis(db: Session, record_id: int, user_id: int) -> bool:
    r = db.query(AIInsightRecord).filter(
        AIInsightRecord.id == record_id,
        AIInsightRecord.user_id == user_id,
    ).first()
    if not r:
        return False
    db.delete(r)
    db.commit()
    return True