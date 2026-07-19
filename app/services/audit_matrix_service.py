"""审计覆盖矩阵服务（P2 任务#11）

审计完整性闭环：
1. 静态扫描所有 router 端点，标记写操作
2. 中间件自动记录写操作到 audit_logs 表
3. 矩阵展示: 路径 × 方法 × 是否写操作 × 是否已记审计 × 实际审计记录数

设计:
- 路径推断 target_type（assets/incidents/users/config/tokens 等）
- 路径推断 action（POST→create / PUT→update / DELETE→delete / approve / login 等）
- 密码字段脱敏（password / token / secret / key 等）
- 列表查询接口跳过审计（避免噪声）
"""
from __future__ import annotations

import re
import time
from datetime import datetime
from typing import Any, Dict, List, Optional

from sqlalchemy import func, desc
from sqlalchemy.orm import Session

from app.logger import logger
from app.models import AuditLog


# ── 路径 → target_type 推断 ──
_TARGET_TYPE_PATTERNS = [
    (re.compile(r"/(assets|asset_changes|asset_discovery|lifecycle|topology)"), "asset"),
    (re.compile(r"/(incidents|incident_approvals)"), "incident"),
    (re.compile(r"/(users|roles|tokens)"), "user_permission"),
    (re.compile(r"/(ai_providers|ai/providers|agent_workflow|agent_chat|ab_test|agent_ground_truth)"), "ai_provider"),
    (re.compile(r"/(settings|system_configs|system|config)"), "config"),
    (re.compile(r"/(chaos|chaos_experiments)"), "chaos"),
    (re.compile(r"/(remediation|auto_remediations)"), "remediation"),
    (re.compile(r"/(knowledge|kb_documents|knowledge_drafts|knowledge_base)"), "knowledge"),
    (re.compile(r"/(alerts|alert_rules|alert_silence|alert_storm)"), "alert"),
    (re.compile(r"/(sre|slo|error_budget|burn_rate|availability)"), "sre"),
    (re.compile(r"/(script_exec|scripts)"), "script"),
    (re.compile(r"/(helm|blue_green|service_mesh)"), "deploy"),
    (re.compile(r"/(change_requests|change_workflow|workflow)"), "change"),
    (re.compile(r"/(tenants|tenant_management)"), "tenant"),
    (re.compile(r"/(dashboard|dashboard_config)"), "dashboard"),
    (re.compile(r"/(notifications|notification_templates)"), "notification"),
    (re.compile(r"/(datasources|ext_cmdb|ext_event_sources)"), "datasource"),
]

# ── 路径 → action 推断 ──
_ACTION_PATTERNS = [
    (re.compile(r"/login|/auth"), "login"),
    (re.compile(r"/logout"), "logout"),
    (re.compile(r"/approve"), "approve"),
    (re.compile(r"/reject"), "reject"),
    (re.compile(r"/submit"), "submit"),
    (re.compile(r"/trigger"), "trigger"),
    (re.compile(r"/pause|/resume"), "pause_resume"),
    (re.compile(r"/reset"), "reset"),
    (re.compile(r"/silence"), "silence"),
    (re.compile(r"/escalate"), "escalate"),
    (re.compile(r"/acknowledge"), "acknowledge"),
    (re.compile(r"/resolve"), "resolve"),
    (re.compile(r"/upload"), "upload"),
    (re.compile(r"/index"), "index"),
]

# ── 敏感字段脱敏 ──
_SENSITIVE_KEY_PATTERNS = re.compile(
    r"(password|passwd|secret|token|api_key|apikey|private_key|credential|kubeconfig|ssh_password|db_password)",
    re.IGNORECASE,
)


def infer_target_type(path: str) -> str:
    for pat, ttype in _TARGET_TYPE_PATTERNS:
        if pat.search(path):
            return ttype
    return "other"


def infer_action(method: str, path: str) -> str:
    for pat, act in _ACTION_PATTERNS:
        if pat.search(path):
            return act
    method_action_map = {
        "POST": "create", "PUT": "update", "PATCH": "update", "DELETE": "delete",
    }
    return method_action_map.get(method, method.lower())


def _mask_sensitive_body(body: str, max_len: int = 2000) -> str:
    """脱敏请求体中的敏感字段"""
    if not body:
        return ""
    try:
        import json as _json
        data = _json.loads(body)
        if isinstance(data, dict):
            for k in list(data.keys()):
                if _SENSITIVE_KEY_PATTERNS.search(k):
                    data[k] = "***"
            masked = _json.dumps(data, ensure_ascii=False)
        else:
            masked = body
    except Exception:
        # 非 JSON，用正则替换 "password":"xxx" 模式
        masked = re.sub(
            r'("(?:password|passwd|secret|token|api_key|apikey|private_key|credential|kubeconfig|ssh_password|db_password)"\s*:\s*")([^"]*)(")',
            r'\1***\3', body, flags=re.IGNORECASE,
        )
    return masked[:max_len]


