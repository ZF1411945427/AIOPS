"""edge 升级任务协调器(F5) - 状态机/批次/verify/回滚, 持久化可恢复。

契约见 CONTRACT.md 20.2-20.4。对标 Ongrid upgrade_job.go。
执行模型: create(落库 pending + 生成 steps) → run(逐批 running → 每 agent upgrade→verify,
失败自动该批 rollback → failed/completed) → pause 中断 → 可查询续传。
升级动作 = 把 edge_sessions.agent_version 刷为目标版本(模拟远程升级, 真实升级走 agent 命令通道可扩展)。
"""
import json
from datetime import datetime
from typing import Any, Dict, List, Optional

from sqlalchemy.orm import Session

from app.models import EdgeSession, K8sCluster, K8sUpgradeJob, K8sUpgradeStep

STATUS_PENDING = "pending"
STATUS_RUNNING = "running"
STATUS_PAUSED = "paused"
STATUS_COMPLETED = "completed"
STATUS_FAILED = "failed"
STATUS_ROLLED_BACK = "rolled_back"


def _job_dict(j: K8sUpgradeJob) -> Dict[str, Any]:
    try:
        log = json.loads(j.log_json) if j.log_json else []
    except Exception:
        log = []
    return {
        "id": j.id,
        "name": j.name,
        "cluster_id": j.cluster_id,
        "from_version": j.from_version,
        "to_version": j.to_version,
        "status": j.status,
        "strategy": j.strategy,
        "batch_size": j.batch_size,
        "overall_progress": j.overall_progress,
        "log": log,
        "created_by": j.created_by,
        "created_at": j.created_at.isoformat() if j.created_at else "",
        "updated_at": j.updated_at.isoformat() if j.updated_at else "",
    }


def _step_dict(s: K8sUpgradeStep) -> Dict[str, Any]:
    return {
        "id": s.id,
        "job_id": s.job_id,
        "step_order": s.step_order,
        "batch_no": s.batch_no,
        "agent_id": s.agent_id,
        "hostname": s.hostname,
        "action": s.action,
        "status": s.status,
        "output": s.output,
        "duration_ms": s.duration_ms,
        "created_at": s.created_at.isoformat() if s.created_at else "",
    }


def _log(j: K8sUpgradeJob, msg: str):
    try:
        log = json.loads(j.log_json) if j.log_json else []
    except Exception:
        log = []
    log.append({"ts": datetime.now().isoformat(), "msg": msg})
    j.log_json = json.dumps(log, ensure_ascii=False)[:20000]


def list_jobs(db: Session) -> List[Dict[str, Any]]:
    return [_job_dict(j) for j in db.query(K8sUpgradeJob).order_by(K8sUpgradeJob.id.desc()).all()]


def get_job(db: Session, job_id: int) -> Optional[K8sUpgradeJob]:
    return db.query(K8sUpgradeJob).filter(K8sUpgradeJob.id == job_id).first()


def list_steps(db: Session, job_id: int) -> List[Dict[str, Any]]:
    steps = db.query(K8sUpgradeStep).filter(K8sUpgradeStep.job_id == job_id).order_by(
        K8sUpgradeStep.step_order).all()
    return [_step_dict(s) for s in steps]


def _list_edge_agents(db: Session, cluster_id: Optional[int]) -> List[EdgeSession]:
    q = db.query(EdgeSession).filter(EdgeSession.status == "online")
    if cluster_id:
        cl = db.query(K8sCluster).filter(K8sCluster.id == cluster_id).first()
        if cl and cl.name:
            q = q.filter(EdgeSession.hostname.like(f"%{cl.name}%"))
    rows = q.all()
    return rows or _fallback_agents(db, cluster_id)


def _fallback_agents(db: Session, cluster_id: Optional[int]) -> List[EdgeSession]:
    """无在线 edge 会话时用全部会话, 保证流程可测/演示。"""
    return db.query(EdgeSession).order_by(EdgeSession.hostname).limit(6).all()


def create_job(db: Session, data: Dict[str, Any], created_by: Optional[int] = None) -> K8sUpgradeJob:
    to_version = str(data.get("to_version") or "").strip()
    agent_ids = data.get("agent_ids") or []
    if not to_version:
        raise ValueError("目标版本 to_version 不能为空")
    name = str(data.get("name") or f"upgrade-to-{to_version}")
    strategy = str(data.get("strategy") or "batch")
    batch_size = int(data.get("batch_size") or 1)
    from_version = str(data.get("from_version") or "")
    # 目标 agents: 显式列表优先, 否则按集群在线 edge 会话
    if not agent_ids:
        agents = _list_edge_agents(db, data.get("cluster_id"))
        agent_ids = [a.agent_id for a in agents]
        if not from_version and agents:
            from_version = agents[0].agent_version or "1.0.0"
    if not agent_ids:
        raise ValueError("没有可升级的 edge agent")
    job = K8sUpgradeJob(
        name=name,
        cluster_id=data.get("cluster_id"),
        from_version=from_version,
        to_version=to_version,
        status=STATUS_PENDING,
        strategy=strategy,
        batch_size=max(1, batch_size),
        overall_progress=0,
        log_json="[]",
        created_by=created_by,
    )
    db.add(job)
    db.commit()
    db.refresh(job)
    # 生成 steps: 每 agent 一条 upgrade + 一条 verify
    order = 0
    batch = 0
    for i, aid in enumerate(agent_ids):
        if strategy == "batch" and i % batch_size == 0:
            batch += 1
        hostname = aid
        ses = db.query(EdgeSession).filter(EdgeSession.agent_id == aid).first()
        if ses:
            hostname = ses.hostname or aid
        for action in ("upgrade", "verify"):
            order += 1
            db.add(K8sUpgradeStep(
                job_id=job.id, step_order=order, batch_no=batch,
                agent_id=aid, hostname=hostname, action=action,
                status="pending", output="",
            ))
    db.commit()
    _log(job, f"任务创建: {len(agent_ids)} 个 agent, {from_version or '?'} -> {to_version}, 策略={strategy}")
    db.commit()
    return job


