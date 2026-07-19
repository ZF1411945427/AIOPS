from datetime import datetime

from sqlalchemy.orm import Session

from app.models import SystemConfig


DEFAULT_CONFIGS = {
    "background_interval": {"value": "10", "description": "后台采集间隔(秒)"},
    "data_retention_days": {"value": "30", "description": "指标数据保留天数"},
    "alert_retention_days": {"value": "90", "description": "告警数据保留天数"},
    "escalation_minutes": {"value": "5", "description": "告警升级时间(分钟)"},
    "dedup_window_minutes": {"value": "5", "description": "告警去重窗口(分钟)"},
    "storm_threshold": {"value": "3", "description": "告警风暴阈值(条/分钟)"},
    "incident_window_minutes": {"value": "15", "description": "故障关联时间窗口 (分钟)"},
    "smtp_host": {"value": "", "description": "SMTP 服务器地址"},
    "smtp_port": {"value": "587", "description": "SMTP 服务器端口"},
    "smtp_user": {"value": "", "description": "SMTP user"},
    "smtp_password": {"value": "", "description": "SMTP 密码"},
    "smtp_recipients": {"value": "", "description": "SMTP 收件人列表"},
    "asset_probe_enabled": {"value": "true", "description": "是否启用资产定时探测"},
    "asset_probe_interval": {"value": "60", "description": "资产探测间隔 (秒)"},
    "asset_probe_timeout": {"value": "10", "description": "单次探测超时 (秒)"},
    "metric_collect_enabled": {"value": "true", "description": "是否启用指标采集"},
    "metric_collect_interval": {"value": "60", "description": "指标采集间隔 (秒)"},
    "tenant_mode": {"value": "false", "description": "是否启用多租户模式（true/false）"},
    "incident_approval_enabled": {"value": "false", "description": "是否启用故障单审批角色校验（true/false）。关闭=任何人可审批；开启=仅审批人列表中的用户可审批"},
    "incident_approvers": {"value": "", "description": "故障单审批人 user_id 列表（逗号分隔，如 1,2,3）。仅当 incident_approval_enabled=true 时生效"},
}


def init_configs(db: Session):
    for key, cfg in DEFAULT_CONFIGS.items():
        existing = db.query(SystemConfig).filter(SystemConfig.key == key).first()
        if not existing:
            db.add(SystemConfig(
                key=key, config_value=cfg["value"], description=cfg["description"],
            ))
    db.commit()


def get_config(db: Session, key: str, default: str = "") -> str:
    cfg = db.query(SystemConfig).filter(SystemConfig.key == key).first()
    return cfg.config_value if cfg else default


def get_all_configs(db: Session):
    configs = db.query(SystemConfig).order_by(SystemConfig.id).all()
    result = {}
    for c in configs:
        result[c.key] = {"value": c.config_value, "description": c.description}
    return result


def update_config(db: Session, key: str, value: str):
    cfg = db.query(SystemConfig).filter(SystemConfig.key == key).first()
    if cfg:
        cfg.config_value = value
        cfg.updated_at = datetime.now()
    else:
        cfg = SystemConfig(key=key, config_value=value)
        db.add(cfg)
    db.commit()
    return cfg


def update_configs(db: Session, configs: dict):
    for key, value in configs.items():
        update_config(db, key, value)