def record_audit(
    db: Session,
    user_id: Optional[int],
    username: str,
    method: str,
    path: str,
    status_code: int,
    ip: str = "",
    user_agent: str = "",
    request_body: str = "",
    response_summary: str = "",
    duration_ms: int = 0,
    route_path: str = "",
) -> bool:
    """记录一条审计日志"""
    try:
        log = AuditLog(
            user_id=user_id,
            username=username or "",
            method=method.upper(),
            path=path[:256],
            route_path=(route_path or path)[:256],
            action=infer_action(method, path),
            target_type=infer_target_type(path),
            target_id="",
            status_code=status_code,
            ip=ip[:64] if ip else "",
            user_agent=user_agent[:256] if user_agent else "",
            request_body=_mask_sensitive_body(request_body),
            response_summary=response_summary[:256],
            duration_ms=duration_ms,
        )
        db.add(log)
        db.commit()
        return True
    except Exception as e:
        logger.warning(f"record_audit 异常: {e}")
        db.rollback()
        return False


def list_audit_logs(
    db: Session,
    limit: int = 100,
    action: str = "",
    user_name: str = "",
) -> Dict[str, Any]:
    """查询审计日志（支持 action / user 过滤）"""
    q = db.query(AuditLog)
    if action:
        q = q.filter(AuditLog.action == action)
    if user_name:
        q = q.filter(AuditLog.username.like(f"%{user_name}%"))
    total = q.count()
    logs = q.order_by(desc(AuditLog.created_at)).limit(min(limit, 500)).all()
    return {
        "total": total,
        "logs": [
            {
                "id": l.id,
                "user_id": l.user_id,
                "username": l.username,
                "method": l.method,
                "path": l.path,
                "route_path": getattr(l, "route_path", "") or "",
                "action": l.action,
                "target_type": l.target_type,
                "status_code": l.status_code,
                "ip": l.ip,
                "duration_ms": l.duration_ms,
                "created_at": l.created_at.strftime("%Y-%m-%d %H:%M:%S") if l.created_at else None,
            }
            for l in logs
        ],
    }


