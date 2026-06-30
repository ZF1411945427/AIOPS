from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session
from typing import List, Optional
from pydantic import BaseModel, ConfigDict, field_validator
import json
from datetime import datetime, timedelta

from app.database import get_db as get_db_session
from app.models import SLOConfig, ErrorBudget, OnCallSchedule, EscalationPolicy, SLARecord, AvailabilityReport

router = APIRouter(prefix="/api/sre", tags=["sre"])

# ==================== Pydantic 模型 ====================

class SLOConfigCreate(BaseModel):
    service_name: str
    slo_target: float
    window_days: int = 30
    created_by: Optional[str] = None


class SLOConfigResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)
    
    id: int
    service_name: str
    slo_target: float
    window_days: int
    total_requests: int
    error_requests: int
    status: str
    created_at: datetime


class ErrorBudgetCreate(BaseModel):
    slo_id: int
    service_name: str
    period_start: datetime
    period_end: datetime
    budget_total: float = 100
    budget_consumed: float = 0


class ErrorBudgetResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)
    
    id: int
    slo_id: int
    service_name: str
    period_start: datetime
    period_end: datetime
    budget_total: float
    budget_consumed: float
    budget_remaining: float
    burn_rate: float
    status: str


class OnCallScheduleCreate(BaseModel):
    team_name: str
    rotation_type: str = "weekly"
    members: List[str]
    schedule: List[dict]
    current_oncall: str
    current_period_start: datetime
    current_period_end: datetime
    created_by: Optional[str] = None


class OnCallScheduleResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)
    
    id: int
    team_name: str
    rotation_type: str
    members: List[str]
    schedule: List[dict]
    current_oncall: str
    current_period_start: datetime
    current_period_end: datetime

    @field_validator("members", mode="before")
    @classmethod
    def parse_members(cls, v):
        if isinstance(v, str):
            return json.loads(v)
        return v

    @field_validator("schedule", mode="before")
    @classmethod
    def parse_schedule(cls, v):
        if isinstance(v, str):
            return json.loads(v)
        return v


class EscalationPolicyCreate(BaseModel):
    name: str
    levels: List[str]
    wait_minutes: List[int]
    notify_channels: List[str]
    is_active: bool = True
    created_by: Optional[str] = None


class EscalationPolicyResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)
    
    id: int
    name: str
    levels: List[str]
    wait_minutes: List[int]
    notify_channels: List[str]
    is_active: bool

    @field_validator("levels", mode="before")
    @classmethod
    def parse_levels(cls, v):
        if isinstance(v, str):
            return json.loads(v)
        return v

    @field_validator("wait_minutes", mode="before")
    @classmethod
    def parse_wait_minutes(cls, v):
        if isinstance(v, str):
            return json.loads(v)
        return v

    @field_validator("notify_channels", mode="before")
    @classmethod
    def parse_notify_channels(cls, v):
        if isinstance(v, str):
            return json.loads(v)
        return v


# ==================== SLO 接口 ====================

@router.get("/slo", response_model=List[SLOConfigResponse])
def list_slo(db: Session = Depends(get_db_session)):
    """获取 SLO 配置列表"""
    return db.query(SLOConfig).order_by(SLOConfig.id.desc()).all()


@router.post("/slo", response_model=SLOConfigResponse)
def create_slo(data: SLOConfigCreate, db: Session = Depends(get_db_session)):
    """创建 SLO 配置"""
    obj = SLOConfig(
        service_name=data.service_name,
        slo_target=data.slo_target,
        window_days=data.window_days,
        created_by=data.created_by,
        status='healthy'
    )
    db.add(obj)
    db.commit()
    db.refresh(obj)
    return obj


@router.put("/slo/{slo_id}", response_model=SLOConfigResponse)
def update_slo(slo_id: int, data: SLOConfigCreate, db: Session = Depends(get_db_session)):
    """更新 SLO 配置"""
    obj = db.query(SLOConfig).filter(SLOConfig.id == slo_id).first()
    if not obj:
        raise HTTPException(status_code=404, detail="SLO not found")
    obj.service_name = data.service_name
    obj.slo_target = data.slo_target
    obj.window_days = data.window_days
    db.commit()
    db.refresh(obj)
    return obj


@router.delete("/slo/{slo_id}")
def delete_slo(slo_id: int, db: Session = Depends(get_db_session)):
    """删除 SLO 配置"""
    obj = db.query(SLOConfig).filter(SLOConfig.id == slo_id).first()
    if obj:
        db.delete(obj)
        db.commit()
    return {"status": "ok"}


# ==================== Error Budget 接口 ====================

@router.get("/error-budget", response_model=List[ErrorBudgetResponse])
def list_error_budget(db: Session = Depends(get_db_session)):
    """获取错误预算列表"""
    return db.query(ErrorBudget).order_by(ErrorBudget.id.desc()).all()


