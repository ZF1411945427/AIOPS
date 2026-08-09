"""自主 AI Agent — 周期性巡检 + 自主决策 + 闭环执行 + 验证反思。

行业标准 ReAct (Reason + Act) 循环在自主运维场景的落地：
  Perceive（感知）→ Analyze（分析）→ Plan（计划）→ Act（执行）→ Verify（验证）

每轮循环由 background_loop 触发，周期可配置（默认 5 分钟）。
"""
import json
import time
import uuid
import logging
from datetime import datetime, timedelta
from typing import Dict, List, Optional, Tuple

from sqlalchemy.orm import Session

from app.database import get_session_for, get_db_mode
from app.models import Asset, Alert, MetricRecord, AutonomousCycle
from app.logger import logger
from app.services.health_engine import HEALTH_RED, HEALTH_GREEN, HEALTH_GRAY

logger = logging.getLogger(__name__)

# 自主巡检周期（秒）
AUTONOMOUS_INTERVAL_SECONDS = 300  # 5 分钟

# 健康阈值
CPU_WARN_THRESHOLD = 80.0
CPU_CRIT_THRESHOLD = 90.0
MEM_WARN_THRESHOLD = 80.0
MEM_CRIT_THRESHOLD = 90.0
DISK_WARN_THRESHOLD = 85.0
DISK_CRIT_THRESHOLD = 92.0


def _get_latest_metrics(db: Session, asset_id: int, names: list) -> dict:
    """获取资产最新指标值。"""
    result = {}
    for name in names:
        row = db.query(MetricRecord.value).filter(
            MetricRecord.asset_id == asset_id,
            MetricRecord.name == name,
        ).order_by(MetricRecord.timestamp.desc()).first()
        if row:
            result[name] = row[0]
    return result


def _get_active_alerts(db: Session, asset_id: int, hours: int = 2) -> list:
    """获取资产最近活跃告警。"""
    cutoff = datetime.now() - timedelta(hours=hours)
    return db.query(Alert).filter(
        Alert.asset_id == asset_id,
        Alert.created_at >= cutoff,
        Alert.status.in_(["triggered", "acknowledged", "firing"]),
    ).all()


def _classify_severity(metric_name: str, value: float) -> Tuple[str, str]:
    """根据指标名和值返回 (severity, description)。"""
    if metric_name == "cpu_usage":
        if value >= CPU_CRIT_THRESHOLD:
            return "critical", f"CPU 使用率 {value:.1f}%（阈值 {CPU_CRIT_THRESHOLD}%）"
        if value >= CPU_WARN_THRESHOLD:
            return "warning", f"CPU 使用率 {value:.1f}%（阈值 {CPU_WARN_THRESHOLD}%）"
    elif metric_name == "memory_usage":
        if value >= MEM_CRIT_THRESHOLD:
            return "critical", f"内存使用率 {value:.1f}%（阈值 {MEM_CRIT_THRESHOLD}%）"
        if value >= MEM_WARN_THRESHOLD:
            return "warning", f"内存使用率 {value:.1f}%（阈值 {MEM_WARN_THRESHOLD}%）"
    elif metric_name == "disk_usage":
        if value >= DISK_CRIT_THRESHOLD:
            return "critical", f"磁盘使用率 {value:.1f}%（阈值 {DISK_CRIT_THRESHOLD}%）"
        if value >= DISK_WARN_THRESHOLD:
            return "warning", f"磁盘使用率 {value:.1f}%（阈值 {DISK_WARN_THRESHOLD}%）"
    return "info", f"{metric_name}={value}"


def _perceive_issues(db: Session) -> Tuple[List[dict], List[dict]]:
    """感知阶段：采集系统健康状态，发现异常。

    返回 (issues, all_assets_info)。
    """
    issues = []
    all_assets = db.query(Asset).filter(Asset.ip != "", Asset.ip.isnot(None)).all()
    assets_info = []

    for asset in all_assets:
        info = {"id": asset.id, "name": asset.name, "ip": asset.ip, "ci_type": asset.ci_type or ""}
        metrics = _get_latest_metrics(db, asset.id, ["cpu_usage", "memory_usage", "disk_usage"])
        info["metrics"] = metrics

        for name in ["cpu_usage", "memory_usage", "disk_usage"]:
            val = metrics.get(name)
            if val is not None:
                sev, desc = _classify_severity(name, val)
                if sev in ("warning", "critical"):
                    issues.append({
                        "asset_id": asset.id,
                        "asset_name": asset.name,
                        "ip": asset.ip,
                        "metric": name,
                        "value": val,
                        "severity": sev,
                        "description": desc,
                    })

        active_alerts = _get_active_alerts(db, asset.id)
        if active_alerts:
            info["alert_count"] = len(active_alerts)
            for a in active_alerts:
                issues.append({
                    "asset_id": asset.id,
                    "asset_name": asset.name,
                    "ip": asset.ip,
                    "metric": a.metric_name or "alert",
                    "value": a.severity or "unknown",
                    "severity": a.severity or "warning",
                    "description": a.message or a.name or f"告警 #{a.id}",
                    "alert_id": a.id,
                })

        assets_info.append(info)

    return issues, assets_info


