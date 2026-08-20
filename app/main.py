import json
import mimetypes
import os as _os
import threading
import time

# Windows 上 Python 默认把 .js 映射为 text/plain，导致浏览器拒绝执行 module script
mimetypes.add_type("text/javascript", ".js")
mimetypes.add_type("text/javascript", ".mjs")

from fastapi import FastAPI
from fastapi.staticfiles import StaticFiles as _FastStaticFiles
from fastapi.middleware.cors import CORSMiddleware
from starlette.middleware.sessions import SessionMiddleware
from starlette.middleware.gzip import GZipMiddleware

from fastapi import Request
from starlette.middleware.base import BaseHTTPMiddleware

from fastapi.responses import HTMLResponse, JSONResponse
from pathlib import Path

from app.logger import logger
from app.middleware import PUBLIC_PATHS, TraceIdMiddleware, AuthMiddleware
from app.startup import (_security_startup_check, _scan_builtin_skills,
                         background_loop)


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
# alerts 告警监控域
# k8s 容器编排域
# ai 智能体域
# sre 可靠性工程域
# knowledge 知识管理域
# incident 故障运营域
# tracing 链路追踪域
# platform 平台与集成域
# admin 系统管理路由（领域清单 + 背景任务看板，P1 任务#4/#6）
# 离线部署(Offline Repo) — 对标 Pixiu builder serve
# K8S 离线集群部署 — 对标 Pixiu 一键建集群
# P2 任务#9 告警收敛闭环 / P2 任务#10 RAG 检索质量评估
# 安全自查（SAST / 依赖 CVE / License 合规 / 配置基线，打磨期 P0）
# AI 洞察引擎 — 统一指标/日志/链路三页 AI 增强
from app.services import mcp_tools  # noqa: F401 — register MCP tools on import
from app.services import agent_workflow_service  # noqa: F401 — 工作流告警自动触发 / run 恢复
from app.services import workflow_cron_scheduler  # noqa: F401 — 工作流 cron 定时调度
from app.services import auto_investigator  # noqa: F401 — 告警自动调查闭环(C1/C2/C3)
from app.services import skill_registry  # noqa: F401 — F1/F2 技能注册表与市场
from app.services.license_service import LicenseMiddleware

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
        "review_result TEXT DEFAULT ''",
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
    "alert_rules": [
        "kind VARCHAR(24) DEFAULT 'metric_raw'",
        "config_json TEXT DEFAULT '{}'",
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
        "online_since DATETIME",
    ],
    "alerts": [
        "archived BOOLEAN DEFAULT 0",
        "last_notified_at DATETIME",
        "source VARCHAR(32) DEFAULT 'internal'",
    ],
    "trace_anomaly_configs": [
        "check_window_minutes INTEGER DEFAULT 30",
    ],
    "audit_logs": [
        "route_path VARCHAR(256) DEFAULT ''",
    ],
    "diagnosis_reports": [
        "round_num INTEGER DEFAULT 0",
    ],
    "remediation_logs": [
        "remediation_type VARCHAR(16) DEFAULT 'rule'",
    ],
    "remediation_effects": [
        "remediation_type VARCHAR(16) DEFAULT 'rule'",
    ],
    "deploy_plans": [
        "environment_probe_json TEXT DEFAULT '{}'",
        "env_analysis_json TEXT DEFAULT '{}'",
        "deploy_report_json TEXT DEFAULT '{}'",
        "test_results_json TEXT DEFAULT '{}'",
        "execution_history_json TEXT DEFAULT '[]'",
        "cleanup_history_json TEXT DEFAULT '[]'",
        "last_deployed_at DATETIME",
        "deploy_count INTEGER DEFAULT 0",
        "dag_json TEXT DEFAULT '{}'",
        "pending_decision_json TEXT DEFAULT 'null'",
        "ai_decision_log_json TEXT DEFAULT '[]'",
        "strategy VARCHAR(32) DEFAULT 'auto'",
        "risk_score INTEGER DEFAULT 0",
        "health_gate_json TEXT DEFAULT '[]'",
        "deployment_feature_json TEXT DEFAULT '{}'",
        "artifact_download_path VARCHAR(512) DEFAULT ''",
        "artifact_auto_download BOOLEAN DEFAULT 1",
        "use_offline BOOLEAN DEFAULT 0",
        "http_proxy VARCHAR(256) DEFAULT ''",
        "https_proxy VARCHAR(256) DEFAULT ''",
        "no_proxy VARCHAR(512) DEFAULT ''",
    ],
    "deploy_steps": [
        "diagnosis TEXT DEFAULT ''",
        "fix_command TEXT DEFAULT ''",
        "retry_count INTEGER DEFAULT 0",
        "precheck_result TEXT DEFAULT ''",
    ],
    "metric_dashboard_cards": [
        "user_id INTEGER DEFAULT 0",
        "hours INTEGER DEFAULT 24",
        "w INTEGER DEFAULT 2",
        "h INTEGER DEFAULT 1",
        "order INTEGER DEFAULT 0",
    ],
    "chat_messages": [
        "sub_agent VARCHAR(64) DEFAULT ''",
    ],
    "k8s_cluster_plans": [
        "http_proxy VARCHAR(256) DEFAULT ''",
        "https_proxy VARCHAR(256) DEFAULT ''",
        "no_proxy VARCHAR(512) DEFAULT ''",
        "untaint_master BOOLEAN DEFAULT 0",
        "cert_expiry_years INTEGER",
        "pending_decision_json TEXT DEFAULT 'null'",
    ],
    "sandbox_policies": [
        "allowed_workdirs TEXT DEFAULT '[]'",
    ],
    "component_installs": [
        "report_json TEXT DEFAULT ''",
        "deploy_params TEXT DEFAULT '{}'",
        "pending_decision_json TEXT DEFAULT 'null'",
    ],
    "component_catalog": [
        "param_schema TEXT DEFAULT '[]'",
    ],
}
for _eng in get_all_engines().values():
    _is_pg = _eng.dialect.name == "postgresql"
    with _eng.connect() as _conn:
        for _table, _cols in _MIGRATIONS.items():
            for _col_def in _cols:
                try:
                    if _is_pg:
                        # PG: ADD COLUMN IF NOT EXISTS 幂等, 避免 DuplicateColumn 污染事务
                        _conn.execute(_sa_text(f"ALTER TABLE {_table} ADD COLUMN IF NOT EXISTS {_col_def}"))
                    else:
                        _conn.execute(_sa_text(f"ALTER TABLE {_table} ADD COLUMN {_col_def}"))
                    _conn.commit()
                except Exception:
                    try:
                        _conn.rollback()
                    except Exception:
                        pass

        # 重建 pending_actions 表：旧表 session_id 为 NOT NULL，工作流场景需 NULL
        # (仅 SQLite 需要; PG 由模型 create_all 按 session_id 可空建好)
        if not _is_pg:
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
            "CREATE INDEX IF NOT EXISTS idx_spans_service_time ON spans (service_name, started_at)",
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

