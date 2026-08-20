import asyncio
import concurrent.futures
import json
import queue
from typing import Optional

from fastapi import APIRouter, Depends, Request, UploadFile, File, Body, WebSocket, WebSocketDisconnect
from fastapi.responses import JSONResponse
from sqlalchemy.orm import Session

from app.database import get_db
from app.services import deploy_service
from app.logger import logger

router = APIRouter(prefix="/deploy", tags=["deploy"])


def _get_user_id(request: Request) -> int:
    return request.session.get("user_id", 0)


@router.get("/api/plans")
def list_plans(status: Optional[str] = None, page: int = 1, per_page: int = 20, db: Session = Depends(get_db)):
    try:
        result = deploy_service.list_plans(db, status=status, page=page, per_page=per_page)
        return result
    except Exception as e:
        return JSONResponse({"warning": str(e)}, status_code=200)


@router.get("/api/plans/{plan_id}")
def get_plan(plan_id: int, db: Session = Depends(get_db)):
    try:
        plan = deploy_service.get_plan(db, plan_id)
        if not plan:
            return JSONResponse({"error": "计划不存在"}, status_code=404)
        return plan
    except Exception as e:
        return JSONResponse({"warning": str(e)}, status_code=200)


@router.post("/api/plans/create")
def create_plan(payload: dict, request: Request, db: Session = Depends(get_db)):
    try:
        user_id = _get_user_id(request)
        plan = deploy_service.create_plan(db, payload, user_id=user_id)
        return {"ok": True, "plan": plan}
    except ValueError as e:
        return JSONResponse({"error": str(e)}, status_code=400)
    except Exception as e:
        return JSONResponse({"warning": str(e)}, status_code=200)


@router.post("/api/plans/{plan_id}/update")
def update_plan(plan_id: int, payload: dict, db: Session = Depends(get_db)):
    try:
        plan = deploy_service.update_plan(db, plan_id, payload)
        if not plan:
            return JSONResponse({"error": "计划不存在"}, status_code=404)
        return {"ok": True, "plan": plan}
    except Exception as e:
        return JSONResponse({"warning": str(e)}, status_code=200)


@router.post("/api/plans/{plan_id}/delete")
def delete_plan(plan_id: int, db: Session = Depends(get_db)):
    try:
        ok = deploy_service.delete_plan(db, plan_id)
        if not ok:
            return JSONResponse({"error": "计划不存在"}, status_code=404)
        return {"ok": True}
    except Exception as e:
        return JSONResponse({"warning": str(e)}, status_code=200)


@router.post("/api/plans/{plan_id}/upload-doc")
async def upload_doc(plan_id: int, file: UploadFile = File(...), db: Session = Depends(get_db)):
    try:
        content = await file.read()
        try:
            doc_raw = content.decode("utf-8")
        except UnicodeDecodeError:
            doc_raw = content.decode("gbk", errors="replace")
        doc_file_name = file.filename or ""
        plan = deploy_service.update_doc_raw(db, plan_id, doc_raw, doc_file_name=doc_file_name)
        if not plan:
            return JSONResponse({"error": "计划不存在"}, status_code=404)
        return {"ok": True, "plan": plan, "file_name": doc_file_name, "size": len(content)}
    except Exception as e:
        return JSONResponse({"warning": str(e)}, status_code=200)


@router.post("/api/plans/{plan_id}/parse")
def ai_parse_manual(plan_id: int, db: Session = Depends(get_db)):
    try:
        result = deploy_service.ai_parse_manual(db, plan_id)
        if result.get("error"):
            return JSONResponse({"error": result["error"]}, status_code=200)
        return {"ok": True, "sop": result.get("sop"), "env_vars": result.get("env_vars"), "step_count": result.get("step_count")}
    except Exception as e:
        return JSONResponse({"warning": str(e)}, status_code=200)


@router.post("/api/plans/{plan_id}/resolve-env")
def resolve_env(plan_id: int, body: dict, db: Session = Depends(get_db)):
    try:
        user_mapping = body.get("env_mapping", {})
        result = deploy_service.resolve_env_mapping(db, plan_id, user_mapping)
        if result.get("error"):
            return JSONResponse({"error": result["error"]}, status_code=200)
        return {"ok": True, "env_mapping": result.get("env_mapping")}
    except Exception as e:
        return JSONResponse({"warning": str(e)}, status_code=200)


@router.post("/api/plans/{plan_id}/preflight")
def run_preflight(plan_id: int, db: Session = Depends(get_db)):
    try:
        result = deploy_service.run_preflight(db, plan_id)
        if result.get("error"):
            return JSONResponse({"error": result["error"]}, status_code=200)
        return {"ok": True, "results": result.get("results", []), "all_passed": result.get("all_passed", False), "skipped": result.get("skipped", False)}
    except Exception as e:
        return JSONResponse({"warning": str(e)}, status_code=200)


