import hashlib
import json
import mimetypes
import os as _os
import threading
import time
from datetime import datetime

# Windows 上 Python 默认把 .js 映射为 text/plain，导致浏览器拒绝执行 module script
mimetypes.add_type("text/javascript", ".js")
mimetypes.add_type("text/javascript", ".mjs")

from fastapi import FastAPI
from fastapi.staticfiles import StaticFiles as _FastStaticFiles
from fastapi.middleware.cors import CORSMiddleware
from starlette.middleware.sessions import SessionMiddleware
from starlette.middleware.gzip import GZipMiddleware

from fastapi import Request
from fastapi.responses import RedirectResponse
from starlette.middleware.base import BaseHTTPMiddleware

from fastapi.responses import HTMLResponse, FileResponse
from pathlib import Path


class _MultiStaticFiles(_FastStaticFiles):
    """StaticFiles that tries multiple directories in order."""
    def __init__(self, directories, *args, **kwargs):
        dirs = [str(d) for d in directories]
        kwargs["directory"] = dirs[0]
        super().__init__(*args, **kwargs)
        self._dirs = dirs

    def lookup_path(self, path: str):
        for d in self._dirs:
            fp = _os.path.normpath(_os.path.join(d, path))
            if _os.path.isfile(fp):
                return fp, _os.stat(fp)
        return super().lookup_path(path)


StaticFiles = _FastStaticFiles  # alias so existing mounts keep working
from app.database import Base, get_all_engines, get_session_for, get_db_mode, set_db_mode
from app.routers import auth, sre, dashboard, assets, metrics, alerts, notifications, users, anomaly, incidents, topology, knowledge, knowledge_documents, remediation, datasources, tokens, settings, reports, knowledge_graph, containers, logs, predictions, events, k8s_resources, api_v1, correlation, runbooks, remediation_workflow, alert_silence, k8s_monitor, log_anomaly, notification_templates, hotspot, dashboard_config, alert_webhooks, asset_changes, smart_recommend, predictions_enhanced, trace_view, tags, es_integration, change_workflow, chatops, topo_graph, alert_storm, ci_models, report_schedules, pcadr, alert_events, alert_console, prediction_models, dtw, idice, script_exec, drain, topology_path, lifecycle, pagerank_rca, traces, discovery, ext_cmdb, granger, log_rca, trace_anomaly, kafka_pipeline, trend_prediction, event_sources, netflow, service_mesh, feature_store, blue_green, cluster_anomaly, trace_rca, ai_providers, agent_chat, audit, menu, system, system_posture, traces_api, trace_ingest, chaos, workflow, agent_workflow, helm, ansible, license, mobile
from app.models import User, NotificationChannel, AnomalyConfig, ReportSchedule
from app.services import metric_service, alert_service, anomaly_service, incident_service, remediation_service, datasource_service, config_service, pod_health_service, log_anomaly_service, contention_service, metric_collector, asset_service
from app.services import mcp_tools  # noqa: F401 — register MCP tools on import
from app.services.report_service import generate_report
from app.services.license_service import LicenseMiddleware
from app.seed_data import seed_all
from app.routers.chaos import seed_chaos_scenarios

# 两个库都建表
for _mode, _eng in get_all_engines().items():
    Base.metadata.create_all(bind=_eng)