@router.post("/error-budget", response_model=ErrorBudgetResponse)
def create_error_budget(data: ErrorBudgetCreate, db: Session = Depends(get_db_session)):
    """创建错误预算记录"""
    budget_remaining = data.budget_total - data.budget_consumed
    obj = ErrorBudget(
        slo_id=data.slo_id,
        service_name=data.service_name,
        period_start=data.period_start,
        period_end=data.period_end,
        budget_total=data.budget_total,
        budget_consumed=data.budget_consumed,
        budget_remaining=budget_remaining,
        burn_rate=round(data.budget_consumed / max(1, (data.period_end - data.period_start).days), 2),
        status='healthy' if budget_remaining > 50 else 'warning' if budget_remaining > 20 else 'critical'
    )
    db.add(obj)
    db.commit()
    db.refresh(obj)
    return obj


@router.get("/error-budget/summary")
def get_error_budget_summary(db: Session = Depends(get_db_session)):
    """获取错误预算汇总"""
    budgets = db.query(ErrorBudget).all()
    healthy = sum(1 for b in budgets if b.status == 'healthy')
    warning = sum(1 for b in budgets if b.status == 'warning')
    critical = sum(1 for b in budgets if b.status == 'critical')
    return {
        "total": len(budgets),
        "healthy": healthy,
        "warning": warning,
        "critical": critical
    }


# ==================== On-Call 接口 ====================

@router.get("/oncall", response_model=List[OnCallScheduleResponse])
def list_oncall(db: Session = Depends(get_db_session)):
    """获取值班表列表"""
    return db.query(OnCallSchedule).order_by(OnCallSchedule.id.desc()).all()


@router.post("/oncall", response_model=OnCallScheduleResponse)
def create_oncall(data: OnCallScheduleCreate, db: Session = Depends(get_db_session)):
    """创建值班表"""
    obj = OnCallSchedule(
        team_name=data.team_name,
        rotation_type=data.rotation_type,
        members=json.dumps(data.members),
        schedule=json.dumps(data.schedule),
        current_oncall=data.current_oncall,
        current_period_start=data.current_period_start,
        current_period_end=data.current_period_end,
        created_by=data.created_by
    )
    db.add(obj)
    db.commit()
    db.refresh(obj)
    return obj


@router.get("/oncall/current")
def get_current_oncall(db: Session = Depends(get_db_session)):
    """获取当前值班人"""
    now = datetime.utcnow()
    obj = db.query(OnCallSchedule).filter(
        OnCallSchedule.current_period_start <= now,
        OnCallSchedule.current_period_end >= now
    ).first()
    if obj:
        return {
            "team_name": obj.team_name,
            "current_oncall": obj.current_oncall,
            "period_start": obj.current_period_start,
            "period_end": obj.current_period_end
        }
    return {"team_name": None, "current_oncall": None}


# ==================== Escalation 接口 ====================

@router.get("/escalation", response_model=List[EscalationPolicyResponse])
def list_escalation(db: Session = Depends(get_db_session)):
    """获取升级策略列表"""
    return db.query(EscalationPolicy).order_by(EscalationPolicy.id.desc()).all()


@router.post("/escalation", response_model=EscalationPolicyResponse)
def create_escalation(data: EscalationPolicyCreate, db: Session = Depends(get_db_session)):
    """创建升级策略"""
    obj = EscalationPolicy(
        name=data.name,
        levels=json.dumps(data.levels),
        wait_minutes=json.dumps(data.wait_minutes),
        notify_channels=json.dumps(data.notify_channels),
        is_active=data.is_active,
        created_by=data.created_by
    )
    db.add(obj)
    db.commit()
    db.refresh(obj)
    return obj


@router.delete("/escalation/{policy_id}")
def delete_escalation(policy_id: int, db: Session = Depends(get_db_session)):
    """删除升级策略"""
    obj = db.query(EscalationPolicy).filter(EscalationPolicy.id == policy_id).first()
    if obj:
        db.delete(obj)
        db.commit()
    return {"status": "ok"}


# ==================== Burn Rate 接口 ====================

class BurnRateResponse(BaseModel):
    service_name: str
    slo_target: float
    window_days: int
    error_budget_total: float
    error_budget_remaining: float
    burn_rate_1h: float
    burn_rate_6h: float
    burn_rate_24h: float
    status: str

@router.get("/burn-rate", response_model=List[BurnRateResponse])
def list_burn_rates(db: Session = Depends(get_db_session)):
    """计算所有服务的错误预算消耗速率"""
    slos = db.query(SLOConfig).all()
    results = []
    for slo in slos:
        budgets = db.query(ErrorBudget).filter(
            ErrorBudget.slo_id == slo.id
        ).order_by(ErrorBudget.id.desc()).limit(3).all()

        budget_total = 100.0
        budget_remaining = 100.0
        if budgets:
            budget_total = budgets[0].budget_total
            budget_remaining = budgets[0].budget_remaining

        burn_rate_1h = 0.0
        burn_rate_6h = 0.0
        burn_rate_24h = 0.0

        if budgets and len(budgets) >= 2:
            consumed_diff = budgets[0].budget_consumed - budgets[-1].budget_consumed
            hours_diff = max(1, (budgets[0].created_at - budgets[-1].created_at).total_seconds() / 3600)
            avg_rate = consumed_diff / hours_diff if hours_diff > 0 else 0
            burn_rate_1h = round(avg_rate, 4)
            burn_rate_6h = round(avg_rate * 6, 4)
            burn_rate_24h = round(avg_rate * 24, 4)

        status = "healthy"
        if burn_rate_1h > 10 or budget_remaining < 20:
            status = "critical"
        elif burn_rate_1h > 5 or budget_remaining < 50:
            status = "warning"

        results.append(BurnRateResponse(
            service_name=slo.service_name,
            slo_target=slo.slo_target,
            window_days=slo.window_days,
            error_budget_total=budget_total,
            error_budget_remaining=budget_remaining,
            burn_rate_1h=burn_rate_1h,
            burn_rate_6h=burn_rate_6h,
            burn_rate_24h=burn_rate_24h,
            status=status
        ))
    return results