# ── 全局 JSON 序列化：Decimal → float 兜底 ──
from decimal import Decimal as _Decimal
_json_encoder_default = json.JSONEncoder.default
def _json_default(self, obj):
    if isinstance(obj, _Decimal):
        return float(obj)
    return _json_encoder_default(self, obj)
json.JSONEncoder.default = _json_default
# 替换 json.dumps() 内部缓存的编码器实例, 使补丁生效
json._default_encoder = json.JSONEncoder()

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
    emsg = str(exc)
    # 连接池耗尽在 demo 模式下是预期行为, 降级为 WARNING 不刷 ERROR
    if "QueuePool" in emsg and "overflow" in emsg:
        logger.warning(f"连接池耗尽: {request.url.path} - {emsg}")
    else:
        logger.error(f"Unhandled exception on {request.url.path}: {exc}\n{traceback.format_exc()}")
    if isinstance(exc, _HTTPException):
        # H1: 统一错误结构(保留 detail/error 兼容 request.js)
        return JSONResponse({
            "ok": False, "code": exc.status_code, "message": exc.detail,
            "detail": exc.detail, "error": exc.detail, "data": None,
        }, status_code=exc.status_code)
    # fail-soft 兜底：未预期异常返回 200 + warning，避免前端整页 500 (保留旧字段兼容)
    return JSONResponse({"warning": f"服务器内部错误: {exc}", "items": [], "total": 0, "code": 500, "ok": False}, status_code=200)