# SQLite 幂等迁移: create_all 只建新表不 ALTER 已存在表, 补充缺失列
from sqlalchemy import text as _sa_text
_MIGRATIONS = {
    "pending_actions": [
        "reason VARCHAR(500)",
        "run_id INTEGER",
        "node_run_id INTEGER",
    ],
    "agent_workflow_node_runs": [
        "requires_confirm BOOLEAN DEFAULT 0",
        "pending_action_id INTEGER",
    ],
    "agent_workflow_runs": [
        "triggered_by VARCHAR(64)",
    ],
}
for _eng in get_all_engines().values():
    with _eng.connect() as _conn:
        for _table, _cols in _MIGRATIONS.items():
            for _col_def in _cols:
                try:
                    _conn.execute(_sa_text(f"ALTER TABLE {_table} ADD COLUMN {_col_def}"))
                    _conn.commit()
                except Exception:
                    pass

        # 重建 pending_actions 表：旧表 session_id 为 NOT NULL，工作流场景需 NULL
        try:
            _info = _conn.execute(_sa_text("PRAGMA table_info(pending_actions)")).fetchall()
            _sess_col = [r for r in _info if r[1] == "session_id"]
            if _sess_col and _sess_col[0][3] == 1:  # notnull=1
                _conn.execute(_sa_text(
                    "CREATE TABLE _pa_new (id INTEGER PRIMARY KEY AUTOINCREMENT, "
                    "session_id INTEGER, message_id INTEGER, run_id INTEGER, node_run_id INTEGER, "
                    "action_type VARCHAR(64) NOT NULL, title VARCHAR(128) DEFAULT '', "
                    "risk_level VARCHAR(16) DEFAULT 'low', reason VARCHAR(500), "
                    "status VARCHAR(16) DEFAULT 'pending', action_payload TEXT DEFAULT '{}', "
                    "result_payload TEXT DEFAULT '{}', confirmed_by VARCHAR(64) DEFAULT '', "
                    "confirmed_at DATETIME, created_at DATETIME DEFAULT CURRENT_TIMESTAMP, "
                    "updated_at DATETIME DEFAULT CURRENT_TIMESTAMP)"
                ))
                _conn.execute(_sa_text(
                    "INSERT INTO _pa_new (id, session_id, message_id, run_id, node_run_id, "
                    "action_type, title, risk_level, reason, status, action_payload, "
                    "result_payload, confirmed_by, confirmed_at, created_at, updated_at) "
                    "SELECT id, session_id, message_id, run_id, node_run_id, action_type, "
                    "title, risk_level, reason, status, action_payload, result_payload, "
                    "confirmed_by, confirmed_at, created_at, updated_at FROM pending_actions"
                ))
                _conn.execute(_sa_text("DROP TABLE pending_actions"))
                _conn.execute(_sa_text("ALTER TABLE _pa_new RENAME TO pending_actions"))
                _conn.commit()
                print("[migrate] pending_actions 重建完成: session_id 已改为 nullable")
        except Exception as _e:
            try:
                _conn.rollback()
            except Exception:
                pass

app = FastAPI(title="AIOPS 智能运维系统", version="0.1.0")

PUBLIC_PATHS = {"/login", "/static", "/assets", "/product", "/vue-assets", "/mobile-app", "/api/system/db-mode", "/api/sre", "/api/sre/", "/api/system/db-switch", "/api/menu", "/api/v1/traces/ingest-status", "/api/v1/traces/otlp", "/api/v1/traces/jaeger", "/api/v1/traces/agent-guide", "/mobile", "/me", "/ansible"}


class AuthMiddleware(BaseHTTPMiddleware):
    async def dispatch(self, request: Request, call_next):
        path = request.url.path
        if not any(path.startswith(p) for p in PUBLIC_PATHS):
            user_id = request.session.get("user_id")
            if not user_id:
                auth = request.headers.get("authorization", "")
                if auth.startswith("Bearer "):
                    from app.services.mobile_push_service import verify_login_token
                    payload = verify_login_token(auth[7:])
                    if payload:
                        request.session["user_id"] = payload.get("user_id")
                        request.session["username"] = payload.get("username", "")
                        return await call_next(request)
                return RedirectResponse(url="/login", status_code=303)
        return await call_next(request)


app.add_middleware(GZipMiddleware, minimum_size=1000)
app.add_middleware(AuthMiddleware)
app.add_middleware(LicenseMiddleware)
app.add_middleware(SessionMiddleware, secret_key="aiops-secret-key-change-in-production")

