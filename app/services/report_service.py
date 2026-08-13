import json
import logging
from datetime import datetime, timedelta
from collections import defaultdict

from sqlalchemy.orm import Session
from sqlalchemy import func

from app.models import Alert, Report, Asset, Incident, AIProvider, AgentConfig
from app.services.ai_provider_health import select_healthy_provider
from app.services.agent_service import call_llm

logger = logging.getLogger(__name__)


def _severity_label(s):
    mapping = {"critical": "严重", "warning": "警告", "info": "提示"}
    return mapping.get(s, s or "未知")


def _status_label(s):
    mapping = {"triggered": "已触发", "acknowledged": "已确认", "resolved": "已解决"}
    return mapping.get(s, s or "未知")


def _period_label(t):
    labels = {"daily": "日报", "weekly": "周报", "monthly": "月报"}
    return labels.get(t, "报表")


def _get_provider(db: Session):
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


def _generate_ai_summary(period_label, stats, prev_stats, trend_data, db):
    provider = _get_provider(db)
    if not provider:
        return None

    top_rules_str = "\n".join(
        f"  {i+1}. {r} — {c} 次" for i, (r, c) in enumerate(stats.get("top_rules", [])[:5])
    ) if stats.get("top_rules") else "  无"
    top_assets_str = "\n".join(
        f"  {i+1}. {a['name']} — {a['count']} 次告警" for i, a in enumerate(stats.get("top_assets", [])[:5])
    ) if stats.get("top_assets") else "  无"

    prev_alerts = prev_stats.get("total_alerts", 0) if prev_stats else 0
    alert_change = ""
    if prev_alerts > 0:
        diff = stats["total_alerts"] - prev_alerts
        pct = round(diff / prev_alerts * 100, 1)
        arrow = "↑" if diff > 0 else "↓"
        alert_change = f"（环比 {arrow} {abs(pct)}%，{abs(diff)} 条）"

    prompt = f"""你是一位专业的运维负责人，请根据以下 {period_label} 运营数据，撰写一份专业的评估总结。

报告周期：{stats.get('period_label', '')}
时间范围：{stats.get('period_start', '')} ~ {stats.get('period_end', '')}

【告警概况】
告警总数：{stats['total_alerts']} 条 {alert_change}
严重：{stats['critical_count']} 条 / 警告：{stats['warning_count']} 条 / 提示：{stats['info_count']} 条
已解决：{stats['resolved_count']} 条 / 待处理：{stats['pending_count']} 条
解决率：{stats['resolve_rate']}%

【高频告警指标 TOP 5】
{top_rules_str}

【告警最多资产 TOP 5】
{top_assets_str}

【资产概况】
资产总数：{stats['asset_count']} 台 / 在线率：{stats['asset_health']}%
事件总数：{stats['total_incidents']} 个 / 未关闭：{stats['open_incidents']} 个

请输出：
1. 一句话总结本周期整体运维状况（好/一般/差）
2. 核心风险点（基于告警数据和资产状态）
3. 改进建议（2-3 条，具体可执行）
4. 总体评价（A/B/C/D）

格式简洁，不要多余开场白。"""

    try:
        resp = call_llm(provider, [{"role": "user", "content": prompt}], timeout_override=30)
        if resp and isinstance(resp, dict) and resp.get("content"):
            return resp["content"].strip()
    except Exception as e:
        logger.warning("AI 摘要生成失败: %s", e)
    return None


def _rule_based_summary(stats, period_label):
    lines = []
    lines.append(f"【告警概览】{stats['total_alerts']} 条（严重 {stats['critical_count']} / 警告 {stats['warning_count']} / 提示 {stats['info_count']}），解决率 {stats['resolve_rate']}%")
    if stats.get("prev_alerts") is not None and stats["prev_alerts"] > 0:
        diff = stats["total_alerts"] - stats["prev_alerts"]
        pct = round(diff / stats["prev_alerts"] * 100, 1) if stats["prev_alerts"] else 0
        arrow = "↑" if diff > 0 else "↓"
        lines.append(f"  【环比】上周期告警 {stats['prev_alerts']} 条，本期 {stats['total_alerts']} 条（{arrow}{abs(pct)}%）")
    if stats["critical_count"] > 0:
        lines.append(f"  ⚠ 本周期有 {stats['critical_count']} 条严重告警，建议优先排查并复盘处理流程。")
    if stats["resolve_rate"] < 80:
        lines.append(f"  ⚠ 告警解决率 {stats['resolve_rate']}% 低于 80%，建议增加运维人力或优化自愈规则。")
    if stats["top_rules"]:
        lines.append(f"  ⚠ 指标「{stats['top_rules'][0][0]}」告警频次最高（{stats['top_rules'][0][1]} 次），建议关注相关资产健康度。")
    if stats["resolve_rate"] >= 80 and stats["critical_count"] == 0:
        lines.append(f"  ✓ 系统整体运行状况良好，告警处理及时，继续保持。")
    return "\n".join(lines)


