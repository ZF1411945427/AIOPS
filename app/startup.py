"""启动初始化: 种子数据/后台任务/安全检测。从 main.py 拆出。"""
import json
import os as _os
import threading
import time
from datetime import datetime, timedelta
from concurrent.futures import ThreadPoolExecutor, as_completed

from app.database import get_session_for, get_db_mode
from app.logger import logger
from app import config as _config
from app.security import verify_password
from app.models import User, NotificationChannel, AnomalyConfig, ReportSchedule, MetricRecord
from app.services import alert_service, anomaly_service, incident_service, remediation_service, datasource_service, config_service, pod_health_service, log_anomaly_service, contention_service, metric_collector, asset_service, trace_anomaly_service
from app.services import agent_workflow_service, workflow_cron_scheduler, auto_investigator
from app.services.synthetic_monitor import check_all_synthetics
from app.services import skill_registry

_scan_builtin_skills = skill_registry.scan_builtin_skills

BACKGROUND_INTERVAL = 10
_last_probe_time = 0
_last_collect_time = 0.0
_last_archive_time = 0.0
_last_scrape_time = 0.0
_last_autonomous_time = 0.0
METRIC_RETENTION_DAYS = int(_os.environ.get("AIOPS_METRIC_RETENTION_DAYS", "90"))


def _collect_all_menu_keys() -> list:
    """从 menu_config.json 收集所有菜单 key（含分组 item 叶子）"""
    _p = _os.path.join(_os.path.dirname(_os.path.abspath(__file__)), "routers", "menu_config.json")
    if _os.path.exists(_p):
        with open(_p, encoding="utf-8") as _f:
            _menu = json.load(_f)
    else:
        _menu = []
    _keys = set()
    for _g in _menu:
        _keys.add(_g["key"])
        for _i in _g.get("items", []):
            _keys.add(_i["key"])
            for _s in _i.get("items", []):
                _keys.add(_s["key"])
    return list(_keys)