@router.post("/api/plans/{plan_id}/probe")
def probe_plan(plan_id: int, db: Session = Depends(get_db)):
    """SSH 探查目标机真实环境（A 层：环境感知）。"""
    try:
        result = deploy_service.probe_environment(db, plan_id)
        if result.get("error"):
            return JSONResponse({"error": result["error"]}, status_code=200)
        return {"ok": True, "probe": result.get("probe", {})}
    except Exception as e:
        return JSONResponse({"warning": str(e)}, status_code=200)


@router.post("/api/plans/{plan_id}/artifact-download")
def artifact_download(plan_id: int, force: bool = False, db: Session = Depends(get_db)):
    """手动触发源码下载到目标机（在线 git/HTTP + 离线仓库）。force=true 强制重新下载。"""
    try:
        result = deploy_service.auto_download_artifact(db, plan_id, force=force)
        if not result.get("ok"):
            return JSONResponse({"error": result.get("error", "下载失败")}, status_code=200)
        return {"ok": True, **result}
    except Exception as e:
        return JSONResponse({"warning": str(e)}, status_code=200)


@router.post("/api/plans/{plan_id}/auto-env")
def auto_env_mapping(plan_id: int, db: Session = Depends(get_db)):
    """基于探查结果，AI 自动生成环境映射 + SOP 适配建议（A+C 层）。"""
    try:
        result = deploy_service.ai_auto_env_mapping(db, plan_id)
        if result.get("error"):
            return JSONResponse({"error": result["error"]}, status_code=200)
        return {"ok": True, "analysis": result.get("analysis", {}), "env_mapping": result.get("env_mapping", {})}
    except Exception as e:
        return JSONResponse({"warning": str(e)}, status_code=200)


@router.post("/api/plans/{plan_id}/execute")
def execute_plan(plan_id: int, request: Request, db: Session = Depends(get_db)):
    try:
        user_id = _get_user_id(request)
        result = deploy_service.execute_plan(db, plan_id, user_id=user_id)
        if result.get("error"):
            return JSONResponse({"error": result["error"]}, status_code=200)
        return {"ok": True, "status": result.get("status"), "total_assets": result.get("total_assets"), "succeeded_assets": result.get("succeeded_assets")}
    except Exception as e:
        return JSONResponse({"warning": str(e)}, status_code=200)


@router.websocket("/ws/plans/{plan_id}/rollback-cleanup")
async def ws_rollback_cleanup(websocket: WebSocket, plan_id: int):
    """WebSocket 一键清理回滚：回滚所有已执行步骤，重置计划为 planned。"""
    await websocket.accept()
    from app.database import get_session_for, get_db_mode
    _session_factory = get_session_for(get_db_mode())
    db = _session_factory()
    _queue = queue.Queue()
    _sentinel = object()
    _thread_pool = concurrent.futures.ThreadPoolExecutor(max_workers=1)

    def _producer():
        _pdb = _session_factory()
        try:
            for event in deploy_service.stream_rollback_cleanup(_pdb, plan_id):
                _queue.put(event)
        except Exception as e:
            logger.error(f"清理回滚异常: plan_id={plan_id} {e}")
            _queue.put({"type": "error", "message": str(e)})
        finally:
            _pdb.close()
            _queue.put(_sentinel)

    _disconnected = asyncio.Event()
    async def _watch_disconnect():
        try:
            while True:
                await websocket.receive()
        except Exception:
            _disconnected.set()

    try:
        _watch_task = asyncio.ensure_future(_watch_disconnect())
        _thread_pool.submit(_producer)
        while True:
            try:
                event = _queue.get_nowait()
            except queue.Empty:
                if _disconnected.is_set():
                    break
                await asyncio.sleep(0.05)
                continue
            if event is _sentinel:
                try:
                    await websocket.close()
                except Exception as _exc:
                    logger.warning("[except:pass] Exception: %s", _exc, exc_info=True)
                break
            await websocket.send_text(json.dumps(event, ensure_ascii=False))
    except WebSocketDisconnect:
        pass
    except Exception as e:
        logger.error(f"清理回滚 WS 异常: plan_id={plan_id} {e}")
    finally:
        _thread_pool.shutdown(wait=False)
        db.close()


@router.post("/api/plans/{plan_id}/decision")
def api_plan_decision(plan_id: int, payload: dict, db: Session = Depends(get_db)):
    return deploy_service.submit_decision(db, plan_id, action=payload.get("action", ""))


@router.post("/api/plans/{plan_id}/stop")
def stop_plan(plan_id: int, db: Session = Depends(get_db)):
    """停止正在执行的部署（关闭 SSH 连接中断命令，恢复状态为 planned）。"""
    try:
        result = deploy_service.stop_execution(db, plan_id)
        if result.get("error"):
            return JSONResponse({"error": result["error"]}, status_code=200)
        return {"ok": True, "message": result.get("message", "已停止执行")}
    except Exception as e:
        return JSONResponse({"warning": str(e)}, status_code=200)


