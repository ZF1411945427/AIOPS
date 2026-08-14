"""域模型: sre (H2 models 拆分) - 各域模型, 无跨文件循环引用(全字符串FK)。"""


from datetime import datetime

from sqlalchemy import Column, Integer, String, Float, Boolean, DateTime, ForeignKey, Text

from app.database import Base


class SLOConfig(Base):
    __tablename__ = "slo_configs"
    """SLO 配置"""
    id = Column(Integer, primary_key=True)
    service_name = Column(String(100), nullable=False)  # 服务名
    slo_target = Column(Float, nullable=False)       # 目标可用性 0.999
    window_days = Column(Integer, default=30)       # 窗口天数
    total_requests = Column(Integer, default=0)      # 总请求数
    error_requests = Column(Integer, default=0)     # 错误请求数
    status = Column(String(20), default='healthy')   # healthy/warning/critical
    created_by = Column(String(50))
    created_at = Column(DateTime, default=datetime.utcnow)
    updated_at = Column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)


class ErrorBudget(Base):
    __tablename__ = "error_budgets"
    """错误预算记录"""
    id = Column(Integer, primary_key=True)
    slo_id = Column(Integer, ForeignKey('slo_configs.id'))  # 关联的 SLO
    service_name = Column(String(100), nullable=False)
    period_started_at = Column(DateTime)                     # 周期开始
    period_ended_at = Column(DateTime)                     # 周期结束
    budget_total = Column(Float, default=100)       # 总预算 %
    budget_consumed = Column(Float, default=0)      # 已消耗 %
    budget_remaining = Column(Float, default=100)     # 剩余 %
    burn_rate = Column(Float, default=0)              # 消耗速率
    status = Column(String(20), default='healthy')
    created_at = Column(DateTime, default=datetime.utcnow)


class OnCallSchedule(Base):
    __tablename__ = "oncall_schedules"
    """值班表"""
    id = Column(Integer, primary_key=True)
    team_name = Column(String(50), nullable=False)  # 团队名
    rotation_type = Column(String(20), default='weekly')  # weekly/monthly
    members = Column(Text)                          # 成员列表 JSON
    schedule = Column(Text)                         # 轮值表 JSON
    current_oncall = Column(String(50))             # 当前值班人
    current_period_started_at = Column(DateTime)         # 当前周期开始
    current_period_ended_at = Column(DateTime)          # 当前周期结束
    is_auto_rotate = Column(Boolean, default=True)     # 是否自动轮转
    holidays = Column(Text, default="[]")           # 节假日 JSON 列表
    created_by = Column(String(50))
    created_at = Column(DateTime, default=datetime.utcnow)
    updated_at = Column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)


class EscalationPolicy(Base):
    __tablename__ = "escalation_policies"
    """升级策略"""
    id = Column(Integer, primary_key=True)
    name = Column(String(100), nullable=False)       # 策略名
    levels = Column(Text)                           # 升级级别 JSON
    wait_minutes = Column(Text)                      # 每级等待时间 JSON
    notify_channels = Column(Text)                  # 通知渠道 JSON
    is_active = Column(Boolean, default=True)
    created_by = Column(String(50))
    created_at = Column(DateTime, default=datetime.utcnow)
    updated_at = Column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)


class SLARecord(Base):
    __tablename__ = "sla_records"
    """SLA 协议记录"""
    id = Column(Integer, primary_key=True)
    service_name = Column(String(100), nullable=False)
    sla_target = Column(Float, nullable=False)        # SLA 目标 0.999
    period_started_at = Column(DateTime)
    period_ended_at = Column(DateTime)
    uptime_seconds = Column(Integer, default=0)
    downtime_seconds = Column(Integer, default=0)
    achieved_sla = Column(Float, default=0.0)         # 实际达成的 SLA
    penalty = Column(String(50), default="none")       # 处罚: none/warning/penalty
    status = Column(String(20), default="active")
    created_at = Column(DateTime, default=datetime.utcnow)


class AvailabilityReport(Base):
    __tablename__ = "availability_reports"
    """可用性报告"""
    id = Column(Integer, primary_key=True)
    service_name = Column(String(100), nullable=False)
    reported_at = Column(DateTime)                     # 报告日期
    total_uptime = Column(Integer, default=0)          # 总运行时间(秒)
    total_downtime = Column(Integer, default=0)        # 总停机时间(秒)
    availability_pct = Column(Float, default=100.0)    # 可用性百分比
    incident_count = Column(Integer, default=0)         # 故障次数
    total_duration = Column(Integer, default=0)         # 总时长(秒)
    created_at = Column(DateTime, default=datetime.utcnow)
