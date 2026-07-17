"""
智能巡检 API 路由

端点:
  GET    /inspection/api/stats          — 总览统计
  GET    /inspection/api/templates      — 模板列表
  POST   /inspection/api/templates      — 创建模板
  PUT    /inspection/api/templates/{id} — 更新模板
  DELETE /inspection/api/templates/{id} — 删除模板
  GET    /inspection/api/tasks          — 任务列表
  POST   /inspection/api/tasks          — 创建任务
  PUT    /inspection/api/tasks/{id}     — 更新任务
  DELETE /inspection/api/tasks/{id}     — 删除任务
  POST   /inspection/api/tasks/{id}/run — 触发执行
  GET    /inspection/api/records        — 记录列表
  GET    /inspection/api/records/{id}   — 记录详情
  GET    /inspection/api/assets-browse  — 资产浏览（供选择）
"""
from fastapi import APIRouter, Query, Body

from app.services.inspection_service import (
    list_templates, get_template, create_template, update_template, delete_template,
    list_tasks, get_task, create_task, update_task, delete_task,
    run_inspection, list_records, get_record, get_inspection_stats,
    browse_assets, seed_builtin_templates, trigger_by_alert,
)
from app.database import get_db

router = APIRouter(prefix="/inspection", tags=["SmartInspection"])


@router.on_event("startup")
def _on_startup():
    db = next(get_db())
    try:
        seed_builtin_templates(db)
    except Exception:
        pass


# ── 统计 ──

@router.get("/api/stats")
def stats():
    db = next(get_db())
    return get_inspection_stats(db)


# ── 模板 ──

@router.get("/api/templates")
def api_list_templates():
    db = next(get_db())
    return list_templates(db)


@router.post("/api/templates")
def api_create_template(body: dict = Body(...)):
    db = next(get_db())
    return create_template(db, body)


@router.put("/api/templates/{template_id}")
def api_update_template(template_id: int, body: dict = Body(...)):
    db = next(get_db())
    result = update_template(db, template_id, body)
    if result is None:
        return {"error": "Template not found"}
    return result


@router.delete("/api/templates/{template_id}")
def api_delete_template(template_id: int):
    db = next(get_db())
    return {"ok": delete_template(db, template_id)}


# ── 任务 ──

@router.get("/api/tasks")
def api_list_tasks():
    db = next(get_db())
    return list_tasks(db)


@router.post("/api/tasks")
def api_create_task(body: dict = Body(...)):
    db = next(get_db())
    return create_task(db, body)


@router.put("/api/tasks/{task_id}")
def api_update_task(task_id: int, body: dict = Body(...)):
    db = next(get_db())
    result = update_task(db, task_id, body)
    if result is None:
        return {"error": "Task not found"}
    return result


@router.delete("/api/tasks/{task_id}")
def api_delete_task(task_id: int):
    db = next(get_db())
    return {"ok": delete_task(db, task_id)}


@router.post("/api/tasks/{task_id}/run")
def api_run_task(task_id: int):
    db = next(get_db())
    result = run_inspection(db, task_id)
    if result is None:
        return {"error": "Task not found"}
    return result


# ── 记录 ──

@router.get("/api/records")
def api_list_records(task_id: int = Query(None), limit: int = Query(50)):
    db = next(get_db())
    return list_records(db, task_id=task_id, limit=limit)


@router.get("/api/records/{record_id}")
def api_get_record(record_id: int):
    db = next(get_db())
    result = get_record(db, record_id)
    if result is None:
        return {"error": "Record not found"}
    return result


# ── 资产浏览 ──

@router.get("/api/assets-browse")
def api_browse_assets(
    ci_type: str = Query(None),
    ci_types: str = Query(None),
    tag: str = Query(None),
    keyword: str = Query(None),
    page: int = Query(1),
    per_page: int = Query(20),
):
    db = next(get_db())
    return browse_assets(db, ci_type=ci_type, ci_types=ci_types, tag=tag, keyword=keyword, page=page, per_page=per_page)


@router.post("/api/trigger-by-alert/{alert_id}")
def api_trigger_by_alert(alert_id: int):
    db = next(get_db())
    result = trigger_by_alert(alert_id, db)
    if result is None:
        return {"error": "告警不存在"}
    if "error" in result:
        return result
    return result
