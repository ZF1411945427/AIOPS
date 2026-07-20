"""子智能体（Sub-agent）服务 — Multi-Agent Orchestration 的核心。

功能：
1. 5 个预置子专家定义（SRE/网络/数据库/中间件/K8s）
2. 关键词路由：根据用户消息自动选择子专家（零 LLM 调用，零延迟）
3. 工具白名单过滤：子专家只暴露其域内工具 + 通用工具
4. system_prompt 注入：子专家使用专属 prompt

设计原则：
- 路由用规则匹配（关键词），不引入额外 LLM 调用
- 用户可手动指定 sub_agent（覆盖自动路由）
- 子专家工具白名单为空时继承全部工具（向后兼容）
- 通用工具（propose_action/list_executable_actions 等）所有子专家都可见
"""
import json
from typing import List, Dict, Optional, Any

from sqlalchemy.orm import Session

from app.models import SubAgent
from app.services.mcp_registry import get_mcp_manifest, _MCP_TOOLS


# ─── 预置子专家定义 ───────────────────────────────────────────────

PRESET_SUB_AGENTS = [
    {
        "name": "sre_expert",
        "display_name": "SRE 可靠性专家",
        "domain": "sre",
        "description": "聚焦告警、故障、指标、变更、自愈等 SRE 核心场景，做根因分析与处置建议",
        "icon": "🛡️",
        "color": "#6366f1",
        "sort_order": 1,
        "keywords": ["告警", "故障", "根因", "rca", "异常", "指标", "cpu", "内存", "磁盘", "负载", "自愈", "重启", "变更", "sre", "可靠", "可用性", "故障单", "incident", "告警风暴", "级联"],
        "system_prompt": "你是 SRE 可靠性专家。专注告警分析、故障根因定位、指标异常排查、变更影响分析。排查时遵循：先看告警时序 → 再看指标异常 → 再看变更记录 → 给出根因假设 → 验证假设 → 给出处置建议。涉及网络/数据库/中间件/K8s 深度问题时，建议用户切换到对应子专家。",
        "tool_whitelist": [],  # 继承全部
    },
    {
        "name": "network_expert",
        "display_name": "网络专家",
        "domain": "network",
        "description": "聚焦网络连通性、带宽、丢包、DNS、路由、防火墙等网络问题",
        "icon": "🌐",
        "color": "#0ea5e9",
        "sort_order": 2,
        "keywords": ["网络", "ping", "连通", "带宽", "丢包", "dns", "域名", "路由", "traceroute", "防火墙", "iptables", "netflow", "tcp", "udp", "端口", "网络不通", "延迟", "网络抖动"],
        "system_prompt": "你是网络专家。专注网络连通性、带宽、丢包、DNS、路由、防火墙等问题。排查时遵循：先 ping/ttraceroute 测连通性 → 查 DNS 解析 → 查端口监听 → 查防火墙规则 → 查网络流量（netflow）→ 定位网络故障点。给出网络拓扑路径和故障点定位。",
        "tool_whitelist": ["query_assets", "query_metrics", "query_alerts", "query_logs", "query_runbook", "query_knowledge_rag", "query_correlation_analysis", "propose_action", "list_executable_actions", "get_task_status", "list_recent_tasks"],
    },
    {
        "name": "database_expert",
        "display_name": "数据库专家",
        "domain": "database",
        "description": "聚焦 MySQL/PostgreSQL/MongoDB 数据库性能、慢查询、连接数、锁等",
        "icon": "🗄️",
        "color": "#f59e0b",
        "sort_order": 3,
        "keywords": ["数据库", "mysql", "sql", "慢查询", "连接数", "锁", "死锁", "索引", "postgres", "mongodb", "redis", "数据库性能", "db", "查询优化", "事务", "主从", "延迟"],
        "system_prompt": "你是数据库专家。专注 MySQL/PostgreSQL/MongoDB 性能、慢查询、连接数、锁、索引、主从延迟等问题。排查时遵循：先查慢查询日志 → 查连接数/线程数 → 查锁等待 → 查索引使用 → 查主从延迟 → 给出优化建议。使用 query_mysql 执行诊断 SQL（SHOW PROCESSLIST / SHOW ENGINE INNODB STATUS 等）。",
        "tool_whitelist": ["query_mysql", "check_mysql_permissions", "query_assets", "query_metrics", "query_alerts", "query_logs", "query_runbook", "query_knowledge_rag", "propose_action", "list_executable_actions", "get_task_status", "list_recent_tasks"],
    },
    {
        "name": "middleware_expert",
        "display_name": "中间件专家",
        "domain": "middleware",
        "description": "聚焦 Nginx/Kafka/Redis/RabbitMQ/Elasticsearch 等中间件问题",
        "icon": "🔧",
        "color": "#10b981",
        "sort_order": 4,
        "keywords": ["中间件", "nginx", "kafka", "rabbitmq", "elasticsearch", "es", "zookeeper", "tomcat", "连接池", "消息队列", "消费", "生产者", "消费者", "中间件性能", "反代", "负载均衡"],
        "system_prompt": "你是中间件专家。专注 Nginx/Kafka/Redis/RabbitMQ/Elasticsearch/Tomcat 等中间件问题。排查时遵循：先查中间件进程状态 → 查连接数/线程数 → 查慢日志 → 查队列积压 → 查集群健康 → 给出调优建议。使用 query_metrics 查中间件指标，query_logs 查中间件日志。",
        "tool_whitelist": ["query_assets", "query_metrics", "query_alerts", "query_logs", "query_traces", "query_runbook", "query_knowledge_rag", "query_correlation_analysis", "propose_action", "list_executable_actions", "get_task_status", "list_recent_tasks"],
    },
    {
        "name": "k8s_expert",
        "display_name": "K8s 容器专家",
        "domain": "k8s",
        "description": "聚焦 K8s Pod/Deployment/Service/Node/Cluster 等容器编排问题",
        "icon": "☸️",
        "color": "#8b5cf6",
        "sort_order": 5,
        "keywords": ["k8s", "kubernetes", "pod", "deployment", "service", "node", "cluster", "容器", "docker", "镜像", "namespace", "cronjob", "job", "副本", "滚动更新", "pod 重启", "oomkill", "image"],
        "system_prompt": "你是 K8s 容器专家。专注 Pod/Deployment/Service/Node/Cluster 等容器编排问题。排查时遵循：先查 Pod 状态（Pending/Running/CrashLoopBackOff）→ 查 Events → 查 Pod 日志 → 查 Node 资源 → 查 Deployment 副本数 → 给出修复建议。使用 list_k8s_pods 和 query_k8s_events 查 K8s 状态。",
        "tool_whitelist": ["list_k8s_pods", "query_k8s_events", "query_assets", "query_metrics", "query_alerts", "query_logs", "query_traces", "query_runbook", "query_knowledge_rag", "query_correlation_analysis", "propose_action", "list_executable_actions", "get_task_status", "list_recent_tasks"],
    },
    {
        "name": "general",
        "display_name": "通用助手",
        "domain": "general",
        "description": "通用运维助手，不限定域，使用全部工具",
        "icon": "🤖",
        "color": "#64748b",
        "sort_order": 0,
        "keywords": [],
        "system_prompt": "",
        "tool_whitelist": [],
    },
]


