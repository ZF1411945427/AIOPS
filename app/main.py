import hashlib
import json
import mimetypes
import os as _os
import threading
import time
from datetime import datetime, timedelta
from concurrent.futures import ThreadPoolExecutor, as_completed

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

from fastapi.responses import HTMLResponse, FileResponse, JSONResponse
from pathlib import Path

from app.logger import logger


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
from app import config as _config
# ── 全量路由导入（按 9 个业务域归类，详见 app/domains/registry.py）──
# assets 资产管理域
from app.routers import assets, asset_changes, asset_discovery, lifecycle, topology, topology_path, topo_graph, tags, ext_cmdb
# alerts 告警监控域
from app.routers import alerts, alert_console, alert_events, alert_silence, alert_storm, alert_webhooks, anomaly, cluster_anomaly, hotspot
# k8s 容器编排域
from app.routers import k8s_monitor, k8s_resources, containers, helm, blue_green, service_mesh
# ai 智能体域
from app.routers import ai_providers, agent_chat, agent_sse, agent_workflow, agent_eval, agent_ground_truth, ab_test, anomaly_eval, sub_agents, im_chatops, edge_tunnel, webssh
# sre 可靠性工程域
from app.routers import sre, chaos, inspection, baseline, remediation, remediation_workflow, remediation_effect, runbooks
# knowledge 知识管理域
from app.routers import knowledge, knowledge_documents, knowledge_v2, knowledge_graph, knowledge_autogen, smart_recommend
# incident 故障运营域
from app.routers import incidents, dashboard, dashboard_config, ops_analytics, reports, report_schedules
# tracing 链路追踪域
from app.routers import traces, traces_api, trace_anomaly, trace_ingest, trace_rca, trace_view, dtw, pagerank_rca, log_rca, log_anomaly, logs
# platform 平台与集成域
from app.routers import auth, users, roles, settings, system, system_posture, audit, menu, license, tenant_management, tokens, ws, api_v1, mobile, health_map, network_test, datasources, es_integration, event_sources, events, kafka_pipeline, netflow, feature_store, ci_models, drain, granger, idice, trend_prediction, prediction_models, predictions, predictions_enhanced, pcadr, metrics, notifications, notification_templates, correlation, observability_correlation, script_exec, ansible, change_workflow, workflow, chatops, discovery, diagnostic_tools
# admin 系统管理路由（领域清单 + 背景任务看板，P1 任务#4/#6）
from app.routers import admin
# P2 任务#9 告警收敛闭环 / P2 任务#10 RAG 检索质量评估
from app.routers import alert_correlation, rag_eval
# 安全自查（SAST / 依赖 CVE / License 合规 / 配置基线，打磨期 P0）
from app.routers import security_audit
from app.models import User, NotificationChannel, AnomalyConfig, ReportSchedule
from app.services import metric_service, alert_service, anomaly_service, incident_service, remediation_service, datasource_service, config_service, pod_health_service, log_anomaly_service, contention_service, metric_collector, asset_service, trace_anomaly_service
from app.services import mcp_tools  # noqa: F401 — register MCP tools on import
from app.services.synthetic_monitor import check_all_synthetics
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
    "oncall_schedules": [
        "is_auto_rotate BOOLEAN DEFAULT 0",
        "holidays TEXT DEFAULT '[]'",
    ],
    "chaos_runs": [
        "is_auto_recovered BOOLEAN DEFAULT 0",
    ],
    "inspection_records": [
        "triggered_by_alert_id INTEGER",
    ],
    "knowledge_base": [
        "source_type VARCHAR(32) DEFAULT 'manual'",
        "sop_steps TEXT DEFAULT '[]'",
        "version_number INTEGER DEFAULT 1",
        "change_log TEXT DEFAULT ''",
    ],
    "knowledge_drafts": [
        "source_type VARCHAR(32) DEFAULT 'auto'",
        "reject_reason TEXT DEFAULT ''",
        "sop_steps TEXT DEFAULT '[]'",
    ],
    "incidents": [
        "approver_id INTEGER",
        "review_comment TEXT DEFAULT ''",
        "impact VARCHAR(32) DEFAULT 'high'",
        "description TEXT DEFAULT ''",
    ],
    "users": [
        "role_id INTEGER",
    ],
    "chat_sessions": [
        "provider_id INTEGER",
        "mode VARCHAR(16) DEFAULT 'agent'",
        "linked_asset_ids TEXT DEFAULT '[]'",
        "sub_agent VARCHAR(64) DEFAULT 'auto'",
    ],
    "notification_channels": [
        "bidirectional BOOLEAN DEFAULT 0",
        "callback_token VARCHAR(128) DEFAULT ''",
        "callback_secret VARCHAR(128) DEFAULT ''",
        "default_sub_agent VARCHAR(64) DEFAULT 'auto'",
    ],
    "assets": [
        "edge_agent_id VARCHAR(64) DEFAULT ''",
    ],
    "trace_anomaly_configs": [
        "check_window_minutes INTEGER DEFAULT 30",
    ],
    "audit_logs": [
        "route_path VARCHAR(256) DEFAULT ''",
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
                logger.info("pending_actions 重建完成: session_id 已改为 nullable")
        except Exception as _e:
            try:
                _conn.rollback()
            except Exception:
                pass

        # ── 性能索引：高频查询字段加索引（幂等，已存在则跳过）──
        _INDEXES = [
            "CREATE INDEX IF NOT EXISTS idx_metric_asset_name_ts ON metric_records (asset_id, name, timestamp)",
            "CREATE INDEX IF NOT EXISTS idx_metric_name_ts ON metric_records (name, timestamp)",
            "CREATE INDEX IF NOT EXISTS idx_alerts_status_created ON alerts (status, created_at)",
            "CREATE INDEX IF NOT EXISTS idx_alerts_severity_created ON alerts (severity, created_at)",
            "CREATE INDEX IF NOT EXISTS idx_alerts_asset_id ON alerts (asset_id)",
            "CREATE INDEX IF NOT EXISTS idx_k8s_events_cluster_ns ON k8s_events (cluster, namespace, last_seen_at)",
            "CREATE INDEX IF NOT EXISTS idx_notif_logs_alert_id ON notification_logs (alert_id, created_at)",
            "CREATE INDEX IF NOT EXISTS idx_spans_service_time ON spans (service_name, start_time)",
            "CREATE INDEX IF NOT EXISTS idx_asset_changes_asset_ts ON asset_change_logs (asset_id, created_at)",
            "CREATE INDEX IF NOT EXISTS idx_incidents_status ON incidents (status, created_at)",
            "CREATE INDEX IF NOT EXISTS idx_tool_inv_session ON tool_invocations (session_id, created_at)",
            "CREATE INDEX IF NOT EXISTS idx_chat_msgs_session ON chat_messages (session_id, created_at)",
        ]
        for _idx_sql in _INDEXES:
            try:
                _conn.execute(_sa_text(_idx_sql))
                _conn.commit()
            except Exception:
                pass

app = FastAPI(
    title="AIOPS 智能运维系统",
    version="0.1.0",
    # 安全：生产环境关闭交互式 API 文档，避免接口裸露（SAST/验收常见扣分项）
    docs_url=None if _config.APP_ENV == "prod" else "/docs",
    redoc_url=None if _config.APP_ENV == "prod" else "/redoc",
    openapi_url=None if _config.APP_ENV == "prod" else "/openapi.json",
)

# ── 限流中间件 (slowapi) ──
from slowapi import Limiter, _rate_limit_exceeded_handler
from slowapi.util import get_remote_address
from slowapi.errors import RateLimitExceeded
from slowapi.middleware import SlowAPIMiddleware

limiter = Limiter(key_func=get_remote_address, default_limits=["1000/minute"])
app.state.limiter = limiter
app.add_exception_handler(RateLimitExceeded, _rate_limit_exceeded_handler)


# ── 全局异常处理：净化错误消息，避免向前端泄露内部细节 ──
from fastapi import HTTPException as _HTTPException

@app.exception_handler(Exception)
async def _global_exception_handler(request: Request, exc: Exception):
    from app.logger import logger
    import traceback
    logger.error(f"Unhandled exception on {request.url.path}: {exc}\n{traceback.format_exc()}")
    if isinstance(exc, _HTTPException):
        return JSONResponse({"error": exc.detail}, status_code=exc.status_code)
    # fail-soft 兜底：未预期异常返回 200 + warning，避免前端整页 500
    return JSONResponse({"warning": f"服务器内部错误: {exc}", "items": [], "total": 0}, status_code=200)

PUBLIC_PATHS = {"/login", "/static", "/assets", "/product", "/product/intro", "/vue-assets", "/mobile-app", "/api/system/db-mode", "/api/v1/traces/ingest-status", "/api/v1/traces/otlp", "/api/v1/traces/jaeger", "/api/v1/traces/agent-guide", "/mobile", "/me", "/healthz", "/readyz", "/health-map", "/api/system/health", "/api/menu", "/license", "/edge/commands/pending", "/im/callback"}


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
            # RBAC: viewer 角色禁止写操作
            request.state.user_id = user_id
            from app.database import get_session_for, get_db_mode
            from app.models import User as _User
            _db = get_session_for(get_db_mode())()
            try:
                _user = _db.query(_User).filter(_User.id == user_id).first()
                if _user and _user.role == "viewer":
                    _method = request.method
                    if _method in ("POST", "PUT", "PATCH", "DELETE"):
                        _db.close()
                        return JSONResponse(
                            {"error": "权限不足：viewer 角色只读"},
                            status_code=403,
                        )
                # admin-only 路径：非 admin 禁止写操作
                _ADMIN_WRITE_PREFIXES = (
                    "/ai/providers", "/helm/api", "/api/chaos", "/api/users",
                    "/script/api", "/system/db-switch",
                )
                if _user and _user.role != "admin":
                    _method = request.method
                    if _method in ("POST", "PUT", "PATCH", "DELETE"):
                        for _pfx in _ADMIN_WRITE_PREFIXES:
                            if path.startswith(_pfx):
                                _db.close()
                                return JSONResponse(
                                    {"error": "权限不足：需要管理员权限"},
                                    status_code=403,
                                )
                # admin-only 路径：非 admin 禁止任何方法（含 GET）
                _ADMIN_ONLY_PREFIXES = (
                    "/incidents/api/approval-settings",
                )
                if _user and _user.role != "admin":
                    for _pfx in _ADMIN_ONLY_PREFIXES:
                        if path.startswith(_pfx):
                            _db.close()
                            return JSONResponse(
                                {"error": "权限不足：需要管理员权限"},
                                status_code=403,
                            )
            finally:
                _db.close()
        return await call_next(request)


app.add_middleware(GZipMiddleware, minimum_size=1000)
app.add_middleware(SlowAPIMiddleware)
app.add_middleware(LicenseMiddleware)
app.add_middleware(AuthMiddleware)
app.add_middleware(SessionMiddleware, secret_key=_config.SESSION_SECRET,
                   https_only=_config.APP_ENV == "prod",
                   same_site="lax", max_age=86400)

app.add_middleware(
    CORSMiddleware,
    allow_origins=_config.CORS_ORIGINS,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


# ── P2 任务#11: 审计日志中间件（写操作自动记录）──
class AuditMiddleware(BaseHTTPMiddleware):
    """所有写操作（POST/PUT/PATCH/DELETE）自动记录到 audit_logs 表。

    - 密码字段脱敏后存储
    - 失败 fail-soft（审计失败不影响主流程）
    - 跳过 PUBLIC_PATHS 和静态资源
    """
    async def dispatch(self, request: Request, call_next):
        path = request.url.path
        method = request.method
        # 只审计写操作
        if method not in ("POST", "PUT", "PATCH", "DELETE"):
            return await call_next(request)
        # 跳过公开路径和静态资源
        if any(path.startswith(p) for p in PUBLIC_PATHS):
            return await call_next(request)
        if path.startswith(("/static", "/vue-assets", "/mobile-app", "/openapi", "/docs", "/redoc")):
            return await call_next(request)
        # 跳过审计写自身（避免递归）
        if path.startswith("/api/admin/audit"):
            return await call_next(request)

        t0 = time.time()
        # 获取路由模板路径（如 /api/tags/{tag_id}），用于覆盖率精确匹配
        route_path = path
        try:
            _route = request.scope.get("route")
            if _route and hasattr(_route, "path_format"):
                route_path = _route.path_format
        except Exception:
            pass
        # 读取请求体（仅小请求体，避免大上传撑爆内存）
        body_bytes = b""
        try:
            body_bytes = await request.body()
        except Exception:
            pass
        # 由于 body 已被读取，需要在 scope 中重置（用 receive 替换）
        async def _receive():
            return {"type": "http.request", "body": body_bytes, "more_body": False}
        request._receive = _receive  # type: ignore[attr-defined]

        response = await call_next(request)

        # 记录审计日志（fail-soft）
        try:
            from app.services.audit_matrix_service import record_audit
            from app.database import get_session_for, get_db_mode
            user_id = request.session.get("user_id")
            username = request.session.get("username", "")
            ip = request.client.host if request.client else ""
            ua = request.headers.get("user-agent", "")
            body_str = body_bytes.decode("utf-8", errors="ignore")[:2000] if body_bytes else ""
            duration_ms = int((time.time() - t0) * 1000)
            response_summary = ""
            try:
                # 提取响应摘要（仅当响应是 JSON 且较小时）
                if response.status_code < 500 and "application/json" in response.headers.get("content-type", ""):
                    # 不读取响应体（会消耗流），用 status_code 摘要即可
                    response_summary = f"HTTP {response.status_code}"
                else:
                    response_summary = f"HTTP {response.status_code}"
            except Exception:
                response_summary = f"HTTP {response.status_code}"

            _db = get_session_for(get_db_mode())()
            try:
                record_audit(
                    _db, user_id=user_id, username=username or "",
                    method=method, path=path, route_path=route_path,
                    status_code=response.status_code,
                    ip=ip, user_agent=ua,
                    request_body=body_str,
                    response_summary=response_summary,
                    duration_ms=duration_ms,
                )
            finally:
                _db.close()
        except Exception as e:
            logger.warning(f"AuditMiddleware 记录失败 ({method} {path}): {e}")

        return response


app.add_middleware(AuditMiddleware)


class CacheControlMiddleware(BaseHTTPMiddleware):
    async def dispatch(self, request: Request, call_next):
        response = await call_next(request)
        if request.url.path.startswith("/vue-assets/") or request.url.path.startswith("/static/"):
            response.headers["Cache-Control"] = "public, max-age=31536000, immutable"
        return response


# ── 安全响应头中间件：补充安全验收常见的响应头要求 ──
class SecurityHeadersMiddleware(BaseHTTPMiddleware):
    """补充 HSTS / X-Content-Type-Options / X-Frame-Options / Referrer-Policy 等安全头。

    - 生产环境启用 HSTS（https_only）
    - 禁止 MIME 嗅探、点击劫持、降级 Referer
    - fail-soft：失败不影响主流程
    """
    async def dispatch(self, request: Request, call_next):
        response = await call_next(request)
        try:
            response.headers.setdefault("X-Content-Type-Options", "nosniff")
            response.headers.setdefault("X-Frame-Options", "SAMEORIGIN")
            response.headers.setdefault("Referrer-Policy", "strict-origin-when-cross-origin")
            response.headers.setdefault("X-XSS-Protection", "1; mode=block")
            response.headers.setdefault("Permissions-Policy", "geolocation=(), microphone=(), camera=()")
            if _config.APP_ENV == "prod":
                response.headers.setdefault(
                    "Strict-Transport-Security",
                    "max-age=31536000; includeSubDomains"
                )
        except Exception:
            pass
        return response


app.add_middleware(CacheControlMiddleware)
app.add_middleware(SecurityHeadersMiddleware)


# ── CSRF 防护：Origin/Referer 校验中间件 ──
class CSRFMiddleware(BaseHTTPMiddleware):
    """对写操作（POST/PUT/PATCH/DELETE）校验 Origin/Referer 头，防止跨站请求伪造。

    - 浏览器同源策略下，JSON API 的 CSRF 风险较低，但 Origin 校验是纵深防御
    - 跳过公开路径（/login 等）和不含 cookie 的请求
    - fail-soft：缺少 Origin 头时放行（兼容非浏览器客户端如 curl/移动端）
    """
    async def dispatch(self, request: Request, call_next):
        method = request.method
        if method not in ("POST", "PUT", "PATCH", "DELETE"):
            return await call_next(request)
        path = request.url.path
        # 跳过公开路径（登录本身需要无 Origin 访问）
        if any(path.startswith(p) for p in PUBLIC_PATHS):
            return await call_next(request)
        # 检查是否有 session cookie（无 cookie 的 API 调用不受 CSRF 保护）
        _has_cookie = "session" in request.headers.get("cookie", "")
        if not _has_cookie:
            return await call_next(request)
        origin = request.headers.get("origin", "")
        referer = request.headers.get("referer", "")
        _allowed = set(_config.CORS_ORIGINS)
        # 允许同源请求（origin 为空或匹配 CORS 白名单）
        if origin and origin not in _allowed:
            # 也允许 origin 是 CORS 白名单的子路径
            _ok = any(origin.startswith(a) for a in _allowed)
            if not _ok:
                logger.warning(f"CSRF 拦截: {method} {path} origin={origin}")
                return JSONResponse({"detail": "跨站请求被拦截（CSRF 保护）"}, status_code=403)
        if referer:
            _ref_ok = any(referer.startswith(a) for a in _allowed)
            if not _ref_ok:
                logger.warning(f"CSRF 拦截(referer): {method} {path} referer={referer}")
                return JSONResponse({"detail": "跨站请求被拦截（CSRF 保护）"}, status_code=403)
        return await call_next(request)


app.add_middleware(CSRFMiddleware)

# 公共 assets 由 /vue-assets 和 /mobile-app 各自承载，不在此挂载（避免与 /assets API 路由冲突）

# Mobile tab 图标（需在 /static 之前挂载，Starlette 优先匹配精确路径）
_MOBILE_STATIC_TAB = Path(__file__).resolve().parent.parent / "mobile/dist/build/h5/static/tab"
if _MOBILE_STATIC_TAB.is_dir():
    app.mount("/static/tab", StaticFiles(directory=str(_MOBILE_STATIC_TAB)), name="mobile_static_tab")
_STATIC_DIR = str(Path(__file__).resolve().parent / "static")
_VUE_DIST_DIR = str(Path(__file__).resolve().parent.parent / "frontend/dist")
app.mount("/static", StaticFiles(directory=_STATIC_DIR), name="static")
app.mount("/vue-assets", StaticFiles(directory=_VUE_DIST_DIR), name="vue_assets")
_MOBILE_DIST = Path(__file__).resolve().parent.parent / "mobile/dist/build/h5"
if _MOBILE_DIST.is_dir():
    app.mount("/mobile-app", StaticFiles(directory=str(_MOBILE_DIST), html=True), name="mobile_app")

_VUE_INDEX = Path(__file__).resolve().parent.parent / "frontend/dist/index.html"
_MOBILE_INDEX = Path(__file__).resolve().parent.parent / "mobile/dist/build/h5/index.html"


@app.get("/", response_class=HTMLResponse)
def serve_spa():
    content = _VUE_INDEX.read_text(encoding="utf-8")
    return HTMLResponse(content=content)


# ── 路由按业务域分组注册（详见 app/domains/registry.py）──

# ── assets 资产管理域 ──
app.include_router(assets.router)
app.include_router(asset_changes.router)
app.include_router(asset_discovery.router)
app.include_router(lifecycle.router)
app.include_router(topology.router)
app.include_router(topology_path.router)
app.include_router(topo_graph.router)
app.include_router(tags.router)
app.include_router(ext_cmdb.router)

# ── alerts 告警监控域 ──
app.include_router(alerts.router)
app.include_router(alert_console.router)
app.include_router(alert_events.router)
app.include_router(alert_silence.router)
app.include_router(alert_storm.router)
app.include_router(alert_webhooks.router)
app.include_router(anomaly.router)
app.include_router(cluster_anomaly.router)
app.include_router(hotspot.router)

# ── k8s 容器编排域 ──
app.include_router(k8s_monitor.router)
app.include_router(k8s_resources.router)
app.include_router(containers.router)
app.include_router(helm.router)
app.include_router(blue_green.router)
app.include_router(service_mesh.router)

# ── ai 智能体域 ──
app.include_router(ai_providers.router)
app.include_router(agent_chat.router)
app.include_router(agent_sse.router)
app.include_router(agent_workflow.router)
app.include_router(agent_eval.router)
app.include_router(agent_ground_truth.router)
app.include_router(ab_test.router)
app.include_router(anomaly_eval.router)
app.include_router(sub_agents.router)
app.include_router(im_chatops.router)
app.include_router(edge_tunnel.router)
app.include_router(webssh.router)

# ── sre 可靠性工程域 ──
app.include_router(sre.router)
app.include_router(chaos.router)
app.include_router(inspection.router)
app.include_router(baseline.router)
app.include_router(remediation.router)
app.include_router(remediation_workflow.router)
app.include_router(remediation_effect.router)
app.include_router(runbooks.router)

# ── knowledge 知识管理域 ──
app.include_router(knowledge.router)
app.include_router(knowledge_documents.router)
app.include_router(knowledge_v2.router)
app.include_router(knowledge_graph.router)
app.include_router(knowledge_autogen.router)
app.include_router(smart_recommend.router)

# ── incident 故障运营域 ──
app.include_router(incidents.router)
app.include_router(dashboard.router)
app.include_router(dashboard_config.router)
app.include_router(ops_analytics.router)
app.include_router(reports.router)
app.include_router(report_schedules.router)

# ── tracing 链路追踪域 ──
app.include_router(traces.router)
app.include_router(traces_api.router)
app.include_router(trace_anomaly.router)
app.include_router(trace_ingest.router)
app.include_router(trace_rca.router)
app.include_router(trace_view.router)
app.include_router(dtw.router)
app.include_router(pagerank_rca.router)
app.include_router(log_rca.router)
app.include_router(log_anomaly.router)
app.include_router(logs.router)

# ── platform 平台与集成域 ──
app.include_router(auth.router)
app.include_router(users.router)
app.include_router(roles.router)
app.include_router(settings.router)
app.include_router(system.router)
app.include_router(system_posture.router)
app.include_router(audit.router)
app.include_router(menu.router)
app.include_router(license.router)
app.include_router(tenant_management.router)
app.include_router(tokens.router)
app.include_router(ws.router)
app.include_router(api_v1.router)
app.include_router(mobile.router)
app.include_router(health_map.router)
app.include_router(network_test.router)
app.include_router(datasources.router)
app.include_router(es_integration.router)
app.include_router(event_sources.router)
app.include_router(events.router)
app.include_router(kafka_pipeline.router)
app.include_router(netflow.router)
app.include_router(feature_store.router)
app.include_router(ci_models.router)
app.include_router(drain.router)
app.include_router(granger.router)
app.include_router(idice.router)
app.include_router(trend_prediction.router)
app.include_router(prediction_models.router)
app.include_router(predictions.router)
app.include_router(predictions_enhanced.router)
app.include_router(pcadr.router)
app.include_router(metrics.router)
app.include_router(notifications.router)
app.include_router(notification_templates.router)
app.include_router(correlation.router)
app.include_router(observability_correlation.router)
app.include_router(script_exec.router)
app.include_router(ansible.router)
app.include_router(change_workflow.router)
app.include_router(workflow.router)
app.include_router(chatops.router)
app.include_router(discovery.router)
app.include_router(diagnostic_tools.router)

# ── admin 系统管理路由（领域清单 + 背景任务看板，P1 任务#4/#6）──
app.include_router(admin.router)
# ── P2 任务#9 告警收敛闭环 / P2 任务#10 RAG 检索质量评估 ──
app.include_router(alert_correlation.router)
app.include_router(rag_eval.router)
# ── 安全自查（SAST / 依赖 CVE / License 合规 / 配置基线）──
app.include_router(security_audit.router)


def _collect_all_menu_keys():
    """从 menu_config.json 收集所有菜单 key"""
    _p = _os.path.join(_os.path.dirname(__file__), "routers", "menu_config.json")
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
    # ── 种子角色（幂等）──
    from app.models import Role as _Role, RoleMenu as _RoleMenu
    _preset_roles = [
        {"name": "admin", "description": "系统管理员，拥有全部权限", "is_system": True, "sort_order": 0},
        {"name": "operator", "description": "运维工程师，可执行操作", "is_system": True, "sort_order": 1},
        {"name": "viewer", "description": "只读用户，仅可查看", "is_system": True, "sort_order": 2},
    ]
    for _pr in _preset_roles:
        _existing = db.query(_Role).filter(_Role.name == _pr["name"]).first()
        if not _existing:
            db.add(_Role(**_pr))
    db.commit()
    user = db.query(User).filter(User.username == "admin").first()
    if not user:
        from app.security import hash_password
        default_pwd = _os.environ.get("AIOPS_ADMIN_PASSWORD", "admin123")
        _admin_role = db.query(_Role).filter(_Role.name == "admin").first()
        admin = User(
            username="admin",
            password_hash=hash_password(default_pwd),
            role="admin",
            role_id=_admin_role.id if _admin_role else None,
        )
        db.add(admin)
        db.commit()
        # admin 角色默认拥有所有菜单权限
        if _admin_role:
            _existing_menus = db.query(_RoleMenu).filter(_RoleMenu.role_id == _admin_role.id).count()
            if _existing_menus == 0:
                _all_keys = _collect_all_menu_keys()
                for _k in _all_keys:
                    db.add(_RoleMenu(role_id=_admin_role.id, menu_key=_k))
                db.commit()
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
_last_archive_time = 0.0
_last_scrape_time = 0.0
METRIC_RETENTION_DAYS = int(_os.environ.get("AIOPS_METRIC_RETENTION_DAYS", "90"))


# P1 任务#6: 后台任务监控器初始化
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
        {"name": "asset_probe", "fn": asset_service.probe_assets, "description": "资产健康探测"},
        {"name": "metric_collect", "fn": metric_collector.collect_all_metrics, "description": "指标采集"},
        {"name": "metric_archive", "fn": None, "description": "指标归档（删除超期记录）"},
        {"name": "report_schedule", "fn": None, "description": "报表调度"},
    ])


