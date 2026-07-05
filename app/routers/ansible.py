import os
import json
import shutil
import subprocess
import tempfile
from datetime import datetime

from fastapi import APIRouter, Depends
from fastapi.responses import JSONResponse
from pydantic import BaseModel
from sqlalchemy.orm import Session

from app.database import get_db
from app.models import AnsibleInventory, AnsiblePlaybook, AnsibleRun

router = APIRouter(prefix="/ansible", tags=["ansible"])


def _inventory_to_dict(inv) -> dict:
    return {
        "id": inv.id,
        "name": inv.name or "",
        "description": inv.description or "",
        "content": inv.content or "",
        "created_at": inv.created_at.strftime("%Y-%m-%d %H:%M:%S") if inv.created_at else None,
        "updated_at": inv.updated_at.strftime("%Y-%m-%d %H:%M:%S") if inv.updated_at else None,
    }


def _playbook_to_dict(pb) -> dict:
    return {
        "id": pb.id,
        "name": pb.name or "",
        "description": pb.description or "",
        "content": pb.content or "",
        "created_at": pb.created_at.strftime("%Y-%m-%d %H:%M:%S") if pb.created_at else None,
        "updated_at": pb.updated_at.strftime("%Y-%m-%d %H:%M:%S") if pb.updated_at else None,
    }


def _run_to_dict(r) -> dict:
    return {
        "id": r.id,
        "inventory_id": r.inventory_id,
        "playbook_id": r.playbook_id,
        "inventory_name": r.inventory_name or "",
        "playbook_name": r.playbook_name or "",
        "extra_vars": r.extra_vars or "",
        "output": r.output or "",
        "error": r.error or "",
        "exit_code": r.exit_code if r.exit_code is not None else 0,
        "status": r.status or "pending",
        "created_at": r.created_at.strftime("%Y-%m-%d %H:%M:%S") if r.created_at else None,
        "finished_at": r.finished_at.strftime("%Y-%m-%d %H:%M:%S") if r.finished_at else None,
    }


class InventoryCreate(BaseModel):
    name: str
    description: str = ""
    content: str = ""


class PlaybookCreate(BaseModel):
    name: str
    description: str = ""
    content: str = ""


class RunCreate(BaseModel):
    inventory_id: int
    playbook_id: int
    extra_vars: dict = {}


class TestInventoryReq(BaseModel):
    content: str


@router.get("/api/inventories")
def list_inventories(db: Session = Depends(get_db)):
    items = db.query(AnsibleInventory).order_by(AnsibleInventory.id.desc()).all()
    return JSONResponse({"items": [_inventory_to_dict(i) for i in items], "total": len(items)})


@router.post("/api/inventories")
def create_inventory(body: InventoryCreate, db: Session = Depends(get_db)):
    name = (body.name or "").strip()
    if not name:
        return JSONResponse({"ok": False, "detail": "名称不能为空"}, status_code=400)
    if db.query(AnsibleInventory).filter(AnsibleInventory.name == name).first():
        return JSONResponse({"ok": False, "detail": "名称已存在"}, status_code=400)
    inv = AnsibleInventory(name=name, description=body.description or "", content=body.content or "")
    db.add(inv)
    db.commit()
    db.refresh(inv)
    return JSONResponse({"ok": True, "item": _inventory_to_dict(inv)})


@router.put("/api/inventories/{inv_id}")
def update_inventory(inv_id: int, body: InventoryCreate, db: Session = Depends(get_db)):
    inv = db.query(AnsibleInventory).filter(AnsibleInventory.id == inv_id).first()
    if not inv:
        return JSONResponse({"ok": False, "detail": "主机清单不存在"}, status_code=404)
    name = (body.name or "").strip()
    if not name:
        return JSONResponse({"ok": False, "detail": "名称不能为空"}, status_code=400)
    dup = db.query(AnsibleInventory).filter(AnsibleInventory.name == name, AnsibleInventory.id != inv_id).first()
    if dup:
        return JSONResponse({"ok": False, "detail": "名称已存在"}, status_code=400)
    inv.name = name
    inv.description = body.description or ""
    inv.content = body.content or ""
    db.commit()
    db.refresh(inv)
    return JSONResponse({"ok": True, "item": _inventory_to_dict(inv)})


@router.delete("/api/inventories/{inv_id}")
def delete_inventory(inv_id: int, db: Session = Depends(get_db)):
    inv = db.query(AnsibleInventory).filter(AnsibleInventory.id == inv_id).first()
    if not inv:
        return JSONResponse({"ok": False, "detail": "主机清单不存在"}, status_code=404)
    db.delete(inv)
    db.commit()
    return JSONResponse({"ok": True})


