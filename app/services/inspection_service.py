"""
智能巡检服务 — AI 驱动的资产健康巡检引擎

核心能力：
1. 多维数据采集：指标(MetricRecord) + 告警(Alert) + 链路(Span) + 资产状态(Asset)
2. AI 智能分析：LLM 生成巡检报告、风险预判、趋势分析
3. 可控范围：支持按标签/CI类型/手动选择资产范围
"""
import json
from datetime import datetime, timedelta
from typing import List, Dict, Optional

from sqlalchemy.orm import Session
from sqlalchemy import func

from app.models import (
    Asset, Alert, Span, MetricRecord, AIProvider,
    InspectionTemplate, InspectionTask, InspectionRecord,
)


# ── 内置巡检模板 ──

BUILTIN_TEMPLATES = [
    {
        "name": "服务器健康巡检",
        "description": "检查服务器 CPU/内存/磁盘/网络/告警/进程状态",
        "target_ci_types": ["server", "virtual_machine", "cloud_host"],
        "check_items": [
            {"name": "CPU 使用率", "metric": "cpu_usage", "threshold": 90, "unit": "%", "severity": "critical"},
            {"name": "内存使用率", "metric": "memory_usage", "threshold": 90, "unit": "%", "severity": "critical"},
            {"name": "磁盘使用率", "metric": "disk_usage", "threshold": 85, "unit": "%", "severity": "warning"},
            {"name": "活跃告警", "metric": "active_alerts", "threshold": 1, "unit": "个", "severity": "warning"},
            {"name": "资产在线状态", "metric": "asset_status", "threshold": 0, "unit": "", "severity": "critical"},
            {"name": "最近检查时间", "metric": "last_checked_at", "threshold": 300, "unit": "秒", "severity": "warning"},
        ],
    },
    {
        "name": "中间件健康巡检",
        "description": "检查数据库/Redis/Kafka/ES 的连接、告警、性能指标",
        "target_ci_types": ["database", "redis", "mysql", "postgresql", "kafka", "elasticsearch", "middleware"],
        "check_items": [
            {"name": "活跃告警", "metric": "active_alerts", "threshold": 1, "unit": "个", "severity": "warning"},
            {"name": "资产在线状态", "metric": "asset_status", "threshold": 0, "unit": "", "severity": "critical"},
            {"name": "最近检查时间", "metric": "last_checked_at", "threshold": 300, "unit": "秒", "severity": "warning"},
        ],
    },
    {
        "name": "微服务健康巡检",
        "description": "检查 K8s 部署/服务的 Pod 状态、告警、链路健康",
        "target_ci_types": ["deployment", "service", "pod", "container", "statefulset", "daemonset"],
        "check_items": [
            {"name": "活跃告警", "metric": "active_alerts", "threshold": 1, "unit": "个", "severity": "warning"},
            {"name": "资产在线状态", "metric": "asset_status", "threshold": 0, "unit": "", "severity": "critical"},
            {"name": "Span 错误率", "metric": "span_error_rate", "threshold": 5, "unit": "%", "severity": "critical"},
            {"name": "Span P99 延迟", "metric": "span_p99_ms", "threshold": 1000, "unit": "ms", "severity": "warning"},
        ],
    },
    {
        "name": "API 接口巡检",
        "description": "检查 API 服务的链路追踪数据、错误率、延迟",
        "target_ci_types": ["api_service", "api_gateway", "api"],
        "check_items": [
            {"name": "活跃告警", "metric": "active_alerts", "threshold": 1, "unit": "个", "severity": "warning"},
            {"name": "Span 错误率", "metric": "span_error_rate", "threshold": 5, "unit": "%", "severity": "critical"},
            {"name": "Span P99 延迟", "metric": "span_p99_ms", "threshold": 1000, "unit": "ms", "severity": "warning"},
            {"name": "Span 平均延迟", "metric": "span_avg_ms", "threshold": 500, "unit": "ms", "severity": "warning"},
        ],
    },
]

LAYER_MAP = {
    "server": "infra", "virtual_machine": "infra", "cloud_host": "infra",
    "network_device": "infra", "switch": "infra", "router": "infra",
    "firewall": "infra", "load_balancer": "infra", "storage_device": "infra",
    "database": "middleware", "redis": "middleware", "mysql": "middleware",
    "postgresql": "middleware", "kafka": "middleware", "rabbitmq": "middleware",
    "rocketmq": "middleware", "mongodb": "middleware", "elasticsearch": "middleware",
    "middleware": "middleware",
    "deployment": "microservice", "service": "microservice", "pod": "microservice",
    "container": "microservice", "statefulset": "microservice", "daemonset": "microservice",
    "api_service": "api", "api_gateway": "api", "api": "api",
}


