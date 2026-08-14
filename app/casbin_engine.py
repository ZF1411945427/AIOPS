"""资源级 RBAC 策略引擎（对齐 Ongrid Casbin resource:action 策略矩阵，自研实现）。

设计：
- 策略 = RolePermission(resource, action) 三元组，按角色存 DB
- HTTP 请求 → (method, path) → (resource, action) 映射
- superuser 完全绕过策略（防策略损坏锁死管理员）
- 覆盖现有角色继承：菜单级 role_menus 仍在 AuthMiddleware 负责可见性，
  本引擎负责**操作权限**（写/执行/删除），作为第二道闸
"""
from typing import Optional, Tuple, Dict, List

# 资源:路径前缀映射（path → resource）。覆盖主要功能域，未列出的路径默认不拦截
RESOURCE_PATH_MAP: List[Tuple[str, str]] = [
    ("/agent-workflow", "workflow"),
    ("/agent/sub-agents", "sub_agent"),
    ("/agent/autonomous", "agent"),
    ("/agent/api/eval", "agent"),
    ("/agent/api/ground-truth", "agent"),
    ("/agent/api/ab-test", "agent"),
    ("/agent", "agent"),
    ("/alert-console", "alert"),
    ("/alert-silence", "alert"),
    ("/alert-storm", "alert"),
    ("/alert-webhooks", "alert"),
    ("/alerts", "alert"),
    ("/api/alert-correlation", "alert"),
    ("/alert-events", "alert"),
    ("/anomaly", "anomaly"),
    ("/api/chaos", "chaos"),
    ("/api/diagnostic-tools", "diagnostic"),
    ("/api/ops-analytics", "analytics"),
    ("/api/security-audit", "audit"),
    ("/api/audit", "audit"),
    ("/api/admin", "admin"),
    ("/api/system", "system"),
    ("/api/sre", "sre"),
    ("/api/network-test", "network"),
    ("/api/traces", "trace"),
    ("/api/tokens", "token"),
    ("/api/roles", "role"),
    ("/asset-changes", "asset"),
    ("/assets", "asset"),
    ("/baseline", "baseline"),
    ("/blue-green", "deploy"),
    ("/change-workflow", "change"),
    ("/chatops", "chatops"),
    ("/containers", "container"),
    ("/datasources", "datasource"),
    ("/deploy", "deploy"),
    ("/discovery", "asset"),
    ("/edge", "edge"),
    ("/events", "event"),
    ("/event-sources", "event"),
    ("/ext-cmdb", "cmdb"),
    ("/feature-store", "feature"),
    ("/health-map", "monitor"),
    ("/helm", "k8s"),
    ("/im", "chatops"),
    ("/incidents", "incident"),
    ("/inspection", "inspection"),
    ("/k8s", "k8s"),
    ("/knowledge", "knowledge"),
    ("/lifecycle", "asset"),
    ("/logs", "log"),
    ("/log-rca", "rca"),
    ("/log-anomaly", "log"),
    ("/metrics", "metric"),
    ("/notification-templates", "notification"),
    ("/notifications", "notification"),
    ("/observability", "observability"),
    ("/remediation", "remediation"),
    ("/report-schedules", "report"),
    ("/reports", "report"),
    ("/runbooks", "runbook"),
    ("/sandbox", "sandbox"),
    ("/script", "script"),
    ("/service-mesh", "mesh"),
    ("/settings", "config"),
    ("/smart-recommend", "ai"),
    ("/tags", "asset"),
    ("/topology", "topology"),
    ("/trace-rca", "rca"),
    ("/traces", "trace"),
    ("/users", "user"),
    ("/workflow", "workflow"),
    ("/predictions", "metric"),
    ("/prediction-models", "metric"),
    ("/pcadr", "rca"),
    ("/pagerank-rca", "rca"),
    ("/dtw", "rca"),
    ("/idice", "rca"),
    ("/granger", "rca"),
    ("/hotspot", "metric"),
    ("/trend-prediction", "metric"),
    ("/ci-models", "metric"),
    ("/cluster-anomaly", "anomaly"),
    ("/netflow", "network"),
    ("/webssh", "remote"),
    ("/drain", "k8s"),
]