@router.post("/api/plans/{plan_id}/post-verify")
def post_verify(plan_id: int, db: Session = Depends(get_db)):
    """部署后验证：SSH 目标机健康检查，产出测试记录。"""
    try:
        result = deploy_service.post_deploy_verify(db, plan_id)
        if result.get("error"):
            return JSONResponse({"error": result["error"]}, status_code=200)
        return {"ok": True, "result": result.get("result", {})}
    except Exception as e:
        return JSONResponse({"warning": str(e)}, status_code=200)


@router.post("/api/plans/{plan_id}/generate-report")
def generate_report(plan_id: int, body: dict = Body({}), db: Session = Depends(get_db)):
    """AI 生成部署报告。body: {template_id?: 知识库报告模板ID, 可选}"""
    try:
        result = deploy_service.generate_deploy_report(db, plan_id, template_id=body.get("template_id") or 0)
        if result.get("error"):
            return JSONResponse({"error": result["error"]}, status_code=200)
        return {"ok": True, "report": result.get("report", {})}
    except Exception as e:
        return JSONResponse({"warning": str(e)}, status_code=200)


@router.get("/api/plans/{plan_id}/report/download")
def download_report(plan_id: int, fmt: str = "docx", db: Session = Depends(get_db)):
    """下载部署报告。支持格式: docx(Word, 默认), html。"""
    try:
        result = deploy_service.download_report(db, plan_id, fmt=fmt)
        if result.get("error"):
            return JSONResponse({"error": result["error"]}, status_code=200)
        from fastapi.responses import Response
        content = result["content"]
        filename = result["filename"]
        mime = result["mime"]
        if isinstance(content, bytes):
            raw_bytes = content
        else:
            raw_bytes = content.encode("utf-8")
        safe_filename = "".join(c if c.isalnum() or c in "._-" else "_" for c in filename)
        return Response(content=raw_bytes, media_type=mime,
            headers={"Content-Disposition": f'attachment; filename="{safe_filename}"; filename*=UTF-8\'\'{safe_filename}'})
    except Exception as e:
        return JSONResponse({"warning": str(e)}, status_code=200)


@router.websocket("/ws/plans/{plan_id}/execute")
async def ws_execute_plan(websocket: WebSocket, plan_id: int):
    """WebSocket 实时流式执行部署计划，逐行推送输出到浏览器终端。"""
    await websocket.accept()
    from app.database import get_session_for, get_db_mode
    _session_factory = get_session_for(get_db_mode())
    db = _session_factory()
    _queue = queue.Queue()
    _decision_queue = queue.Queue()  # 用户决策队列（修复/重试/回滚/跳过）
    _sentinel = object()
    _thread_pool = concurrent.futures.ThreadPoolExecutor(max_workers=1)

    def _producer():
        # 独立会话：不与主协程共享 db（SQLAlchemy session 非线程安全），断开时主协程 close 不影响 producer
        _pdb = _session_factory()
        try:
            for event in deploy_service.stream_execute(_pdb, plan_id, decision_queue=_decision_queue):
                _queue.put(event)
        except Exception as e:
            logger.error(f"部署执行流异常: plan_id={plan_id} {e}")
            _queue.put({"type": "error", "message": str(e)})
        finally:
            _pdb.close()
            _queue.put(_sentinel)

    _disconnected = asyncio.Event()

    async def _watch_disconnect():
        # 消费客户端消息：决策消息路由到 decision_queue，断开时置标志
        try:
            while True:
                raw = await websocket.receive()
                try:
                    data = json.loads(raw.get("text", "{}"))
                except Exception:
                    continue
                if data.get("type") == "decision":
                    _decision_queue.put(data.get("action", "rollback"))
        except Exception:
            _disconnected.set()

    try:
        _watch_task = asyncio.ensure_future(_watch_disconnect())
        _thread_pool.submit(_producer)

        while True:
            # get_nowait 轮询：绝不在 asyncio 里做阻塞式 queue.get（会泄漏线程池）
            try:
                event = _queue.get_nowait()
            except queue.Empty:
                if _disconnected.is_set():
                    logger.info(f"部署客户端已断开: plan_id={plan_id}")
                    break
                await asyncio.sleep(0.05)
                continue
            if event is _sentinel:
                break
            await websocket.send_text(json.dumps(event, ensure_ascii=False))
    except WebSocketDisconnect:
        logger.info(f"部署实时终端断开: plan_id={plan_id}")
    except Exception as e:
        logger.error(f"部署实时终端异常: plan_id={plan_id} {e}")
        try:
            await websocket.send_text(json.dumps({"type": "error", "message": str(e)}))
        except Exception as _exc1:
            logger.warning("[except:pass] Exception: %s", _exc1, exc_info=True)
    finally:
        # 断开时停止执行（关闭 SSH 连接中断命令，恢复状态、释放锁）
        try:
            from app.services.deploy_service import stop_execution
            stop_execution(db, plan_id)
            logger.info(f"部署中断，已停止执行: plan_id={plan_id}")
        except Exception as _e:
            logger.warning(f"部署中断停止执行失败: plan_id={plan_id} {_e}")
        deploy_service.release_exec_lock(plan_id)
        if '_watch_task' in locals():
            _watch_task.cancel()
        _thread_pool.shutdown(wait=False)
        db.close()