def _build_alert_trend(db, period_start, now):
    days = (now - period_start).days + 1
    if days < 1:
        days = 1
    trend = []
    for i in range(days):
        day_start = period_start + timedelta(days=i)
        day_end = day_start + timedelta(days=1)
        cnt = db.query(func.count(Alert.id)).filter(
            Alert.created_at >= day_start, Alert.created_at < day_end
        ).scalar() or 0
        trend.append({"date": day_start.strftime("%m-%d"), "count": cnt})
    return trend


def generate_report(db: Session, report_type: str) -> Report:
    now = datetime.now()
    if report_type == "daily":
        period_start = now - timedelta(days=1)
        prev_period_start = now - timedelta(days=2)
        days = 1
    elif report_type == "weekly":
        period_start = now - timedelta(days=7)
        prev_period_start = now - timedelta(days=14)
        days = 7
    elif report_type == "monthly":
        period_start = now - timedelta(days=30)
        prev_period_start = now - timedelta(days=60)
        days = 30
    else:
        report_type = "daily"
        period_start = now - timedelta(days=1)
        prev_period_start = now - timedelta(days=2)
        days = 1

    title = f"{_period_label(report_type)} - {now.strftime('%Y-%m-%d')}"

    # ── 本期告警统计 ──
    alerts = db.query(Alert).filter(
        Alert.created_at >= period_start, Alert.created_at <= now
    ).all()
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

    # ── 处置效率指标（MTTR / 最长处置） ──
    resolve_times = []
    for a in alerts:
        if a.status == "resolved" and a.resolved_at and a.created_at:
            try:
                dt = a.resolved_at - a.created_at
                resolve_times.append(dt.total_seconds() / 60)
            except (TypeError, ValueError):
                continue
    avg_resolve_minutes = round(sum(resolve_times) / len(resolve_times), 1) if resolve_times else 0
    max_resolve_minutes = round(max(resolve_times), 1) if resolve_times else 0

    top_rules = sorted(by_rule.items(), key=lambda x: -x[1])[:8]

    # ── 上周期告警统计（环比） ──
    prev_alerts = db.query(Alert).filter(
        Alert.created_at >= prev_period_start, Alert.created_at < period_start
    ).all()
    prev_total = len(prev_alerts)
    prev_resolved = sum(1 for a in prev_alerts if a.status == "resolved")
    prev_resolve_rate = round(prev_resolved / prev_total * 100, 1) if prev_total else 0

    # ── 告警趋势（每日分布） ──
    trend_data = _build_alert_trend(db, period_start, now)

    # ── 资产统计 ──
    asset_count = db.query(func.count(Asset.id)).scalar() or 0
    online_count = db.query(func.count(Asset.id)).filter(Asset.status == "online").scalar() or 0
    offline_count = db.query(func.count(Asset.id)).filter(Asset.status == "offline").scalar() or 0
    asset_health = round(online_count / asset_count * 100, 1) if asset_count else 0

    # ── 事件统计 ──
    incidents = db.query(Incident).filter(
        Incident.created_at >= period_start, Incident.created_at <= now
    ).order_by(Incident.created_at.desc()).all()
    total_incidents = len(incidents)
    open_incidents = sum(1 for i in incidents if i.status in ("open", "analyzing", "triggered", "active"))
    resolved_incidents = sum(1 for i in incidents if i.status in ("resolved", "closed", "done"))

    # 事件明细（标题/级别/状态/影响/时间）
    incident_details = []
    for inc in incidents[:20]:
        incident_details.append({
            "id": inc.id,
            "title": inc.title,
            "severity": inc.severity,
            "status": inc.status,
            "impact": inc.impact,
            "alert_count": inc.alert_count,
            "created_at": inc.created_at.strftime("%m-%d %H:%M") if inc.created_at else "",
            "resolved_at": inc.resolved_at.strftime("%m-%d %H:%M") if inc.resolved_at else "",
            "description": (inc.description or "")[:80],
        })

    # ── 最活跃的告警资产 Top8 ──
    top_assets = []
    if by_asset:
        asset_ids = sorted(by_asset.items(), key=lambda x: -x[1])[:8]
        aid_set = set(aid for aid, _ in asset_ids)
        asset_map = {a.id: a.name for a in db.query(Asset).filter(Asset.id.in_(aid_set)).all()} if aid_set else {}
        for aid, cnt in asset_ids:
            top_assets.append({"name": asset_map.get(aid, f"资产#{aid}"), "count": cnt})

    stats = {
        "total_alerts": total_alerts,
        "critical_count": critical_count,
        "warning_count": warning_count,
        "info_count": info_count,
        "resolved_count": resolved_count,
        "pending_count": pending_count,
        "resolve_rate": resolve_rate,
        "avg_resolve_minutes": avg_resolve_minutes,
        "max_resolve_minutes": max_resolve_minutes,
        "by_severity": {_severity_label(k): v for k, v in by_severity.items()},
        "by_status": {_status_label(k): v for k, v in by_status.items()},
        "top_rules": top_rules,
        "top_assets": top_assets,
        "asset_count": asset_count,
        "online_count": online_count,
        "offline_count": offline_count,
        "asset_health": asset_health,
        "total_incidents": total_incidents,
        "open_incidents": open_incidents,
        "resolved_incidents": resolved_incidents,
        "incident_details": incident_details,
        "trend": trend_data,
        "prev_total_alerts": prev_total,
        "prev_resolve_rate": prev_resolve_rate,
        "period_label": _period_label(report_type),
        "period_start": period_start.strftime("%Y-%m-%d %H:%M"),
        "period_end": now.strftime("%Y-%m-%d %H:%M"),
    }

    # ── AI 摘要（有 provider 则用 AI，否则规则引擎） ──
    ai_summary = _generate_ai_summary(_period_label(report_type), stats,
                                       {"total_alerts": prev_total} if prev_total else None,
                                       trend_data, db)
    if ai_summary:
        full_summary = f"═══ {_period_label(report_type)}概要 ═══\n报告周期：{period_start.strftime('%Y-%m-%d %H:%M')} 至 {now.strftime('%Y-%m-%d %H:%M')}（{days} 天）\n\n【AI 评估摘要】\n{ai_summary}\n\n"
    else:
        full_summary = ""

    rule_summary = _rule_based_summary({**stats, "prev_alerts": prev_total}, _period_label(report_type))
    full_summary += rule_summary

    data = json.dumps(stats, ensure_ascii=False, default=str)

    report = Report(
        title=title, type=report_type,
        period_started_at=period_start, period_ended_at=now,
        summary=full_summary, report_data=data,
    )
    db.add(report)
    db.commit()
    db.refresh(report)
    return report