# 资源的中文名（前端展示用）
RESOURCE_LABELS: Dict[str, str] = {
    "admin": "系统管理", "agent": "智能体", "sub_agent": "子智能体", "workflow": "智能体编排",
    "alert": "告警", "anomaly": "异常", "asset": "资产", "audit": "审计", "baseline": "基线",
    "change": "变更", "chatops": "IM通道", "chaos": "混沌实验", "cmdb": "外部CMDB",
    "config": "系统配置", "container": "容器", "datasource": "数据源", "deploy": "部署",
    "diagnostic": "诊断工具", "edge": "边缘Agent", "event": "事件", "feature": "特征库",
    "incident": "故障", "inspection": "巡检", "k8s": "K8s", "knowledge": "知识库",
    "log": "日志", "mesh": "服务网格", "metric": "指标", "monitor": "监控",
    "network": "网络", "notification": "通知", "observability": "可观测性", "remote": "远程终端",
    "remediation": "自愈", "report": "报告", "rca": "根因分析", "role": "角色",
    "runbook": "操作手册", "sandbox": "沙盒", "script": "脚本", "sre": "SRE",
    "system": "系统", "token": "Token", "topology": "拓扑", "trace": "链路",
    "user": "用户", "analytics": "运维分析",
}

# 动作枚举（前端展示用）
ACTIONS: List[str] = ["read", "write", "execute", "delete"]
ACTION_LABELS: Dict[str, str] = {
    "read": "查看", "write": "修改", "execute": "执行", "delete": "删除",
}

# HTTP method → action 映射
_METHOD_ACTION = {
    "GET": "read",
    "HEAD": "read",
    "OPTIONS": "read",
    "POST": "write",
    "PUT": "write",
    "PATCH": "write",
    "DELETE": "delete",
}

# 视为"执行"操作的路径片段（POST/PUT 命中这些片段 → execute 而非 write）
_EXECUTE_HINTS = (
    "/run", "/execute", "/deploy", "/rollout", "/restart", "/confirm", "/retry",
    "/abort", "/start", "/stop", "/scale", "/apply", "/install", "/submit",
    "/test", "/probe", "/check", "/eval", "/switch", "/remediate", "/rollback",
    "/canary", "/promote", "/sync",
)

# 敏感执行动作：非 execute 权限的 write 也会被拦截到 execute 级
_STRICT_EXECUTE_PREFIXES = (
    "/deploy/", "/containers/api/deploy/", "/remediation/", "/script/api",
    "/sandbox/api/execute", "/k8s-offline/", "/helm/api/release/install",
    "/helm/api/release/uninstall", "/edge/commands",
)


def map_path_resource(path: str) -> Optional[str]:
    """path → resource（最长前缀匹配，命中即返回）。"""
    best: Optional[Tuple[int, str]] = None
    for prefix, resource in RESOURCE_PATH_MAP:
        if path.startswith(prefix):
            if best is None or len(prefix) > best[0]:
                best = (len(prefix), resource)
    return best[1] if best else None


def map_method_action(method: str, path: str) -> str:
    """(method, path) → action。POST/PUT 命中执行提示片段视为 execute。"""
    base = _METHOD_ACTION.get(method, "read")
    if method in ("POST", "PUT") and path.startswith(_STRICT_EXECUTE_PREFIXES):
        return "execute"
    if method in ("POST", "PUT"):
        for hint in _EXECUTE_HINTS:
            if hint in path:
                return "execute"
    return base


def resolve_request(path: str, method: str) -> Optional[Tuple[str, str]]:
    """HTTP 请求 → (resource, action)；无法映射的路径返回 None（不拦截）。"""
    resource = map_path_resource(path)
    if resource is None:
        return None
    action = map_method_action(method, path)
    return resource, action


def get_all_resources() -> List[str]:
    return sorted({r for _, r in RESOURCE_PATH_MAP})


def is_superuser_role(role_name: str, is_system: bool = False) -> bool:
    """superuser 判定：admin 角色 / 系统内置角色视为 superuser（完全绕过策略）。"""
    return role_name in ("admin", "superuser") or (is_system and role_name == "admin")