# ══════════════════════════════════════════════════
# 模板 CRUD
# ══════════════════════════════════════════════════

def list_templates(db: Session) -> List[dict]:
    rows = db.query(InspectionTemplate).order_by(InspectionTemplate.id).all()
    return [_template_to_dict(r) for r in rows]


def get_template(db: Session, template_id: int) -> Optional[dict]:
    r = db.query(InspectionTemplate).filter(InspectionTemplate.id == template_id).first()
    return _template_to_dict(r) if r else None


def create_template(db: Session, data: dict) -> dict:
    t = InspectionTemplate(
        name=data["name"],
        description=data.get("description", ""),
        target_ci_types=json.dumps(data.get("target_ci_types", []), ensure_ascii=False),
        check_items=json.dumps(data.get("check_items", []), ensure_ascii=False),
        enabled=data.get("enabled", True),
    )
    db.add(t)
    db.commit()
    db.refresh(t)
    return _template_to_dict(t)


def update_template(db: Session, template_id: int, data: dict) -> Optional[dict]:
    t = db.query(InspectionTemplate).filter(InspectionTemplate.id == template_id).first()
    if not t:
        return None
    for key in ["name", "description", "enabled"]:
        if key in data:
            setattr(t, key, data[key])
    if "target_ci_types" in data:
        t.target_ci_types = json.dumps(data["target_ci_types"], ensure_ascii=False)
    if "check_items" in data:
        t.check_items = json.dumps(data["check_items"], ensure_ascii=False)
    t.updated_at = datetime.now()
    db.commit()
    db.refresh(t)
    return _template_to_dict(t)


def delete_template(db: Session, template_id: int) -> bool:
    t = db.query(InspectionTemplate).filter(InspectionTemplate.id == template_id).first()
    if not t:
        return False
    db.delete(t)
    db.commit()
    return True


def seed_builtin_templates(db: Session):
    existing = db.query(InspectionTemplate.name).all()
    existing_names = {r[0] for r in existing}
    for tpl in BUILTIN_TEMPLATES:
        if tpl["name"] not in existing_names:
            db.add(InspectionTemplate(
                name=tpl["name"],
                description=tpl["description"],
                target_ci_types=json.dumps(tpl["target_ci_types"], ensure_ascii=False),
                check_items=json.dumps(tpl["check_items"], ensure_ascii=False),
            ))
    db.commit()


# ══════════════════════════════════════════════════
# 任务 CRUD
# ══════════════════════════════════════════════════

def list_tasks(db: Session) -> List[dict]:
    rows = db.query(InspectionTask).order_by(InspectionTask.id.desc()).all()
    return [_task_to_dict(r) for r in rows]


def get_task(db: Session, task_id: int) -> Optional[dict]:
    r = db.query(InspectionTask).filter(InspectionTask.id == task_id).first()
    return _task_to_dict(r) if r else None


def create_task(db: Session, data: dict) -> dict:
    t = InspectionTask(
        name=data["name"],
        template_id=data["template_id"],
        scope_type=data.get("scope_type", "manual"),
        scope_filter=json.dumps(data.get("scope_filter", {}), ensure_ascii=False),
        asset_ids=json.dumps(data.get("asset_ids", []), ensure_ascii=False),
        schedule_cron=data.get("schedule_cron"),
        schedule_enabled=data.get("schedule_enabled", False),
        ai_analysis=data.get("ai_analysis", True),
    )
    db.add(t)
    db.commit()
    db.refresh(t)
    return _task_to_dict(t)


def update_task(db: Session, task_id: int, data: dict) -> Optional[dict]:
    t = db.query(InspectionTask).filter(InspectionTask.id == task_id).first()
    if not t:
        return None
    for key in ["name", "template_id", "scope_type", "schedule_cron", "schedule_enabled", "ai_analysis", "status"]:
        if key in data:
            setattr(t, key, data[key])
    if "scope_filter" in data:
        t.scope_filter = json.dumps(data["scope_filter"], ensure_ascii=False)
    if "asset_ids" in data:
        t.asset_ids = json.dumps(data["asset_ids"], ensure_ascii=False)
    db.commit()
    db.refresh(t)
    return _task_to_dict(t)


