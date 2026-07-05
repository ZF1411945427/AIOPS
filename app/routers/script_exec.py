import subprocess
import paramiko
import json
from fastapi import APIRouter, Depends, Request, Form, HTTPException
from fastapi.responses import HTMLResponse
from sqlalchemy.orm import Session
from app.database import get_db
from app.models import DataSource, ScriptTask
from app.template_utils import get_templates, parse_json_config

router = APIRouter(prefix="/script", tags=["script"])
templates = get_templates()


@router.get("", response_class=HTMLResponse)
def script_page(request: Request, db: Session = Depends(get_db)):
    targets = db.query(DataSource).filter(DataSource.type.in_(["ssh", "host", "linux"])).all()
    history = db.query(ScriptTask).order_by(ScriptTask.id.desc()).limit(50).all()
    return templates.TemplateResponse("script.html", {
        "request": request, "targets": targets, "history": history,
    })


@router.post("/execute")
def execute_script(
    request: Request,
    target_id: int = Form(...),
    script_content: str = Form(...),
    timeout: int = Form(30),
    db: Session = Depends(get_db),
):
    target = db.query(DataSource).filter(DataSource.id == target_id).first()
    if not target:
        raise HTTPException(404, "Target not found")

    cfg = parse_json_config(target.auth_config)
    host = target.api_url or cfg.get("host") or target.name
    port = cfg.get("port", 22)
    username = cfg.get("username", "root")
    password = cfg.get("password")
    key_path = cfg.get("key_path") or cfg.get("private_key")
    use_local = cfg.get("local", False) or host in ("localhost", "127.0.0.1")

    output = ""
    error = ""
    if use_local:
        try:
            r = subprocess.run(
                script_content, shell=True, capture_output=True, text=True, timeout=timeout
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
            client = paramiko.SSHClient()
            client.set_missing_host_key_policy(paramiko.AutoAddPolicy())
            if key_path:
                key = paramiko.RSAKey.from_private_key_file(key_path)
                client.connect(host, port=port, username=username, pkey=key, timeout=timeout)
            else:
                client.connect(host, port=port, username=username, password=password, timeout=timeout)
            stdin, stdout, stderr = client.exec_command(script_content, timeout=timeout)
            output = stdout.read().decode()
            error = stderr.read().decode()
            client.close()
        except Exception as e:
            error = str(e)

    task = ScriptTask(
        target_name=target.name,
        script_content=script_content,
        output=output[:5000],
        error=error[:2000],
        exit_code=0 if not error else -1,
    )
    db.add(task)
    db.commit()

    history = db.query(ScriptTask).order_by(ScriptTask.id.desc()).limit(50).all()
    targets = db.query(DataSource).filter(DataSource.type.in_(["ssh", "host", "linux"])).all()
    return templates.TemplateResponse("script.html", {
        "request": request, "targets": targets, "history": history,
        "last_output": output[:2000], "last_error": error[:1000],
    })