def init_admin():
    db = get_session_for(get_db_mode())()
    _admin_role = None
    from app.models import Role as _Role, RoleMenu as _RoleMenu
    _preset_roles = [
        {"name": "admin", "description": "系统管理员，拥有全部权限", "is_system": True, "sort_order": 0},
        {"name": "operator", "description": "运维工程师，可执行操作", "is_system": True, "sort_order": 1},
        {"name": "viewer", "description": "只读用户，仅可查看", "is_system": True, "sort_order": 2},
    ]
    try:
        for _pr in _preset_roles:
            _existing = db.query(_Role).filter(_Role.name == _pr["name"]).first()
            if not _existing:
                db.add(_Role(**_pr))
        db.commit()
        _admin_role = db.query(_Role).filter(_Role.name == "admin").first()
    except Exception:
        import logging
        logging.getLogger(__name__).warning("init_admin 种子角色失败(DB 忙/锁), 跳过本次: ", exc_info=True)
        db.rollback()
        _admin_role = db.query(_Role).filter(_Role.name == "admin").first()
    user = db.query(User).filter(User.username == "admin").first()
    if not user:
        from app.security import hash_password
        default_pwd = _os.environ.get("AIOPS_ADMIN_PASSWORD", "admin123")
        admin = User(
            username="admin",
            password_hash=hash_password(default_pwd),
            role="admin",
            role_id=_admin_role.id if _admin_role else None,
        )
        db.add(admin)
        db.commit()
        if _admin_role:
            _existing_menus = db.query(_RoleMenu).filter(_RoleMenu.role_id == _admin_role.id).count()
            if _existing_menus == 0:
                _all_keys = _collect_all_menu_keys()
                for _k in _all_keys:
                    db.add(_RoleMenu(role_id=_admin_role.id, menu_key=_k))
                db.commit()
    if _admin_role:
        _existing_admin_keys = set(_k for _k, in db.query(_RoleMenu.menu_key).filter(_RoleMenu.role_id == _admin_role.id).all())
        for _new_key in _collect_all_menu_keys():
            if _new_key not in _existing_admin_keys:
                db.add(_RoleMenu(role_id=_admin_role.id, menu_key=_new_key))
        db.commit()
    try:
        from app.services.permission_service import sync_admin_full_permissions
        sync_admin_full_permissions(db)
    except Exception as _perm_e:
        import logging as _perm_logging
        _perm_logging.getLogger(__name__).warning(f"sync_admin_full_permissions 失败: {_perm_e}")
    log_channel = db.query(NotificationChannel).filter(NotificationChannel.type == "log").first()
    if not log_channel:
        db.add(NotificationChannel(name="系统日志", type="log", channel_config="{}", enabled=True))
        db.commit()
    config_service.init_configs(db)
    try:
        from sqlalchemy import text
        db.execute(text("ALTER TABLE anomaly_configs ADD COLUMN algorithm VARCHAR(32) DEFAULT 'sigma'"))
        db.commit()
    except Exception:
        pass
    try:
        from sqlalchemy import text
        db.execute(text("ALTER TABLE anomaly_configs ADD COLUMN period INTEGER DEFAULT 12"))
    except Exception:
        pass
    try:
        from app.routers.chaos import seed_chaos_scenarios
        seed_chaos_scenarios(db)
        db.commit()
    except Exception:
        pass
    try:
        from sqlalchemy import text
        db.execute(text("ALTER TABLE chaos_scenarios ADD COLUMN target_layer VARCHAR(32) DEFAULT 'host'"))
        db.commit()
    except Exception:
        pass
    try:
        from sqlalchemy import text
        db.execute(text("ALTER TABLE chaos_experiments ADD COLUMN target_layer VARCHAR(32) DEFAULT 'host'"))
        db.commit()
    except Exception:
        pass
    try:
        from sqlalchemy import text
        db.execute(text("ALTER TABLE assets ADD COLUMN connection_type VARCHAR(32) DEFAULT 'ssh'"))
        db.execute(text("ALTER TABLE assets ADD COLUMN connection_config TEXT DEFAULT '{}'"))
        db.commit()
    except Exception:
        pass
    try:
        from sqlalchemy import text
        db.execute(text("ALTER TABLE assets DROP COLUMN ssh_user"))
        db.execute(text("ALTER TABLE assets DROP COLUMN ssh_password"))
        db.execute(text("ALTER TABLE assets DROP COLUMN ssh_port"))
        db.commit()
    except Exception:
        pass
    try:
        from sqlalchemy import text as _t
        db.execute(_t("ALTER TABLE deploy_plans ADD COLUMN doc_file_name VARCHAR(256) DEFAULT ''"))
        db.commit()
    except Exception:
        pass
    try:
        from sqlalchemy import text as _t
        db.execute(_t("ALTER TABLE deploy_plans ADD COLUMN asset_ids TEXT DEFAULT '[]'"))
        db.commit()
    except Exception:
        pass
    if not db.query(AnomalyConfig).first():
        for metric in ["cpu_usage", "memory_usage", "disk_usage"]:
            db.add(AnomalyConfig(
                name=f"{metric} 3sigma jiance", metric_name=metric,
                sensitivity=3.0, window_size=20, enabled=True,
            ))
        db.commit()
    from app.models import AIProvider, AgentConfig
    if not db.query(AgentConfig).filter(AgentConfig.name == "default").first():
        first_provider = db.query(AIProvider).filter(AIProvider.is_enabled == True).first()
        default_config = AgentConfig(
            name="default",
            default_provider_id=first_provider.id if first_provider else None,
            is_enabled=True,
        )
        db.add(default_config)
        db.commit()
    db.close()