def delete_task(db: Session, task_id: int) -> bool:
    t = db.query(InspectionTask).filter(InspectionTask.id == task_id).first()
    if not t:
        return False
    db.delete(t)
    db.commit()
    return True


def resolve_task_assets(db: Session, task: InspectionTask, template: InspectionTemplate = None) -> List[Asset]:
    scope_type = task.scope_type or "manual"

    # 先收集模板的目标 CI 类型（用于兜底过滤）
    template_ci_types = set()
    if template:
        template_ci_types = set(json.loads(template.target_ci_types or "[]"))

    if scope_type == "manual":
        ids = json.loads(task.asset_ids or "[]")
        if not ids:
            return []
        assets = db.query(Asset).filter(Asset.id.in_(ids)).all()
        # 兜底：即使手动选择了，也排除不属于模板目标类型的资产
        if template_ci_types:
            assets = [a for a in assets if a.ci_type in template_ci_types]
        return assets

    sf = json.loads(task.scope_filter or "{}")
    query = db.query(Asset)

    # 任务自身有 ci_types 过滤时用任务的；没有时用模板的兜底
    ci_types = sf.get("ci_types", [])
    if ci_types:
        query = query.filter(Asset.ci_type.in_(ci_types))
    elif template_ci_types:
        query = query.filter(Asset.ci_type.in_(template_ci_types))

    tags = sf.get("tags", [])
    if tags:
        for tag in tags:
            query = query.filter(Asset.tags.ilike(f"%{tag}%"))

    domain = sf.get("domain")
    if domain:
        query = query.filter(Asset.tags.ilike(f"%{domain}%"))

    status = sf.get("status")
    if status:
        query = query.filter(Asset.status == status)

    return query.all()


# ══════════════════════════════════════════════════
# 巡检执行
# ══════════════════════════════════════════════════

def run_inspection(db: Session, task_id: int) -> Optional[dict]:
    task = db.query(InspectionTask).filter(InspectionTask.id == task_id).first()
    if not task:
        return None
    if task.status == "running":
        return {"error": "任务正在执行中"}

    template = db.query(InspectionTemplate).filter(InspectionTemplate.id == task.template_id).first()
    if not template:
        return {"error": "模板不存在"}

    assets = resolve_task_assets(db, task, template)
    if not assets:
        return {"error": "未匹配到任何资产"}

    check_items = json.loads(template.check_items or "[]")

    record = InspectionRecord(
        task_id=task_id,
        status="running",
        total_assets=len(assets),
    )
    db.add(record)
    db.flush()

    item_results = []
    normal_count = 0
    warning_count = 0
    critical_count = 0

    for asset in assets:
        asset_result = _check_asset(db, asset, check_items)
        item_results.append(asset_result)

        worst = asset_result.get("worst_status", "normal")
        if worst == "critical":
            critical_count += 1
        elif worst == "warning":
            warning_count += 1
        else:
            normal_count += 1

    score = 100.0
    if len(assets) > 0:
        score = round((normal_count / len(assets)) * 100, 1)

    record.checked_assets = len(assets)
    record.normal_count = normal_count
    record.warning_count = warning_count
    record.critical_count = critical_count
    record.overall_score = score
    record.item_results = json.dumps(item_results, ensure_ascii=False)
    record.status = "analyzing" if task.ai_analysis else "completed"
    record.finished_at = datetime.now()
    record.duration_seconds = (record.finished_at - record.started_at).total_seconds()

    if task.ai_analysis:
        record.ai_report = _generate_ai_report(db, task, template, assets, item_results, score)

    record.status = "completed"
    task.last_run_at = datetime.now()
    task.status = "idle"
    db.commit()
    db.refresh(record)

    return _record_to_dict(record)