# ==================== SLA 接口 ====================

class SLARecordCreate(BaseModel):
    service_name: str
    sla_target: float
    period_start: datetime
    period_end: datetime
    uptime_seconds: int = 0
    downtime_seconds: int = 0

class SLARecordResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)
    id: int
    service_name: str
    sla_target: float
    period_start: datetime
    period_end: datetime
    uptime_seconds: int
    downtime_seconds: int
    achieved_sla: float
    penalty: str
    status: str
    created_at: datetime

@router.get("/sla", response_model=List[SLARecordResponse])
def list_sla_records(db: Session = Depends(get_db_session)):
    """获取 SLA 记录列表"""
    return db.query(SLARecord).order_by(SLARecord.id.desc()).all()

@router.post("/sla", response_model=SLARecordResponse)
def create_sla_record(data: SLARecordCreate, db: Session = Depends(get_db_session)):
    """创建 SLA 记录"""
    total_secs = data.uptime_seconds + data.downtime_seconds
    achieved = round(data.uptime_seconds / max(1, total_secs), 4)

    if achieved >= data.sla_target:
        penalty = "none"
    elif achieved >= data.sla_target * 0.99:
        penalty = "warning"
    else:
        penalty = "penalty"

    obj = SLARecord(
        service_name=data.service_name,
        sla_target=data.sla_target,
        period_start=data.period_start,
        period_end=data.period_end,
        uptime_seconds=data.uptime_seconds,
        downtime_seconds=data.downtime_seconds,
        achieved_sla=achieved,
        penalty=penalty,
        status="active"
    )
    db.add(obj)
    db.commit()
    db.refresh(obj)
    return obj

@router.delete("/sla/{record_id}")
def delete_sla_record(record_id: int, db: Session = Depends(get_db_session)):
    """删除 SLA 记录"""
    obj = db.query(SLARecord).filter(SLARecord.id == record_id).first()
    if obj:
        db.delete(obj)
        db.commit()
    return {"status": "ok"}


# ==================== Availability 接口 ====================

class AvailabilityReportResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)
    id: int
    service_name: str
    report_date: datetime
    total_uptime: int
    total_downtime: int
    availability_pct: float
    incident_count: int
    total_duration: int
    created_at: datetime

@router.get("/availability", response_model=List[AvailabilityReportResponse])
def list_availability_reports(db: Session = Depends(get_db_session)):
    """获取可用性报表列表"""
    return db.query(AvailabilityReport).order_by(AvailabilityReport.id.desc()).all()

@router.post("/availability/generate")
def generate_availability_report(db: Session = Depends(get_db_session)):
    """从 SLO 和错误预算数据生成可用性报表"""
    slos = db.query(SLOConfig).all()
    if not slos:
        return {"status": "ok", "message": "没有 SLO 配置", "count": 0}

    count = 0
    now = datetime.utcnow()
    for slo in slos:
        budgets = db.query(ErrorBudget).filter(
            ErrorBudget.slo_id == slo.id
        ).order_by(ErrorBudget.id.desc()).limit(30).all()

        total_downtime = 0
        for b in budgets:
            consumed_pct = b.budget_consumed / max(1, b.budget_total)
            window_secs = (b.period_end - b.period_start).total_seconds()
            total_downtime += int(window_secs * (consumed_pct / 100))

        total_uptime_secs = 30 * 24 * 3600 - total_downtime
        avail_pct = round(total_uptime_secs / (30 * 24 * 3600) * 100, 4)

        report = AvailabilityReport(
            service_name=slo.service_name,
            report_date=now,
            total_uptime=total_uptime_secs,
            total_downtime=total_downtime,
            availability_pct=avail_pct,
            incident_count=len(budgets),
            total_duration=30 * 24 * 3600
        )
        db.add(report)
        count += 1

    db.commit()
    return {"status": "ok", "message": f"已生成 {count} 条可用性报告", "count": count}

@router.delete("/availability/{report_id}")
def delete_availability_report(report_id: int, db: Session = Depends(get_db_session)):
    """删除可用性报表"""
    obj = db.query(AvailabilityReport).filter(AvailabilityReport.id == report_id).first()
    if obj:
        db.delete(obj)
        db.commit()
    return {"status": "ok"}
