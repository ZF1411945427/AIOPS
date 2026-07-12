import json
from fastapi import APIRouter, Depends, Request
from fastapi.responses import JSONResponse
from app.template_utils import get_templates

from datetime import datetime

from app.database import get_db
from app.services import alert_service, rca_service
from app.models import Alert, AlertSilence, RemediationWorkflow, RemediationLog, Asset, K8sEvent, AIProvider, AgentConfig, MetricRecord
from app.models import ChatSession, AlertSessionLink, AssetSessionLink
from app.services.remediation_service import execute_action
from app.services.agent_service import call_llm, get_or_create_session, add_message
from sqlalchemy.orm import Session

router = APIRouter(prefix="/alerts", tags=["alerts"])
templates = get_templates()


@router.post("/check")
def check_alerts(db: Session = Depends(get_db)):
    new_alerts = alert_service.check_rules(db)
    return {"new_alerts": len(new_alerts)}


def _alert_to_dict(a):
    return {
        "id": a.id,
        "metric_name": a.metric_name,
        "actual_value": a.actual_value,
        "threshold": a.threshold,
        "severity": a.severity,
        "status": a.status,
        "message": a.message,
        "asset_id": getattr(a, "asset_id", None),
        "rule_id": getattr(a, "rule_id", None),
        "created_at": a.created_at.strftime("%Y-%m-%d %H:%M:%S") if a.created_at else None,
        "acknowledged_at": a.acknowledged_at.strftime("%Y-%m-%d %H:%M:%S") if getattr(a, "acknowledged_at", None) else None,
        "resolved_at": a.resolved_at.strftime("%Y-%m-%d %H:%M:%S") if getattr(a, "resolved_at", None) else None,
    }


@router.get("/api/list")
def api_alert_list(
    status: str = "",
    severity: str = "",
    page: int = 1,
    per_page: int = 20,
    db: Session = Depends(get_db)):
    """告警列表 JSON API."""
    alerts, total = alert_service.list_alerts(db, status, severity, page, per_page)
    stats = alert_service.get_alert_stats(db)
    total_pages = (total + per_page - 1) // per_page if total > 0 else 1
    return JSONResponse({
        "alerts": [_alert_to_dict(a) for a in alerts],
        "stats": stats,
        "page": page,
        "per_page": per_page,
        "total": total,
        "total_pages": total_pages,
    })


@router.post("/api/batch-acknowledge")
def api_batch_acknowledge(db: Session = Depends(get_db)):
    count = alert_service.batch_acknowledge(db)
    return JSONResponse({"acknowledged": count})


@router.post("/api/batch-resolve")
def api_batch_resolve(db: Session = Depends(get_db)):
    count = alert_service.batch_resolve(db)
    return JSONResponse({"resolved": count})


@router.post("/api/check")
def api_check_alerts(db: Session = Depends(get_db)):
    new_alerts = alert_service.check_rules(db)
    return JSONResponse({"new_alerts": len(new_alerts)})


@router.post("/api/{alert_id}/acknowledge")
def api_acknowledge_alert(alert_id: int, db: Session = Depends(get_db)):
    alert_service.acknowledge_alert(db, alert_id)
    return JSONResponse({"ok": True})


@router.post("/api/{alert_id}/resolve")
def api_resolve_alert(alert_id: int, db: Session = Depends(get_db)):
    alert_service.resolve_alert(db, alert_id)
    return JSONResponse({"ok": True})


@router.post("/api/{alert_id}/heal")
def api_heal_alert(alert_id: int, db: Session = Depends(get_db)):
    """触发自愈：对指定告警运行第一个启用的自愈工作流."""
    alert = db.query(Alert).filter(Alert.id == alert_id).first()
    if not alert:
        return JSONResponse({"error": "告警不存在"}, status_code=404)

    wf = db.query(RemediationWorkflow).filter(
        RemediationWorkflow.enabled == True
    ).order_by(RemediationWorkflow.id.asc()).first()
    if not wf:
        return JSONResponse({"error": "没有启用的自愈工作流"}, status_code=400)

    steps = json.loads(wf.steps) if isinstance(wf.steps, str) else (wf.steps or [])
    asset = db.query(Asset).filter(Asset.id == alert.asset_id).first() if alert.asset_id else None
    target = asset.name if asset else f"asset_{alert.asset_id}"
    results = []

    for step_idx, step in enumerate(steps):
        if isinstance(step, dict):
            action_type = step.get("action", "restart")
            params = {k: v for k, v in step.items() if k not in ("step", "action")}
        else:
            action_type = step
            params = {}
        if not asset:
            success, output = False, f"未找到资产 alert.asset_id={alert.asset_id}，无法远程执行"
        else:
            success, output = execute_action(action_type, params, asset)
        log = RemediationLog(
            remediation_id=wf.id,
            alert_id=alert.id,
            action_type=action_type,
            target=target,
            success=success,
            output=f"[Step {step_idx+1}/{len(steps)}] {output}")
        db.add(log)
        results.append({"step": step_idx + 1, "action": action_type, "success": success, "output": output})
        if not success:
            break

    alert.status = "acknowledged"
    db.commit()

    return JSONResponse({"ok": True, "alert_id": alert.id, "workflow": wf.name, "steps": results})


