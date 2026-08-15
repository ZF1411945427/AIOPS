"""AI 多专家路由服务 (对标天穹「多智能体协同」)

根据用户提问领域识别并注入对应"子专家"身份与优先工具引导,
让 LLM 自动倾向调用对应领域组件诊断工具, 提升组件对话管控效果。
纯提示注入 + 工具引导, 不动核心 tool-loop, 低风险。
"""
from typing import Dict, List

# 专家领域定义: 关键词 -> (专家名, 身份描述, 优先工具引导)
EXPERT_GROUPS: List[Dict] = [
    {
        "domain": "database",
        "name": "数据库专家",
        "keywords": ["数据库", "sql", "查询", "慢查询", "表", "索引", "主从", "复制", "mysql", "postgres", "postgresql", "mongo", "oracle", "tidb", "mariadb", "达梦", "金仓", "opengauss", "oceanbase", "clickhouse", "influxdb", "redis 数据", "表空间", "死锁", "锁等待", "连接池", "dba"],
        "tools": ["query_mysql", "pg_diagnose", "mongo_diagnose", "oracle_diagnose", "tidb_diagnose", "mariadb_diagnose", "clickhouse_diagnose", "mysql_variable", "check_mysql_permissions"],
        "guide": "你是数据库专家。请优先用对应数据库诊断工具(如 pg_diagnose/mongo_diagnose/query_mysql/tidb_diagnose/mariadb_diagnose)获取慢查询/连接/复制/锁的真实数据,再给出根因与优化建议,不要凭空猜测。",
    },
    {
        "domain": "cache",
        "name": "缓存专家",
        "keywords": ["redis", "缓存", "热key", "热 key", "命中率", "大key", "大 key", "valkey", "memcached", "内存淘汰", "逐出", "redis 连接", "雪崩", "穿透", "击穿"],
        "tools": ["redis_monitor", "valkey_diagnose", "memcached_diagnose"],
        "guide": "你是缓存专家。请优先用 redis_monitor/valkey_diagnose/memcached_diagnose 查内存/命中率/连接/热Key 真实指标,再给优化建议(大Key拆分/淘汰策略/连接池)。",
    },
    {
        "domain": "message",
        "name": "消息队列专家",
        "keywords": ["kafka", "rabbitmq", "rocketmq", "消息队列", "消费", "lag", "延迟", "堆积", "topic", "emqx", "mqtt", "nats", "actvemq", "activemq", "topic 分区", "offset", "消费组"],
        "tools": ["kafka_monitor", "rabbitmq_diagnose", "rocketmq_diagnose", "emqx_diagnose"],
        "guide": "你是消息队列专家。请优先用 kafka_monitor/rabbitmq_diagnose/rocketmq_diagnose/emqx_diagnose 查消费延迟/Topic/Broker/堆积真实数据,再定位根因。",
    },
    {
        "domain": "network",
        "name": "网络专家",
        "keywords": ["网络", "交换机", "路由器", "llpd", "lldp", "接口", "链路", "丢包", "延迟", "带宽", "tcp", "防火墙", "路由", "vlan", "网卡", "netflow"],
        "tools": ["net_device_query", "prometheus_diagnose", "query_metrics"],
        "guide": "你是网络专家。请优先用 net_device_query 查接口/LLDP/链路,结合 query_metrics 看带宽/丢包真实数据,再诊断。",
    },
    {
        "domain": "kubernetes",
        "name": "Kubernetes 专家",
        "keywords": ["k8s", "kubernetes", "kubectl", "pod", "deployment", "容器", "节点", "命名空间", "namespace", "helm", "docker", "镜像", "cgroup", "调度", "集群 pod", "service", "ingress"],
        "tools": ["list_k8s_pods", "query_k8s_events", "list_k8s_deployments", "query_k8s_workloads", "k8s_resource_optimize"],
        "guide": "你是 Kubernetes 专家。请优先用 list_k8s_pods/query_k8s_events 查 Pod 状态与事件,再结合 query_logs/query_metrics 判定根因,给出处置建议。",
    },
    {
        "domain": "middleware",
        "name": "中间件/网关专家",
        "keywords": ["中间件", "网关", "nginx", "haproxy", "apisix", "traefik", "consul", "nacos", "zookeeper", "etcd", "vault", "keycloak", "代理", "反向代理", "负载均衡", "注册中心", "配置中心", "密钥"],
        "tools": ["nginx_diagnose", "consul_diagnose", "apisix_diagnose", "traefik_diagnose", "keycloak_diagnose", "nacos_diagnose", "zk_diagnose", "etcd_diagnose", "net_device_query"],
        "guide": "你是中间件/网关专家。请优先用 nginx_diagnose/consul_diagnose/apisix_diagnose/traefik_diagnose/nacos_diagnose 等查配置/路由/健康真实数据,再诊断。",
    },
    {
        "domain": "observability",
        "name": "可观测性专家",
        "keywords": ["监控", "指标", "prometheus", "grafana", "告警", "日志", "链路", "trace", "loki", "jaeger", "opentelemetry", "es 集群", "elasticsearch", "kibana", "logstash", "alertmanager", "victoria", "遥测", "可视化"],
        "tools": ["query_metrics", "query_logs", "query_traces", "query_alerts", "prometheus_diagnose", "grafana_diagnose", "loki_diagnose", "es_diagnose"],
        "guide": "你是可观测性专家。请优先用 query_metrics/query_logs/query_traces/query_alerts 查真实指标/日志/链路/告警,结合 prometheus_diagnose/es_diagnose/loki_diagnose 判断,再给结论。",
    },
    {
        "domain": "security",
        "name": "安全专家",
        "keywords": ["漏洞", "cve", "trivy", "安全", "漏洞扫描", "审计", "入侵", "攻击", "弱口令", "等保", "勒索", "恶意", "补丁", "cve扫", "基线安全"],
        "tools": ["check_config", "check_vuln", "query_asset_baseline", "query_security_audit"],
        "guide": "你是安全专家。请优先用 check_vuln/check_config/安全检查工具 查漏洞(CVE/Trivy)与基线,再给修复建议。",
    },
]


def route_expert(user_message: str) -> Dict:
    """根据用户提问识别领域专家。返回识别到的专家配置(未命中返回 None)。"""
    text = (user_message or "").lower()
    best = None
    best_score = 0
    for g in EXPERT_GROUPS:
        score = sum(1 for kw in g["keywords"] if kw in text)
        if score > best_score:
            best_score = score
            best = g
    return best if best and best_score > 0 else None


def build_expert_injection(user_message: str) -> str:
    """构建专家提示注入片段, 供 system_prompt 追加。未命中返回空串。"""
    expert = route_expert(user_message)
    if not expert:
        return ""
    tools_hint = "、".join(expert["tools"][:8])
    return (
        f"\n\n## 🧠 AI 子专家已激活: {expert['name']}\n"
        f"{expert['guide']}\n"
        f"优先推荐工具: {tools_hint}\n"
        f"(若问题涉及其他领域, 仍可使用全部工具)"
    )