@router.get("/api/playbooks")
def list_playbooks(db: Session = Depends(get_db)):
    items = db.query(AnsiblePlaybook).order_by(AnsiblePlaybook.id.desc()).all()
    return JSONResponse({"items": [_playbook_to_dict(i) for i in items], "total": len(items)})


@router.post("/api/playbooks")
def create_playbook(body: PlaybookCreate, db: Session = Depends(get_db)):
    name = (body.name or "").strip()
    if not name:
        return JSONResponse({"ok": False, "detail": "名称不能为空"}, status_code=400)
    if db.query(AnsiblePlaybook).filter(AnsiblePlaybook.name == name).first():
        return JSONResponse({"ok": False, "detail": "名称已存在"}, status_code=400)
    pb = AnsiblePlaybook(name=name, description=body.description or "", content=body.content or "")
    db.add(pb)
    db.commit()
    db.refresh(pb)
    return JSONResponse({"ok": True, "item": _playbook_to_dict(pb)})


@router.put("/api/playbooks/{pb_id}")
def update_playbook(pb_id: int, body: PlaybookCreate, db: Session = Depends(get_db)):
    pb = db.query(AnsiblePlaybook).filter(AnsiblePlaybook.id == pb_id).first()
    if not pb:
        return JSONResponse({"ok": False, "detail": "Playbook 不存在"}, status_code=404)
    name = (body.name or "").strip()
    if not name:
        return JSONResponse({"ok": False, "detail": "名称不能为空"}, status_code=400)
    dup = db.query(AnsiblePlaybook).filter(AnsiblePlaybook.name == name, AnsiblePlaybook.id != pb_id).first()
    if dup:
        return JSONResponse({"ok": False, "detail": "名称已存在"}, status_code=400)
    pb.name = name
    pb.description = body.description or ""
    pb.content = body.content or ""
    db.commit()
    db.refresh(pb)
    return JSONResponse({"ok": True, "item": _playbook_to_dict(pb)})


@router.delete("/api/playbooks/{pb_id}")
def delete_playbook(pb_id: int, db: Session = Depends(get_db)):
    pb = db.query(AnsiblePlaybook).filter(AnsiblePlaybook.id == pb_id).first()
    if not pb:
        return JSONResponse({"ok": False, "detail": "Playbook 不存在"}, status_code=404)
    db.delete(pb)
    db.commit()
    return JSONResponse({"ok": True})


@router.post("/api/run")
def run_playbook(body: RunCreate, db: Session = Depends(get_db)):
    inv = db.query(AnsibleInventory).filter(AnsibleInventory.id == body.inventory_id).first()
    pb = db.query(AnsiblePlaybook).filter(AnsiblePlaybook.id == body.playbook_id).first()
    if not inv:
        return JSONResponse({"ok": False, "detail": "主机清单不存在"}, status_code=404)
    if not pb:
        return JSONResponse({"ok": False, "detail": "Playbook 不存在"}, status_code=404)

    extra_vars_str = ""
    if body.extra_vars:
        try:
            extra_vars_str = json.dumps(body.extra_vars, ensure_ascii=False)
        except Exception:
            extra_vars_str = ""

    run = AnsibleRun(
        inventory_id=inv.id,
        playbook_id=pb.id,
        inventory_name=inv.name,
        playbook_name=pb.name,
        extra_vars=extra_vars_str,
        status="running",
        created_at=datetime.now(),
    )
    db.add(run)
    db.commit()
    db.refresh(run)

    inv_file = None
    pb_file = None
    output = ""
    error = ""
    exit_code = -1
    status = "failed"
    try:
        try:
            inv_file = tempfile.NamedTemporaryFile(suffix=".yml", delete=False, mode="w", encoding="utf-8")
            inv_file.write(inv.content or "")
            inv_file.flush()
            inv_file.close()
        except Exception as e:
            error = f"写入 inventory 临时文件失败: {e}"
            raise

        try:
            pb_file = tempfile.NamedTemporaryFile(suffix=".yml", delete=False, mode="w", encoding="utf-8")
            pb_file.write(pb.content or "")
            pb_file.flush()
            pb_file.close()
        except Exception as e:
            error = f"写入 playbook 临时文件失败: {e}"
            raise

        cmd = ["ansible-playbook", "-i", inv_file.name, pb_file.name]
        if extra_vars_str:
            cmd += ["-e", extra_vars_str]
        try:
            r = subprocess.run(cmd, capture_output=True, text=True, timeout=300, encoding="utf-8", errors="ignore")
            output = r.stdout or ""
            error = r.stderr or ""
            exit_code = r.returncode if r.returncode is not None else -1
            status = "completed" if exit_code == 0 else "failed"
        except FileNotFoundError:
            error = "未找到 ansible-playbook 命令，请先安装 Ansible"
            exit_code = -2
            status = "failed"
        except subprocess.TimeoutExpired:
            error = "执行超时（300s）"
            exit_code = -3
            status = "failed"
        except Exception as e:
            error = f"执行异常: {e}"
            exit_code = -4
            status = "failed"
    finally:
        for f in (inv_file, pb_file):
            if f and hasattr(f, "name") and os.path.exists(f.name):
                try:
                    os.unlink(f.name)
                except Exception:
                    pass

    run.output = output[:20000]
    run.error = error[:8000]
    run.exit_code = exit_code
    run.status = status
    run.finished_at = datetime.now()
    db.commit()
    db.refresh(run)

    return JSONResponse({
        "ok": status == "completed",
        "run_id": run.id,
        "output": run.output,
        "error": run.error,
        "exit_code": run.exit_code,
        "status": run.status,
    })