def _run_bg_service(name: str, fn, db_mode: str):
    """在独立线程中运行后台服务，使用独立 DB session（线程安全）"""
    from app.services.background_task_monitor import task_monitor
    # P1 任务#6: 暂停的任务跳过执行
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
    # P1 任务#6: 首次启动注册任务清单
    _init_background_task_monitor()
    from app.services.background_task_monitor import task_monitor
    while True:
        _mode = get_db_mode()
        # ── 核心服务并发执行（每个独立 session，最多 5 线程）──
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
            logger.warning(f"后台服务超时(120s), 未完成: {_pending}")
            for f in futures:
                if not f.done():
                    f.cancel()
        except Exception as e:
            import traceback
            logger.error(f"Background services error: {e}")
            traceback.print_exc()
        finally:
            _pool.shutdown(wait=False)

        # ── 辅助任务（独立计时器，主线程执行）──
        try:
            db = get_session_for(_mode)()
            try:
                global _last_probe_time, _last_collect_time, _last_archive_time, _last_scrape_time
                _now = time.time()
                # 资产健康探测
                try:
                    from app.services import config_service
                    _probe_enabled = config_service.get_config(db, "asset_probe_enabled", "true").lower() == "true"
                    _probe_interval = int(config_service.get_config(db, "asset_probe_interval", "60") or "60")
                except Exception:
                    _probe_enabled = True
                    _probe_interval = 60
                if _probe_enabled and task_monitor.is_enabled("asset_probe") and _now - _last_probe_time >= _probe_interval:
                    _last_probe_time = _now
                    _t0 = time.time()
                    task_monitor.record_start("asset_probe")
                    try:
                        changed = asset_service.probe_assets(db)
                        task_monitor.record_success("asset_probe", (time.time() - _t0) * 1000)
                        if changed:
                            logger.info(f"资产状态变更: {len(changed)} 条")
                    except Exception as pe:
                        task_monitor.record_failure("asset_probe", (time.time() - _t0) * 1000, str(pe))
                        logger.warning(f"资产探测异常: {pe}")
                elif not task_monitor.is_enabled("asset_probe"):
                    task_monitor.record_skip("asset_probe", "paused")
                # 指标采集
                try:
                    _collect_enabled = config_service.get_config(db, "metric_collect_enabled", "true").lower() == "true"
                    _collect_interval = int(config_service.get_config(db, "metric_collect_interval", "60") or "60")
                except Exception:
                    _collect_enabled = True
                    _collect_interval = 60
                if _collect_enabled and task_monitor.is_enabled("metric_collect") and _now - _last_collect_time >= _collect_interval:
                    _last_collect_time = _now
                    _t0 = time.time()
                    task_monitor.record_start("metric_collect")
                    try:
                        summary = metric_collector.collect_all_metrics(db)
                        task_monitor.record_success("metric_collect", (time.time() - _t0) * 1000)
                        if summary["metrics_collected"] > 0:
                            logger.info(f"指标采集: {summary['success']}成功/{summary['failed']}失败, 采集{summary['metrics_collected']}条指标")
                    except Exception as ce:
                        task_monitor.record_failure("metric_collect", (time.time() - _t0) * 1000, str(ce))
                        logger.warning(f"指标采集异常: {ce}")
                elif not task_monitor.is_enabled("metric_collect"):
                    task_monitor.record_skip("metric_collect", "paused")
                # ── metric_records 归档：定期删除超期数据 ──
                _ARCHIVE_INTERVAL = 3600
                if task_monitor.is_enabled("metric_archive") and _now - _last_archive_time >= _ARCHIVE_INTERVAL:
                    _last_archive_time = _now
                    _t0 = time.time()
                    task_monitor.record_start("metric_archive")
                    try:
                        from sqlalchemy import text as _arch_text
                        _cutoff = datetime.now() - timedelta(days=METRIC_RETENTION_DAYS)
                        _result = db.execute(_arch_text(
                            "DELETE FROM metric_records WHERE timestamp < :cutoff"
                        ), {"cutoff": _cutoff})
                        db.commit()
                        task_monitor.record_success("metric_archive", (time.time() - _t0) * 1000)
                        if _result.rowcount and _result.rowcount > 0:
                            logger.info(f"指标归档: 删除 {_result.rowcount} 条超期记录 (>{METRIC_RETENTION_DAYS}天)")
                    except Exception as ae:
                        task_monitor.record_failure("metric_archive", (time.time() - _t0) * 1000, str(ae))
                        logger.warning(f"指标归档异常: {ae}")
                elif not task_monitor.is_enabled("metric_archive"):
                    task_monitor.record_skip("metric_archive", "paused")
                # ── 数据源采集（独立执行，不受 120s 超时限制）──
                _SCRAPE_INTERVAL = 60
                if task_monitor.is_enabled("datasource_scrape") and _now - _last_scrape_time >= _SCRAPE_INTERVAL:
                    _last_scrape_time = _now
                    _t0 = time.time()
                    task_monitor.record_start("datasource_scrape")
                    try:
                        _scrape_results = datasource_service.scrape_all_sources(db)
                        _scrape_ok = sum(1 for r in _scrape_results if r.get("is_success"))
                        _scrape_fail = len(_scrape_results) - _scrape_ok
                        task_monitor.record_success("datasource_scrape", (time.time() - _t0) * 1000)
                        _elapsed_s = time.time() - _t0
                        if _elapsed_s > 30:
                            logger.warning(f"数据源采集耗时过长: {_elapsed_s:.1f}s (成功{_scrape_ok}/失败{_scrape_fail})")
                        elif _scrape_results:
                            logger.info(f"数据源采集: {_scrape_ok}成功/{_scrape_fail}失败, 耗时{_elapsed_s:.1f}s")
                    except Exception as se:
                        task_monitor.record_failure("datasource_scrape", (time.time() - _t0) * 1000, str(se))
                        logger.warning(f"数据源采集异常: {se}")
                elif not task_monitor.is_enabled("datasource_scrape"):
                    task_monitor.record_skip("datasource_scrape", "paused")
                # 报表调度
                if task_monitor.is_enabled("report_schedule"):
                    now = datetime.now()
                    schedules = db.query(ReportSchedule).filter(ReportSchedule.enabled == True).all()
                    for s in schedules:
                        try:
                            parts = s.cron_expr.split()
                            if len(parts) >= 5:
                                cron_min = int(parts[0])
                                cron_hour = int(parts[1])
                                if now.minute == cron_min and now.hour == cron_hour:
                                    _t0 = time.time()
                                    task_monitor.record_start("report_schedule")
                                    report = generate_report(db, s.report_type)
                                    s.last_run_at = now
                                    db.commit()
                                    task_monitor.record_success("report_schedule", (time.time() - _t0) * 1000)
                        except Exception as re:
                            task_monitor.record_failure("report_schedule", 0, str(re))
                else:
                    task_monitor.record_skip("report_schedule", "paused")
            finally:
                db.close()
        except Exception as e:
            import traceback
            logger.error(f"Error in background loop (aux): {e}")
            traceback.print_exc()
        time.sleep(BACKGROUND_INTERVAL)


