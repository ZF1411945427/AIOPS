import subprocess
import paramiko
import json
from fastapi import APIRouter, Depends, Request, Form, HTTPException
from fastapi.responses import JSONResponse
from sqlalchemy.orm import Session
from slowapi import Limiter
from slowapi.util import get_remote_address
from app.database import get_db
from app.models import DataSource, ScriptTask
from app.template_utils import get_templates, parse_json_config

router = APIRouter(prefix="/script", tags=["script"])
templates = get_templates()
_limiter = Limiter(key_func=get_remote_address)


def _target_to_dict(t) -> dict:
    cfg = parse_json_config(t.auth_config)
    return {
        "id": t.id,
        "name": t.name or "",
        "type": t.type or "",
        "endpoint": t.endpoint or "",
        "host": cfg.get("host") or t.endpoint or t.name,
        "enabled": bool(t.enabled),
    }


def _script_task_to_dict(s) -> dict:
    return {
        "id": s.id,
        "target_name": s.target_name or "",
        "script_content": s.script_content or "",
        "output": s.output or "",
        "error": s.error or "",
        "exit_code": s.exit_code if s.exit_code is not None else 0,
        "created_at": s.created_at.strftime("%Y-%m-%d %H:%M:%S") if s.created_at else None,
    }


@router.get("/api/targets")
def api_script_targets(db: Session = Depends(get_db)):
    """远程脚本目标主机列表 JSON API."""
    targets = db.query(DataSource).filter(DataSource.type.in_(["ssh", "host", "linux"])).all()
    return JSONResponse({"targets": [_target_to_dict(t) for t in targets], "total": len(targets)})


@router.get("/api/history")
def api_script_history(page: int = 1, per_page: int = 20, db: Session = Depends(get_db)):
    """远程脚本执行历史 JSON API（分页）."""
    q = db.query(ScriptTask).order_by(ScriptTask.id.desc())
    total = q.count()
    history = q.offset((page - 1) * per_page).limit(per_page).all()
    total_pages = (total + per_page - 1) // per_page if total > 0 else 1
    return JSONResponse({
        "history": [_script_task_to_dict(s) for s in history],
        "total": total,
        "page": page,
        "per_page": per_page,
        "total_pages": total_pages,
    })


@router.post("/api/execute")
@_limiter.limit("10/minute")
def api_script_execute(
    request: Request,
    target_id: int = Form(...),
    script_content: str = Form(...),
    timeout: int = Form(30),
    db: Session = Depends(get_db)):
    """执行远程脚本 JSON API."""
    from app.security import is_dangerous_command
    dangerous, pattern = is_dangerous_command(script_content)
    if dangerous:
        return JSONResponse({"ok": False, "error": f"命令被安全策略拦截(匹配: {pattern})"}, status_code=403)

    target = db.query(DataSource).filter(DataSource.id == target_id).first()
    if not target:
        return JSONResponse({"error": "Target not found"}, status_code=404)

    cfg = parse_json_config(target.auth_config)
    host = target.endpoint or cfg.get("host") or target.name
    port = cfg.get("ssh_port", cfg.get("port", 22))
    username = cfg.get("ssh_user", cfg.get("username", "root"))
    password = cfg.get("ssh_password", cfg.get("password"))
    key_path = cfg.get("key_path") or cfg.get("private_key")
    use_local = cfg.get("local", False) or host in ("localhost", "127.0.0.1")

    output = ""
    error = ""
    if use_local:
        try:
            r = subprocess.run(
                ["sh", "-c", script_content],
                capture_output=True, text=True, timeout=timeout,
                shell=False,
            )
            output = r.stdout
            error = r.stderr
        except subprocess.TimeoutExpired:
            output = ""
            error = f"Timed out after {timeout}s"
        except Exception as e:
            error = str(e)
    else:
        try:
            from app.services.ssh_helper import get_ssh_client
            client = get_ssh_client()
            if key_path:
                key = paramiko.RSAKey.from_private_key_file(key_path)
                client.connect(host, port=port, username=username, pkey=key, timeout=timeout)
            else:
                client.connect(host, port=port, username=username, password=password, timeout=timeout)
            stdin, stdout, stderr = client.exec_command(script_content, timeout=timeout)
            output = stdout.read().decode(errors="ignore")
            error = stderr.read().decode(errors="ignore")
            client.close()
        except Exception as e:
            error = str(e)

    task = ScriptTask(
        target_name=target.name,
        script_content=script_content,
        output=output[:5000],
        error=error[:2000],
        exit_code=0 if not error else -1)
    db.add(task)
    db.commit()
    db.refresh(task)
    return JSONResponse({
        "ok": True,
        "task_id": task.id,
        "output": output[:2000],
        "error": error[:1000],
        "exit_code": task.exit_code,
    })
