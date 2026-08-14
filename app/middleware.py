"""中间件层: 从 main.py 拆出的中间件类 + 公开路径集。"""
from fastapi import Request
from fastapi.responses import RedirectResponse, JSONResponse
from starlette.middleware.base import BaseHTTPMiddleware

PUBLIC_PATHS = {"/login", "/static", "/assets", "/product", "/product/intro", "/product/overview", "/user-guide", "/vue-assets", "/mobile-app", "/api/system/db-mode", "/api/v1/traces/ingest-status", "/api/v1/traces/otlp", "/api/v1/traces/jaeger", "/api/v1/traces/agent-guide", "/v1/traces", "/mobile", "/me", "/healthz", "/readyz", "/health-map", "/api/system/health", "/api/menu", "/license", "/edge/commands/pending", "/im/callback", "/api/traces/domains", "/api/traces/services", "/api/traces/asset-domains", "/sandbox", "/agent", "/edge/metrics", "/metrics"}


class TraceIdMiddleware(BaseHTTPMiddleware):
    """为每个请求生成/透传 trace_id，绑定到 logger，实现全链路日志串联(D3)。"""

    def __init__(self, app, logger):
        super().__init__(app)
        self._logger = logger

    async def dispatch(self, request: Request, call_next):
        trace_id = request.headers.get("x-request-id") or request.headers.get("trace-id")
        if not trace_id:
            import uuid
            trace_id = uuid.uuid4().hex[:16]
        request.state.trace_id = trace_id
        request.headers._list.append((b"x-request-id", trace_id.encode()))
        with self._logger.contextualize(trace_id=trace_id):
            return await call_next(request)


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
                _method = request.method
                if _method in ("POST", "PUT", "PATCH", "DELETE"):
                    if _user is None:
                        _db.close()
                        return JSONResponse({"error": "用户不存在"}, status_code=401)
                    from app.services.permission_service import check_path_permission
                    _allowed = check_path_permission(_db, user_id, path, _method)
                    if _allowed is False:
                        _db.close()
                        return JSONResponse(
                            {"error": "权限不足：当前角色无此资源操作权限"},
                            status_code=403,
                        )
            finally:
                _db.close()
        return await call_next(request)