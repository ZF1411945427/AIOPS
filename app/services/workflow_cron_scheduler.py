"""B3: 工作流 cron 定时调度器（trigger_type=cron）。

后台轮询式 cron 调度（对齐 check_alert_triggers 风格，不引入 APScheduler 常驻线程）：
- 遍历 trigger_type='cron' 且 enabled 的工作流
- trigger_condition 形如 {"cron": "0 2 * * *"}（5 字段 cron 表达式，分钟级精度）
- croniter 判断当前分钟是否命中；用上次 cron 触发的 run 时间做防重复（同一分钟只触发一次）
- 命中 → start_workflow_run(trigger_source="cron", triggered_by="system")

约定（见 CONTRACT.md 第15章扩展）：
- trigger_type = "cron"
- trigger_condition = {"cron": "<5字段cron>"}；cron 字段非法 → 跳过该工作流并告警日志
"""
from datetime import datetime, timedelta
from typing import Any, Dict, List, Optional

from sqlalchemy.orm import Session


def _get_cron_expr(condition: Dict) -> Optional[str]:
    """从 trigger_condition 提取 cron 表达式。非法返回 None。"""
    if not condition or not isinstance(condition, dict):
        return None
    cron = condition.get("cron") or condition.get("cron_expr")
    if not cron or not isinstance(cron, str):
        return None
    cron = cron.strip()
    if not cron:
        return None
    try:
        parts = cron.split()
        if len(parts) != 5:
            return None
        # 字段非空校验；具体语法交给 croniter 兜底
        if any(p == "" for p in parts):
            return None
        return cron
    except (ValueError, TypeError):
        return None


def _cron_matches_now(cron_expr: str, now: Optional[datetime] = None) -> bool:
    """croniter 判断当前分钟是否命中。now 默认当前时间（测试可注入）。"""
    from croniter import croniter
    now = now or datetime.now()
    it = croniter(cron_expr, now)
    return it.get_prev(datetime) == now.replace(second=0, microsecond=0)


def check_cron_triggers(db: Session, max_workflows: int = 20, now: Optional[datetime] = None) -> List[Dict]:
    """后台轮询：cron 命中 → 自动拉起工作流。由 main.py background_loop 周期调用。

    防重复：同一工作流每分钟最多触发一次（查该工作流最后一次 trigger_source='cron'
    的 run 的 started_at，若与当前命中分钟相同则跳过）。
    """
    from app.logger import logger
    from app.models import AgentWorkflow, AgentWorkflowRun

    wfs = db.query(AgentWorkflow).filter(
        AgentWorkflow.trigger_type == "cron",
        AgentWorkflow.enabled == True,
    ).order_by(AgentWorkflow.id.desc()).limit(max_workflows).all()
    if not wfs:
        return []

    now = now or datetime.now()
    current_minute = now.replace(second=0, microsecond=0)
    triggered = []
    for wf in wfs:
        condition = wf.get_trigger_condition() or {}
        cron_expr = _get_cron_expr(condition)
        if not cron_expr:
            logger.warning(f"[workflow-cron] 工作流「{wf.name}」trigger_condition 缺少合法 cron 表达式: {condition}")
            continue
        try:
            if not _cron_matches_now(cron_expr, now):
                continue
        except Exception as e:
            logger.warning(f"[workflow-cron] 工作流「{wf.name}」cron 解析异常: {e}")
            continue

        # 防重复：同一分钟内该工作流已由 cron 触发过则跳过
        # 用 last_run.started_at >= current_minute 而非精确相等（started_at 是真实执行时间，可能与调度判定时刻有秒级差）
        last_run = db.query(AgentWorkflowRun).filter(
            AgentWorkflowRun.workflow_id == wf.id,
            AgentWorkflowRun.trigger_source == "cron",
        ).order_by(AgentWorkflowRun.id.desc()).first()
        if last_run and last_run.started_at and last_run.started_at >= current_minute:
            continue

        from app.services.agent_workflow_service import start_workflow_run
        try:
            run, err = start_workflow_run(
                db, wf.id, condition.get("inputs", {}) or {},
                trigger_source="cron", triggered_by="system",
            )
            if run:
                triggered.append({"workflow_id": wf.id, "workflow_name": wf.name, "run_id": run.id, "cron": cron_expr})
                logger.info(f"[workflow-cron] cron「{cron_expr}」触发工作流「{wf.name}」 run#{run.id}")
            elif err:
                logger.warning(f"[workflow-cron] 工作流「{wf.name}」触发失败: {err}")
        except Exception as e:
            logger.warning(f"[workflow-cron] 工作流「{wf.name}」触发异常: {e}")
    return triggered