def list_reports(db: Session, limit: int = 50):
    return db.query(Report).order_by(Report.created_at.desc()).limit(limit).all()


def get_report(db: Session, report_id: int):
    return db.query(Report).filter(Report.id == report_id).first()


def delete_report(db: Session, report_id: int) -> bool:
    report = db.query(Report).filter(Report.id == report_id).first()
    if not report:
        return False
    db.delete(report)
    db.commit()
    return True


def _render_incidents_html(incidents):
    if not incidents:
        return ""
    groups = {}
    for inc in incidents:
        title = inc.get("title", "")
        import re
        m = re.search(r'\]\s*(.+?)\s*(异常|故障|告警|down|宕机)', title)
        asset = m.group(1).strip() if m else title
        if asset not in groups:
            groups[asset] = {"items": [], "total_alerts": 0, "severity": inc.get("severity", "info"), "status": "open"}
        groups[asset]["items"].append(inc)
        groups[asset]["total_alerts"] += inc.get("alert_count", 1)
        if inc.get("severity") == "critical":
            groups[asset]["severity"] = "critical"
        if inc.get("status") in ("resolved", "closed", "done"):
            groups[asset]["status"] = "resolved"

    rows = []
    for asset, g in sorted(groups.items(), key=lambda x: -x[1]["total_alerts"]):
        sev_cls = {"critical": "sev-critical", "warning": "sev-warning", "info": "sev-info"}.get(g["severity"], "sev-info")
        sta_cls = {"open": "sta-open", "resolved": "sta-resolved"}.get(g["status"], "sta-open")
        sev_label = {"critical": "严重", "warning": "警告", "info": "提示"}.get(g["severity"], g["severity"])
        sta_label = {"open": "待处理", "resolved": "已解决"}.get(g["status"], g["status"])
        latest = g["items"][0]
        rows.append(f'<tr class="inc-{g["severity"]}">'
                    f'<td>{asset}</td>'
                    f'<td><span class="sev-badge {sev_cls}">{sev_label}</span></td>'
                    f'<td><span class="sta-badge {sta_cls}">{sta_label}</span></td>'
                    f'<td>{g["total_alerts"]}</td>'
                    f'<td>{latest.get("created_at","")}</td></tr>')
    total = len(groups)
    return f'<div class="section"><h3>受影响资产（{total} 个）</h3><table class="inc-table"><thead><tr><th>资产</th><th>级别</th><th>状态</th><th>关联告警数</th><th>最近时间</th></tr></thead><tbody>{"".join(rows)}</tbody></table></div>'


