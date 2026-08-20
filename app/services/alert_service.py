from datetime import datetime, timedelta

from sqlalchemy.orm import Session
from sqlalchemy import func

from app.models import Alert, AlertRule, MetricRecord, Asset, AlertSilence, AlertSuppression, AlertEscalation, SystemConfig, NotificationChannel, AlertSilenceSchedule, K8sEvent
from app.services import notification_service


import logging
logger = logging.getLogger(__name__)

def _serialize_alert(a: Alert) -> dict:
    return {
        "id": a.id,
        "rule_id": a.rule_id,
        "asset_id": a.asset_id,
        "metric_name": a.metric_name,
        "actual_value": a.actual_value,
        "threshold": a.threshold,
        "severity": a.severity,
        "status": a.status,
        "source": getattr(a, "source", "internal") or "internal",
        "message": a.message,
        "created_at": a.created_at.strftime("%Y-%m-%d %H:%M:%S") if a.created_at else None,
    }


def _ws_publish_async(alert_dicts: list):
    """在新线程中异步推送告警到 WebSocket，不阻塞主流程."""
    import asyncio
    from app.services.ws_manager import ws_manager
    try:
        loop = asyncio.new_event_loop()
        asyncio.set_event_loop(loop)
        loop.run_until_complete(
            ws_manager.publish_alert({"type": "alert", "alerts": alert_dicts})
        )
        loop.close()
    except Exception as _exc:
        logger.warning("[except:pass] Exception: %s", _exc, exc_info=True)


def list_rules(db: Session):
    return db.query(AlertRule).order_by(AlertRule.id.desc()).all()


def get_rule(db: Session, rule_id: int):
    return db.query(AlertRule).filter(AlertRule.id == rule_id).first()


def create_rule(db: Session, data: dict):
    rule = AlertRule(**data)
    db.add(rule)
    db.commit()
    db.refresh(rule)
    return rule


def update_rule(db: Session, rule_id: int, data: dict):
    rule = get_rule(db, rule_id)
    if not rule:
        return None
    for k, v in data.items():
        setattr(rule, k, v)
    db.commit()
    db.refresh(rule)
    return rule


def delete_rule(db: Session, rule_id: int):
    rule = get_rule(db, rule_id)
    if not rule:
        return False
    db.delete(rule)
    db.commit()
    return True


def get_active_silences(db: Session):
    now = datetime.now()
    return db.query(AlertSilence).filter(AlertSilence.expires_at > now).all()


def create_silence(db: Session, rule_id: int, minutes: int, reason: str = ""):
    expires_at = datetime.now() + timedelta(minutes=minutes)
    silence = AlertSilence(rule_id=rule_id, expires_at=expires_at, reason=reason)
    db.add(silence)
    db.commit()
    db.refresh(silence)
    return silence


def delete_silence(db: Session, silence_id: int):
    db.query(AlertSilence).filter(AlertSilence.id == silence_id).delete()
    db.commit()


# ─── G1 告警规则类型化评估 ──────────────────────────────────────
RULE_KINDS = ["metric_raw", "anomaly", "forecast", "burn_rate",
              "trace_latency", "trace_error_rate", "log_match", "log_volume"]


def _load_config(rule) -> dict:
    import json
    try:
        cfg = json.loads(rule.config_json) if rule.config_json else {}
        return cfg if isinstance(cfg, dict) else {}
    except Exception:
        return {}


def _metric_history(db: Session, metric_name: str, asset_id, limit: int = 120):
    """返回某资产某指标最近 limit 条 (value, timestamp)。"""
    q = db.query(MetricRecord).filter(MetricRecord.name == metric_name)
    if asset_id is not None:
        q = q.filter(MetricRecord.asset_id == asset_id)
    rows = q.order_by(MetricRecord.timestamp.desc()).limit(limit).all()
    return [(r.value, r.timestamp) for r in reversed(rows)]


def _eval_metric_raw(rule, latest, db):
    """静态阈值: 原逻辑。支持 config_json.expression 的 AND/OR 组合条件表达式。"""
    v = latest.value
    cfg = _load_config(rule)

    # 组合条件表达式: {"and":[{"op":">","threshold":80},{"op":"<","threshold":95}]}
    expr = cfg.get("expression")
    if isinstance(expr, dict) and expr:
        result = _eval_expression(expr, v, rule)
        return result[0], v, result[1]

    cond = (rule.condition or "").strip().lower()
    if cond in (">", "gt"):
        return v > rule.threshold, v, f"{rule.metric_name} 当前值:{v} 超出阈值:{rule.threshold}"
    if cond in ("<", "lt"):
        return v < rule.threshold, v, f"{rule.metric_name} 当前值:{v} 低于阈值:{rule.threshold}"
    if cond in (">=", "gte"):
        return v >= rule.threshold, v, f"{rule.metric_name} 当前值:{v} 达到阈值:{rule.threshold}"
    if cond in ("<=", "lte"):
        return v <= rule.threshold, v, f"{rule.metric_name} 当前值:{v} 不超过阈值:{rule.threshold}"
    if cond in ("=", "==", "eq"):
        return v == rule.threshold, v, f"{rule.metric_name} 当前值:{v} 等于阈值:{rule.threshold}"
    return False, v, ""