import time as _time_import
_APP_START_TIME = _time_import.time()  # 进程启动时间（/metrics 用）

# 中间件定义移至 app/middleware.py


app.add_middleware(GZipMiddleware, minimum_size=1000)
app.add_middleware(SlowAPIMiddleware)
app.add_middleware(LicenseMiddleware)
app.add_middleware(AuthMiddleware)
app.add_middleware(SessionMiddleware, secret_key=_config.SESSION_SECRET,
                   https_only=_config.APP_ENV == "prod",
                   same_site="lax", max_age=86400)
# trace_id 全链路串联: 注册最外层(包裹所有中间件), 保证每个请求都有 trace_id 上下文
from app.logger import logger as _trace_logger
app.add_middleware(TraceIdMiddleware, logger=_trace_logger)
# D2 增强: HTTP 应用级指标计数(最外层, 记录请求/错误/延迟)
from app.services.http_metrics import HttpMetricsMiddleware
app.add_middleware(HttpMetricsMiddleware)

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
            # 构建产物文件名带 hash，改为每次重新校验，避免强制刷新仍命中旧 JS/CSS
            response.headers["Cache-Control"] = "public, max-age=0, must-revalidate"
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
            response.headers.setdefault("Permissions-Policy", "geolocation=(), microphone=(self), camera=()")
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
    # index.html 禁止缓存: 构建产物文件名带 hash, 缓存旧 index.html 会导致引用旧 JS/CSS 404
    return HTMLResponse(content=content, headers={"Cache-Control": "no-cache, no-store, must-revalidate"})


from app.bootstrap import register_routers as _register_routers
_register_routers(app)



# 启动函数移至 app/startup.py






_security_startup_check()
# 两个库都播种 SOP 工作流模板（幂等，按 name 去重）
from app.services.workflow_service import seed_workflow_templates
from app.services.agent_workflow_service import seed_agent_workflows, _preset_workflows as _get_agent_presets
from app.services.sub_agent_service import seed_sub_agents as _seed_sub_agents
for _mode in ("demo", "real"):
    set_db_mode(_mode)
    _seed_db = get_session_for(_mode)()
    try:
        # PG/生产库严格外键: 先确保默认租户存在, 再初始化 admin 角色/用户/权限
        from app.services.tenant_service import get_or_create_default_tenant as _ensure_tenant
        from app.startup import init_admin as _init_admin
        _ensure_tenant(_seed_db)
        _init_admin()
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
        # F1: 扫描内置 SKILL.md 技能入库（增量, 已有 name 不覆盖）
        _added4 = _scan_builtin_skills(_seed_db)
        if _added4:
            logger.info(f"{_mode} 库扫描加载 {_added4} 个内置技能")
        # P1-5: 重载外部 MCP 服务器已启用工具
        try:
            from app.services import mcp_external as _mcp_ext
            _mcp_ext.reload_external_tools(_seed_db)
        except Exception:
            pass
        # 给已有种子工作流的 tool 节点补 execution_mode: auto（向后兼容）
        from app.models import AgentWorkflow
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