def next_runs(db: Session, workflow_id: Optional[int] = None, count: int = 5) -> List[Dict]:
    """查询 cron 工作流的最近触发计划（供前端展示 next run）。"""
    from app.models import AgentWorkflow
    q = db.query(AgentWorkflow).filter(
        AgentWorkflow.trigger_type == "cron",
        AgentWorkflow.enabled == True,
    )
    if workflow_id:
        q = q.filter(AgentWorkflow.id == workflow_id)
    wfs = q.order_by(AgentWorkflow.id.desc()).limit(20).all()
    from croniter import croniter
    now = datetime.now()
    result = []
    for wf in wfs:
        condition = wf.get_trigger_condition() or {}
        cron_expr = _get_cron_expr(condition)
        if not cron_expr:
            continue
        try:
            it = croniter(cron_expr, now)
            nexts = [it.get_next(datetime).strftime("%Y-%m-%d %H:%M") for _ in range(count)]
        except Exception:
            continue
        result.append({
            "workflow_id": wf.id, "workflow_name": wf.name,
            "cron": cron_expr, "next_runs": nexts,
        })
    return result


# ─── SOP 工作流（WorkflowTemplate）触发接通（B6，2026-08-16）───────────────
# 修复既有缺口：原先 check_cron_triggers 只查 agent_workflows，导致
# workflow_templates（SOP 剧本）的 trigger_type='scheduled'/'alert_auto' 是
# "纸面配置、不自动执行"。以下两个函数补齐 SOP 的定时与告警自动触发。


def check_sop_cron_triggers(db: Session, max_workflows: int = 20, now: Optional[datetime] = None) -> List[Dict]:
    """SOP 剧本定时调度：扫描 WorkflowTemplate.trigger_type='scheduled'，
    命中 cron 后经 workflow_service.start_workflow_run 拉起。

    防重复：该模板最后一次 trigger_source='cron' 的 run 的 started_at >= 当前分钟则跳过。
    由 main.py background_loop 周期调用。
    """
    from app.logger import logger
    from app.models import WorkflowTemplate, WorkflowRun

    tpls = db.query(WorkflowTemplate).filter(
        WorkflowTemplate.trigger_type == "scheduled",
        WorkflowTemplate.enabled == True,
    ).order_by(WorkflowTemplate.id.desc()).limit(max_workflows).all()
    if not tpls:
        return []

    now = now or datetime.now()
    current_minute = now.replace(second=0, microsecond=0)
    triggered = []
    for tpl in tpls:
        condition = tpl.get_trigger_condition() or {}
        cron_expr = _get_cron_expr(condition)
        if not cron_expr:
            # 存量 scheduled 模板 trigger_condition 可能是 {"metric":..., "threshold":...}
            # （指标占位，依赖具体资产/告警上下文），无 cron 表达式时不自动调度（避免
            # 无目标资产导致大量失败 run），静默跳过。
            if condition.get("metric"):
                continue
            logger.warning(f"[workflow-cron-sop] 模板「{tpl.name}」trigger_condition 缺少合法 cron 表达式: {condition}")
            continue
        try:
            if not _cron_matches_now(cron_expr, now):
                continue
        except Exception as e:
            logger.warning(f"[workflow-cron-sop] 模板「{tpl.name}」cron 解析异常: {e}")
            continue

        last_run = db.query(WorkflowRun).filter(
            WorkflowRun.template_id == tpl.id,
            WorkflowRun.trigger_source == "cron",
        ).order_by(WorkflowRun.id.desc()).first()
        if last_run and last_run.started_at and last_run.started_at >= current_minute:
            continue

        from app.services.workflow_service import start_workflow_run
        try:
            context = dict(condition.get("context") or {})
            context.setdefault("cron", cron_expr)
            run, err = start_workflow_run(
                db, tpl.id, title=tpl.name or "SOP 定时执行",
                context=context, trigger_source="cron",
            )
            if run:
                triggered.append({"template_id": tpl.id, "template_name": tpl.name, "run_id": run.id, "cron": cron_expr})
                logger.info(f"[workflow-cron-sop] cron「{cron_expr}」触发 SOP 模板「{tpl.name}」 run#{run.id}")
            elif err:
                logger.warning(f"[workflow-cron-sop] SOP 模板「{tpl.name}」触发失败: {err}")
        except Exception as e:
            logger.warning(f"[workflow-cron-sop] SOP 模板「{tpl.name}」触发异常: {e}")
    return triggered