def _llm_analyze(issues: List[dict], assets_info: List[dict]) -> Tuple[str, List[dict]]:
    """分析阶段：调用 LLM 分析异常并制定修复计划。

    返回 (analysis_text, remediation_plan)。
    如果无 LLM 配置，走规则引擎降级。
    """
    if not issues:
        return "未发现异常，系统运行正常。", []

    # 规则引擎降级方案
    plan = []
    for issue in issues[:5]:  # 最多处理 5 个问题
        if issue["metric"] == "cpu_usage" and issue["value"] >= CPU_CRIT_THRESHOLD:
            plan.append({
                "action": "diagnose_top_process",
                "asset_id": issue["asset_id"],
                "command": "ps aux --sort=-%cpu | head -10",
                "description": f"CPU 告警: {issue['asset_name']} CPU={issue['value']}%，排查 top 进程",
                "risk_level": "low",
            })
        elif issue["metric"] == "memory_usage" and issue["value"] >= MEM_CRIT_THRESHOLD:
            plan.append({
                "action": "diagnose_memory",
                "asset_id": issue["asset_id"],
                "command": "free -m && ps aux --sort=-%mem | head -10",
                "description": f"内存告警: {issue['asset_name']} 内存={issue['value']}%，排查内存占用",
                "risk_level": "low",
            })
        elif issue["metric"] == "disk_usage" and issue["value"] >= DISK_CRIT_THRESHOLD:
            plan.append({
                "action": "diagnose_disk",
                "asset_id": issue["asset_id"],
                "command": "df -h && du -sh /* | sort -rh | head -10",
                "description": f"磁盘告警: {issue['asset_name']} 磁盘={issue['value']}%，排查空间占用",
                "risk_level": "low",
            })
        elif issue["metric"] == "alert" and issue["severity"] == "critical":
            plan.append({
                "action": "diagnose_alert",
                "asset_id": issue["asset_id"],
                "command": "echo 'alert check: " + str(issue.get("alert_id", "?")) + " - " + issue.get("description", "") + "'",
                "description": "告警: " + issue["asset_name"] + " - " + issue["description"],
                "risk_level": "medium",
            })

    # 去重（同一个 asset 合并诊断命令）
    seen = set()
    deduped = []
    for p in plan:
        key = (p["asset_id"], p["action"])
        if key not in seen:
            seen.add(key)
            deduped.append(p)

    summary = f"发现 {len(issues)} 个问题，已制定 {len(deduped)} 个诊断/修复步骤。"
    return summary, deduped


def _act_and_verify(plan: List[dict], cycle_id: str, db: Session) -> Tuple[List[dict], int, int]:
    """执行阶段：通过统一路由执行诊断/修复命令。

    返回 (actions_taken, action_count, success_count)。
    """
    from app.routers.agent_deploy import route_exec

    actions_taken = []
    action_count = 0
    success_count = 0

    for step in plan:
        try:
            result = route_exec(
                step["asset_id"],
                step["command"],
                user_id=0,
                username="autonomous-agent",
                timeout=30,
            )
            success = result.get("exit_code", -1) == 0
            action_count += 1
            if success:
                success_count += 1
            actions_taken.append({
                "action": step["action"],
                "asset_id": step["asset_id"],
                "command": step["command"][:100],
                "description": step["description"],
                "risk_level": step["risk_level"],
                "exit_code": result.get("exit_code", -1),
                "stdout": (result.get("stdout", "") or "")[:300],
                "channel": result.get("channel", "ssh"),
                "success": success,
            })
            logger.info(f"自主巡检[{cycle_id}] {step['action']} asset={step['asset_id']} exit={result.get('exit_code')}")
        except Exception as e:
            action_count += 1
            actions_taken.append({
                "action": step["action"],
                "asset_id": step["asset_id"],
                "command": step["command"][:100],
                "description": step["description"],
                "risk_level": step["risk_level"],
                "exit_code": -1,
                "stdout": "",
                "channel": "error",
                "success": False,
                "error": str(e)[:200],
            })
            logger.error(f"自主巡检[{cycle_id}] 执行失败: {e}")

    return actions_taken, action_count, success_count


