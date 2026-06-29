import json
import random
from datetime import datetime, timedelta
from typing import List, Optional

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, ConfigDict
from sqlalchemy.orm import Session
from sqlalchemy import func

from app.database import get_db
from app.models import ChaosExperiment, ChaosRun, ChaosScenario

router = APIRouter(prefix="/api/chaos", tags=["chaos"])


# ==================== Pydantic 模型 ====================

class FaultParams(BaseModel):
    duration: int = 300
    kill_percentage: Optional[int] = None
    load_percentage: Optional[int] = None
    fill_mb: Optional[int] = None
    latency_ms: Optional[int] = None
    percentage: Optional[int] = None
    loss_percent: Optional[int] = None
    fill_percent: Optional[int] = None


class SteadyState(BaseModel):
    metric: str = "availability"
    threshold: float = 99.0


class TargetSelector(BaseModel):
    service: str = ""
    namespace: str = "default"


class ExperimentCreate(BaseModel):
    name: str
    description: str = ""
    target_type: str = "pod"
    target_selector: TargetSelector
    fault_type: str
    fault_params: FaultParams
    steady_state: SteadyState


class ScenarioCreate(BaseModel):
    name: str
    description: str = ""
    category: str = "pod"
    fault_type: str = "pod-kill"
    fault_params: FaultParams
    risk_level: str = "low"
    recommended_slo: str = ""


# ==================== 内置场景数据 ====================

BUILTIN_SCENARIOS = [
    {"name": "Pod 意外终止", "description": "随机杀掉目标服务的 Pod，验证 K8s 自动恢复能力", "category": "pod", "fault_type": "pod-kill", "fault_params": {"duration": 180, "kill_percentage": 50}, "risk_level": "medium", "recommended_slo": "payment-service"},
    {"name": "CPU 爆炸", "description": "对目标 Pod 注入 CPU 压力，测试 HPA 弹性伸缩", "category": "cpu", "fault_type": "cpu-stress", "fault_params": {"duration": 300, "load_percentage": 80}, "risk_level": "high", "recommended_slo": "user-service"},
    {"name": "内存泄漏模拟", "description": "填充 Pod 内存，验证 OOM Kill 和资源限制", "category": "memory", "fault_type": "mem-stress", "fault_params": {"duration": 240, "fill_mb": 512}, "risk_level": "high", "recommended_slo": "inventory-service"},
    {"name": "网络延迟注入", "description": "在服务间加入延迟，测试超时和重试机制", "category": "network", "fault_type": "network-delay", "fault_params": {"duration": 200, "latency_ms": 500, "percentage": 50}, "risk_level": "medium", "recommended_slo": "gateway-service"},
    {"name": "网络丢包模拟", "description": "模拟网络不稳定场景，验证熔断降级", "category": "network", "fault_type": "network-loss", "fault_params": {"duration": 200, "loss_percent": 30}, "risk_level": "high", "recommended_slo": "gateway-service"},
    {"name": "磁盘空间告警", "description": "填充磁盘触发告警，验证监控和自愈", "category": "disk", "fault_type": "disk-fill", "fault_params": {"duration": 300, "fill_percent": 90}, "risk_level": "low", "recommended_slo": "log-service"},
]


# ==================== Helper ====================

def get_fault_params_dict(fp) -> dict:
    return fp.model_dump(exclude_none=True) if hasattr(fp, 'model_dump') else {}


# ==================== 摘要接口 ====================

@router.get("/summary")
def get_summary(db: Session = Depends(get_db)):
    experiments = db.query(ChaosExperiment).count()
    runs = db.query(ChaosRun).count()
    passed = db.query(ChaosRun).filter(ChaosRun.steady_state_passed.is_(True)).count()
    failed = db.query(ChaosRun).filter(ChaosRun.steady_state_passed.is_(False)).count()
    total_alerts = db.query(func.coalesce(func.sum(ChaosRun.alerts_triggered), 0)).scalar() or 0

    fault_types = db.query(ChaosExperiment.fault_type, func.count(ChaosExperiment.id)).group_by(ChaosExperiment.fault_type).all()
    fault_distribution = {ft: cnt for ft, cnt in fault_types}

    pass_rate = round((passed / runs * 100) if runs else 100, 1)
    active_schedules = db.query(ChaosExperiment).filter(ChaosExperiment.status == "running").count()

    return {
        "total_experiments": experiments,
        "pass_rate": pass_rate,
        "total_runs": runs,
        "active_schedules": active_schedules,
        "passed": passed,
        "failed": failed,
        "total_alerts": total_alerts,
        "fault_distribution": fault_distribution,
    }