def trigger_by_alert(alert_id: int, db: Session) -> Optional[dict]:
    """按告警自动触发巡检：查找告警关联资产的同类资产，执行对应模板巡检.

    流程：
    1. 根据告警的 asset_id 找到对应资产
    2. 根据资产的 ci_type 找到匹配的内置模板（或最新自定义模板）
    3. 自动创建临时任务（scope = 同类资产）
    4. 执行巡检并返回结果
    5. 结果自动关联该告警 ID
    """
    alert = db.query(Alert).filter(Alert.id == alert_id).first()
    if not alert:
        return None

    asset = db.query(Asset).filter(Asset.id == alert.asset_id).first() if alert.asset_id else None
    ci_type = asset.ci_type if asset else None

    templates = db.query(InspectionTemplate).filter(
        InspectionTemplate.enabled == True
    ).all()
    template = None
    for t in templates:
        target_types = json.loads(t.target_ci_types or "[]")
        if ci_type and ci_type in target_types:
            template = t
            break
    if not template:
        template = db.query(InspectionTemplate).filter(
            InspectionTemplate.enabled == True
        ).order_by(InspectionTemplate.id.desc()).first()

    if not template:
        return {"error": "没有可用的巡检模板"}

    target_types = json.loads(template.target_ci_types or "[]")
    if ci_type and ci_type in target_types:
        scope_filter = {"ci_types": [ci_type]}
    else:
        scope_filter = {"ci_types": target_types[:1] if target_types else []}

    task = InspectionTask(
        name=f"[自动] 告警 #{alert_id} 触发巡检",
        template_id=template.id,
        scope_type="dynamic",
        scope_filter=json.dumps(scope_filter, ensure_ascii=False),
        asset_ids="[]",
        ai_analysis=True,
        status="idle",
    )
    db.add(task)
    db.flush()

    return run_inspection_for_alert(db, task.id, alert_id)


def run_inspection_for_alert(db: Session, task_id: int, triggered_by_alert_id: int) -> Optional[dict]:
    """按告警触发的巡检执行（内部用，不修改 task.last_run_at）."""
    task = db.query(InspectionTask).filter(InspectionTask.id == task_id).first()
    if not task:
        return None

    template = db.query(InspectionTemplate).filter(InspectionTemplate.id == task.template_id).first()
    if not template:
        return {"error": "模板不存在"}

    assets = resolve_task_assets(db, task, template)
    if not assets:
        return {"error": "未匹配到任何资产"}

    check_items = json.loads(template.check_items or "[]")

    record = InspectionRecord(
        task_id=task_id,
        triggered_by_alert_id=triggered_by_alert_id,
        status="running",
        total_assets=len(assets),
    )
    db.add(record)
    db.flush()

    item_results = []
    normal_count = 0
    warning_count = 0
    critical_count = 0

    for asset in assets:
        asset_result = _check_asset(db, asset, check_items)
        item_results.append(asset_result)
        worst = asset_result.get("worst_status", "normal")
        if worst == "critical":
            critical_count += 1
        elif worst == "warning":
            warning_count += 1
        else:
            normal_count += 1

    score = 100.0
    if assets:
        score = round((normal_count / len(assets)) * 100, 1)

    record.checked_assets = len(assets)
    record.normal_count = normal_count
    record.warning_count = warning_count
    record.critical_count = critical_count
    record.overall_score = score
    record.item_results = json.dumps(item_results, ensure_ascii=False)
    record.status = "analyzing" if task.ai_analysis else "completed"
    record.finished_at = datetime.now()
    record.duration_seconds = (record.finished_at - record.started_at).total_seconds()

    if task.ai_analysis:
        record.ai_report = _generate_ai_report(db, task, template, assets, item_results, score)

    record.status = "completed"
    task.status = "idle"
    db.commit()
    db.refresh(record)

    return _record_to_dict(record)


def _check_asset(db: Session, asset: Asset, check_items: list) -> dict:
    results = []
    worst = "normal"

    for item in check_items:
        metric = item.get("metric", "")
        threshold = item.get("threshold", 0)
        severity = item.get("severity", "warning")
        name = item.get("name", metric)

        value, status, detail = _evaluate_check(db, asset, metric, threshold, severity)

        if status == "critical":
            worst = "critical"
        elif status == "warning" and worst != "critical":
            worst = "warning"

        results.append({
            "name": name,
            "metric": metric,
            "value": value,
            "threshold": threshold,
            "unit": item.get("unit", ""),
            "status": status,
            "detail": detail,
        })

    return {
        "asset_id": asset.id,
        "asset_name": asset.name,
        "ci_type": asset.ci_type or "",
        "ip": asset.ip or "",
        "layer": LAYER_MAP.get(asset.ci_type or "", "infra"),
        "checks": results,
        "worst_status": worst,
    }