def _init_background_task_monitor():
    """注册所有后台任务到监控器（仅一次）"""
    from app.services.background_task_monitor import init_task_monitor
    init_task_monitor([
        {"name": "alert_check", "fn": alert_service.check_rules, "description": "告警规则检查"},
        {"name": "alert_escalate", "fn": alert_service.escalate_alerts, "description": "告警升级"},
        {"name": "k8s_event_alert", "fn": alert_service.check_k8s_events, "description": "K8s 事件告警"},
        {"name": "anomaly_detect", "fn": anomaly_service.detect_anomalies, "description": "异常检测"},
        {"name": "incident_correlate", "fn": incident_service.correlate_alerts, "description": "故障关联"},
        {"name": "remediation", "fn": remediation_service.check_and_remediate, "description": "自愈执行"},
        {"name": "datasource_scrape", "fn": datasource_service.scrape_all_sources, "description": "数据源采集"},
        {"name": "pod_health", "fn": pod_health_service.check_pod_anomalies, "description": "Pod 健康检查"},
        {"name": "log_anomaly", "fn": log_anomaly_service.check_log_anomalies, "description": "日志异常检测"},
        {"name": "trace_anomaly", "fn": trace_anomaly_service.check_trace_anomalies, "description": "链路异常检测"},
        {"name": "contention", "fn": contention_service.detect_contention, "description": "资源竞争检测"},
        {"name": "synthetic_monitor", "fn": check_all_synthetics, "description": "拨测探测"},
        {"name": "workflow_alert_trigger", "fn": agent_workflow_service.check_alert_triggers, "description": "工作流告警自动触发"},
        {"name": "workflow_cron_trigger", "fn": workflow_cron_scheduler.check_cron_triggers, "description": "工作流 cron 定时调度"},
        {"name": "auto_investigate", "fn": auto_investigator.auto_investigate_new_incidents, "description": "告警自动调查闭环"},
        {"name": "asset_probe", "fn": asset_service.probe_assets, "description": "资产健康探测"},
        {"name": "metric_collect", "fn": metric_collector.collect_all_metrics, "description": "指标采集"},
        {"name": "metric_archive", "fn": None, "description": "指标归档（删除超期记录）"},
        {"name": "report_schedule", "fn": None, "description": "报表调度"},
    ])


def _run_bg_service(name: str, fn, db_mode: str):
    """在独立线程中运行后台服务，使用独立 DB session（线程安全）"""
    from app.services.background_task_monitor import task_monitor
    if not task_monitor.is_enabled(name):
        task_monitor.record_skip(name, "paused")
        return
    _t0 = time.time()
    task_monitor.record_start(name)
    _db = get_session_for(db_mode)()
    try:
        fn(_db)
        _elapsed = time.time() - _t0
        task_monitor.record_success(name, _elapsed * 1000)
        if _elapsed > 30:
            logger.warning(f"后台服务 {name} 耗时过长: {_elapsed:.1f}s")
        elif _elapsed > 5:
            logger.info(f"后台服务 {name} 完成: {_elapsed:.1f}s")
    except Exception as e:
        _elapsed = time.time() - _t0
        task_monitor.record_failure(name, _elapsed * 1000, str(e))
        logger.warning(f"后台服务 {name} 异常({_elapsed:.1f}s): {e}")
    finally:
        _db.close()