# M5: 启动时注册所有 Provider 到统一注册表
try:
    _reg_db = get_session_for(get_db_mode())()
    try:
        from app.core.provider_base import register_all_providers
        _n = register_all_providers(_reg_db)
        logger.info(f"Provider 注册表初始化完成: {_n} 个 Provider")
    finally:
        _reg_db.close()
except Exception as _reg_e:
    logger.warning(f"Provider 注册表初始化失败: {_reg_e}")

threading.Thread(target=background_loop, daemon=True).start()

# B4: 进程重启后恢复未完成的工作流 run（running/awaiting_confirm 续跑）
try:
    from app.database import get_session_for as _gsf
    from app.database import get_db_mode as _gdm
    _resume_db = _gsf(_gdm())()
    try:
        agent_workflow_service.resume_unfinished_runs(_resume_db)
    finally:
        _resume_db.close()
except Exception as _resume_e:
    from app.logger import logger
    logger.warning(f"工作流 run 恢复初始化失败: {_resume_e}")


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


@app.get("/metrics")
async def prom_metrics():
    """Prometheus exposition 端点(D2): 应用级指标 + Python 进程指标(无第三方依赖)。"""
    import time
    from fastapi.responses import PlainTextResponse
    from app.services import mcp_registry
    lines = [
        "# HELP aiops_healthz Backend alive (1=ok)",
        "# TYPE aiops_healthz gauge",
        "aiops_healthz 1",
        "# HELP aiops_mcp_tool_count Number of registered internal+external MCP tools",
        "# TYPE aiops_mcp_tool_count gauge",
        f"aiops_mcp_tool_count {len(mcp_registry._MCP_TOOLS) + len(mcp_registry._EXTERNAL_TOOLS)}",
        "# HELP aiops_db_alive Database reachable (1=ok)",
        "# TYPE aiops_db_alive gauge",
        "aiops_db_alive 1",
        "# HELP aiops_app_up App run time (seconds since process start)",
        "# TYPE aiops_app_up counter",
        f"aiops_app_up {int(time.time() - _APP_START_TIME)}",
        "# HELP python_gc_objects_collected Number of collected objects",
        "# TYPE python_gc_objects_collected counter",
    ]
    try:
        from app.database import get_session_for, get_db_mode
        from sqlalchemy import text as _sa_text
        _metrics_db = get_session_for(get_db_mode())()
        rules = _metrics_db.execute(_sa_text("select count(*) from alert_rules")).scalar() or 0
        skills = _metrics_db.execute(_sa_text("select count(*) from skills")).scalar() or 0
        _metrics_db.close()
        lines.append("# HELP aiops_alert_rule_count Number of alert rules")
        lines.append("# TYPE aiops_alert_rule_count gauge")
        lines.append(f"aiops_alert_rule_count {rules}")
        lines.append('# HELP aiops_skill_count Number of skills')
        lines.append('# TYPE aiops_skill_count gauge')
        lines.append(f"aiops_skill_count {skills}")
    except Exception:
        pass
    # D2 增强: HTTP 应用级请求/错误/延迟指标
    try:
        from app.services.http_metrics import render_http_metrics
        lines = render_http_metrics(lines)
    except Exception:
        pass
    # H3[B]: 工具级调用/错误/延迟指标(metric decorator)
    try:
        from app.services.tool_metrics import render_tool_metrics
        lines = render_tool_metrics(lines)
    except Exception:
        pass
    return PlainTextResponse("\n".join(lines) + "\n", media_type="text/plain; version=0.0.4")


# ── gRPC OTLP TraceService 服务器（接收微服务 gRPC OTLP 流量）──
try:
    from app.grpc_server import start_grpc_server, stop_grpc_server
    import atexit
    start_grpc_server()
    atexit.register(stop_grpc_server)
except Exception as _grpc_err:
    logger.warning(f"[gRPC] OTLP TraceService 启动失败: {_grpc_err}")