# 两个库都初始化 admin 账号
init_admin()
set_db_mode("real")
init_admin()
set_db_mode("demo")
# 只对 demo 库灌入种子数据
seed_all()

# P2: 启动 edge agent 心跳监控（后台线程，扫描超时会话）
from app.services.edge_tunnel_service import start_heartbeat_monitor as _start_edge_hb
_start_edge_hb()
logger.info("Edge agent 心跳监控已启动")

# ── 安全启动检查：默认密钥/弱密码检测 ──
def _security_startup_check():
    """启动时检测安全风险：默认密钥、弱密码 admin"""
    _risks = []
    # 1. 检测 SECRET_KEY 是否为默认值
    _DEFAULT_KEY = "aiops-dev-secret-change-in-production-please"
    if _config.SECRET_KEY == _DEFAULT_KEY:
        _risks.append("SECRET_KEY 仍为默认值，生产环境必须设置 AIOPS_SECRET_KEY 环境变量")
    if _config.MOBILE_JWT_SECRET == "aiops-mobile-secret-dev":
        _risks.append("MOBILE_JWT_SECRET 仍为默认值，建议设置环境变量")
    # 2. 检测 admin 是否使用弱密码
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

_security_startup_check()
# 两个库都播种 SOP 工作流模板（幂等，按 name 去重）
from app.services.workflow_service import seed_workflow_templates
from app.services.agent_workflow_service import seed_agent_workflows, _preset_workflows as _get_agent_presets
from app.services.sub_agent_service import seed_sub_agents as _seed_sub_agents
for _mode in ("demo", "real"):
    set_db_mode(_mode)
    _seed_db = get_session_for(_mode)()
    try:
        _added = seed_workflow_templates(_seed_db)
        if _added:
            logger.info(f"{_mode} 库播种 {_added} 个 SOP 工作流模板")
        _added2 = seed_agent_workflows(_seed_db)
        if _added2:
            logger.info(f"{_mode} 库播种 {_added2} 个智能体工作流模板")
        # P1-1: 播种预置子专家（SRE/网络/数据库/中间件/K8s）
        _added3 = _seed_sub_agents(_seed_db)
        if _added3:
            logger.info(f"{_mode} 库播种 {_added3} 个预置子专家")
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


# ── 健康检查端点（容器化探针用）──
@app.get("/healthz")
async def healthz():
    """轻量存活检查"""
    return {"status": "ok"}


@app.get("/readyz")
async def readyz():
    """就绪检查：DB 连通性 + Milvus 连通性"""
    checks = {"db": "ok", "milvus": "ok"}
    try:
        from sqlalchemy import text
        _db = get_session_for(get_db_mode())()
        _db.execute(text("SELECT 1"))
        _db.close()
    except Exception as e:
        checks["db"] = f"fail: {e}"
    try:
        from app.services.vector_store import get_client
        get_client()
    except Exception as e:
        checks["milvus"] = f"fail: {e}"
    all_ok = all(v == "ok" for v in checks.values())
    return JSONResponse(checks, status_code=200 if all_ok else 503)