def _evaluate_check(db: Session, asset: Asset, metric: str, threshold, severity: str):
    if metric == "cpu_usage":
        return _check_metric_threshold(db, asset.id, "cpu_usage", threshold, ">", severity)
    elif metric == "memory_usage":
        return _check_metric_threshold(db, asset.id, "memory_usage", threshold, ">", severity)
    elif metric == "disk_usage":
        return _check_metric_threshold(db, asset.id, "disk_usage", threshold, ">", severity)
    elif metric == "active_alerts":
        count = (
            db.query(func.count(Alert.id))
            .filter(Alert.asset_id == asset.id, Alert.status.in_(["triggered", "acknowledged"]))
            .scalar() or 0
        )
        status = "critical" if count >= threshold else "normal"
        return count, status, f"{count} 个活跃告警" if count > 0 else "无活跃告警"
    elif metric == "asset_status":
        if asset.status != "online":
            return asset.status, "critical", f"资产状态: {asset.status}"
        return "online", "normal", "资产在线"
    elif metric == "last_checked_at":
        if not asset.last_checked_at:
            return None, "warning", "从未检查"
        elapsed = (datetime.now() - asset.last_checked_at).total_seconds()
        status = "warning" if elapsed > threshold else "normal"
        return int(elapsed), status, f"{int(elapsed)} 秒前检查"
    elif metric == "span_error_rate":
        return _check_span_error_rate(db, asset, threshold, severity)
    elif metric == "span_p99_ms":
        return _check_span_latency(db, asset, threshold, "p99", severity)
    elif metric == "span_avg_ms":
        return _check_span_latency(db, asset, threshold, "avg", severity)

    return None, "normal", "未知检查项"


def _check_metric_threshold(db: Session, asset_id: int, metric_name: str, threshold, op: str, severity: str):
    row = (
        db.query(MetricRecord.value)
        .filter(MetricRecord.asset_id == asset_id, MetricRecord.name == metric_name)
        .order_by(MetricRecord.timestamp.desc())
        .first()
    )
    if not row:
        return None, "warning", f"无 {metric_name} 数据"
    value = row[0]
    if op == ">" and value > threshold:
        status = "critical" if severity == "critical" else "warning"
        return round(value, 1), status, f"{metric_name}={value:.1f}% > 阈值{threshold}%"
    return round(value, 1), "normal", f"{metric_name}={value:.1f}%"


def _check_span_error_rate(db: Session, asset: Asset, threshold, severity: str):
    from app.services.health_engine import _match_asset_to_services
    service_names = _match_asset_to_services(asset, db)
    if not service_names:
        return 0, "normal", "无匹配 Span 服务"

    cutoff = datetime.now() - timedelta(minutes=5)
    total = (
        db.query(func.count(Span.id))
        .filter(Span.service_name.in_(service_names), Span.started_at >= cutoff)
        .scalar() or 0
    )
    if total == 0:
        return 0, "normal", "窗口内无 Span"

    error_count = (
        db.query(func.count(Span.id))
        .filter(
            Span.service_name.in_(service_names),
            Span.started_at >= cutoff,
            Span.status == "ERROR",
        )
        .scalar() or 0
    )
    rate = round(error_count / total * 100, 2)
    status = "critical" if rate > threshold else "normal"
    return rate, status, f"错误率 {rate}% ({error_count}/{total})"


def _check_span_latency(db: Session, asset: Asset, threshold, mode: str, severity: str):
    from app.services.health_engine import _match_asset_to_services
    service_names = _match_asset_to_services(asset, db)
    if not service_names:
        return 0, "normal", "无匹配 Span 服务"

    cutoff = datetime.now() - timedelta(minutes=5)
    durations = [
        r[0] for r in
        db.query(Span.duration_ms)
        .filter(
            Span.service_name.in_(service_names),
            Span.started_at >= cutoff,
            Span.duration_ms.isnot(None),
            Span.duration_ms > 0,
        )
        .all()
    ]
    if not durations:
        return 0, "normal", "窗口内无 Span 延迟数据"

    durations.sort()
    if mode == "p99":
        value = durations[int(len(durations) * 0.99)] if len(durations) > 1 else durations[0]
        label = "P99"
    else:
        value = round(sum(durations) / len(durations), 1)
        label = "平均"

    status = "warning" if value > threshold else "normal"
    return round(value, 1), status, f"{label}延迟 {value}ms"


# ══════════════════════════════════════════════════
# AI 报告生成
# ══════════════════════════════════════════════════

