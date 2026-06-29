import json
import subprocess
import re
from datetime import datetime
from fastapi import APIRouter, Depends, Request, Form
from fastapi.responses import HTMLResponse, RedirectResponse, PlainTextResponse
from sqlalchemy.orm import Session
from app.database import get_db
from app.models import DiscoveryJob, Asset
from app.template_utils import get_templates

router = APIRouter(prefix="/discovery", tags=["discovery"])
templates = get_templates()


@router.get("", response_class=HTMLResponse)
def discovery_page(request: Request, db: Session = Depends(get_db)):
    jobs = db.query(DiscoveryJob).order_by(DiscoveryJob.id.desc()).all()
    return templates.TemplateResponse("discovery.html", {
        "request": request, "jobs": jobs,
    })


@router.post("/create", response_class=HTMLResponse)
def create_job(
    request: Request, name: str = Form(...), job_type: str = Form("ssh"),
    target: str = Form(...), config_json: str = Form("{}"),
    db: Session = Depends(get_db),
):
    job = DiscoveryJob(name=name, job_type=job_type, target=target, config=config_json)
    db.add(job)
    db.commit()
    return RedirectResponse("/discovery", status_code=303)


@router.post("/run/{job_id}")
def run_job(job_id: int, request: Request, db: Session = Depends(get_db)):
    job = db.query(DiscoveryJob).filter(DiscoveryJob.id == job_id).first()
    if not job:
        return PlainTextResponse("Job not found", 404)
    job.status = "running"
    db.commit()
    cfg = json.loads(job.config) if isinstance(job.config, str) else job.config or {}
    discovered = []
    try:
        if job.job_type == "ssh":
            host = job.target
            port = cfg.get("port", 22)
            username = cfg.get("username", "root")
            password = cfg.get("password", "")
            cmd = "cat /etc/hostname; ip a | grep 'inet ' | awk '{print $2}'; cat /proc/cpuinfo | grep 'model name' | head -1; free -h | grep Mem; df -h / | tail -1"
            if password:
                result = subprocess.run(
                    ["sshpass", "-p", password, "ssh", "-oStrictHostKeyChecking=no", f"{username}@{host}", cmd],
                    capture_output=True, text=True, timeout=30
                )
            else:
                result = subprocess.run(
                    ["ssh", "-oStrictHostKeyChecking=no", f"{username}@{host}", cmd],
                    capture_output=True, text=True, timeout=30
                )
            lines = result.stdout.strip().split("\n")
            hostname = lines[0] if lines else host
            ips = re.findall(r'\d+\.\d+\.\d+\.\d+', " ".join(lines[1:3]))
            ip = ips[0] if ips else host
            asset = Asset(
                name=hostname, ip=ip, ci_type="server", type="host",
                tags=f"discovered,ssh,{job.name}",
            )
            db.add(asset)
            discovered.append(hostname)
        elif job.job_type == "subnet":
            subnet = job.target
            result = subprocess.run(
                ["nmap", "-sn", subnet], capture_output=True, text=True, timeout=120
            )
            for line in result.stdout.split("\n"):
                m = re.search(r'Nmap scan report for (.+)', line)
                if m:
                    name_or_ip = m.group(1)
                    asset = Asset(
                        name=name_or_ip, ip=name_or_ip,
                        ci_type="server", type="host",
                        tags=f"discovered,subnet,{job.name}",
                    )
                    db.add(asset)
                    discovered.append(name_or_ip)
        db.commit()
        job.status = "completed"
        job.result_summary = f"Discovered {len(discovered)} assets: {', '.join(discovered[:20])}"
        job.finished_at = datetime.now()
        db.commit()
    except Exception as e:
        job.status = "failed"
        job.result_summary = str(e)[:500]
        db.commit()
    return RedirectResponse("/discovery", status_code=303)
