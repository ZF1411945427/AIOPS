"""领域注册中心 - 9 个业务域归类 100+ 路由

每个域包含：
- key: 域唯一标识
- label: 中文标签
- description: 域职责描述
- icon: Element Plus 图标名
- routers: 路由模块名列表（对应 app.routers 下的模块名）
- color: 域主题色（前端展示用）

注册顺序即路由注册顺序（保持向后兼容）。
"""

from typing import Dict, List, Any

# ── 9 个业务域定义 ──────────────────────────────────────────────────
DOMAIN_REGISTRY: Dict[str, Dict[str, Any]] = {
    "assets": {
        "key": "assets",
        "label": "资产管理",
        "description": "资产清单、自动发现、生命周期、拓扑关系、标签",
        "icon": "Box",
        "color": "#10b981",
        "routers": [
            "assets", "asset_changes", "asset_discovery", "lifecycle",
            "topology", "topology_path", "topo_graph", "tags", "ext_cmdb",
        ],
    },
    "alerts": {
        "key": "alerts",
        "label": "告警监控",
        "description": "告警中心、告警事件、风暴抑制、异常检测、热点分析",
        "icon": "Bell",
        "color": "#ef4444",
        "routers": [
            "alerts", "alert_console", "alert_events", "alert_silence",
            "alert_storm", "alert_webhooks", "anomaly", "cluster_anomaly",
            "hotspot",
        ],
    },
    "k8s": {
        "key": "k8s",
        "label": "容器编排",
        "description": "K8s 集群、资源监控、容器管理、Helm、蓝绿、服务网格",
        "icon": "Cloudy",
        "color": "#3b82f6",
        "routers": [
            "k8s_monitor", "k8s_resources", "containers", "helm",
            "blue_green", "service_mesh",
        ],
    },
    "ai": {
        "key": "ai",
        "label": "AI 智能体",
        "description": "AI Provider、智能助手、Agent 工作流、A/B 测试、Agent 评估",
        "icon": "Cpu",
        "color": "#8b5cf6",
        "routers": [
            "ai_providers", "agent_chat", "agent_sse", "agent_workflow",
            "agent_eval", "agent_ground_truth", "ab_test", "anomaly_eval",
        ],
    },
    "sre": {
        "key": "sre",
        "label": "可靠性工程",
        "description": "SLO、混沌工程、自愈、巡检、基线、Runbook",
        "icon": "Trophy",
        "color": "#f59e0b",
        "routers": [
            "sre", "chaos", "inspection", "baseline",
            "remediation", "remediation_workflow", "remediation_effect", "runbooks",
        ],
    },
    "knowledge": {
        "key": "knowledge",
        "label": "知识管理",
        "description": "故障知识库、RAG 文档、知识图谱、自动生成、智能推荐",
        "icon": "Reading",
        "color": "#14b8a6",
        "routers": [
            "knowledge", "knowledge_documents", "knowledge_v2", "knowledge_graph",
            "knowledge_autogen", "smart_recommend",
        ],
    },
    "incident": {
        "key": "incident",
        "label": "故障运营",
        "description": "故障单、仪表盘、运营分析、报表、报表调度",
        "icon": "Tickets",
        "color": "#f97316",
        "routers": [
            "incidents", "dashboard", "dashboard_config",
            "ops_analytics", "reports", "report_schedules",
        ],
    },
    "tracing": {
        "key": "tracing",
        "label": "链路追踪",
        "description": "Trace、链路异常、链路根因、日志异常、日志根因、DTW、PageRank",
        "icon": "Guide",
        "color": "#06b6d4",
        "routers": [
            "traces", "traces_api", "trace_anomaly", "trace_ingest",
            "trace_rca", "trace_view", "dtw", "pagerank_rca",
            "log_rca", "log_anomaly", "logs",
        ],
    },
    "platform": {
        "key": "platform",
        "label": "平台与集成",
        "description": "认证、用户、角色、租户、令牌、系统配置、审计、菜单、License、WebSocket、移动端、集成、数据源、事件、指标、通知、诊断、脚本、变更、工作流、ChatOps、关联分析、可观测性关联、健康图",
        "icon": "Setting",
        "color": "#6366f1",
        "routers": [
            "auth", "users", "roles", "settings", "system", "system_posture",
            "audit", "menu", "license", "tenant_management", "tokens", "ws",
            "api_v1", "mobile", "health_map", "network_test",
            "datasources", "es_integration", "event_sources", "events",
            "kafka_pipeline", "netflow", "feature_store", "ci_models",
            "drain", "granger", "idice", "trend_prediction",
            "prediction_models", "predictions", "predictions_enhanced", "pcadr",
            "metrics", "notifications", "notification_templates",
            "correlation", "observability_correlation",
            "script_exec", "ansible", "change_workflow", "workflow",
            "chatops", "discovery", "diagnostic_tools",
            "security_audit",
        ],
    },
}

# 注册顺序（用于路由按域分组注册）
DOMAIN_ORDER: List[str] = [
    "assets", "alerts", "k8s", "ai", "sre",
    "knowledge", "incident", "tracing", "platform",
]


def get_routers_for_domain(domain_key: str) -> List[str]:
    """返回指定域的所有路由模块名"""
    domain = DOMAIN_REGISTRY.get(domain_key)
    return list(domain["routers"]) if domain else []


def get_domain_summary() -> List[Dict[str, Any]]:
    """返回所有域的汇总信息（含路由数量）"""
    summary = []
    for key in DOMAIN_ORDER:
        domain = DOMAIN_REGISTRY[key]
        summary.append({
            "key": domain["key"],
            "label": domain["label"],
            "description": domain["description"],
            "icon": domain["icon"],
            "color": domain["color"],
            "router_count": len(domain["routers"]),
            "routers": list(domain["routers"]),
        })
    return summary


def get_all_router_modules() -> List[str]:
    """返回所有域的路由模块名（按域顺序）"""
    modules = []
    for key in DOMAIN_ORDER:
        modules.extend(DOMAIN_REGISTRY[key]["routers"])
    return modules