# ==================== 实验 CRUD ====================

@router.get("/experiments")
def list_experiments(db: Session = Depends(get_db)):
    exps = db.query(ChaosExperiment).order_by(ChaosExperiment.id.desc()).all()
    results = []
    for e in exps:
        results.append({
            "id": e.id,
            "name": e.name,
            "description": e.description,
            "fault_type": e.fault_type,
            "target_selector": json.loads(e.target_selector) if e.target_selector else {},
            "target_type": e.target_type,
            "fault_params": json.loads(e.fault_params) if e.fault_params else {},
            "steady_state": json.loads(e.steady_state) if e.steady_state else {},
            "status": e.status,
            "result": e.result,
            "started_at": e.started_at.isoformat() if e.started_at else None,
            "finished_at": e.finished_at.isoformat() if e.finished_at else None,
            "created_at": e.created_at.isoformat() if e.created_at else None,
        })
    return results


@router.post("/experiments")
def create_experiment(body: ExperimentCreate, db: Session = Depends(get_db)):
    exp = ChaosExperiment(
        name=body.name,
        description=body.description,
        target_type=body.target_type,
        target_selector=body.target_selector.model_dump_json(),
        fault_type=body.fault_type,
        fault_params=body.fault_params.model_dump_json(),
        steady_state=body.steady_state.model_dump_json(),
        status="pending",
    )
    db.add(exp)
    db.commit()
    db.refresh(exp)
    return {"id": exp.id, "name": exp.name, "status": "pending"}


@router.post("/experiments/{exp_id}/start")
def start_experiment(exp_id: int, db: Session = Depends(get_db)):
    exp = db.query(ChaosExperiment).filter(ChaosExperiment.id == exp_id).first()
    if not exp:
        raise HTTPException(404, "实验不存在")
    exp.status = "running"
    exp.started_at = datetime.now()
    db.commit()

    fp = json.loads(exp.fault_params) if exp.fault_params else {}
    duration = fp.get("duration", 300)

    import time, math
    time.sleep(2)

    before = {"availability": round(random.uniform(99.0, 100.0), 2)}
    passed = random.random() < 0.75
    after = {"availability": round(random.uniform(95.0 if not passed else 99.0, 100.0), 2)}
    alerts = random.randint(0, 5)

    run = ChaosRun(
        experiment_id=exp.id,
        steady_state_passed=passed,
        alerts_triggered=alerts,
        error_budget_impact=round(random.uniform(0.5, 8.0), 2),
        duration_seconds=duration,
        steady_state_before=json.dumps(before),
        steady_state_after=json.dumps(after),
        notes=f"实验 {exp.name}: {'稳态通过' if passed else '稳态未通过'}",
    )
    db.add(run)

    exp.status = "completed"
    exp.result = "passed" if passed else "failed"
    exp.finished_at = datetime.now()
    db.commit()
    db.refresh(run)

    return {
        "id": run.id,
        "steady_state_passed": passed,
        "alerts_triggered": alerts,
        "error_budget_impact": run.error_budget_impact,
        "duration_seconds": duration,
        "steady_state_before": before,
        "steady_state_after": after,
    }


@router.post("/experiments/{exp_id}/abort")
def abort_experiment(exp_id: int, db: Session = Depends(get_db)):
    exp = db.query(ChaosExperiment).filter(ChaosExperiment.id == exp_id).first()
    if not exp:
        raise HTTPException(404, "实验不存在")
    exp.status = "aborted"
    exp.finished_at = datetime.now()
    db.commit()
    return {"message": "已终止"}


@router.delete("/experiments/{exp_id}")
def delete_experiment(exp_id: int, db: Session = Depends(get_db)):
    exp = db.query(ChaosExperiment).filter(ChaosExperiment.id == exp_id).first()
    if not exp:
        raise HTTPException(404, "实验不存在")
    db.query(ChaosRun).filter(ChaosRun.experiment_id == exp_id).delete()
    db.delete(exp)
    db.commit()
    return {"message": "已删除"}


# ==================== 运行历史 ====================

@router.get("/experiments/{exp_id}/runs")
def get_experiment_runs(exp_id: int, db: Session = Depends(get_db)):
    runs = db.query(ChaosRun).filter(ChaosRun.experiment_id == exp_id).order_by(ChaosRun.id.desc()).all()
    results = []
    for r in runs:
        results.append({
            "id": r.id,
            "experiment_id": r.experiment_id,
            "steady_state_passed": r.steady_state_passed,
            "alerts_triggered": r.alerts_triggered,
            "error_budget_impact": r.error_budget_impact,
            "duration_seconds": r.duration_seconds,
            "steady_state_before": json.loads(r.steady_state_before) if r.steady_state_before else {},
            "steady_state_after": json.loads(r.steady_state_after) if r.steady_state_after else {},
            "notes": r.notes,
            "started_at": r.started_at.isoformat() if r.started_at else None,
        })
    return results


