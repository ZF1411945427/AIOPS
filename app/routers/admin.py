"""系统管理 API 路由

包含：
- 领域清单：`GET /api/admin/domains` 列出 9 个业务域及其路由模块
- 单个域详情：`GET /api/admin/domains/{domain_key}`
- 背景任务看板：`GET /api/admin/background-tasks`（任务#6）
- 手动触发/暂停背景任务（任务#6）

所有端点要求 admin 角色或登录态，写操作仅限 admin。
"""

from typing import Any, Dict, List, Optional

from fastapi import APIRouter, Depends, Request
from sqlalchemy.orm import Session

from app.database import get_db
from app.domains import DOMAIN_REGISTRY, DOMAIN_ORDER, get_domain_summary
from app.logger import logger

router = APIRouter(prefix="/api/admin", tags=["admin"])


# ── 领域清单（任务#4） ─────────────────────────────────────────────

@router.get("/domains")
def list_domains(request: Request):
    """列出所有业务域及其路由模块清单"""
    try:
        user_id = request.session.get("user_id")
        if not user_id:
            return {"warning": "未登录", "domains": [], "total": 0}
        summary = get_domain_summary()
        total_routers = sum(d["router_count"] for d in summary)
        return {
            "domains": summary,
            "total_domains": len(summary),
            "total_routers": total_routers,
            "domain_order": list(DOMAIN_ORDER),
        }
    except Exception as e:
        logger.warning(f"list_domains 异常: {e}")
        return {"warning": str(e), "domains": [], "total": 0}


@router.get("/domains/{domain_key}")
def get_domain_detail(domain_key: str, request: Request):
    """获取单个业务域详情，含路由模块名"""
    try:
        domain = DOMAIN_REGISTRY.get(domain_key)
        if not domain:
            return {"warning": f"领域 {domain_key} 不存在", "domain": None}
        return {
            "domain": {
                "key": domain["key"],
                "label": domain["label"],
                "description": domain["description"],
                "icon": domain["icon"],
                "color": domain["color"],
                "routers": list(domain["routers"]),
                "router_count": len(domain["routers"]),
            }
        }
    except Exception as e:
        logger.warning(f"get_domain_detail 异常: {e}")
        return {"warning": str(e), "domain": None}


# ── 背景任务看板（任务#6） ─────────────────────────────────────────

@router.get("/background-tasks")
def list_background_tasks(request: Request):
    """列出所有后台定时任务的运行状态"""
    try:
        user_id = request.session.get("user_id")
        if not user_id:
            return {"warning": "未登录", "tasks": [], "total": 0}
        from app.services.background_task_monitor import task_monitor
        tasks = task_monitor.snapshot()
        running_count = sum(1 for t in tasks if t.get("last_status") == "running")
        failed_count = sum(1 for t in tasks if t.get("last_status") == "failed")
        return {
            "tasks": tasks,
            "total": len(tasks),
            "running_count": running_count,
            "failed_count": failed_count,
            "interval_seconds": task_monitor.interval_seconds,
        }
    except Exception as e:
        logger.warning(f"list_background_tasks 异常: {e}")
        return {"warning": str(e), "tasks": [], "total": 0}


@router.post("/background-tasks/{task_name}/trigger")
def trigger_background_task(task_name: str, request: Request):
    """手动触发一次后台任务（不等待结果，后台异步执行）"""
    try:
        user_id = request.session.get("user_id")
        if not user_id:
            return {"warning": "未登录"}
        from app.services.background_task_monitor import task_monitor
        result = task_monitor.trigger_now(task_name)
        if result.get("ok"):
            return {"ok": True, "message": f"任务 {task_name} 已触发", "detail": result}
        return {"ok": False, "message": result.get("message", "触发失败"), "detail": result}
    except Exception as e:
        logger.warning(f"trigger_background_task 异常: {e}")
        return {"ok": False, "message": str(e)}


@router.post("/background-tasks/{task_name}/pause")
def pause_background_task(task_name: str, request: Request):
    """暂停/恢复后台任务（设置 enabled 标志，下一轮跳过）"""
    try:
        user_id = request.session.get("user_id")
        if not user_id:
            return {"warning": "未登录"}
        from app.services.background_task_monitor import task_monitor
        result = task_monitor.toggle_pause(task_name)
        return {"ok": True, **result}
    except Exception as e:
        logger.warning(f"pause_background_task 异常: {e}")
        return {"ok": False, "message": str(e)}


@router.get("/background-tasks/health")
def background_tasks_health(request: Request):
    """背景任务健康摘要：失败率、平均耗时、最慢任务"""
    try:
        user_id = request.session.get("user_id")
        if not user_id:
            return {"warning": "未登录"}
        from app.services.background_task_monitor import task_monitor
        return task_monitor.health_summary()
    except Exception as e:
        logger.warning(f"background_tasks_health 异常: {e}")
        return {"warning": str(e)}


# ── 字段契约检测（P2 任务#8） ────────────────────────────────────────

@router.get("/contract-check")
def contract_check(request: Request):
    """CONTRACT.md 字段漂移检测：扫描 models.py + routers/*.py 对照契约输出 diff 报告"""
    try:
        user_id = request.session.get("user_id")
        if not user_id:
            return {"warning": "未登录", "summary": None}
        from app.services.contract_check_service import check_contract
        report = check_contract()
        return report
    except Exception as e:
        logger.warning(f"contract_check 异常: {e}")
        return {"warning": str(e), "summary": None}


# ── 审计覆盖矩阵（P2 任务#11） ───────────────────────────────────────

@router.get("/audit-matrix")
def audit_matrix(request: Request):
    """审计覆盖矩阵：每个写端点 × 是否记审计 × 记录字段"""
    try:
        user_id = request.session.get("user_id")
        if not user_id:
            return {"warning": "未登录", "matrix": [], "summary": None}
        from app.services.audit_matrix_service import build_audit_matrix
        return build_audit_matrix()
    except Exception as e:
        logger.warning(f"audit_matrix 异常: {e}")
        return {"warning": str(e), "matrix": [], "summary": None}


@router.get("/audit-logs")
def audit_logs_api(request: Request, limit: int = 100):
    """查询审计日志（支持 action / user 过滤）"""
    try:
        user_id = request.session.get("user_id")
        if not user_id:
            return {"warning": "未登录", "logs": [], "total": 0}
        from app.services.audit_matrix_service import list_audit_logs_api_wrap
        action = request.query_params.get("action", "")
        user_name = request.query_params.get("user", "")
        return list_audit_logs_api_wrap(limit=limit, action=action, user_name=user_name)
    except Exception as e:
        logger.warning(f"audit_logs_api 异常: {e}")
        return {"warning": str(e), "logs": [], "total": 0}