# ─── 告警根因分析 ───

@router.get("/api/{alert_id}/rca")
def api_alert_rca(alert_id: int, db: Session = Depends(get_db)):
    """告警根因分析：基于拓扑依赖评分 + 关联资产 + K8S Event，推断根因"""
    alert = db.query(Alert).filter(Alert.id == alert_id).first()
    if not alert:
        return JSONResponse({"error": "告警不存在"}, status_code=404)

    asset = db.query(Asset).filter(Asset.id == alert.asset_id).first() if alert.asset_id else None

    # 1. 查关联 K8S Event（同一资产/名称的最近 warning/critical 事件）
    k8s_events = []
    if asset:
        ev_q = db.query(K8sEvent).filter(
            K8sEvent.severity.in_(["warning", "critical"]),
            K8sEvent.last_seen >= datetime.now().replace(hour=0, minute=0, second=0),
        )
        ev_q = ev_q.filter(
            (K8sEvent.name.ilike(f"%{asset.name}%")) |
            (K8sEvent.name.ilike(f"%{asset.name.split('/')[-1]}%") if '/' in asset.name else K8sEvent.name.ilike(f"%{asset.name}%"))
        )
        k8s_events = ev_q.order_by(K8sEvent.last_seen.desc()).limit(10).all()

    # 2. 查同资产近期其他告警
    related_alerts = db.query(Alert).filter(
        Alert.asset_id == alert.asset_id,
        Alert.id != alert.id,
        Alert.created_at >= datetime.now().replace(hour=0, minute=0, second=0),
    ).order_by(Alert.created_at.desc()).limit(10).all() if alert.asset_id else []

    # 3. 查近期指标趋势（该指标最近 10 个数据点）
    metric_history = db.query(MetricRecord).filter(
        MetricRecord.name == alert.metric_name,
        MetricRecord.asset_id == alert.asset_id,
    ).order_by(MetricRecord.timestamp.desc()).limit(10).all() if alert.asset_id else []
    metric_history.reverse()

    # 4. 拓扑依赖评分（复用 rca_service 的评分逻辑思路）
    from app.models import AssetRelation
    from collections import defaultdict
    relations = db.query(AssetRelation).all()
    child_map = defaultdict(list)
    for r in relations:
        child_map[r.parent_id].append(r.child_id)
    parent_map = defaultdict(list)
    for r in relations:
        parent_map[r.child_id].append(r.parent_id)

    # 根因推断：如果告警资产有父依赖，父依赖可能才是根因
    root_candidates = []
    if asset:
        for pid in parent_map.get(asset.id, []):
            p = db.query(Asset).filter(Asset.id == pid).first()
            if p:
                root_candidates.append({"id": p.id, "name": p.name, "type": p.type, "ci_type": getattr(p, 'ci_type', '')})

    return JSONResponse({
        "alert": {
            "id": alert.id,
            "metric_name": alert.metric_name,
            "actual_value": alert.actual_value,
            "threshold": alert.threshold,
            "severity": alert.severity,
            "message": alert.message or "",
        },
        "asset": {"id": asset.id, "name": asset.name, "ip": asset.ip or "", "ci_type": getattr(asset, 'ci_type', '')} if asset else None,
        "root_candidates": root_candidates,
        "related_alerts": [
            {"id": a.id, "metric_name": a.metric_name, "severity": a.severity, "message": a.message or "", "created_at": a.created_at.strftime("%Y-%m-%d %H:%M:%S") if a.created_at else ""}
            for a in related_alerts
        ],
        "k8s_events": [
            {"id": e.id, "reason": e.reason, "message": e.message or "", "kind": e.kind, "namespace": e.namespace, "severity": e.severity, "last_seen": e.last_seen.strftime("%Y-%m-%d %H:%M:%S") if e.last_seen else ""}
            for e in k8s_events
        ],
        "metric_history": [
            {"timestamp": m.timestamp.strftime("%H:%M:%S") if m.timestamp else "", "value": m.value}
            for m in metric_history
        ],
        "report": _build_alert_report(alert, asset, root_candidates, related_alerts, k8s_events, metric_history),
    })