def run_autonomous_cycle(db: Optional[Session] = None) -> str:
    """运行一轮自主巡检闭环。

    返回 cycle_id，供前端查询。
    """
    close_db = False
    if db is None:
        db = get_session_for(get_db_mode())()
        close_db = True
    start = time.time()
    cycle_id = str(uuid.uuid4())

    try:
        # 创建记录
        cycle = AutonomousCycle(
            cycle_id=cycle_id,
            status=AutonomousCycle.STATUS_RUNNING,
            phase="perceive",
        )
        db.add(cycle)
        db.commit()

        # Phase 1: 感知
        cycle.phase = "perceive"
        issues, assets_info = _perceive_issues(db)
        cycle.asset_count = len(assets_info)
        cycle.issue_count = len(issues)
        cycle.issues_found = json.dumps(issues, ensure_ascii=False, default=str)
        db.commit()

        if not issues:
            cycle.status = AutonomousCycle.STATUS_SUCCESS
            cycle.phase = "done"
            cycle.summary = "系统运行正常，未发现异常。"
            cycle.duration_ms = int((time.time() - start) * 1000)
            cycle.finished_at = datetime.now()
            db.commit()
            logger.info(f"自主巡检[{cycle_id}] 完成，未发现异常")
            return cycle_id

        # Phase 2: 分析
        cycle.phase = "analyze"
        analysis_text, plan = _llm_analyze(issues, assets_info)
        cycle.llm_analysis = analysis_text
        db.commit()

        if not plan:
            cycle.status = AutonomousCycle.STATUS_PARTIAL
            cycle.phase = "done"
            cycle.summary = f"发现 {len(issues)} 个问题，但无可执行的修复方案。"
            cycle.duration_ms = int((time.time() - start) * 1000)
            cycle.finished_at = datetime.now()
            db.commit()
            logger.info(f"自主巡检[{cycle_id}] 发现 {len(issues)} 个问题，无修复方案")
            return cycle_id

        # Phase 3: 执行 + 验证
        cycle.phase = "act"
        actions_taken, action_count, success_count = _act_and_verify(plan, cycle_id, db)
        cycle.actions_taken = json.dumps(actions_taken, ensure_ascii=False, default=str)
        cycle.action_count = action_count
        cycle.success_count = success_count
        cycle.status = AutonomousCycle.STATUS_PARTIAL if success_count < action_count else AutonomousCycle.STATUS_SUCCESS
        cycle.phase = "verify"
        cycle.summary = f"发现 {len(issues)} 个问题，执行 {action_count} 个动作，成功 {success_count}/{action_count}"
        cycle.duration_ms = int((time.time() - start) * 1000)
        cycle.finished_at = datetime.now()
        db.commit()

        logger.info(f"自主巡检[{cycle_id}] 完成: {cycle.summary}")
        return cycle_id

    except Exception as e:
        logger.error(f"自主巡检[{cycle_id}] 异常: {e}")
        try:
            cycle = db.query(AutonomousCycle).filter(AutonomousCycle.cycle_id == cycle_id).first()
            if cycle:
                cycle.status = AutonomousCycle.STATUS_FAILED
                cycle.phase = "error"
                cycle.error_message = str(e)[:500]
                cycle.duration_ms = int((time.time() - start) * 1000)
                cycle.finished_at = datetime.now()
                db.commit()
        except Exception:
            pass
        return cycle_id
    finally:
        if close_db:
            db.close()


def get_cycle_history(db: Session, limit: int = 20) -> list:
    """获取自主巡检历史。"""
    rows = db.query(AutonomousCycle).order_by(AutonomousCycle.created_at.desc()).limit(limit).all()
    return [
        {
            "id": r.id,
            "cycle_id": r.cycle_id,
            "status": r.status,
            "phase": r.phase,
            "summary": r.summary,
            "detail": r.detail,
            "issues_found": json.loads(r.issues_found or "[]"),
            "actions_taken": json.loads(r.actions_taken or "[]"),
            "llm_analysis": r.llm_analysis,
            "error_message": r.error_message,
            "asset_count": r.asset_count,
            "issue_count": r.issue_count,
            "action_count": r.action_count,
            "success_count": r.success_count,
            "duration_ms": r.duration_ms,
            "created_at": r.created_at.isoformat() if r.created_at else None,
            "finished_at": r.finished_at.isoformat() if r.finished_at else None,
        }
        for r in rows
    ]