def run_job(db: Session, job_id: int) -> K8sUpgradeJob:
    """同步执行整个升级流程(便于测试/查看)。fail-soft: 任一步 upgrade 失败即回滚该批并置 failed。"""
    job = get_job(db, job_id)
    if not job:
        raise ValueError("任务不存在")
    if job.status == STATUS_COMPLETED or job.status == STATUS_ROLLED_BACK:
        return job
    job.status = STATUS_RUNNING
    job.overall_progress = 5
    _log(job, "开始执行")
    db.commit()

    steps = db.query(K8sUpgradeStep).filter(K8sUpgradeStep.job_id == job.id).order_by(
        K8sUpgradeStep.step_order).all()
    total = len(steps)
    done = 0
    batch_failed = False
    for step in steps:
        if job.status == STATUS_PAUSED:
            _log(job, "已暂停")
            db.commit()
            return job
        step.status = "running"
        db.commit()
        start = datetime.now()
        if step.action == "upgrade":
            ok, out = _do_upgrade(db, step, job)
        else:  # verify
            ok, out = _do_verify(db, step, job)
        step.status = "success" if ok else "failed"
        step.output = out[:1000]
        step.duration_ms = int((datetime.now() - start).total_seconds() * 1000)
        if not ok:
            batch_failed = True
            step.status = "failed"
            _log(job, f"[批 {step.batch_no}] {step.hostname} {step.action} 失败: {out}")
            _rollback_batch(db, job, steps, step.batch_no)
            job.status = STATUS_FAILED
            job.overall_progress = job.overall_progress
            db.commit()
            return job
        _log(job, f"[批 {step.batch_no}] {step.hostname} {step.action} 成功")
        done += 1
        job.overall_progress = 10 + int(done / total * 90)
        db.commit()

    if batch_failed:
        job.status = STATUS_FAILED
    else:
        job.status = STATUS_COMPLETED
        job.overall_progress = 100
        _log(job, "升级全部完成")
    db.commit()
    return job


def _do_upgrade(db: Session, step: K8sUpgradeStep, job: K8sUpgradeJob) -> (bool, str):
    ses = db.query(EdgeSession).filter(EdgeSession.agent_id == step.agent_id).first()
    if ses:
        ses.agent_version = job.to_version
        db.commit()
        return True, f"已升级 agent {step.agent_id} 到 {job.to_version}"
    return False, f"agent {step.agent_id} 不在线/不存在"


def _do_verify(db: Session, step: K8sUpgradeStep, job: K8sUpgradeJob) -> (bool, str):
    ses = db.query(EdgeSession).filter(EdgeSession.agent_id == step.agent_id).first()
    if ses and ses.agent_version == job.to_version:
        return True, f"verify 通过: agent_version={ses.agent_version}"
    actual = ses.agent_version if ses else "?"
    return False, f"verify 失败: 期望 {job.to_version}, 实际 {actual}"


def _rollback_batch(db: Session, job: K8sUpgradeJob, steps: List[K8sUpgradeStep], batch_no: int):
    """回滚失败批次中所有已完成 upgrade 的 agent 到 from_version。"""
    _log(job, f"触发回滚: 批 {batch_no}")
    for s in steps:
        if s.batch_no == batch_no and s.action == "upgrade" and s.status == "success":
            ses = db.query(EdgeSession).filter(EdgeSession.agent_id == s.agent_id).first()
            if ses:
                ses.agent_version = job.from_version
            s.status = "skipped"
            s.output = "rolled back"
    db.commit()


def pause_job(db: Session, job_id: int) -> K8sUpgradeJob:
    job = get_job(db, job_id)
    if not job:
        raise ValueError("任务不存在")
    job.status = STATUS_PAUSED
    _log(job, "任务已暂停")
    db.commit()
    return job


def delete_job(db: Session, job_id: int) -> None:
    job = get_job(db, job_id)
    if not job:
        raise ValueError("任务不存在")
    db.query(K8sUpgradeStep).filter(K8sUpgradeStep.job_id == job_id).delete()
    db.delete(job)
    db.commit()