app.add_middleware(
    CORSMiddleware,
    allow_origins=["http://localhost:5173", "http://127.0.0.1:5173", "http://localhost:3000", "http://127.0.0.1:3000"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


class CacheControlMiddleware(BaseHTTPMiddleware):
    async def dispatch(self, request: Request, call_next):
        response = await call_next(request)
        if request.url.path.startswith("/vue-assets/") or request.url.path.startswith("/static/"):
            response.headers["Cache-Control"] = "public, max-age=31536000, immutable"
        return response


app.add_middleware(CacheControlMiddleware)

# 公共 assets 由 /vue-assets 和 /mobile-assets 各自承载，不在此挂载（避免与 /assets API 路由冲突）

# Mobile tab 图标（需在 /static 之前挂载，Starlette 优先匹配精确路径）
_MOBILE_STATIC_TAB = Path(__file__).resolve().parent.parent / "mobile/dist/build/h5/static/tab"
if _MOBILE_STATIC_TAB.is_dir():
    app.mount("/static/tab", StaticFiles(directory=str(_MOBILE_STATIC_TAB)), name="mobile_static_tab")
app.mount("/static", StaticFiles(directory="app/static"), name="static")
app.mount("/vue-assets", StaticFiles(directory="frontend/dist"), name="vue_assets")
_MOBILE_DIST = Path(__file__).resolve().parent.parent / "mobile/dist/build/h5"
if _MOBILE_DIST.is_dir():
    app.mount("/mobile-app", StaticFiles(directory=str(_MOBILE_DIST), html=True), name="mobile_app")

_VUE_INDEX = Path(__file__).resolve().parent.parent / "frontend/dist/index.html"
_MOBILE_INDEX = Path(__file__).resolve().parent.parent / "mobile/dist/build/h5/index.html"


@app.get("/", response_class=HTMLResponse)
def serve_spa():
    content = _VUE_INDEX.read_text(encoding="utf-8")
    content = content.replace('/assets/', '/vue-assets/assets/')
    return HTMLResponse(content=content)


app.include_router(auth.router)
app.include_router(sre.router)
app.include_router(dashboard.router)
app.include_router(assets.router)
app.include_router(metrics.router)
app.include_router(alerts.router)
app.include_router(notifications.router)
app.include_router(users.router)
app.include_router(anomaly.router)
app.include_router(incidents.router)
app.include_router(topology.router)
app.include_router(containers.router)
app.include_router(knowledge_graph.router)
app.include_router(knowledge_documents.router)
app.include_router(knowledge.router)
app.include_router(remediation.router)
app.include_router(datasources.router)
app.include_router(tokens.router)
app.include_router(settings.router)
app.include_router(reports.router)
app.include_router(logs.router)
app.include_router(predictions.router)
app.include_router(events.router)
app.include_router(k8s_resources.router)
app.include_router(api_v1.router)
app.include_router(correlation.router)
app.include_router(runbooks.router)
app.include_router(remediation_workflow.router)
app.include_router(alert_silence.router)
app.include_router(k8s_monitor.router)
app.include_router(log_anomaly.router)
app.include_router(notification_templates.router)
app.include_router(hotspot.router)
app.include_router(dashboard_config.router)
app.include_router(alert_webhooks.router)
app.include_router(asset_changes.router)
app.include_router(smart_recommend.router)
app.include_router(predictions_enhanced.router)
app.include_router(trace_view.router)
app.include_router(tags.router)
app.include_router(es_integration.router)
app.include_router(change_workflow.router)
app.include_router(chatops.router)
app.include_router(topo_graph.router)
app.include_router(alert_storm.router)
app.include_router(ci_models.router)
app.include_router(report_schedules.router)
app.include_router(pcadr.router)
app.include_router(alert_events.router)
app.include_router(alert_console.router)
app.include_router(prediction_models.router)
app.include_router(dtw.router)
app.include_router(idice.router)
app.include_router(script_exec.router)
app.include_router(drain.router)
app.include_router(topology_path.router)
app.include_router(lifecycle.router)
app.include_router(pagerank_rca.router)
app.include_router(traces.router)
app.include_router(discovery.router)
app.include_router(ext_cmdb.router)
app.include_router(granger.router)
app.include_router(log_rca.router)
app.include_router(trace_anomaly.router)
app.include_router(kafka_pipeline.router)
app.include_router(trend_prediction.router)
app.include_router(event_sources.router)
app.include_router(netflow.router)
app.include_router(service_mesh.router)
app.include_router(feature_store.router)
app.include_router(blue_green.router)
app.include_router(cluster_anomaly.router)
app.include_router(trace_rca.router)
app.include_router(ai_providers.router)
app.include_router(agent_chat.router)
app.include_router(audit.router)
app.include_router(menu.router)
app.include_router(system.router)
app.include_router(system_posture.router)
app.include_router(traces_api.router)
app.include_router(trace_ingest.router)
app.include_router(chaos.router)
app.include_router(workflow.router)
app.include_router(agent_workflow.router)
app.include_router(helm.router)
app.include_router(ansible.router)
app.include_router(license.router)
app.include_router(mobile.router)


def init_admin():
    db = get_session_for(get_db_mode())()
    user = db.query(User).filter(User.username == "admin").first()
    if not user:
        admin = User(
            username="admin",
            password_hash=hashlib.sha256(b"admin123").hexdigest(),
            role="admin",
        )
        db.add(admin)
        db.commit()
    log_channel = db.query(NotificationChannel).filter(NotificationChannel.type == "log").first()
    if not log_channel:
        db.add(NotificationChannel(name="系统日志", type="log", config="{}", enabled=True))
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


BACKGROUND_INTERVAL = 10
_last_probe_time = 0
_last_collect_time = 0.0


def background_loop():
    while True:
        try:
            db = get_session_for(get_db_mode())()
            try:
                alert_service.check_rules(db)
                alert_service.escalate_alerts(db)
                anomaly_service.detect_anomalies(db)
                incident_service.correlate_alerts(db)
                remediation_service.check_and_remediate(db)
                datasource_service.scrape_all_sources(db)
                pod_health_service.check_pod_anomalies(db)
                log_anomaly_service.check_log_anomalies(db)
                contention_service.detect_contention(db)
                # 资产健康探测（间隔从系统配置读取，独立计时避免阻塞主循环）
                global _last_probe_time
                _now = time.time()
                try:
                    from app.services import config_service
                    _probe_enabled = config_service.get_config(db, "asset_probe_enabled", "true").lower() == "true"
                    _probe_interval = int(config_service.get_config(db, "asset_probe_interval", "60") or "60")
                except Exception:
                    _probe_enabled = True
                    _probe_interval = 60
                if _probe_enabled and _now - _last_probe_time >= _probe_interval:
                    _last_probe_time = _now
                    try:
                        _probe_mode = get_db_mode()
                        print(f"[bg] 资产探测开始, db_mode={_probe_mode}")
                        changed = asset_service.probe_assets(db)
                        print(f"[bg] 资产探测完成, 变更: {len(changed)} 条")
                        if changed:
                            print(f"[bg] 资产状态变更: {changed}")
                    except Exception as pe:
                        print(f"[bg] 资产探测异常: {pe}")
                # 指标采集（独立计时器，间隔从配置读取）
                global _last_collect_time
                try:
                    _collect_enabled = config_service.get_config(db, "metric_collect_enabled", "true").lower() == "true"
                    _collect_interval = int(config_service.get_config(db, "metric_collect_interval", "60") or "60")
                except Exception:
                    _collect_enabled = True
                    _collect_interval = 60
                if _collect_enabled and _now - _last_collect_time >= _collect_interval:
                    _last_collect_time = _now
                    try:
                        summary = metric_collector.collect_all_metrics(db)
                        if summary["metrics_collected"] > 0:
                            print(f"[bg] 指标采集: {summary['success']}成功/{summary['failed']}失败, 采集{summary['metrics_collected']}条指标")
                    except Exception as ce:
                        print(f"[bg] 指标采集异常: {ce}")
                now = datetime.now()
                schedules = db.query(ReportSchedule).filter(ReportSchedule.enabled == True).all()
                for s in schedules:
                    try:
                        parts = s.cron_expr.split()
                        if len(parts) >= 5:
                            cron_min = int(parts[0])
                            cron_hour = int(parts[1])
                            if now.minute == cron_min and now.hour == cron_hour:
                                report = generate_report(db, s.report_type)
                                s.last_run = now
                                db.commit()
                    except Exception:
                        pass
            except Exception as e:
                import traceback
                print(f"[bg] Error in loop: {e}")
                traceback.print_exc()
            finally:
                db.close()
        except Exception as e:
            import traceback
            print(f"[bg] Fatal error: {e}")
            traceback.print_exc()
        time.sleep(BACKGROUND_INTERVAL)


# 两个库都初始化 admin 账号
init_admin()
set_db_mode("real")
init_admin()
set_db_mode("demo")
# 只对 demo 库灌入种子数据
seed_all()
# 两个库都播种 SOP 工作流模板（幂等，按 name 去重）
from app.services.workflow_service import seed_workflow_templates
from app.services.agent_workflow_service import seed_agent_workflows, _preset_workflows as _get_agent_presets
for _mode in ("demo", "real"):
    set_db_mode(_mode)
    _seed_db = get_session_for(_mode)()
    try:
        _added = seed_workflow_templates(_seed_db)
        if _added:
            print(f"[seed] {_mode} 库播种 {_added} 个 SOP 工作流模板")
        _added2 = seed_agent_workflows(_seed_db)
        if _added2:
            print(f"[seed] {_mode} 库播种 {_added2} 个智能体工作流模板")
        # 给已有种子工作流的 tool 节点补 execution_mode: auto（向后兼容）
        from app.models import AgentWorkflow
        from sqlalchemy import text as _sa_text2
        _preset_names = [p["name"] for p in _get_agent_presets()]
        for _wf in _seed_db.query(AgentWorkflow).filter(AgentWorkflow.name.in_(_preset_names)).all():
            _nodes = _wf.get_nodes()
            _changed = False
            for _n in _nodes:
                if _n.get("type") == "tool" and "execution_mode" not in _n.get("data", {}):
                    _n.setdefault("data", {})["execution_mode"] = "auto"
                    _changed = True
            if _changed:
                _wf.nodes = json.dumps(_nodes, ensure_ascii=False)
                _seed_db.commit()
    finally:
        _seed_db.close()
set_db_mode("demo")
threading.Thread(target=background_loop, daemon=True).start()