def _build_alert_report(alert, asset, root_candidates, related_alerts, k8s_events, metric_history) -> str:
    """生成告警根因分析中文自然语言报告（Markdown格式）"""
    sev_cn = {"critical": "严重", "warning": "警告", "info": "提示"}
    type_cn = {"cloud_host": "云主机", "network_device": "网络设备", "k8s": "K8s资源",
                "docker": "容器", "server": "服务器", "database": "数据库"}
    lines = []

    lines.append("## 根因分析报告\n")

    # 告警概况
    lines.append("### 告警概况\n")
    lines.append(f"- **指标**: `{alert.metric_name}`")
    lines.append(f"- **当前值**: {alert.actual_value}（阈值: {alert.threshold}）")
    lines.append(f"- **级别**: {sev_cn.get(alert.severity, alert.severity)}")
    if asset:
        ci = type_cn.get(getattr(asset, 'ci_type', ''), getattr(asset, 'ci_type', ''))
        lines.append(f"- **涉事资产**: `{asset.name}` (IP: {asset.ip or 'N/A'}, 类型: {ci})")
    lines.append("")

    # 指标趋势分析
    if metric_history:
        lines.append("### 指标趋势分析\n")
        vals = [m.value for m in metric_history]
        avg = sum(vals) / len(vals) if vals else 0
        max_val = max(vals) if vals else 0
        min_val = min(vals) if vals else 0
        latest = vals[-1] if vals else 0
        lines.append(f"- **最近 {len(vals)} 个数据点**: 最低 {min_val} / 最高 {max_val} / 均值 {avg:.2f} / 最新 {latest}")
        if latest > avg * 2 and avg > 0:
            lines.append(f"- **趋势异常**: 当前值是均值的 {latest/avg:.1f} 倍，存在明显突增")
        elif latest > alert.threshold:
            lines.append(f"- **超阈值**: 当前值 {latest} 已超过阈值 {alert.threshold}")
        elif all(v == 0 for v in vals[:-1]) and latest > 0:
            lines.append(f"- **从零突增**: 之前指标为 0，突然升至 {latest}，可能是刚启动或采集恢复")
        lines.append("")

    # 上游依赖
    if root_candidates:
        lines.append("### 上游依赖分析\n")
        lines.append("以下上游资产可能是真正的根因：\n")
        for rc in root_candidates:
            tc = type_cn.get(rc.get('ci_type', ''), rc.get('ci_type', ''))
            lines.append(f"- `{rc['name']}` (类型: {tc})")
        lines.append("")

    # 关联告警
    if related_alerts:
        lines.append("### 同资产近期其他告警\n")
        lines.append(f"该资产近期还有 **{len(related_alerts)}** 条告警：\n")
        for ra in related_alerts[:5]:
            sv = sev_cn.get(ra.severity, ra.severity)
            lines.append(f"- [{sv}] `{ra.metric_name}`: {(ra.message or '')[:80]}")
        lines.append("")

    # K8S 事件
    if k8s_events:
        lines.append("### 关联 K8S 事件\n")
        lines.append(f"发现 **{len(k8s_events)}** 条关联事件：\n")
        for ev in k8s_events[:5]:
            sv = sev_cn.get(ev.severity, ev.severity)
            lines.append(f"- [{sv}] **{ev.reason}** {ev.kind} (ns: {ev.namespace}): {(ev.message or '')[:100]}")
        lines.append("")

    # 结论
    lines.append("### 分析结论\n")
    if root_candidates:
        lines.append(f"> 告警可能由上游依赖 **`{root_candidates[0]['name']}`** 引起，建议优先检查上游资产状态。")
    elif k8s_events:
        lines.append(f"> 告警与 K8S 事件 **{k8s_events[0].reason}** 相关，建议检查对应 Pod/Node 运行状态。")
    elif related_alerts:
        lines.append(f"> 该资产近期有多条告警，可能存在持续性故障，建议全面检查资产健康状态。")
    elif metric_history and len(metric_history) >= 3:
        vals = [m.value for m in metric_history]
        if vals[-1] > (sum(vals[:-1]) / max(len(vals)-1, 1)) * 2:
            lines.append(f"> 指标出现突增，可能是瞬时突发流量或进程异常，建议关注资源使用情况。")
        else:
            lines.append(f"> 指标持续偏高，建议检查对应服务负载和资源配置。")
    else:
        lines.append(f"> 当前数据不足以定位明确根因，建议使用 **AI 深度分析** 获取更详细的诊断。")

    return "\n".join(lines)


