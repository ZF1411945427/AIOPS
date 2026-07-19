from typing import Optional

from fastapi import APIRouter, Depends, Request
from fastapi.responses import JSONResponse
from sqlalchemy.orm import Session

from app.database import get_db
from app.services import workflow_service

router = APIRouter(prefix="/workflow", tags=["workflow"])


@router.get("/api/templates")
def list_templates(category: Optional[str] = None, only_enabled: bool = False, page: Optional[int] = None, per_page: int = 20, db: Session = Depends(get_db)):
    try:
        result = workflow_service.list_templates(db, category=category, only_enabled=only_enabled, page=page, per_page=per_page)
        return result
    except Exception as e:
        return JSONResponse({"warning": str(e)}, status_code=200)


@router.get("/api/templates/{template_id}")
def get_template(template_id: int, db: Session = Depends(get_db)):
    try:
        t = workflow_service.get_template(db, template_id)
        if not t:
            return JSONResponse({"error": "模板不存在"}, status_code=404)
        return t
    except Exception as e:
        return JSONResponse({"warning": str(e)}, status_code=200)


@router.post("/api/templates/create")
def create_template(payload: dict, db: Session = Depends(get_db)):
    try:
        if not payload.get("name"):
            return JSONResponse({"error": "缺少 name"}, status_code=400)
        t = workflow_service.create_template(db, payload)
        return {"ok": True, "id": t["id"], "template": t}
    except Exception as e:
        return JSONResponse({"warning": str(e)}, status_code=200)


@router.post("/api/templates/{template_id}/update")
def update_template(template_id: int, payload: dict, db: Session = Depends(get_db)):
    try:
        t = workflow_service.update_template(db, template_id, payload)
        if not t:
            return JSONResponse({"error": "模板不存在"}, status_code=404)
        return {"ok": True, "template": t}
    except Exception as e:
        return JSONResponse({"warning": str(e)}, status_code=200)


@router.post("/api/templates/{template_id}/delete")
def delete_template(template_id: int, db: Session = Depends(get_db)):
    try:
        ok = workflow_service.delete_template(db, template_id)
        if not ok:
            return JSONResponse({"error": "模板不存在"}, status_code=404)
        return {"ok": True}
    except Exception as e:
        return JSONResponse({"warning": str(e)}, status_code=200)


@router.get("/api/runs")
def list_runs(status: Optional[str] = None, page: Optional[int] = None, per_page: int = 20, limit: int = 50, db: Session = Depends(get_db)):
    try:
        result = workflow_service.list_runs(db, status=status, limit=limit, page=page, per_page=per_page)
        return result
    except Exception as e:
        return JSONResponse({"warning": str(e)}, status_code=200)


@router.get("/api/runs/{run_id}")
def get_run(run_id: int, db: Session = Depends(get_db)):
    try:
        r = workflow_service.get_run(db, run_id)
        if not r:
            return JSONResponse({"error": "工作流实例不存在"}, status_code=404)
        return r
    except Exception as e:
        return JSONResponse({"warning": str(e)}, status_code=200)


@router.post("/api/runs/create")
def create_run(payload: dict, request: Request, db: Session = Depends(get_db)):
    try:
        template_id = payload.get("template_id")
        title = payload.get("title", "")
        context = payload.get("context") or {}
        custom_nodes = payload.get("nodes")
        custom_edges = payload.get("edges")
        if not template_id and not custom_nodes:
            return JSONResponse({"error": "必须提供 template_id 或自定义 nodes"}, status_code=400)
        run, err = workflow_service.start_workflow_run(
            db,
            template_id=template_id,
            title=title,
            context=context,
            trigger_source="manual",
            session_id=None,
            custom_nodes=custom_nodes,
            custom_edges=custom_edges,
        )
        if err:
            return JSONResponse({"error": err}, status_code=400)
        run_data = workflow_service.get_run(db, run.id)
        return {"ok": True, "id": run.id, "run": run_data}
    except Exception as e:
        return JSONResponse({"warning": str(e)}, status_code=200)


@router.post("/api/runs/{run_id}/node/{node_run_id}/confirm")
def confirm_node(run_id: int, node_run_id: int, request: Request, db: Session = Depends(get_db)):
    try:
        user_name = request.session.get("username", "unknown")
        result = workflow_service.confirm_node(db, node_run_id, user_name=user_name)
        if not result.get("success"):
            return JSONResponse({"error": result.get("message", "确认失败")}, status_code=400)
        return {"ok": True, "result": result}
    except Exception as e:
        return JSONResponse({"warning": str(e)}, status_code=200)


@router.post("/api/runs/{run_id}/node/{node_run_id}/cancel")
def cancel_node(run_id: int, node_run_id: int, payload: dict = None, db: Session = Depends(get_db)):
    try:
        reason = (payload or {}).get("reason", "")
        result = workflow_service.cancel_node(db, node_run_id, reason=reason)
        if not result.get("success"):
            return JSONResponse({"error": result.get("message", "取消失败")}, status_code=400)
        return {"ok": True, "result": result}
    except Exception as e:
        return JSONResponse({"warning": str(e)}, status_code=200)


@router.post("/api/runs/{run_id}/node/{node_run_id}/retry")
def retry_node(run_id: int, node_run_id: int, db: Session = Depends(get_db)):
    try:
        result = workflow_service.retry_node(db, node_run_id)
        if not result.get("success"):
            return JSONResponse({"error": result.get("message", "重试失败")}, status_code=400)
        return {"ok": True, "result": result}
    except Exception as e:
        return JSONResponse({"warning": str(e)}, status_code=200)


@router.post("/api/runs/{run_id}/abort")
def abort_run(run_id: int, payload: dict = None, db: Session = Depends(get_db)):
    try:
        reason = (payload or {}).get("reason", "")
        result = workflow_service.abort_run(db, run_id, reason=reason)
        if not result.get("success"):
            return JSONResponse({"error": result.get("message", "中止失败")}, status_code=400)
        return {"ok": True, "result": result}
    except Exception as e:
        return JSONResponse({"warning": str(e)}, status_code=200)