def seed_sub_agents(db: Session) -> int:
    """幂等播种预置子专家。返回新增数量。"""
    added = 0
    for preset in PRESET_SUB_AGENTS:
        existing = db.query(SubAgent).filter(SubAgent.name == preset["name"]).first()
        if existing:
            # 更新关键字段（保留用户自定义的 system_prompt 如果改过）
            existing.display_name = preset["display_name"]
            existing.domain = preset["domain"]
            existing.description = preset["description"]
            existing.icon = preset["icon"]
            existing.color = preset["color"]
            existing.sort_order = preset["sort_order"]
            existing.keywords = json.dumps(preset["keywords"], ensure_ascii=False)
            existing.tool_whitelist = json.dumps(preset["tool_whitelist"], ensure_ascii=False)
            existing.is_enabled = True
            # system_prompt 只在为空时回填（保留用户自定义）
            if not existing.system_prompt:
                existing.system_prompt = preset["system_prompt"]
            continue
        sa = SubAgent(
            name=preset["name"],
            display_name=preset["display_name"],
            domain=preset["domain"],
            description=preset["description"],
            icon=preset["icon"],
            color=preset["color"],
            sort_order=preset["sort_order"],
            keywords=json.dumps(preset["keywords"], ensure_ascii=False),
            tool_whitelist=json.dumps(preset["tool_whitelist"], ensure_ascii=False),
            system_prompt=preset["system_prompt"],
            is_enabled=True,
        )
        db.add(sa)
        added += 1
    db.commit()
    return added


def list_sub_agents(db: Session, enabled_only: bool = True) -> List[SubAgent]:
    """列出所有子专家（按 sort_order）。"""
    q = db.query(SubAgent)
    if enabled_only:
        q = q.filter(SubAgent.is_enabled == True)
    return q.order_by(SubAgent.sort_order).all()


def get_sub_agent(db: Session, name: str) -> Optional[SubAgent]:
    """按 name 查子专家。"""
    return db.query(SubAgent).filter(SubAgent.name == name).first()


def route_sub_agent(message: str, db: Session) -> str:
    """根据用户消息关键词路由到子专家 name。

    匹配规则：按 sort_order 遍历，命中关键词最多的子专家胜出。
    无匹配返回 "general"。
    """
    if not message:
        return "general"
    msg_lower = message.lower()
    sub_agents = list_sub_agents(db, enabled_only=True)
    best_name = "general"
    best_score = 0
    for sa in sub_agents:
        if sa.name == "general":
            continue
        keywords = sa.get_keywords()
        score = sum(1 for kw in keywords if kw.lower() in msg_lower)
        if score > best_score:
            best_score = score
            best_name = sa.name
    return best_name if best_score > 0 else "general"


def filter_tools_by_sub_agent(tools: List[Dict[str, Any]], sub_agent: Optional[SubAgent]) -> List[Dict[str, Any]]:
    """按子专家工具白名单过滤工具列表。

    - sub_agent 为 None 或 tool_whitelist 为空 → 返回原列表
    - 否则只保留白名单内的工具
    """
    if not sub_agent:
        return tools
    whitelist = sub_agent.get_tool_whitelist()
    if not whitelist:
        return tools
    return [t for t in tools if t.get("name") in whitelist]


def get_sub_agent_prompt(sub_agent: Optional[SubAgent]) -> str:
    """获取子专家的 system_prompt。空则返回空字符串。"""
    if not sub_agent:
        return ""
    return sub_agent.system_prompt or ""


def sub_agent_to_dict(sa: SubAgent) -> Dict[str, Any]:
    """转成可 JSON 序列化的 dict。"""
    return {
        "id": sa.id,
        "name": sa.name,
        "display_name": sa.display_name,
        "domain": sa.domain,
        "description": sa.description,
        "icon": sa.icon,
        "color": sa.color,
        "sort_order": sa.sort_order,
        "is_enabled": sa.is_enabled,
        "keywords": sa.get_keywords(),
        "tool_whitelist": sa.get_tool_whitelist(),
        "tool_count": len(sa.get_tool_whitelist()) if sa.get_tool_whitelist() else 45,  # 空=继承全部
        "system_prompt": sa.system_prompt,
    }