def _eval_condition_atom(op, value, threshold) -> bool:
    """求值单个原子条件 (op: > < >= <= == != )"""
    op = (op or "").strip().lower()
    try:
        tv = float(threshold)
    except (TypeError, ValueError):
        tv = threshold
    try:
        value = float(value)
    except (TypeError, ValueError):
        pass
    if op in (">", "gt"):
        return value > tv
    if op in ("<", "lt"):
        return value < tv
    if op in (">=", "gte"):
        return value >= tv
    if op in ("<=", "lte"):
        return value <= tv
    if op in ("=", "==", "eq"):
        return value == tv
    if op in ("!=", "ne"):
        return value != tv
    return False


def _eval_expression(expr: dict, value, rule) -> tuple:
    """递归求值 AND/OR 组合表达式。返回 (triggered, message 摘要)。
    expr: {"and":[atom|expr, ...]} / {"or":[...]} / 原子 {"op","threshold"}"""
    from app.logger import logger as _lg
    atom_msgs = []
    if "and" in expr or "or" in expr:
        items = expr.get("and") or expr.get("or") or []
        op = "and" if "and" in expr else "or"
        results = []
        for it in items:
            if isinstance(it, dict) and ("and" in it or "or" in it):
                res, msg = _eval_expression(it, value, rule)
                results.append(res)
                atom_msgs.append(msg)
            elif isinstance(it, dict) and "op" in it:
                res = _eval_condition_atom(it.get("op"), value, it.get("threshold"))
                results.append(res)
                atom_msgs.append(f"{it.get('op')} {it.get('threshold')}")
            else:
                results.append(False)
                atom_msgs.append("invalid")
        if op == "and":
            triggered = all(results)
        else:
            triggered = any(results)
        summary = " AND ".join(f"[{m}]" for m in atom_msgs) if op == "and" else " OR ".join(f"[{m}]" for m in atom_msgs)
        return triggered, f"{rule.metric_name} 当前值:{value} 组合条件({summary})"
    if "op" in expr:
        res = _eval_condition_atom(expr.get("op"), value, expr.get("threshold"))
        return res, f"{rule.metric_name} 当前值:{value} {expr.get('op')} {expr.get('threshold')}"
    return False, f"{rule.metric_name} 表达式无效"


def _eval_anomaly(rule, latest, db):
    """基于均值和标准差的统计偏差: 触发阈值 = mean + z*std。"""
    import statistics
    cfg = _load_config(rule)
    z = float(cfg.get("z_score", rule.threshold if rule.threshold else 3.0))
    hist = [x for x, _ in _metric_history(db, rule.metric_name, latest.asset_id, 120)]
    if len(hist) < 5:
        return False, latest.value, "样本不足(anomaly)"
    mean = statistics.mean(hist)
    std = statistics.stdev(hist) if len(hist) > 1 else 0.0
    v = latest.value
    cond = (rule.condition or "").strip().lower()
    upper = mean + z * std
    lower = mean - z * std
    if cond in (">", "gt", ">=", "gte"):
        triggered = v >= upper
        msg = f"{rule.metric_name} 当前:{v:.2f} 超出基线均值+{z}σ:({upper:.2f})(mean={mean:.2f},std={std:.2f})"
    elif cond in ("<", "lt", "<=", "lte"):
        triggered = v <= lower
        msg = f"{rule.metric_name} 当前:{v:.2f} 低于基线均值-{z}σ:({lower:.2f})(mean={mean:.2f},std={std:.2f})"
    else:
        triggered = abs(v - mean) > z * (std or 1e-9)
        msg = f"{rule.metric_name} 当前:{v:.2f} 偏离基线 {abs(v-mean):.2f} > {z}σ"
    return bool(triggered), v, msg