# ─── 告警 AI 深度分析 ───

@router.post("/api/{alert_id}/ai-rca")
def api_alert_ai_rca(alert_id: int, db: Session = Depends(get_db)):
    """AI 深度根因分析：结合 RCA 结果 + K8S Event + 指标趋势，调用 LLM 给出自然语言分析"""
    alert = db.query(Alert).filter(Alert.id == alert_id).first()
    if not alert:
        return JSONResponse({"error": "告警不存在"}, status_code=404)

    # 直接获取 RCA 上下文（不调用路由函数）
    asset_obj = db.query(Asset).filter(Asset.id == alert.asset_id).first() if alert.asset_id else None
    k8s_events = []
    if asset_obj:
        ev_q = db.query(K8sEvent).filter(
            K8sEvent.severity.in_(["warning", "critical"]),
            K8sEvent.last_seen >= datetime.now().replace(hour=0, minute=0, second=0),
        )
        short_name = asset_obj.name.split('/')[-1] if '/' in asset_obj.name else asset_obj.name
        ev_q = ev_q.filter(
            (K8sEvent.name.ilike(f"%{asset_obj.name}%")) |
            (K8sEvent.name.ilike(f"%{short_name}%"))
        )
        k8s_events = ev_q.order_by(K8sEvent.last_seen.desc()).limit(10).all()
    related_alerts = db.query(Alert).filter(
        Alert.asset_id == alert.asset_id, Alert.id != alert.id,
        Alert.created_at >= datetime.now().replace(hour=0, minute=0, second=0),
    ).order_by(Alert.created_at.desc()).limit(10).all() if alert.asset_id else []
    metric_history = db.query(MetricRecord).filter(
        MetricRecord.name == alert.metric_name, MetricRecord.asset_id == alert.asset_id,
    ).order_by(MetricRecord.timestamp.desc()).limit(10).all() if alert.asset_id else []
    metric_history.reverse()
    from app.models import AssetRelation
    from collections import defaultdict
    relations = db.query(AssetRelation).all()
    parent_map = defaultdict(list)
    for r in relations:
        parent_map[r.child_id].append(r.parent_id)
    root_candidates = []
    if asset_obj:
        for pid in parent_map.get(asset_obj.id, []):
            p = db.query(Asset).filter(Asset.id == pid).first()
            if p:
                root_candidates.append({"name": p.name, "ci_type": getattr(p, 'ci_type', '')})

    # 找可用 AI provider
    config = db.query(AgentConfig).filter(AgentConfig.id == 1).first()
    provider = None
    if config and config.default_provider_id:
        provider = db.query(AIProvider).filter(
            AIProvider.id == config.default_provider_id,
            AIProvider.is_enabled == True,
        ).first()
    if not provider:
        provider = db.query(AIProvider).filter(AIProvider.is_enabled == True).first()
    if not provider:
        return JSONResponse({"ok": False, "error": "未配置 AI 提供商，请在「智能体配置 > AI 提供商」中添加并启用"}, status_code=400)

    # 格式化上下文
    asset_name = asset_obj.name if asset_obj else "未知"
    asset_ip = asset_obj.ip if asset_obj else "N/A"
    asset_ci = getattr(asset_obj, 'ci_type', '') if asset_obj else "N/A"
    rc_text = "\n".join([f"- {r['name']} (类型: {r.get('ci_type','')})" for r in root_candidates]) or "无"
    ra_text = "\n".join([f"- [{a.severity}] {a.metric_name}: {(a.message or '')[:100]}" for a in related_alerts]) or "无"
    ev_text = "\n".join([f"- [{e.severity}] {e.reason}: {(e.message or '')[:120]} (ns: {e.namespace})" for e in k8s_events]) or "无"
    mh_text = "\n".join([f"  {m.timestamp.strftime('%H:%M:%S') if m.timestamp else ''}: {m.value}" for m in metric_history]) or "无数据"

    prompt = f"""你是一个资深 SRE 根因分析专家。请根据以下告警信息进行深度分析，用中文输出。

## 告警概况
- 告警ID: {alert.id}
- 指标: {alert.metric_name}
- 当前值: {alert.actual_value}
- 阈值: {alert.threshold}
- 级别: {alert.severity}
- 消息: {alert.message or '无'}

## 涉事资产
- 名称: {asset_name}
- IP: {asset_ip}
- 类型: {asset_ci}

## 上游依赖资产（可能的根因来源）
{rc_text}

## 同资产近期其他告警
{ra_text}

## 关联 K8S 事件
{ev_text}

## 指标趋势（最近10个数据点）
{mh_text}

请依次分析：
1. **可能的根因分析**：结合指标趋势、K8S事件和上游依赖，推断最可能的根本原因
2. **影响评估**：该告警可能影响的业务范围和关联系统
3. **修复建议**：给出具体的、可操作的前 3 条修复步骤（按紧急程度排序）
4. **风险提示**：需要重点关注的事项"""

    messages = [
        {"role": "system", "content": "你是资深 SRE 根因分析专家，根据告警数据、K8S事件和拓扑关系给出精准的根因分析和可操作的修复建议。回答简洁专业，用中文。"},
        {"role": "user", "content": prompt},
    ]
    result = call_llm(provider, messages, timeout_override=60)
    if "error" in result:
        return JSONResponse({"ok": False, "error": f"AI 调用失败: {result['error']}"}, status_code=502)
    try:
        content = result["choices"][0]["message"]["content"]
    except (KeyError, IndexError, TypeError):
        content = str(result)

    return JSONResponse({"ok": True, "analysis": content})