# ==================== 趋势图 ====================

@router.get("/trend")
def get_trend(db: Session = Depends(get_db)):
    days = 30
    dates = []
    runs_data = []
    passed_data = []
    failed_data = []
    now = datetime.now()

    for i in range(days, -1, -1):
        day = now - timedelta(days=i)
        day_start = day.replace(hour=0, minute=0, second=0, microsecond=0)
        day_end = day_start + timedelta(days=1)
        dates.append(day.strftime("%m-%d"))

        day_runs = db.query(ChaosRun).filter(
            ChaosRun.started_at >= day_start,
            ChaosRun.started_at < day_end,
        ).count()
        day_passed = db.query(ChaosRun).filter(
            ChaosRun.started_at >= day_start,
            ChaosRun.started_at < day_end,
            ChaosRun.steady_state_passed.is_(True),
        ).count()
        day_failed = db.query(ChaosRun).filter(
            ChaosRun.started_at >= day_start,
            ChaosRun.started_at < day_end,
            ChaosRun.steady_state_passed.is_(False),
        ).count()

        runs_data.append(day_runs)
        passed_data.append(day_passed)
        failed_data.append(day_failed)

    return {"dates": dates, "runs": runs_data, "passed": passed_data, "failed": failed_data}


# ==================== 韧性雷达 ====================

@router.get("/resilience-radar")
def get_resilience_radar(db: Session = Depends(get_db)):
    dimensions = ["Pod 故障", "CPU 压力", "内存压力", "网络延迟", "网络丢包", "磁盘填充"]
    values = []
    for ft in ["pod-kill", "cpu-stress", "mem-stress", "network-delay", "network-loss", "disk-fill"]:
        total = db.query(ChaosRun).join(ChaosExperiment).filter(ChaosExperiment.fault_type == ft).count()
        passed = db.query(ChaosRun).join(ChaosExperiment).filter(
            ChaosExperiment.fault_type == ft,
            ChaosRun.steady_state_passed.is_(True),
        ).count()
        score = round((passed / total * 100) if total else random.uniform(60, 95), 1)
        values.append(score)
    return {"dimensions": dimensions, "values": values}


# ==================== 场景库 ====================

@router.get("/scenarios")
def list_scenarios(db: Session = Depends(get_db)):
    scenarios = db.query(ChaosScenario).order_by(ChaosScenario.is_builtin.desc(), ChaosScenario.id).all()
    results = []
    for s in scenarios:
        results.append({
            "id": s.id,
            "name": s.name,
            "description": s.description,
            "category": s.category,
            "fault_type": s.fault_type,
            "fault_params": json.loads(s.fault_params) if s.fault_params else {},
            "risk_level": s.risk_level,
            "recommended_slo": s.recommended_slo,
            "is_builtin": s.is_builtin,
        })
    return results


@router.post("/scenarios")
def create_scenario(body: ScenarioCreate, db: Session = Depends(get_db)):
    scenario = ChaosScenario(
        name=body.name,
        description=body.description,
        category=body.category,
        fault_type=body.fault_type,
        fault_params=body.fault_params.model_dump_json(),
        risk_level=body.risk_level,
        recommended_slo=body.recommended_slo,
        is_builtin=False,
    )
    db.add(scenario)
    db.commit()
    db.refresh(scenario)
    return {"id": scenario.id, "name": scenario.name, "is_builtin": False}


@router.delete("/scenarios/{scenario_id}")
def delete_scenario(scenario_id: int, db: Session = Depends(get_db)):
    s = db.query(ChaosScenario).filter(ChaosScenario.id == scenario_id).first()
    if not s:
        raise HTTPException(404, "场景不存在")
    if s.is_builtin:
        raise HTTPException(400, "内置场景不可删除")
    db.delete(s)
    db.commit()
    return {"message": "已删除"}


# ==================== 种子数据 ====================

def seed_chaos_scenarios(db: Session):
    if db.query(ChaosScenario).count() > 0:
        return
    for bs in BUILTIN_SCENARIOS:
        s = ChaosScenario(
            name=bs["name"],
            description=bs["description"],
            category=bs["category"],
            fault_type=bs["fault_type"],
            fault_params=json.dumps(bs["fault_params"]),
            risk_level=bs["risk_level"],
            recommended_slo=bs["recommended_slo"],
            is_builtin=True,
        )
        db.add(s)
    db.commit()