def _eval_forecast(rule, latest, db):
    """线性外推预测未来 points 个点, 若投影值穿越阈值则触发。"""
    cfg = _load_config(rule)
    horizon = int(cfg.get("horizon_points", 5))
    hist = [x for x, _ in _metric_history(db, rule.metric_name, latest.asset_id, 60)]
    if len(hist) < 5:
        return False, latest.value, "样本不足(forecast)"
    xs = list(range(len(hist)))
    n = len(hist)
    sx = sum(xs); sy = sum(hist); sxx = sum(x * x for x in xs); sxy = sum(x * y for x, y in zip(xs, hist))
    denom = n * sxx - sx * sx
    if denom == 0:
        slope = 0.0
    else:
        slope = (n * sxy - sx * sy) / denom
    intercept = (sy - slope * sx) / n
    projected = [intercept + slope * (n - 1 + i) for i in range(1, horizon + 1)]
    cond = (rule.condition or "").strip().lower()
    if cond in (">", "gt", ">=", "gte"):
        triggered = any(p >= rule.threshold for p in projected)
    elif cond in ("<", "lt", "<=", "lte"):
        triggered = any(p <= rule.threshold for p in projected)
    else:
        triggered = False
    msg = f"{rule.metric_name} 预测未来{horizon}点将穿越阈值:{rule.threshold} (斜率:{slope:.4f},投影:{[round(x,2) for x in projected[:3]]}...)"
    return bool(triggered), latest.value, msg


def _eval_burn_rate(rule, latest, db):
    """燃尽率: 基于 error_rate 类指标在窗口内累计, 触发 = 燃尽率 > 阈值倍。"""
    cfg = _load_config(rule)
    window_hours = float(cfg.get("window_hours", 1))
    budget = float(cfg.get("error_budget", rule.threshold if rule.threshold else 99.0))  # 目标可用性%
    if budget <= 0 or budget >= 100:
        budget = 99.0
    error_budget_s = (100.0 - budget) / 100.0 * (window_hours * 3600)
    hist = [x for x, _ in _metric_history(db, rule.metric_name, latest.asset_id, 500)]
    # 取窗口内样本: 按最近 window_hours 的样本数近似(样本有 timestamp 但此处简化用全体)
    if not hist:
        return False, latest.value, "无样本(burn_rate)"
    errors = sum(1 for x in hist if x is not None and float(x) < 0.99)  # 视 <0.99 为失败占比样本(0/1)
    consumed = len(hist) * (100.0 - float(latest.value if latest.value is not None else 0)) / 100.0 * 1.0
    burn_rate = (consumed + 1e-9) / (error_budget_s + 1e-9)
    triggered = burn_rate > float(rule.threshold if rule.threshold else 1.0)
    msg = f"{rule.metric_name} burn_rate:{burn_rate:.3f} 预算:{budget}% 窗口:{window_hours}h (阈值倍:{rule.threshold})"
    return bool(triggered), latest.value, msg


def _eval_rule_by_kind(rule, latest, db) -> tuple:
    """按 kind 分发评估, 返回 (triggered, actual_value, message)。"""
    kind = (rule.kind or "metric_raw").strip().lower()
    if kind == "anomaly":
        return _eval_anomaly(rule, latest, db)
    if kind == "forecast":
        return _eval_forecast(rule, latest, db)
    if kind == "burn_rate":
        return _eval_burn_rate(rule, latest, db)
    return _eval_metric_raw(rule, latest, db)


# ─── A 补齐: log / trace 类规则(按 service_name / 关键字, 走 check_rules 独立分支) ──

