import json
from datetime import datetime, timedelta

from sqlalchemy.orm import Session
from sqlalchemy import func

from app.models import Alert, Report, Asset, Incident


def _severity_label(s):
    mapping = {"critical": "严重", "warning": "警告", "info": "提示"}
    return mapping.get(s, s or "未知")


def _status_label(s):
    mapping = {"triggered": "已触发", "acknowledged": "已确认", "resolved": "已解决"}
    return mapping.get(s, s or "未知")


def _period_label(t):
    labels = {"daily": "日报", "weekly": "周报", "monthly": "月报"}
    return labels.get(t, "报表")


def generate_report(db: Session, report_type: str) -> Report:
    now = datetime.now()
    if report_type == "daily":
        period_start = now - timedelta(days=1)
        days = 1
    elif report_type == "weekly":
        period_start = now - timedelta(days=7)
        days = 7
    elif report_type == "monthly":
        period_start = now - timedelta(days=30)
        days = 30
    else:
        report_type = "daily"
        period_start = now - timedelta(days=1)
        days = 1

    title = f"{_period_label(report_type)} - {now.strftime('%Y-%m-%d')}"

    # ── 告警统计（查全部告警，因为演示数据可能不在报告周期内） ──
    alerts = db.query(Alert).all()
    total_alerts = len(alerts)
    by_severity = {}
    by_status = {}
    by_rule = {}
    by_asset = {}
    for a in alerts:
        by_severity[a.severity] = by_severity.get(a.severity, 0) + 1
        by_status[a.status] = by_status.get(a.status, 0) + 1
        rule_key = a.metric_name or "未知指标"
        by_rule[rule_key] = by_rule.get(rule_key, 0) + 1
        if a.asset_id:
            by_asset[a.asset_id] = by_asset.get(a.asset_id, 0) + 1

    critical_count = by_severity.get("critical", 0)
    warning_count = by_severity.get("warning", 0)
    info_count = by_severity.get("info", 0)
    resolved_count = by_status.get("resolved", 0)
    pending_count = by_status.get("triggered", 0) + by_status.get("acknowledged", 0)
    resolve_rate = round(resolved_count / total_alerts * 100, 1) if total_alerts else 0

    top_rules = sorted(by_rule.items(), key=lambda x: -x[1])[:8]

    # ── 资产统计 ──
    asset_count = db.query(func.count(Asset.id)).scalar() or 0
    online_count = db.query(func.count(Asset.id)).filter(Asset.status == "online").scalar() or 0
    offline_count = db.query(func.count(Asset.id)).filter(Asset.status == "offline").scalar() or 0
    asset_health = round(online_count / asset_count * 100, 1) if asset_count else 0

    # ── 事件统计（查全部事件，不分时间窗口，因为事件可能跨越多个报告周期） ──
    incidents = db.query(Incident).all()
    total_incidents = len(incidents)
    open_incidents = sum(1 for i in incidents if i.status in ("open", "analyzing", "triggered", "active"))
    resolved_incidents = sum(1 for i in incidents if i.status in ("resolved", "closed", "done"))

    # ── 最活跃的告警资产 Top5 ──
    top_assets = []
    if by_asset:
        asset_ids = sorted(by_asset.items(), key=lambda x: -x[1])[:8]
        aid_set = set(aid for aid, _ in asset_ids)
        asset_map = {a.id: a.name for a in db.query(Asset).filter(Asset.id.in_(aid_set)).all()} if aid_set else {}
        for aid, cnt in asset_ids:
            top_assets.append({"name": asset_map.get(aid, f"资产#{aid}"), "count": cnt})

    # ── 生成专业摘要 ──
    lines = []
    lines.append(f"═══ {_period_label(report_type)}概要 ═══")
    lines.append(f"报告周期：{period_start.strftime('%Y-%m-%d %H:%M')} 至 {now.strftime('%Y-%m-%d %H:%M')}（{days} 天）")
    lines.append(f"生成时间：{now.strftime('%Y-%m-%d %H:%M:%S')}")
    lines.append("")

    lines.append("【告警概览】")
    lines.append(f"  告警总数：{total_alerts} 条")
    lines.append(f"  按级别分布：严重 {critical_count} 条 / 警告 {warning_count} 条 / 提示 {info_count} 条")
    lines.append(f"  处理状态：已解决 {resolved_count} 条 / 待处理 {pending_count} 条")
    lines.append(f"  告警解决率：{resolve_rate}%")
    lines.append("")

    if top_rules:
        lines.append("【高频告警指标 TOP 8】")
        for i, (rule, cnt) in enumerate(top_rules[:8], 1):
            lines.append(f"  {i}. {rule} — {cnt} 次")
        lines.append("")

    if top_assets:
        lines.append("【告警最多的资产 TOP 8】")
        for i, a in enumerate(top_assets, 1):
            lines.append(f"  {i}. {a['name']} — {a['count']} 次告警")
        lines.append("")

    lines.append("【资产概览】")
    lines.append(f"  资产总数：{asset_count} 台")
    lines.append(f"  在线：{online_count} 台 / 离线：{offline_count} 台")
    lines.append(f"  资产在线率：{asset_health}%")
    lines.append("")

    lines.append("【事件概览】")
    lines.append(f"  事件总数：{total_incidents} 个")
    lines.append(f"  未关闭：{open_incidents} 个 / 已关闭：{resolved_incidents} 个")
    lines.append("")

    lines.append("【评估与建议】")
    if total_alerts == 0:
        lines.append("  本周期内系统运行平稳，无告警产生。建议继续保持日常监控。")
    else:
        if critical_count > 0:
            lines.append(f"  ⚠ 本周期有 {critical_count} 条严重告警，建议优先排查并复盘处理流程。")
        if resolve_rate < 80:
            lines.append(f"  ⚠ 告警解决率 {resolve_rate}% 低于 80%，建议增加运维人力或优化自愈规则。")
        if top_rules:
            lines.append(f"  ⚠ 指标「{top_rules[0][0]}」告警频次最高（{top_rules[0][1]} 次），建议关注相关资产健康度。")
        if resolve_rate >= 80 and critical_count == 0:
            lines.append("  ✓ 系统整体运行状况良好，告警处理及时，继续保持。")

    summary = "\n".join(lines)

    data = json.dumps({
        "total_alerts": total_alerts,
        "critical_count": critical_count,
        "warning_count": warning_count,
        "info_count": info_count,
        "resolved_count": resolved_count,
        "pending_count": pending_count,
        "resolve_rate": resolve_rate,
        "by_severity": {_severity_label(k): v for k, v in by_severity.items()},
        "by_status": {_status_label(k): v for k, v in by_status.items()},
        "top_rules": top_rules,
        "asset_count": asset_count,
        "online_count": online_count,
        "offline_count": offline_count,
        "asset_health": asset_health,
        "total_incidents": total_incidents,
        "open_incidents": open_incidents,
        "resolved_incidents": resolved_incidents,
        "top_assets": top_assets,
    }, ensure_ascii=False)

    report = Report(
        title=title, type=report_type,
        period_started_at=period_start, period_ended_at=now,
        summary=summary, report_data=data,
    )
    db.add(report)
    db.commit()
    db.refresh(report)
    return report


def list_reports(db: Session, limit: int = 50):
    return db.query(Report).order_by(Report.created_at.desc()).limit(limit).all()


def get_report(db: Session, report_id: int):
    return db.query(Report).filter(Report.id == report_id).first()