def _generate_ai_report(db: Session, task: InspectionTask, template: InspectionTemplate,
                         assets: List[Asset], item_results: list, score: float) -> str:
    provider = db.query(AIProvider).filter(AIProvider.is_enabled == True).first()
    if not provider:
        return _generate_rule_report(task, template, assets, item_results, score)

    critical_assets = [r for r in item_results if r["worst_status"] == "critical"]
    warning_assets = [r for r in item_results if r["worst_status"] == "warning"]
    normal_assets = [r for r in item_results if r["worst_status"] == "normal"]

    findings = []
    for r in critical_assets:
        failed = [c for c in r["checks"] if c["status"] == "critical"]
        findings.append(f"🔴 {r['asset_name']}({r['ip']}): " + "; ".join(c["detail"] for c in failed))
    for r in warning_assets:
        warns = [c for c in r["checks"] if c["status"] == "warning"]
        findings.append(f"🟡 {r['asset_name']}({r['ip']}): " + "; ".join(c["detail"] for c in warns))

    prompt = f"""你是一位资深 SRE 运维专家，请根据以下巡检数据生成一份专业的巡检报告。

## 巡检概况
- 巡检任务: {task.name}
- 巡检模板: {template.name}
- 巡检时间: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}
- 巡检资产数: {len(assets)} 个
- 健康评分: {score}/100
- 正常: {len(normal_assets)} | 警告: {len(warning_assets)} | 严重: {len(critical_assets)}

## 异常发现
{chr(10).join(findings) if findings else "所有资产状态正常，未发现异常。"}

## 请生成报告
请按以下格式生成：
1. **巡检摘要**（一句话总结）
2. **健康评分解读**（评分含义）
3. **异常分析**（逐项分析，含风险等级）
4. **趋势预判**（基于当前数据预测未来风险）
5. **处置建议**（按优先级排序的具体操作）
6. **风险预警**（潜在的隐患和建议预防措施）

请用专业但易懂的语言，适合运维团队阅读。"""

    messages = [
        {"role": "system", "content": "你是 AIOps 智能巡检系统的 AI 分析引擎，擅长运维健康分析和风险预判。"},
        {"role": "user", "content": prompt},
    ]

    try:
        from app.services.agent_service import call_llm
        resp = call_llm(provider, messages, timeout_override=60)
        if "error" not in resp:
            choices = resp.get("choices", [])
            if choices:
                return choices[0].get("message", {}).get("content", "")
    except Exception:
        pass

    return _generate_rule_report(task, template, assets, item_results, score)


def _generate_rule_report(task, template, assets, item_results, score) -> str:
    critical_assets = [r for r in item_results if r["worst_status"] == "critical"]
    warning_assets = [r for r in item_results if r["worst_status"] == "warning"]

    lines = [
        f"## 巡检报告 — {template.name}",
        f"",
        f"**巡检时间**: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}",
        f"**巡检资产**: {len(assets)} 个 | **健康评分**: {score}/100",
        f"**正常**: {len(assets) - len(critical_assets) - len(warning_assets)} | "
        f"**警告**: {len(warning_assets)} | **严重**: {len(critical_assets)}",
        "",
    ]

    if critical_assets:
        lines.append("### 🔴 严重异常")
        for r in critical_assets:
            failed = [c for c in r["checks"] if c["status"] == "critical"]
            lines.append(f"- **{r['asset_name']}** ({r['ip']}):")
            for c in failed:
                lines.append(f"  - {c['name']}: {c['detail']}")
        lines.append("")

    if warning_assets:
        lines.append("### 🟡 需关注")
        for r in warning_assets:
            warns = [c for c in r["checks"] if c["status"] == "warning"]
            lines.append(f"- **{r['asset_name']}** ({r['ip']}):")
            for c in warns:
                lines.append(f"  - {c['name']}: {c['detail']}")
        lines.append("")

    if not critical_assets and not warning_assets:
        lines.append("### ✅ 所有资产状态正常")
        lines.append("未发现异常，系统运行健康。")

    return "\n".join(lines)


# ══════════════════════════════════════════════════
# 记录查询
# ══════════════════════════════════════════════════

def list_records(db: Session, task_id: Optional[int] = None, limit: int = 50) -> List[dict]:
    query = db.query(InspectionRecord)
    if task_id:
        query = query.filter(InspectionRecord.task_id == task_id)
    rows = query.order_by(InspectionRecord.id.desc()).limit(limit).all()
    return [_record_to_dict(r) for r in rows]


