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
import json
from datetime import datetime
from typing import Dict, List, Optional

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