def render_report_html(report: Report) -> str:
    data = {}
    if report.report_data:
        try:
            data = json.loads(report.report_data)
        except (json.JSONDecodeError, TypeError):
            data = {}

    trend_chart_labels = json.dumps([d["date"] for d in data.get("trend", [])])
    trend_chart_values = json.dumps([d["count"] for d in data.get("trend", [])])

    sev = data.get("by_severity", {})
    sev_labels = json.dumps(list(sev.keys()))
    sev_values = json.dumps(list(sev.values()))

    top_rules = data.get("top_rules", [])
    top_assets = data.get("top_assets", [])

    prev_total = data.get("prev_total_alerts", 0)
    diff_html = ""
    if prev_total and data.get("total_alerts", 0) is not None:
        diff = data["total_alerts"] - prev_total
        pct = round(abs(diff) / prev_total * 100, 1) if prev_total else 0
        arrow = "&#9650;" if diff > 0 else "&#9660;"
        color = "#ef4444" if diff > 0 else "#22c55e"
        diff_html = f'<span style="color:{color};font-weight:600;">环比 {arrow} {pct}%（{abs(diff)} 条）</span>'

    return f"""<!DOCTYPE html>
<html lang="zh-CN">
<head><meta charset="UTF-8"><title>{report.title}</title>
<script src="https://cdn.jsdelivr.net/npm/echarts@5/dist/echarts.min.js"></script>
<style>
* {{ margin:0; padding:0; box-sizing:border-box; }}
body {{ font-family:'Inter',-apple-system,BlinkMacSystemFont,'Segoe UI',sans-serif; background:#f5f7fa; color:#1e293b; padding:40px; }}
.page {{ max-width:1000px; margin:0 auto; }}
h1 {{ font-size:24px; font-weight:700; margin-bottom:4px; }}
.sub {{ color:#64748b; font-size:14px; margin-bottom:24px; }}
.stats {{ display:grid; grid-template-columns:repeat(4,1fr); gap:12px; margin-bottom:24px; }}
.stat-card {{ background:#fff; border-radius:10px; padding:16px; text-align:center; box-shadow:0 1px 3px rgba(0,0,0,0.05); }}
.stat-num {{ font-size:28px; font-weight:700; }}
.stat-label {{ font-size:12px; color:#64748b; margin-top:2px; }}
.stat-card.blue .stat-num {{ color:#3b82f6; }} .stat-card.red .stat-num {{ color:#ef4444; }} .stat-card.green .stat-num {{ color:#22c55e; }}
.stat-card.indigo .stat-num {{ color:#6366f1; }} .stat-card.teal .stat-num {{ color:#14b8a6; }} .stat-card.purple .stat-num {{ color:#a855f7; }}
.chart-row {{ display:grid; grid-template-columns:1fr 1fr; gap:14px; margin-bottom:24px; }}
.chart-box {{ background:#fff; border-radius:10px; padding:16px; box-shadow:0 1px 3px rgba(0,0,0,0.05); }}
.chart-box h3 {{ font-size:14px; font-weight:600; margin-bottom:12px; }}
.chart {{ height:260px; }}
.section {{ background:#fff; border-radius:10px; padding:16px; margin-bottom:14px; box-shadow:0 1px 3px rgba(0,0,0,0.05); }}
.section h3 {{ font-size:14px; font-weight:600; margin-bottom:10px; }}
table {{ width:100%; border-collapse:collapse; font-size:13px; }}
th,td {{ padding:8px 10px; text-align:left; border-bottom:1px solid #f1f5f9; }}
th {{ font-weight:600; color:#64748b; font-size:12px; text-transform:uppercase; }}
.summary {{ white-space:pre-wrap; font-size:14px; line-height:1.7; }}
.inc-table {{ font-size:13px; width:100%; }}
.inc-critical {{ border-left:3px solid #ef4444; }}
.inc-warning {{ border-left:3px solid #f59e0b; }}
.sev-badge, .sta-badge {{ display:inline-block; padding:1px 6px; border-radius:4px; font-size:11px; font-weight:600; }}
.sev-critical {{ background:#fef2f2; color:#ef4444; }}
.sev-warning {{ background:#fffbeb; color:#f59e0b; }}
.sev-info {{ background:#eff6ff; color:#3b82f6; }}
.sta-open {{ background:#fef2f2; color:#ef4444; }}
.sta-resolved {{ background:#f0fdf4; color:#22c55e; }}
.sta-acknowledged {{ background:#eef2ff; color:#6366f1; }}
@media print {{ body {{ padding:20px; }} .stats {{ grid-template-columns:repeat(4,1fr); }} }}
</style></head>
<body><div class="page">
<h1>{report.title}</h1>
<p class="sub">{data.get('period_start','')} ~ {data.get('period_end','')} | 生成时间：{report.created_at.strftime('%Y-%m-%d %H:%M') if report.created_at else ''} {diff_html}</p>

<div class="stats">
  <div class="stat-card blue"><div class="stat-num">{data.get('total_alerts',0)}</div><div class="stat-label">告警总数</div></div>
  <div class="stat-card red"><div class="stat-num">{data.get('critical_count',0)}</div><div class="stat-label">严重告警</div></div>
  <div class="stat-card green"><div class="stat-num">{data.get('resolve_rate',0)}%</div><div class="stat-label">解决率</div></div>
  <div class="stat-card purple"><div class="stat-num">{data.get('avg_resolve_minutes','-')}</div><div class="stat-label">平均处置(分钟)</div></div>
  <div class="stat-card indigo"><div class="stat-num">{data.get('asset_count',0)}</div><div class="stat-label">资产总数</div></div>
  <div class="stat-card teal"><div class="stat-num">{data.get('asset_health',0)}%</div><div class="stat-label">在线率</div></div>
  <div class="stat-card blue"><div class="stat-num">{data.get('total_incidents',0)}</div><div class="stat-label">事件总数</div></div>
  <div class="stat-card indigo"><div class="stat-num">{data.get('open_incidents',0)}/{data.get('resolved_incidents',0)}</div><div class="stat-label">事件(未关闭/已关闭)</div></div>
</div>

<div class="chart-row">
  <div class="chart-box"><h3>告警趋势</h3><div id="trendChart" class="chart"></div></div>
  <div class="chart-box"><h3>告警级别分布</h3><div id="severityChart" class="chart"></div></div>
</div>

<div class="section">
<h3>高频告警指标 TOP {min(len(top_rules),8)}</h3>
<table><thead><tr><th>#</th><th>指标</th><th>告警次数</th></tr></thead><tbody>
{''.join(f'<tr><td>{i+1}</td><td>{r}</td><td>{c}</td></tr>' for i,(r,c) in enumerate(top_rules[:8]))}
</tbody></table></div>

<div class="section">
<h3>告警最多资产 TOP {min(len(top_assets),8)}</h3>
<table><thead><tr><th>#</th><th>资产</th><th>告警次数</th></tr></thead><tbody>
{''.join(f'<tr><td>{i+1}</td><td>{a["name"]}</td><td>{a["count"]}</td></tr>' for i,a in enumerate(top_assets[:8]))}
</tbody></table></div>

{_render_incidents_html(data.get('incident_details', []))}

<div class="section">
<h3>评估与建议</h3>
<div class="summary">{report.summary}</div>
</div>

<script>
const labels = {trend_chart_labels};
const values = {trend_chart_values};
if(labels.length){{
  echarts.init(document.getElementById('trendChart')).setOption({{
    tooltip:{{trigger:'axis'}}, grid:{{left:40,right:12,bottom:24,top:8}},
    xAxis:{{type:'category',data:labels}},
    yAxis:{{type:'value',minInterval:1}},
    series:[{{type:'line',data:values,smooth:true,lineStyle:{{color:'#6366f1',width:2}},areaStyle:{{color:'rgba(99,102,241,0.12)'}},symbol:'circle',symbolSize:6}}]
  }});
}}
const sevLabels = {sev_labels};
const sevValues = {sev_values};
if(sevLabels.length){{
  echarts.init(document.getElementById('severityChart')).setOption({{
    tooltip:{{trigger:'item',formatter:'{{b}}: {{c}} ({{d}}%)'}},
    series:[{{type:'pie',radius:['30%','65%'],data:sevLabels.map((n,i)=>({{name:n,value:sevValues[i]}})),
      label:{{formatter:'{{b}}\n{{d}}%'}},
      color:['#ef4444','#f59e0b','#3b82f6']}}]
  }});
}}
</script>
</div></body></html>"""