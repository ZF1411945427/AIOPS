from typing import Optional

from fastapi import APIRouter, Depends, Request
from fastapi.responses import JSONResponse, StreamingResponse
from sqlalchemy.orm import Session

from app.database import get_db
from app.services import agent_workflow_service

router = APIRouter(prefix="/agent-workflow", tags=["agent-workflow"])


@router.get("/api/workflows")
def list_workflows(category: Optional[str] = None, only_enabled: bool = False, db: Session = Depends(get_db)):
    try:
        items = agent_workflow_service.list_workflows(db, category=category, only_enabled=only_enabled)
        return {"items": items, "count": len(items)}
    except Exception as e:
        return JSONResponse({"warning": str(e)}, status_code=200)


@router.get("/api/workflows/{workflow_id}")
def get_workflow(workflow_id: int, db: Session = Depends(get_db)):
    try:
        w = agent_workflow_service.get_workflow(db, workflow_id)
        if not w:
            return JSONResponse({"error": "工作流不存在"}, status_code=404)
        return w
    except Exception as e:
        return JSONResponse({"warning": str(e)}, status_code=200)


@router.post("/api/workflows/create")
def create_workflow(payload: dict, db: Session = Depends(get_db)):
    try:
        if not payload.get("name"):
            return JSONResponse({"error": "缺少 name"}, status_code=400)
        w = agent_workflow_service.create_workflow(db, payload)
        return {"ok": True, "id": w["id"], "workflow": w}
    except Exception as e:
        return JSONResponse({"warning": str(e)}, status_code=200)


@router.post("/api/workflows/{workflow_id}/update")
def update_workflow(workflow_id: int, payload: dict, db: Session = Depends(get_db)):
    try:
        w = agent_workflow_service.update_workflow(db, workflow_id, payload)
        if not w:
            return JSONResponse({"error": "工作流不存在"}, status_code=404)
        return {"ok": True, "workflow": w}
    except Exception as e:
        return JSONResponse({"warning": str(e)}, status_code=200)


@router.post("/api/workflows/{workflow_id}/delete")
def delete_workflow(workflow_id: int, db: Session = Depends(get_db)):
    try:
        ok = agent_workflow_service.delete_workflow(db, workflow_id)
        if not ok:
            return JSONResponse({"error": "工作流不存在"}, status_code=404)
        return {"ok": True}
    except Exception as e:
        return JSONResponse({"warning": str(e)}, status_code=200)


@router.get("/api/runs")
def list_runs(status: Optional[str] = None, limit: int = 50, db: Session = Depends(get_db)):
    try:
        items = agent_workflow_service.list_runs(db, status=status, limit=limit)
        return {"items": items, "count": len(items)}
    except Exception as e:
        return JSONResponse({"warning": str(e)}, status_code=200)


@router.get("/api/runs/{run_id}")
def get_run(run_id: int, db: Session = Depends(get_db)):
    try:
        r = agent_workflow_service.get_run(db, run_id)
        if not r:
            return JSONResponse({"error": "工作流实例不存在"}, status_code=404)
        return r
    except Exception as e:
        return JSONResponse({"warning": str(e)}, status_code=200)


@router.get("/api/runs/{run_id}/pdf")
def download_run_pdf(run_id: int, db: Session = Depends(get_db)):
    try:
        data = agent_workflow_service.export_run_pdf(db, run_id)
        if not data:
            return JSONResponse({"error": "工作流实例不存在"}, status_code=404)
        return StreamingResponse(
            iter([bytes(data)]),
            media_type="application/pdf",
            headers={"Content-Disposition": f"attachment; filename=workflow_run_{run_id}.pdf"}
        )
    except Exception as e:
        return JSONResponse({"warning": str(e)}, status_code=200)


@router.post("/api/runs/{workflow_id}/execute")
def execute_workflow(workflow_id: int, payload: dict, request: Request, db: Session = Depends(get_db)):
    try:
        user_name = request.session.get("username", "")
        inputs = payload.get("inputs") or {}
        run, err = agent_workflow_service.start_workflow_run(
            db, workflow_id=workflow_id, inputs=inputs, trigger_source="api", triggered_by=user_name
        )
        if err:
            return JSONResponse({"error": err}, status_code=400)
        run_data = agent_workflow_service.get_run(db, run.id)
        return {"ok": True, "id": run.id, "run": run_data}
    except Exception as e:
        return JSONResponse({"warning": str(e)}, status_code=200)


@router.post("/api/runs/{run_id}/abort")
def abort_run(run_id: int, request: Request, payload: dict = None, db: Session = Depends(get_db)):
    try:
        user_name = request.session.get("username", "")
        reason = (payload or {}).get("reason", "")
        result = agent_workflow_service.abort_run(db, run_id, reason=reason, operator=user_name)
        if not result.get("success"):
            return JSONResponse({"error": result.get("message")}, status_code=400)
        return {"ok": True, "result": result}
    except Exception as e:
        return JSONResponse({"warning": str(e)}, status_code=200)


@router.post("/api/runs/{run_id}/node/{node_run_id}/retry")
def retry_node(run_id: int, node_run_id: int, request: Request, db: Session = Depends(get_db)):
    try:
        user_name = request.session.get("username", "")
        result = agent_workflow_service.retry_node(db, node_run_id, operator=user_name)
        if not result.get("success"):
            return JSONResponse({"error": result.get("message")}, status_code=400)
        return {"ok": True, "result": result}
    except Exception as e:
        return JSONResponse({"warning": str(e)}, status_code=200)


@router.post("/api/runs/{run_id}/node/{node_run_id}/confirm")
def confirm_node(run_id: int, node_run_id: int, request: Request, db: Session = Depends(get_db)):
    try:
        user_name = request.session.get("username", "")
        result = agent_workflow_service.confirm_workflow_node(db, node_run_id, user_name)
        if not result.get("success"):
            return JSONResponse({"error": result.get("message")}, status_code=400)
        return {"ok": True, "result": result}
    except Exception as e:
        return JSONResponse({"warning": str(e)}, status_code=200)


@router.post("/api/runs/{run_id}/node/{node_run_id}/cancel")
def cancel_node(run_id: int, node_run_id: int, request: Request, db: Session = Depends(get_db)):
    try:
        user_name = request.session.get("username", "")
        result = agent_workflow_service.cancel_workflow_node(db, node_run_id, operator=user_name)
        if not result.get("success"):
            return JSONResponse({"error": result.get("message")}, status_code=400)
        return {"ok": True, "result": result}
    except Exception as e:
        return JSONResponse({"warning": str(e)}, status_code=200)