# ─── 从告警跳转 AI 助手（创建/复用会话并注入上下文） ───

@router.post("/api/{alert_id}/open-assistant")
def open_assistant_from_alert(alert_id: int, request: Request, db: Session = Depends(get_db)):
    user_id = request.session.get("user_id", 1)
    alert = db.query(Alert).filter(Alert.id == alert_id).first()
    if not alert:
        return JSONResponse({"error": "告警不存在"}, status_code=404)

    # 查找已有关联会话（复用逻辑）
    existing = db.query(AlertSessionLink).filter(AlertSessionLink.alert_id == alert_id).first()
    if existing:
        return JSONResponse({"session_id": existing.session_id, "new": False})

    # 创建新会话
    session = get_or_create_session(db, user_id, None)
    
    # 查资产详情
    asset = db.query(Asset).filter(Asset.id == alert.asset_id).first() if alert.asset_id else None
    
    # 构建上下文 JSON
    context = {
        "alert_id": alert.id,
        "alert_metric": alert.metric_name,
        "alert_severity": alert.severity,
        "alert_status": alert.status,
        "alert_value": alert.actual_value,
        "alert_threshold": alert.threshold,
        "asset_id": alert.asset_id,
        "asset_name": asset.name if asset else None,
        "asset_ip": asset.ip if asset else None,
    }
    
    # 更新会话元数据
    session.context = json.dumps(context, ensure_ascii=False)
    session.title = f"告警#{alert.id} {alert.metric_name} ({alert.severity})"
    
    # 创建关联记录
    db.add(AlertSessionLink(
        alert_id=alert_id, 
        session_id=session.id,
        context_summary=f"来自告警中心的关联会话"
    ))
    
    # 自动注入第一条系统消息作为上下文摘要
    summary_content = (
        f"**系统上下文注入**\n"
        f"已关联告警 **#{alert.id}** ({alert.severity})：{alert.message or ''}\n"
        f"- 指标：{alert.metric_name}，当前值：{alert.actual_value}，阈值：{alert.threshold}\n"
        f"- 涉事资产：{asset.name if asset else '未知'} ({asset.ip if asset else 'N/A'})\n"
        f"你可以直接问我这个告警的原因或处理方案，我会调用工具查询详细信息。"
    )
    add_message(db, session.id, "system", summary_content, message_type="text")
    
    return JSONResponse({"session_id": session.id, "new": True})


# ─── K8S Event 告警检测 ───

@router.post("/api/check-k8s-events")
def api_check_k8s_events(db: Session = Depends(get_db)):
    """扫描 K8S Event 表，将严重事件（OOM/CrashLoopBackOff/NodeNotReady 等）自动转为告警。
    手动触发时扫描最近 24 小时，确保能检测到历史事件。"""
    new_alerts, skipped, scanned = alert_service.check_k8s_events(db, window_minutes=1440)
    return JSONResponse({"new_alerts": len(new_alerts), "skipped": skipped, "scanned": scanned})