def _sop_alert_matches_condition(alert: Any, condition: Dict) -> bool:
    """SOP 告警自动触发条件匹配（与 agent_workflow 同语义 + 存量 metric/threshold）。

    支持 key：severity/status/metric_name/rule_id/asset_id。
    兼容存量 scheduled/alert_auto 模板的 {"metric":..., "threshold":...}：
    - metric → 匹配 alert.metric_name
    - threshold → 可选数值比较（trigger 判定用 alert.actual_value）
    """
    if not condition:
        return True
    # 存量 metric 占位条件（无 severity 等白名单键）：按 metric 名匹配
    metric_key = condition.get("metric") or condition.get("metric_name")
    for key, val in condition.items():
        if key in ("cron", "threshold", "context"):
            continue
        if val is None or val == "":
            continue
        try:
            if key in ("metric", "metric_name"):
                if alert.metric_name and metric_key and alert.metric_name != str(metric_key):
                    return False
                continue
            if key == "severity" and alert.severity != val:
                return False
            if key == "status" and alert.status != val:
                return False
            if key == "rule_id" and (alert.rule_id is None or alert.rule_id != int(val)):
                return False
            if key == "asset_id" and (alert.asset_id is None or alert.asset_id != int(val)):
                return False
        except (TypeError, ValueError):
            return False
    # threshold 可选比较
    thr = condition.get("threshold")
    if metric_key and thr is not None:
        try:
            if float(alert.actual_value) < float(thr):
                return False
        except (TypeError, ValueError):
            pass
    return True


def check_sop_alert_triggers(db: Session, lookback_minutes: int = 10, max_workflows: int = 20) -> List[Dict]:
    """SOP 剧本告警自动触发：扫描 WorkflowTemplate.trigger_type='alert_auto'，
    匹配最近新告警后拉起 workflow_service.start_workflow_run。

    防重复：同一告警对同一模板只触发一次（查 WorkflowRun.context.alert_id 历史去重）。
    由 main.py background_loop 周期调用。
    """
    from app.logger import logger
    from app.models import Alert, WorkflowTemplate, WorkflowRun

    tpls = db.query(WorkflowTemplate).filter(
        WorkflowTemplate.trigger_type == "alert_auto",
        WorkflowTemplate.enabled == True,
    ).order_by(WorkflowTemplate.id.desc()).limit(max_workflows).all()
    if not tpls:
        return []

    cutoff = datetime.now() - timedelta(minutes=lookback_minutes)
    recent_alerts = db.query(Alert).filter(Alert.created_at >= cutoff).order_by(Alert.created_at.desc()).limit(200).all()
    if not recent_alerts:
        return []

    triggered = []
    for tpl in tpls:
        condition = tpl.get_trigger_condition() or {}
        history_runs = db.query(WorkflowRun).filter(
            WorkflowRun.template_id == tpl.id,
            WorkflowRun.trigger_source == "alert",
        ).order_by(WorkflowRun.id.desc()).limit(500).all()
        used_alert_ids = set()
        for hr in history_runs:
            try:
                aid = hr.get_context().get("alert_id")
                if aid:
                    used_alert_ids.add(int(aid))
            except Exception:
                continue

        from app.services.workflow_service import start_workflow_run
        for a in recent_alerts:
            if a.id in used_alert_ids:
                continue
            if not _sop_alert_matches_condition(a, condition):
                continue
            context = {
                "alert_id": a.id,
                "asset_id": a.asset_id,
                "alert": {
                    "id": a.id, "rule_id": a.rule_id, "asset_id": a.asset_id,
                    "metric_name": a.metric_name, "actual_value": a.actual_value,
                    "severity": a.severity, "status": a.status, "message": a.message,
                    "created_at": str(a.created_at) if a.created_at else None,
                },
            }
            try:
                run, err = start_workflow_run(
                    db, tpl.id, title=tpl.name or "SOP 告警处置",
                    context=context, trigger_source="alert",
                )
                if run:
                    used_alert_ids.add(a.id)
                    triggered.append({"template_id": tpl.id, "template_name": tpl.name, "run_id": run.id, "alert_id": a.id})
                    logger.info(f"[workflow-alert-sop] 告警#{a.id} 自动触发 SOP 模板「{tpl.name}」 run#{run.id}")
                elif err:
                    logger.warning(f"[workflow-alert-sop] SOP 模板「{tpl.name}」触发失败: {err}")
            except Exception as e:
                logger.warning(f"[workflow-alert-sop] SOP 模板「{tpl.name}」触发异常: {e}")
    return triggered