def background_loop():
    _init_background_task_monitor()
    while True:
        _mode = get_db_mode()
        _services = [
            ("alert_check", alert_service.check_rules),
            ("alert_escalate", alert_service.escalate_alerts),
            ("k8s_event_alert", alert_service.check_k8s_events),
            ("anomaly_detect", anomaly_service.detect_anomalies),
            ("incident_correlate", incident_service.correlate_alerts),
            ("remediation", remediation_service.check_and_remediate),
            ("pod_health", pod_health_service.check_pod_anomalies),
            ("log_anomaly", log_anomaly_service.check_log_anomalies),
            ("trace_anomaly", trace_anomaly_service.check_trace_anomalies),
            ("contention", contention_service.detect_contention),
            ("synthetic_monitor", check_all_synthetics),
            ("workflow_alert_trigger", agent_workflow_service.check_alert_triggers),
            ("workflow_cron_trigger", workflow_cron_scheduler.check_cron_triggers),
            ("auto_investigate", auto_investigator.auto_investigate_new_incidents),
        ]
        _pool = ThreadPoolExecutor(max_workers=5)
        futures = {_pool.submit(_run_bg_service, name, fn, _mode): name
                   for name, fn in _services}
        try:
            for f in as_completed(futures, timeout=120):
                try:
                    f.result()
                except Exception as e:
                    logger.warning(f"后台服务 {futures[f]} 异常: {e}")
        except TimeoutError:
            _pending = [futures[f] for f in futures if not f.done()]
            if _pending:
                logger.warning(f"后台服务超时: {_pending}")
        _pool.shutdown(wait=False)
        # 以下低频率任务在非核心线程中执行
        _now = time.time()
        global _last_probe_time, _last_collect_time, _last_archive_time, _last_scrape_time, _last_autonomous_time
        if _now - _last_probe_time >= 60:
            _last_probe_time = _now
            threading.Thread(target=_run_bg_service, args=("asset_probe", asset_service.probe_assets, _mode), daemon=True).start()
        if _now - _last_scrape_time >= 120:
            _last_scrape_time = _now
            threading.Thread(target=_run_bg_service, args=("datasource_scrape", datasource_service.scrape_all_sources, _mode), daemon=True).start()
        if _now - _last_collect_time >= 300:
            _last_collect_time = _now
            threading.Thread(target=_run_bg_service, args=("metric_collect", metric_collector.collect_all_metrics, _mode), daemon=True).start()
        if _now - _last_archive_time >= 3600:
            _last_archive_time = _now
            _archive_db = get_session_for(_mode)()
            try:
                _cutoff = (datetime.now() - timedelta(days=METRIC_RETENTION_DAYS)).isoformat()
                _archive_db.query(MetricRecord).filter(MetricRecord.timestamp < _cutoff).delete()
                _archive_db.commit()
            except Exception:
                _archive_db.rollback()
            finally:
                _archive_db.close()
            _report_db = get_session_for(_mode)()
            try:
                for _schedule in _report_db.query(ReportSchedule).filter(
                    ReportSchedule.is_enabled == True,
                    ReportSchedule.interval_minutes > 0,
                ).all():
                    _schedule.last_run = datetime.now()
                _report_db.commit()
            except Exception:
                pass
            finally:
                _report_db.close()
        time.sleep(BACKGROUND_INTERVAL)


def _security_startup_check():
    """启动时检测安全风险：默认密钥、弱密码 admin"""
    _risks = []
    _DEFAULT_KEY = "aiops-dev-secret-change-in-production-please"
    if _config.SECRET_KEY == _DEFAULT_KEY:
        _risks.append("SECRET_KEY 仍为默认值，生产环境必须设置 AIOPS_SECRET_KEY 环境变量")
    if _config.MOBILE_JWT_SECRET == "aiops-mobile-secret-dev":
        _risks.append("MOBILE_JWT_SECRET 仍为默认值，建议设置环境变量")
    try:
        _db = get_session_for("demo")()
        try:
            _admin = _db.query(User).filter(User.username == "admin").first()
            if _admin and verify_password("admin123", _admin.password_hash):
                _risks.append("admin 账户使用默认密码 admin123，请尽快修改")
        finally:
            _db.close()
    except Exception:
        pass
    if _risks:
        for _r in _risks:
            logger.warning(f"[安全检查] {_r}")
        logger.warning(f"[安全检查] 共发现 {len(_risks)} 项安全风险，详见上方警告")
    else:
        logger.info("[安全检查] 启动安全检查通过，未发现默认密钥/弱密码风险")