def get_record(db: Session, record_id: int) -> Optional[dict]:
    r = db.query(InspectionRecord).filter(InspectionRecord.id == record_id).first()
    return _record_to_dict(r) if r else None


def get_inspection_stats(db: Session) -> dict:
    total_tasks = db.query(func.count(InspectionTask.id)).scalar() or 0
    total_records = db.query(func.count(InspectionRecord.id)).scalar() or 0
    completed = (
        db.query(func.count(InspectionRecord.id))
        .filter(InspectionRecord.status == "completed")
        .scalar() or 0
    )
    avg_score_row = (
        db.query(func.avg(InspectionRecord.overall_score))
        .filter(InspectionRecord.status == "completed")
        .scalar()
    )
    avg_score = round(avg_score_row, 1) if avg_score_row else 0

    latest = (
        db.query(InspectionRecord)
        .filter(InspectionRecord.status == "completed")
        .order_by(InspectionRecord.id.desc())
        .first()
    )

    return {
        "total_tasks": total_tasks,
        "total_records": total_records,
        "completed_records": completed,
        "avg_score": avg_score,
        "latest_record": _record_to_dict(latest) if latest else None,
    }


# ══════════════════════════════════════════════════
# 资产浏览（供任务选择资产用）
# ══════════════════════════════════════════════════

def browse_assets(db: Session, ci_type: str = None, ci_types: str = None,
                  tag: str = None, keyword: str = None,
                  page: int = 1, per_page: int = 20) -> dict:
    query = db.query(Asset)
    if ci_types:
        types = [t.strip() for t in ci_types.split(",") if t.strip()]
        if types:
            query = query.filter(Asset.ci_type.in_(types))
    elif ci_type:
        query = query.filter(Asset.ci_type == ci_type)
    if tag:
        query = query.filter(Asset.tags.ilike(f"%{tag}%"))
    if keyword:
        query = query.filter(
            (Asset.name.ilike(f"%{keyword}%")) | (Asset.ip.ilike(f"%{keyword}%"))
        )
    total = query.count()
    items = query.offset((page - 1) * per_page).limit(per_page).all()
    return {
        "total": total,
        "items": [{"id": a.id, "name": a.name, "ci_type": a.ci_type, "ip": a.ip or "", "status": a.status or ""} for a in items],
        "page": page,
        "per_page": per_page,
    }


# ── 序列化 ──

def _template_to_dict(t: InspectionTemplate) -> dict:
    return {
        "id": t.id,
        "name": t.name,
        "description": t.description or "",
        "target_ci_types": json.loads(t.target_ci_types or "[]"),
        "check_items": json.loads(t.check_items or "[]"),
        "enabled": t.enabled,
        "created_at": t.created_at.isoformat() if t.created_at else None,
        "updated_at": t.updated_at.isoformat() if t.updated_at else None,
    }


def _task_to_dict(t: InspectionTask) -> dict:
    return {
        "id": t.id,
        "name": t.name,
        "template_id": t.template_id,
        "scope_type": t.scope_type or "manual",
        "scope_filter": json.loads(t.scope_filter or "{}"),
        "asset_ids": json.loads(t.asset_ids or "[]"),
        "schedule_cron": t.schedule_cron,
        "schedule_enabled": t.schedule_enabled,
        "ai_analysis": t.ai_analysis,
        "status": t.status or "idle",
        "last_run_at": t.last_run_at.isoformat() if t.last_run_at else None,
        "created_at": t.created_at.isoformat() if t.created_at else None,
    }


def _record_to_dict(r: InspectionRecord) -> dict:
    return {
        "id": r.id,
        "task_id": r.task_id,
        "status": r.status or "running",
        "total_assets": r.total_assets,
        "checked_assets": r.checked_assets,
        "normal_count": r.normal_count,
        "warning_count": r.warning_count,
        "critical_count": r.critical_count,
        "overall_score": r.overall_score,
        "ai_report": r.ai_report or "",
        "ai_risk_summary": r.ai_risk_summary or "",
        "ai_recommendations": json.loads(r.ai_recommendations or "[]"),
        "item_results": json.loads(r.item_results or "[]"),
        "started_at": r.started_at.isoformat() if r.started_at else None,
        "finished_at": r.finished_at.isoformat() if r.finished_at else None,
        "duration_seconds": r.duration_seconds,
    }