def _eval_trace_latency(rule, db) -> tuple:
    """按 service_name 查 Span 表标量延迟(avg/p99), 触发=超阈值。"""
    cfg = _load_config(rule)
    svc = str(cfg.get("service_name") or "").strip()
    hours = float(cfg.get("hours", 1))
    window = datetime.now() - timedelta(hours=hours)
    from app.models import Span
    rows = db.query(Span).filter(Span.service_name == svc, Span.started_at >= window).all() if svc else []
    if not rows:
        return False, 0.0, f"trace_latency[{svc}] 无样本"
    durations = [float(s.duration_ms or 0) for s in rows]
    stat = cfg.get("stat", "p99")
    if stat == "avg":
        val = sum(durations) / len(durations)
    elif stat == "p50":
        sorted_d = sorted(durations); val = sorted_d[len(sorted_d) // 2]
    else:
        sorted_d = sorted(durations); val = sorted_d[int(len(sorted_d) * 0.99) - 1]
    triggered = val > rule.threshold
    return triggered, val, f"{svc} {stat}延迟:{val:.0f}ms 超阈值:{rule.threshold}ms (样本{len(rows)})"


def _eval_trace_error_rate(rule, db) -> tuple:
    """按 service_name 查 Span 错误率, 触发=超阈值(%)。"""
    cfg = _load_config(rule)
    svc = str(cfg.get("service_name") or "").strip()
    hours = float(cfg.get("hours", 1))
    window = datetime.now() - timedelta(hours=hours)
    from app.models import Span
    rows = db.query(Span).filter(Span.service_name == svc, Span.started_at >= window).all() if svc else []
    if not rows:
        return False, 0.0, f"trace_error_rate[{svc}] 无样本"
    _STATUS_OK = {"OK", "SUCCESS", "2", "0"}
    errors = sum(1 for s in rows if str(getattr(s, "status", "") or "").upper() not in _STATUS_OK)
    rate = errors / len(rows) * 100.0
    triggered = rate > rule.threshold
    return triggered, rate, f"{svc} 错误率:{rate:.2f}% 超阈值:{rule.threshold}% ({errors}/{len(rows)})"


def _count_k8s_events(db, keyword: str = "", level: str = "", hours: float = 2) -> int:
    window = datetime.now() - timedelta(hours=hours)
    q = db.query(K8sEvent)
    if hasattr(K8sEvent, "first_seen_at"):
        q = q.filter(K8sEvent.first_seen_at >= window)
    if keyword:
        q = q.filter(K8sEvent.reason.like(f"%{keyword}%"))
    if level:
        q = q.filter(K8sEvent.severity == level)
    return q.count()


def _eval_log_match(rule, db) -> tuple:
    """关键字/级别日志命中计数, 触发=超阈值。K8sEvent + 可选 ES。"""
    cfg = _load_config(rule)
    keyword = str(cfg.get("keyword") or (rule.metric_name or "")).strip()
    level = str(cfg.get("log_level") or "").strip()
    hours = float(cfg.get("hours", 2))
    threshold = rule.threshold
    count = _count_k8s_events(db, keyword=keyword if keyword != rule.metric_name else "", level=level, hours=hours)
    # 尝试 ES 聚合(幂等, 失败忽略)
    try:
        from app.services.log_anomaly_service import _count_es_logs
        es_source = cfg.get("es_source") or ""
        if es_source:
            count += _count_es_logs(db, es_source, datetime.now() - timedelta(hours=hours), level=level, keyword=keyword)
    except Exception as _exc1:
        logger.warning("[except:pass] Exception: %s", _exc1, exc_info=True)
    triggered = count >= threshold
    return triggered, count, f"日志命中[{keyword or 'all'}] {count} 条 ≥阈值{threshold} (窗口{hours}h)"


def _eval_log_volume(rule, db) -> tuple:
    """日志量突增: 近窗口 vs 前窗口的倍数, 触发=超阈值倍。"""
    cfg = _load_config(rule)
    keyword = str(cfg.get("keyword") or "").strip()
    hours = float(cfg.get("hours", 1))
    window = datetime.now() - timedelta(hours=hours)
    prev_window = window - timedelta(hours=hours)
    recent = _count_k8s_events(db, keyword=keyword, hours=hours)
    prev = K8sEvent  # placeholder to avoid unused
    try:
        from app.models import K8sEvent as _KE
        _kw = f"%{keyword}%" if keyword else "%%"
        prev = db.query(_KE).filter(_KE.first_seen_at >= prev_window, _KE.first_seen_at < window, _KE.reason.like(_kw)).count()
    except Exception:
        prev = 0
    ratio = (recent / prev) if prev > 0 else (recent if recent > 0 else 0.0)
    triggered = prev > 0 and ratio > rule.threshold
    return triggered, ratio, f"日志量 近窗口{recent} vs 前窗口{prev}, 倍数:{ratio:.2f} 超阈值:{rule.threshold}"



def check_rules(db: Session):
    rules = db.query(AlertRule).filter(AlertRule.enabled == True).all()
    now = datetime.now()
    silenced_rule_ids = {
        s.rule_id for s in db.query(AlertSilence).filter(AlertSilence.expires_at > now).all()
    }
    silenced_metric_names = set()
    schedules = db.query(AlertSilenceSchedule).filter(AlertSilenceSchedule.enabled == True).all()
    for s in schedules:
        try:
            import croniter
            cron = croniter.croniter(s.cron_expr, now)
            prev = cron.get_prev(datetime)
            if prev + timedelta(minutes=s.duration_minutes) >= now:
                if s.metric_name:
                    silenced_metric_names.add(s.metric_name)
                if s.rule_id:
                    silenced_rule_ids.add(s.rule_id)
        except Exception as _exc2:
            logger.warning("[except:pass] Exception: %s", _exc2, exc_info=True)
    now = datetime.now()
    dedup_window = timedelta(minutes=5)
    storm_window = timedelta(minutes=1)
    storm_threshold = 3

    new_alerts = []
    suppressed = []

    for rule in rules:
        if rule.id in silenced_rule_ids:
            continue

        # A 补齐: log/trace 类规则按 service_name/关键字独立评估一次(非 per-asset)
        if (rule.kind or "").strip().lower() in ("trace_latency", "trace_error_rate", "log_match", "log_volume"):
            _dispatch = {
                "trace_latency": _eval_trace_latency,
                "trace_error_rate": _eval_trace_error_rate,
                "log_match": _eval_log_match,
                "log_volume": _eval_log_volume,
            }
            try:
                triggered, actual, msg = _dispatch[rule.kind.strip().lower()](rule, db)
            except Exception as e:
                triggered, actual, msg = False, 0.0, f"{rule.kind} 评估异常: {e}"
            if triggered:
                active = db.query(Alert).filter(
                    Alert.rule_id == rule.id,
                    Alert.status.in_(["triggered", "acknowledged"]),
                ).first()
                recent_resolved = db.query(Alert).filter(
                    Alert.rule_id == rule.id,
                    Alert.status == "resolved",
                    Alert.created_at > now - dedup_window,
                ).first()
                if not active and not recent_resolved:
                    a = Alert(rule_id=rule.id, asset_id=None, metric_name=rule.metric_name,
                              actual_value=float(actual), threshold=rule.threshold,
                              severity=rule.severity, status="triggered",
                              message=f"{rule.name} - {msg}")
                    db.add(a)
                    new_alerts.append(a)
            continue

        storm_count = (
            db.query(func.count(Alert.id))
            .filter(Alert.rule_id == rule.id, Alert.created_at > now - storm_window)
            .scalar() or 0
        )
        if storm_count >= storm_threshold:
            sup = db.query(AlertSuppression).filter(
                AlertSuppression.rule_id == rule.id,
                AlertSuppression.reason == "storm",
                AlertSuppression.created_at > now - timedelta(minutes=5),
            ).first()
            if sup:
                sup.suppressed_count += 1
            else:
                db.add(AlertSuppression(rule_id=rule.id, rule_name=rule.name, metric_name=rule.metric_name, reason="storm"))
            db.commit()
            suppressed.append(rule.id)
            continue

        # 修复: 原 latest 只取全局最新一条 metric，未按 asset 区分 → 多资产时只有最新采样的资产会被检查
        # 改为按资产分组取各自最新值，逐资产判断是否触发
        latest_rows = (
            db.query(MetricRecord)
            .filter(MetricRecord.name == rule.metric_name)
            .order_by(MetricRecord.timestamp.desc())
            .limit(50)
            .all()
        )
        # 按 asset_id 去重，保留每个资产最新一条
        seen_assets = set()
        latest_per_asset = []
        for lr in latest_rows:
            if lr.asset_id in seen_assets:
                continue
            seen_assets.add(lr.asset_id)
            latest_per_asset.append(lr)
        # 跳过已离线资产（但 svc_up 指标例外：离线=0 是有效告警信号）
        _skip_asset_ids = set(
            a.id for a in db.query(Asset).filter(Asset.status == "offline").all()
        ) if latest_per_asset else set()
        # 也跳过维护/退役状态的资产
        from app.models import AssetLifecycle
        _lifecycle_skip = set(
            lc.asset_id for lc in db.query(AssetLifecycle).filter(
                AssetLifecycle.status.in_(["maintenance", "decommissioned", "retired"])
            ).all()
        )
        _skip_asset_ids.update(_lifecycle_skip)
        for latest in latest_per_asset:
            if not latest:
                continue
            if latest.asset_id in _skip_asset_ids and latest.name != "svc_up":
                continue
            triggered, actual_value, eval_msg = _eval_rule_by_kind(rule, latest, db)
            if triggered:
                active = (
                    db.query(Alert)
                    .filter(
                        Alert.rule_id == rule.id,
                        Alert.asset_id == latest.asset_id,
                        Alert.status.in_(["triggered", "acknowledged"]),
                    )
                    .first()
                )
                recent_resolved = (
                    db.query(Alert)
                    .filter(
                        Alert.rule_id == rule.id,
                        Alert.asset_id == latest.asset_id,
                        Alert.status == "resolved",
                        Alert.created_at > now - dedup_window,
                    )
                    .first()
                )
                # svc_up 单例去重：同一资产+规则已有活跃告警时不重复写入，仅刷新 last_notified_at
                if rule.metric_name == "svc_up" and latest.value < rule.threshold:
                    if active:
                        active.last_notified_at = now
                        db.commit()
                        continue
                    elif not active and not recent_resolved:
                        alert = Alert(
                            rule_id=rule.id,
                            asset_id=latest.asset_id,
                            metric_name=rule.metric_name,
                            actual_value=actual_value,
                            threshold=rule.threshold,
                            severity=rule.severity,
                            status="triggered",
                            message=f"{rule.name} - {rule.metric_name} 当前值:{actual_value} 超出阈值:{rule.threshold}",
                        )
                        db.add(alert)
                        new_alerts.append(alert)
                    elif not active and recent_resolved:
                        sup = db.query(AlertSuppression).filter(
                            AlertSuppression.rule_id == rule.id,
                            AlertSuppression.reason == "dedup",
                            AlertSuppression.created_at > now - timedelta(hours=1),
                        ).first()
                        if sup:
                            sup.suppressed_count += 1
                        else:
                            db.add(AlertSuppression(rule_id=rule.id, rule_name=rule.name, metric_name=rule.metric_name, reason="dedup"))
                        db.commit()
                    continue
                elif not active and not recent_resolved:
                    alert = Alert(
                        rule_id=rule.id,
                        asset_id=latest.asset_id,
                        metric_name=rule.metric_name,
                        actual_value=actual_value,
                        threshold=rule.threshold,
                        severity=rule.severity,
                        status="triggered",
                        message=f"{rule.name} - {eval_msg}",
                    )
                    db.add(alert)
                    new_alerts.append(alert)
                elif not active and recent_resolved:
                    sup = db.query(AlertSuppression).filter(
                        AlertSuppression.rule_id == rule.id,
                        AlertSuppression.reason == "dedup",
                        AlertSuppression.created_at > now - timedelta(hours=1),
                    ).first()
                    if sup:
                        sup.suppressed_count += 1
                    else:
                        db.add(AlertSuppression(rule_id=rule.id, rule_name=rule.name, metric_name=rule.metric_name, reason="dedup"))
                    db.commit()
    if new_alerts:
        db.commit()
        for a in new_alerts:
            db.refresh(a)
        notification_service.notify_new_alerts(db, new_alerts)
        try:
            from app.routers.alert_webhooks import call_alert_webhooks
            for a in new_alerts:
                call_alert_webhooks(db, a)
        except Exception as _exc3:
            logger.warning("[except:pass] Exception: %s", _exc3, exc_info=True)
        try:
            _ws_publish_async([_serialize_alert(a) for a in new_alerts])
        except Exception as _exc4:
            logger.warning("[except:pass] Exception: %s", _exc4, exc_info=True)
    return new_alerts


def get_alert_detail(db: Session, alert_id: int):
    from app.models import Asset
    from app.services.knowledge_graph_service import recommend_kb_for_alert
    alert = db.query(Alert).filter(Alert.id == alert_id).first()
    if not alert:
        return None
    asset = db.query(Asset).filter(Asset.id == alert.asset_id).first()
    recommendations = recommend_kb_for_alert(db, alert)
    escalations = get_escalations_for_alert(db, alert_id)
    return {
        "alert": alert,
        "asset": asset,
        "notification_logs": notification_service.get_notification_logs_for_alert(db, alert_id),
        "recommendations": recommendations,
        "escalations": escalations,
    }


def list_alerts(db: Session, status: str = "", severity: str = "", page: int = 1, per_page: int = 20):
    q = db.query(Alert).filter(Alert.archived == False)
    if status:
        q = q.filter(Alert.status == status)
    if severity:
        q = q.filter(Alert.severity == severity)
    q = q.order_by(Alert.created_at.desc())
    total = q.count()
    alerts = q.offset((page - 1) * per_page).limit(per_page).all()
    return alerts, total


def acknowledge_alert(db: Session, alert_id: int):
    alert = db.query(Alert).filter(Alert.id == alert_id).first()
    if not alert:
        return None
    alert.status = "acknowledged"
    alert.acknowledged_at = datetime.now()
    db.commit()
    db.refresh(alert)
    return alert


def resolve_alert(db: Session, alert_id: int):
    alert = db.query(Alert).filter(Alert.id == alert_id).first()
    if not alert:
        return None
    alert.status = "resolved"
    alert.resolved_at = datetime.now()
    db.commit()
    db.refresh(alert)
    _auto_resolve_incident_for_alert(db, alert_id)
    return alert


def _auto_resolve_incident_for_alert(db: Session, alert_id: int):
    from app.models import IncidentAlert, Incident
    link = db.query(IncidentAlert).filter(IncidentAlert.alert_id == alert_id).first()
    if not link:
        return
    inc = db.query(Incident).filter(Incident.id == link.incident_id, Incident.status == "open").first()
    if not inc:
        return
    linked_alert_ids = [la.alert_id for la in db.query(IncidentAlert).filter(IncidentAlert.incident_id == inc.id).all()]
    if not linked_alert_ids:
        return
    unresolved = db.query(Alert).filter(Alert.id.in_(linked_alert_ids), Alert.status.in_(["triggered", "acknowledged"])).count()
    if unresolved == 0:
        inc.status = "resolved"
        inc.resolved_at = datetime.now()
        db.commit()


def get_alert_stats(db: Session):
    total = db.query(func.count(Alert.id)).scalar() or 0
    triggered = db.query(func.count(Alert.id)).filter(Alert.status == "triggered").scalar() or 0
    acknowledged = db.query(func.count(Alert.id)).filter(Alert.status == "acknowledged").scalar() or 0
    resolved = db.query(func.count(Alert.id)).filter(Alert.status == "resolved").scalar() or 0
    suppressed_total = db.query(func.sum(AlertSuppression.suppressed_count)).scalar() or 0
    storm_suppressed = (
        db.query(func.sum(AlertSuppression.suppressed_count))
        .filter(AlertSuppression.reason == "storm")
        .scalar() or 0
    )
    dedup_suppressed = (
        db.query(func.sum(AlertSuppression.suppressed_count))
        .filter(AlertSuppression.reason == "dedup")
        .scalar() or 0
    )
    return {
        "total": total, "triggered": triggered,
        "acknowledged": acknowledged, "resolved": resolved,
        "suppressed_total": suppressed_total,
        "storm_suppressed": storm_suppressed,
        "dedup_suppressed": dedup_suppressed,
    }


def get_suppressions(db: Session, limit: int = 50):
    return db.query(AlertSuppression).order_by(AlertSuppression.created_at.desc()).limit(limit).all()


def batch_acknowledge(db: Session):
    alerts = db.query(Alert).filter(Alert.status == "triggered").all()
    now = datetime.now()
    for a in alerts:
        a.status = "acknowledged"
        a.acknowledged_at = now
    db.commit()
    return len(alerts)


def batch_resolve(db: Session):
    alerts = db.query(Alert).filter(Alert.status.in_(["triggered", "acknowledged"])).all()
    now = datetime.now()
    for a in alerts:
        a.status = "resolved"
        a.resolved_at = now
    db.commit()
    for a in alerts:
        _auto_resolve_incident_for_alert(db, a.id)
    return len(alerts)


def get_escalation_minutes(db: Session) -> int:
    cfg = db.query(SystemConfig).filter(SystemConfig.key == "escalation_minutes").first()
    try:
        return int(cfg.config_value) if cfg else 5
    except (ValueError, TypeError):
        return 5


def escalate_alerts(db: Session):
    escalation_minutes = get_escalation_minutes(db)
    now = datetime.now()
    cutoff = now - timedelta(minutes=escalation_minutes)
    old_alerts = (
        db.query(Alert)
        .filter(Alert.status == "triggered", Alert.created_at < cutoff)
        .all()
    )
    promoted = 0
    for a in old_alerts:
        original = a.severity
        if a.severity == "info":
            a.severity = "warning"
        elif a.severity == "warning":
            a.severity = "critical"
        if a.severity != original:
            escalation = AlertEscalation(
                alert_id=a.id,
                from_severity=original,
                to_severity=a.severity,
                reason=f"超时{escalation_minutes}分钟未处理，自动升级",
            )
            db.add(escalation)
            a.message += f" [已升级:{a.severity}]"
            promoted += 1
            _send_escalation_notification(db, a, original)
    if promoted:
        db.commit()
    return promoted


def _send_escalation_notification(db: Session, alert: Alert, from_severity: str):
    from app.services.notification_service import send_notification
    try:
        channels = db.query(NotificationChannel).filter(
            NotificationChannel.enabled == True,
        ).all()
        for ch in channels:
            if alert.severity in (ch.severity or "").split(",") or not ch.severity:
                send_notification(db, alert, ch)
    except Exception as _exc5:
        logger.warning("[except:pass] Exception: %s", _exc5, exc_info=True)


def get_escalations_for_alert(db: Session, alert_id: int):
    return db.query(AlertEscalation).filter(AlertEscalation.alert_id == alert_id).order_by(AlertEscalation.created_at).all()


def is_in_silence_window(db: Session, alert: Alert) -> bool:
    from datetime import datetime, timedelta
    now = datetime.now()
    schedules = db.query(AlertSilenceSchedule).filter(AlertSilenceSchedule.enabled == True).all()
    for s in schedules:
        rule_match = (s.rule_id is None or s.rule_id == alert.rule_id)
        metric_match = (s.metric_name == "" or s.metric_name == alert.metric_name)
        if not rule_match or not metric_match:
            continue
        try:
            import croniter
            cron = croniter.croniter(s.cron_expr, now)
            prev = cron.get_prev(datetime)
            if prev + timedelta(minutes=s.duration_minutes) >= now:
                return True
        except Exception as _exc6:
            logger.warning("[except:pass] Exception: %s", _exc6, exc_info=True)
    return False


# ─── K8S Event 告警检测 ───

_K8S_EVENT_ALERT_MAP = {
    "OOMKilling": "critical",
    "OOMKilled": "critical",
    "CrashLoopBackOff": "critical",
    "BackOff": "warning",
    "FailedScheduling": "warning",
    "NodeNotReady": "critical",
    "NodeUnreachable": "critical",
    "Evicted": "warning",
    "FailedMount": "warning",
    "FailedAttachVolume": "warning",
    "Unhealthy": "warning",
    "FailedSync": "warning",
    "FailedCreate": "warning",
    "ImagePullBackOff": "critical",
    "ErrImagePull": "critical",
    "FailedPreStopHook": "warning",
    "DNSConfigForming": "warning",
}


def check_k8s_events(db: Session, window_minutes: int = 30):
    """扫描 K8S Event 表，将严重事件（OOM/CrashLoopBackOff/NodeNotReady 等）自动转为告警。
    window_minutes: 扫描时间窗口（分钟），手动触发时可传更大的值扫描历史事件
    """
    from app.models import K8sEvent, Asset, Alert
    now = datetime.now()
    since = now - timedelta(minutes=window_minutes)
    events = db.query(K8sEvent).filter(
        K8sEvent.severity.in_(["warning", "critical"]),
        K8sEvent.last_seen_at >= since,
    ).order_by(K8sEvent.last_seen_at.desc()).all()

    new_alerts = []
    skipped = 0
    for ev in events:
        severity = _K8S_EVENT_ALERT_MAP.get(ev.reason, "")
        if not severity:
            reason_lower = (ev.reason or "").lower()
            if "oom" in reason_lower:
                severity = "critical"
            elif "crash" in reason_lower:
                severity = "critical"
            elif "fail" in reason_lower:
                severity = "warning"
            elif "notready" in reason_lower or "unreachable" in reason_lower:
                severity = "critical"
            else:
                continue

        asset = None
        if ev.name:
            asset = db.query(Asset).filter(Asset.name.ilike(f"%{ev.name}%")).first()
            if not asset and ev.cluster:
                asset = db.query(Asset).filter(
                    Asset.name.ilike(f"%{ev.cluster}%"),
                    Asset.ci_type == "kubernetes_cluster",
                ).first()

        existing = db.query(Alert).filter(
            Alert.asset_id == (asset.id if asset else None),
            Alert.metric_name == f"k8s_event_{ev.reason}",
            Alert.created_at >= since,
            Alert.status.in_(["triggered", "acknowledged"]),
        ).first()
        if existing:
            skipped += 1
            continue

        alert = Alert(
            asset_id=asset.id if asset else None,
            metric_name=f"k8s_event_{ev.reason}",
            actual_value=float(ev.count or 1),
            threshold=1.0,
            severity=severity,
            status="triggered",
            message=f"[K8S] {ev.reason} | {ev.kind or ''} {ev.name or ''} | ns: {ev.namespace or '-'} | {ev.message[:200] if ev.message else ''}",
        )
        db.add(alert)
        new_alerts.append(alert)

    if new_alerts:
        db.commit()
        for a in new_alerts:
            db.refresh(a)
        try:
            notification_service.notify_new_alerts(db, new_alerts)
        except Exception as _exc7:
            logger.warning("[except:pass] Exception: %s", _exc7, exc_info=True)

    return new_alerts, skipped, len(events)


ARCHIVE_DAYS = 60  # 已解决告警超过此天数自动归档


def archive_old_alerts(db: Session) -> dict:
    """归档超保留期的已解决告警。返回 {"archived": count}。"""
    cutoff = datetime.now() - timedelta(days=ARCHIVE_DAYS)
    old = (
        db.query(Alert)
        .filter(Alert.status == "resolved", Alert.created_at < cutoff, Alert.archived == False)
        .all()
    )
    count = len(old)
    for a in old:
        a.archived = True
    if count:
        db.commit()
    return {"archived": count}