@router.get("/api/runs")
def list_runs(db: Session = Depends(get_db)):
    items = db.query(AnsibleRun).order_by(AnsibleRun.id.desc()).limit(50).all()
    return JSONResponse({"items": [_run_to_dict(r) for r in items], "total": len(items)})


@router.get("/api/runs/{run_id}")
def get_run(run_id: int, db: Session = Depends(get_db)):
    r = db.query(AnsibleRun).filter(AnsibleRun.id == run_id).first()
    if not r:
        return JSONResponse({"ok": False, "detail": "执行记录不存在"}, status_code=404)
    return JSONResponse({"ok": True, "item": _run_to_dict(r)})


@router.delete("/api/runs/{run_id}")
def delete_run(run_id: int, db: Session = Depends(get_db)):
    r = db.query(AnsibleRun).filter(AnsibleRun.id == run_id).first()
    if not r:
        return JSONResponse({"ok": False, "detail": "执行记录不存在"}, status_code=404)
    db.delete(r)
    db.commit()
    return JSONResponse({"ok": True})


@router.get("/api/status")
def ansible_status():
    installed = shutil.which("ansible-playbook") is not None
    version = ""
    if installed:
        try:
            r = subprocess.run(["ansible-playbook", "--version"], capture_output=True, text=True, timeout=10, encoding="utf-8", errors="ignore")
            first_line = (r.stdout or "").splitlines()[0] if (r.stdout or "").strip() else ""
            version = first_line
        except Exception:
            version = ""
    return JSONResponse({"installed": installed, "version": version})


@router.post("/api/test-inventory")
def test_inventory(body: TestInventoryReq, db: Session = Depends(get_db)):
    inv_file = None
    output = ""
    error = ""
    exit_code = -1
    status = "failed"
    try:
        try:
            inv_file = tempfile.NamedTemporaryFile(suffix=".yml", delete=False, mode="w", encoding="utf-8")
            inv_file.write(body.content or "")
            inv_file.flush()
            inv_file.close()
        except Exception as e:
            return JSONResponse({"ok": False, "output": "", "error": f"写入临时文件失败: {e}", "exit_code": -1, "status": "failed"})

        cmd = ["ansible", "all", "-i", inv_file.name, "-m", "ping"]
        try:
            r = subprocess.run(cmd, capture_output=True, text=True, timeout=120, encoding="utf-8", errors="ignore")
            output = r.stdout or ""
            error = r.stderr or ""
            exit_code = r.returncode if r.returncode is not None else -1
            status = "completed" if exit_code == 0 else "failed"
        except FileNotFoundError:
            error = "未找到 ansible 命令，请先安装 Ansible"
            exit_code = -2
            status = "failed"
        except subprocess.TimeoutExpired:
            error = "测试超时（120s）"
            exit_code = -3
            status = "failed"
        except Exception as e:
            error = f"测试异常: {e}"
            exit_code = -4
            status = "failed"
    finally:
        if inv_file and hasattr(inv_file, "name") and os.path.exists(inv_file.name):
            try:
                os.unlink(inv_file.name)
            except Exception:
                pass

    return JSONResponse({
        "ok": status == "completed",
        "output": output[:20000],
        "error": error[:8000],
        "exit_code": exit_code,
        "status": status,
    })