def build_audit_matrix() -> Dict[str, Any]:
    """构建审计覆盖矩阵（静态分析所有写端点）。

    从 FastAPI app 的 routes 中扫描所有 POST/PUT/PATCH/DELETE 端点，
    按目标类型分组统计，并查询 audit_logs 表的实际记录数。
    """
    try:
        from app.main import app
    except Exception as e:
        logger.warning(f"build_audit_matrix: 无法 import app: {e}")
        return {"matrix": [], "summary": {"warning": str(e)}}

    write_endpoints: List[Dict[str, Any]] = []
    seen_paths: set = set()
    for route in app.routes:
        methods = getattr(route, "methods", None) or set()
        path = getattr(route, "path", "")
        if not path or not methods:
            continue
        # 跳过非业务路径
        if path.startswith(("/static", "/vue-assets", "/mobile-app", "/openapi", "/docs", "/redoc", "/healthz", "/readyz")):
            continue
        for m in methods:
            if m in ("POST", "PUT", "PATCH", "DELETE"):
                key = f"{m} {path}"
                if key in seen_paths:
                    continue
                seen_paths.add(key)
                write_endpoints.append({
                    "method": m,
                    "path": path,
                    "target_type": infer_target_type(path),
                    "action": infer_action(m, path),
                })

    # 按 target_type 分组统计
    by_type: Dict[str, int] = {}
    by_action: Dict[str, int] = {}
    for ep in write_endpoints:
        by_type[ep["target_type"]] = by_type.get(ep["target_type"], 0) + 1
        by_action[ep["action"]] = by_action.get(ep["action"], 0) + 1

    # 查 audit_logs 表的实际记录数（按 target_type / action 分组 + 按 method+route_path 精确匹配）
    try:
        from app.database import get_session_for, get_db_mode
        _db = get_session_for(get_db_mode())()
        try:
            type_counts = _db.query(
                AuditLog.target_type, func.count(AuditLog.id)
            ).group_by(AuditLog.target_type).all()
            action_counts = _db.query(
                AuditLog.action, func.count(AuditLog.id)
            ).group_by(AuditLog.action).all()
            total_logs = _db.query(func.count(AuditLog.id)).scalar() or 0
            recent_logs = _db.query(AuditLog).order_by(desc(AuditLog.created_at)).limit(5).all()
            recent_sample = [
                {
                    "username": l.username,
                    "method": l.method,
                    "path": l.path,
                    "route_path": getattr(l, "route_path", "") or "",
                    "action": l.action,
                    "created_at": l.created_at.strftime("%Y-%m-%d %H:%M:%S") if l.created_at else None,
                }
                for l in recent_logs
            ]
            # 按 method + route_path 精确匹配（用于实际覆盖率）
            # 优先用 route_path（新字段），回退到 path（旧记录）
            endpoint_counts = _db.query(
                AuditLog.method, AuditLog.route_path, func.count(AuditLog.id)
            ).group_by(AuditLog.method, AuditLog.route_path).all()
            endpoint_recorded = {(m, rp): c for m, rp, c in endpoint_counts if rp}
            # 也按 method + path 兜底（旧记录无 route_path）
            path_counts = _db.query(
                AuditLog.method, AuditLog.path, func.count(AuditLog.id)
            ).group_by(AuditLog.method, AuditLog.path).all()
            for m, p, c in path_counts:
                key = (m, p)
                if key not in endpoint_recorded:
                    endpoint_recorded[key] = c
        finally:
            _db.close()
    except Exception as e:
        logger.warning(f"build_audit_matrix 查 audit_logs 异常: {e}")
        type_counts, action_counts, total_logs, recent_sample = [], [], 0, []
        endpoint_recorded = {}

    type_recorded = {t: c for t, c in type_counts}
    action_recorded = {a: c for a, c in action_counts}

    # 构造矩阵：
    # - audited (精确): 该 method+route_path 在 audit_logs 中有记录
    # - type_action_covered (聚合): 同 type 或同 action 有过记录（旧逻辑，保留作辅助）
    # - capability_covered (能力): 中间件能拦截到（所有写端点都= True，因为 AuditMiddleware 拦截所有 POST/PUT/PATCH/DELETE）
    matrix: List[Dict[str, Any]] = []
    actual_audited_count = 0
    for ep in write_endpoints:
        ep_method = ep["method"]
        ep_route = ep["path"]  # matrix 中的 path 就是路由模板
        # 精确匹配：method + route_path
        precise_recorded = endpoint_recorded.get((ep_method, ep_route), 0) > 0
        # 聚合匹配（旧逻辑）：同 type 或同 action 有过记录
        type_action_covered = (
            type_recorded.get(ep["target_type"], 0) > 0
            or action_recorded.get(ep["action"], 0) > 0
        )
        if precise_recorded:
            actual_audited_count += 1
        matrix.append({
            **ep,
            "audited": precise_recorded,  # 精确：该端点有实际审计记录
            "type_action_covered": type_action_covered,  # 聚合：同类型/动作有记录
            "capability_covered": True,  # 能力：中间件能拦截（所有写端点都为 True）
            "records_count": endpoint_recorded.get((ep_method, ep_route), 0),
        })

    # 按路径排序
    matrix.sort(key=lambda x: (x["target_type"], x["path"], x["method"]))

    # 三个覆盖率：
    # - capability_coverage_rate: 审计中间件能拦截的写端点比例（应=100%）
    # - actual_coverage_rate: 实际有审计记录的端点比例（精确匹配 method+route_path）
    # - type_action_coverage_rate: 同类型/动作有记录的端点比例（旧逻辑，聚合）
    capability_count = sum(1 for m in matrix if m.get("capability_covered"))
    type_action_count = sum(1 for m in matrix if m.get("type_action_covered"))

    summary = {
        "total_write_endpoints": len(write_endpoints),
        "audited_endpoint_count": actual_audited_count,  # 精确实际覆盖
        "coverage_rate": round(actual_audited_count / max(len(matrix), 1), 4),  # 主指标改为精确覆盖率
        "capability_coverage_rate": round(capability_count / max(len(matrix), 1), 4),
        "type_action_coverage_rate": round(type_action_count / max(len(matrix), 1), 4),
        "capability_endpoint_count": capability_count,
        "type_action_endpoint_count": type_action_count,
        "total_audit_logs": total_logs,
        "by_target_type": by_type,
        "by_action": by_action,
        "type_recorded": type_recorded,
        "action_recorded": action_recorded,
        "recent_sample": recent_sample,
        "analyzed_at": datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
    }

    return {
        "summary": summary,
        "matrix": matrix,
    }


def list_audit_logs_api_wrap(limit: int = 100, action: str = "", user_name: str = "") -> Dict[str, Any]:
    """API 包装：独立 session 查询审计日志"""
    from app.database import get_session_for, get_db_mode
    _db = get_session_for(get_db_mode())()
    try:
        return list_audit_logs(_db, limit=limit, action=action, user_name=user_name)
    finally:
        _db.close()
