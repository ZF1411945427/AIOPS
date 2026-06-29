import json
import random
import hashlib
from datetime import datetime, timedelta

from app.database import get_session_for, get_db_mode
from app.models import (
    User, Asset, AssetRelation, AssetLifecycle, CiModel, CiAttribute,
    AlertRule, Alert, Incident, IncidentAlert, AlertSuppression,
    AlertSilenceSchedule, AlertWebhook,
    K8sEvent, MetricRecord,
    ChatSession, ChatMessage, ToolInvocation, PendingAction,
    ChangeRequest, ChangeTask,
    KnowledgeBase, Runbook,
    NotificationLog, NotificationTemplate, NotificationChannel,
    DataSource, SystemPostureRecord, NetFlowRecord, ScriptTask,
    AutoRemediation, RemediationWorkflow, BlueGreenDeploy,
    DiscoveryJob, ExtCmdbConfig, ExtEventSource,
    KafkaPipeline, FeatureStoreItem, PredictionModel,
    DashboardCardConfig, ReportSchedule, ApiToken,
    AIProvider, AgentConfig, ServiceMeshConfig, NetFlowCollector,
)
from app.services import config_service


def seed_all():
    db = get_session_for(get_db_mode())()
    # Use a marker to track if seed has been applied
    from app.models import SystemConfig
    marker = db.query(SystemConfig).filter(SystemConfig.key == "seed_data_applied").first()
    if marker and marker.value == "v1":
        db.close()
        return
    marker_v = "v1"
    # Remove the old marker if exists (will be re-created at end)
    if marker:
        db.delete(marker)

    now = datetime.now()
    days_ago = lambda d: now - timedelta(days=d)
    hours_ago = lambda h: now - timedelta(hours=h)

    # ── Users ──
    demo_users = []
    for name in ["admin", "zhangsan", "lisi", "wangwu"]:
        u = db.query(User).filter(User.username == name).first()
        if not u:
            u = User(username=name, password_hash=hashlib.sha256(b"123456").hexdigest(), role="admin")
            db.add(u); db.flush()
        demo_users.append(u)

    # ── CI Models (skip if exist) ──
    ci_types = [
        ("server", "服务器"), ("vm", "虚拟机"), ("container", "容器"),
        ("database", "数据库"), ("network", "网络设备"), ("middleware", "中间件"),
        ("storage", "存储"), ("loadbalancer", "负载均衡"),
    ]
    ci_model_objs = {}
    for key, label in ci_types:
        m = db.query(CiModel).filter(CiModel.name == key).first()
        if not m:
            m = CiModel(name=key, display_name=label)
            db.add(m); db.flush()
        ci_model_objs[key] = m

    # ── Assets (30+) ──
    asset_data = [
        # (name, ci_type, ip, status, tags)
        ("web-prod-01", "server", "10.0.1.10", "online", ["production", "web"]),
        ("web-prod-02", "server", "10.0.1.11", "online", ["production", "web"]),
        ("web-prod-03", "server", "10.0.1.12", "degraded", ["production", "web"]),
        ("api-prod-01", "server", "10.0.2.10", "online", ["production", "api"]),
        ("api-prod-02", "server", "10.0.2.11", "online", ["production", "api"]),
        ("db-master-01", "database", "10.0.3.10", "online", ["production", "mysql", "master"]),
        ("db-slave-01", "database", "10.0.3.11", "online", ["production", "mysql", "slave"]),
        ("db-slave-02", "database", "10.0.3.12", "offline", ["production", "mysql", "slave"]),
        ("redis-cache-01", "middleware", "10.0.4.10", "online", ["production", "redis"]),
        ("k8s-master-01", "server", "10.0.5.10", "online", ["kubernetes", "master"]),
        ("k8s-node-01", "vm", "10.0.5.11", "online", ["kubernetes", "node"]),
        ("k8s-node-02", "vm", "10.0.5.12", "online", ["kubernetes", "node"]),
        ("k8s-node-03", "vm", "10.0.5.13", "offline", ["kubernetes", "node"]),
        ("lb-01", "loadbalancer", "10.0.6.10", "online", ["production", "nginx"]),
        ("nas-storage-01", "storage", "10.0.7.10", "online", ["nfs"]),
        ("mq-prod-01", "middleware", "10.0.8.10", "online", ["production", "kafka"]),
        ("monitor-01", "server", "10.0.9.10", "online", ["monitoring", "prometheus"]),
        ("dev-web-01", "server", "192.168.1.10", "online", ["dev", "web"]),
        ("dev-api-01", "server", "192.168.1.20", "online", ["dev", "api"]),
        ("dev-db-01", "database", "192.168.1.30", "online", ["dev", "postgres"]),
        ("test-node-01", "vm", "192.168.2.10", "online", ["test"]),
        ("test-node-02", "vm", "192.168.2.11", "degraded", ["test"]),
        ("container-app-01", "container", "10.0.10.1", "online", ["k8s", "app"]),
        ("container-app-02", "container", "10.0.10.2", "online", ["k8s", "app"]),
        ("container-app-03", "container", "10.0.10.3", "online", ["k8s", "app"]),
        ("es-cluster-01", "middleware", "10.0.11.10", "online", ["elasticsearch", "data"]),
        ("es-cluster-02", "middleware", "10.0.11.11", "online", ["elasticsearch", "data"]),
        ("gateway-01", "network", "10.0.0.1", "online", ["gateway"]),
        ("fw-01", "network", "10.0.0.2", "online", ["firewall"]),
        ("sw-core-01", "network", "10.0.0.3", "online", ["switch", "core"]),
    ]
    asset_objs = {}
    for name, ci_type, ip, status, tags in asset_data:
        existing = db.query(Asset).filter(Asset.name == name).first()
        if existing:
            asset_objs[name] = existing
            continue
        a = Asset(
            name=name, type=ci_type, ci_type=ci_type,
            ip=ip, status=status, tags=json.dumps(tags),
            ci_attributes=json.dumps({
                "cpu_cores": random.choice([4, 8, 16, 32]),
                "memory_gb": random.choice([8, 16, 32, 64, 128]),
                "disk_gb": random.choice([100, 200, 500, 1000, 2000]),
                "os": random.choice(["Ubuntu 22.04", "CentOS 7", "Debian 11"]),
            }),
            created_at=days_ago(random.randint(30, 180)),
        )
        db.add(a); db.flush()
        asset_objs[name] = a

    # ── Asset Relations (topology, skip if exists) ──
    relations = [
        ("gateway-01", "lb-01"), ("lb-01", "web-prod-01"), ("lb-01", "web-prod-02"), ("lb-01", "web-prod-03"),
        ("web-prod-01", "api-prod-01"), ("web-prod-02", "api-prod-01"), ("web-prod-03", "api-prod-02"),
        ("api-prod-01", "db-master-01"), ("api-prod-02", "db-master-01"),
        ("db-master-01", "db-slave-01"), ("db-master-01", "db-slave-02"),
        ("api-prod-01", "redis-cache-01"), ("api-prod-02", "redis-cache-01"),
        ("api-prod-01", "mq-prod-01"), ("api-prod-02", "mq-prod-01"),
        ("k8s-master-01", "k8s-node-01"), ("k8s-master-01", "k8s-node-02"), ("k8s-master-01", "k8s-node-03"),
        ("k8s-node-01", "container-app-01"), ("k8s-node-02", "container-app-02"), ("k8s-node-03", "container-app-03"),
        ("web-prod-01", "nas-storage-01"), ("db-master-01", "nas-storage-01"),
        ("es-cluster-01", "es-cluster-02"),
        ("fw-01", "gateway-01"),
        ("sw-core-01", "fw-01"),
    ]
    existing_rels = set()
    for rel in db.query(AssetRelation).all():
        existing_rels.add((rel.parent_id, rel.child_id))
    for parent, child in relations:
        if parent in asset_objs and child in asset_objs:
            pid, cid = asset_objs[parent].id, asset_objs[child].id
            if (pid, cid) not in existing_rels:
                db.add(AssetRelation(parent_id=pid, child_id=cid, relation_type="depends"))

    # ── Asset Lifecycle ──
    for a in list(asset_objs.values())[:15]:
        for status in ["provisioning", "running", "running", "running"]:
            db.add(AssetLifecycle(
                asset_id=a.id, status=status,
                previous_status="provisioning" if status == "running" else "unknown",
                changed_by=demo_users[0].id, comment="自动部署",
                created_at=days_ago(random.randint(5, 60)),
            ))

    # ── Alert Rules ──
    rules_data = [
        ("CPU 使用率过高", "cpu_usage", ">", 90, "critical"),
        ("内存使用率过高", "memory_usage", ">", 90, "critical"),
        ("磁盘使用率过高", "disk_usage", ">", 85, "warning"),
        ("网络延迟过高", "network_latency", ">", 200, "warning"),
        ("连接数过多", "connections", ">", 5000, "critical"),
        ("API 错误率过高", "api_error_rate", ">", 5, "critical"),
        ("MySQL 慢查询", "mysql_slow_queries", ">", 50, "warning"),
        ("Redis 内存过高", "redis_memory", ">", 80, "warning"),
        ("磁盘 IO 等待", "disk_iowait", ">", 30, "warning"),
        ("进程数过多", "process_count", ">", 500, "info"),
    ]
    rule_objs = []
    for name, metric, condition, threshold, severity in rules_data:
        r = AlertRule(name=name, metric_name=metric, condition=condition, threshold=threshold, severity=severity, enabled=True)
        db.add(r); db.flush()
        rule_objs.append(r)

    # ── Alerts (80+) ──
    statuses = ["firing", "firing", "resolved", "resolved", "resolved", "resolved"]
    alert_objs = []
    for i in range(80):
        rule = random.choice(rule_objs)
        asset = random.choice(list(asset_objs.values()))
        ts = hours_ago(random.randint(0, 168))
        a = Alert(
            rule_id=rule.id, asset_id=asset.id,
            metric_name=rule.metric_name,
            actual_value=round(random.uniform(rule.threshold * 0.8, rule.threshold * 1.5), 2),
            threshold=rule.threshold, severity=rule.severity,
            status=random.choice(statuses),
            message=f"{asset.name} {rule.metric_name} 异常: {rule.metric_name} = {round(random.uniform(rule.threshold * 0.8, rule.threshold * 1.5), 2)}",
            created_at=ts,
            resolved_at=ts + timedelta(minutes=random.randint(5, 120)) if random.random() > 0.3 else None,
        )
        db.add(a); db.flush()
        alert_objs.append(a)

    # ── Incidents (10+) ──
    for i in range(12):
        alerts_subset = random.sample(alert_objs, min(random.randint(2, 5), len(alert_objs)))
        inc = Incident(
            title=f"{random.choice(['生产', '测试', '预发'])}环境 {random.choice(['数据库', '网络', '应用', '容器', '存储'])}故障 #{i+1}",
            severity=random.choice(["critical", "critical", "warning", "warning", "info"]),
            status=random.choice(["open", "open", "analyzing", "resolved"]),
            asset_id=random.choice(list(asset_objs.values())).id,
            alert_count=len(alerts_subset),
            created_at=hours_ago(random.randint(2, 168)),
            resolved_at=hours_ago(random.randint(0, 48)) if random.random() > 0.4 else None,
        )
        db.add(inc); db.flush()
        for a in alerts_subset:
            db.add(IncidentAlert(incident_id=inc.id, alert_id=a.id))

    # ── K8s Events (40+) ──
    k8s_reasons = ["BackOff", "CrashLoopBackOff", "ImagePullBackOff", "OOMKilling", "NodeNotReady", "FailedScheduling", "Unhealthy", "ProbeWarning", "Evicted"]
    for i in range(45):
        ev = K8sEvent(
            cluster="prod-k8s",
            namespace=random.choice(["default", "production", "monitoring", "logging", "istio-system"]),
            name=f"pod-{random.choice(['web', 'api', 'worker', 'cache', 'db'])}-{random.randint(1000, 9999)}",
            kind="Pod",
            reason=random.choice(k8s_reasons),
            message=random.choice([
                "Back-off restarting failed container", "Container image pull failed",
                "OOMKilled: memory limit exceeded", "Node condition: DiskPressure",
                "Readiness probe failed", "Liveness probe failed: timeout",
                "Failed to schedule pod: insufficient memory",
            ]),
            source=random.choice(["kubelet", "scheduler", "controller-manager"]),
            first_seen=hours_ago(random.randint(0, 720)),
            last_seen=hours_ago(random.randint(0, 24)),
            count=random.randint(1, 50),
            severity=random.choice(["warning", "warning", "warning", "critical", "normal"]),
        )
        db.add(ev)

    # ── MetricRecords (time series last 7 days, one per 2h per asset) ──
    metric_names = ["cpu_usage", "memory_usage", "disk_usage", "network_in", "network_out"]
    for asset in list(asset_objs.values())[:20]:
        for h in range(0, 168, 2):
            ts = hours_ago(h)
            for mn in metric_names:
                base = {
                    "cpu_usage": random.uniform(10, 95),
                    "memory_usage": random.uniform(30, 92),
                    "disk_usage": random.uniform(20, 88),
                    "network_in": random.uniform(10, 500),
                    "network_out": random.uniform(5, 300),
                }[mn]
                noise = random.uniform(-5, 5)
                db.add(MetricRecord(
                    asset_id=asset.id, name=mn,
                    value=round(max(0, base + noise), 2),
                    unit={"cpu_usage": "%", "memory_usage": "%", "disk_usage": "%", "network_in": "Mbps", "network_out": "Mbps"}[mn],
                    labels=json.dumps({"host": asset.ip}),
                    timestamp=ts,
                ))

    # ── DataSources ──
    ds_list = [
        ("Prometheus 生产", "prometheus", "http://10.0.9.10:9090", True),
        ("VictoriaMetrics", "victoriametrics", "http://10.0.9.11:8428", True),
        ("Elasticsearch 生产", "elasticsearch", "http://10.0.11.10:9200", True),
        ("Grafana Loki", "loki", "http://10.0.9.12:3100", True),
        ("SkyWalking", "skywalking", "http://10.0.9.13:12800", True),
        ("Jaeger 测试", "jaeger", "http://192.168.2.10:16686", False),
    ]
    for name, ds_type, endpoint, enabled in ds_list:
        if not db.query(DataSource).filter(DataSource.name == name).first():
            db.add(DataSource(
                name=name, type=ds_type, endpoint=endpoint,
                auth_type="none", scrape_interval=30, enabled=enabled,
                mapping_config=json.dumps({"default_asset_type": "server"}),
                last_status="healthy" if enabled else "unknown",
                last_scrape=hours_ago(random.randint(0, 2)),
            ))

    # ── Notification Channels ──
    if not db.query(NotificationChannel).filter(NotificationChannel.type == "email").first():
        db.add(NotificationChannel(name="邮件通知", type="email", config=json.dumps({"smtp_host": "smtp.example.com", "smtp_port": 587}), enabled=True))
    if not db.query(NotificationChannel).filter(NotificationChannel.type == "webhook").first():
        db.add(NotificationChannel(name="企业微信", type="webhook", config=json.dumps({"url": "https://qyapi.weixin.qq.com/cgi-bin/webhook/send?key=xxx"}), enabled=True))
    if not db.query(NotificationChannel).filter(NotificationChannel.type == "slack").first():
        db.add(NotificationChannel(name="Slack 告警", type="slack", config=json.dumps({"webhook_url": "https://hooks.slack.com/services/xxx"}), enabled=False))

    # ── Notification Logs ──
    channels = db.query(NotificationChannel).all()
    for i in range(50):
        alert = random.choice(alert_objs)
        db.add(NotificationLog(
            alert_id=alert.id,
            channel_id=random.choice(channels).id if channels else None,
            channel_type=random.choice(["email", "webhook", "slack"]),
            recipient=random.choice(["admin@example.com", "ops@example.com", "dev@example.com"]),
            title=f"告警通知: {alert.metric_name}",
            content=f"{alert.message} — 来自 {alert.created_at}",
            success=random.random() > 0.15,
            error_message=None if random.random() > 0.15 else "Connection timeout",
            created_at=alert.created_at,
        ))

    # ── Notification Templates ──
    for tpl in [
        ("告警通知-邮件", "email", "【AIOps】{{ alert.severity }} 告警: {{ alert.metric_name }}", "告警详情:\n  资源: {{ asset.name }}\n  指标: {{ alert.metric_name }}\n  当前值: {{ alert.actual_value }}\n  阈值: {{ alert.threshold }}"),
        ("告警通知-企业微信", "webhook", "告警通知", '{"msgtype": "markdown", "markdown": {"content": "## {{ alert.severity }} 告警\\n  **资源:** {{ asset.name }}\\n **指标:** {{ alert.metric_name }}"}}'),
    ]:
        name, ct, title_tpl, body_tpl = tpl
        if not db.query(NotificationTemplate).filter(NotificationTemplate.name == name).first():
            db.add(NotificationTemplate(name=name, channel_type=ct, title_template=title_tpl, body_template=body_tpl, enabled=True))

    # ── Chat Sessions + Messages + ToolInvocations ──
    for user in demo_users[:2]:
        for topic, msgs in [
            ("排查 Web 服务器 CPU 过高问题", [
                ("user", "帮我查一下 web-prod-01 的 CPU 使用率"),
                ("assistant", "正在查询 web-prod-01 的 CPU 指标...", '{"tool_calls": "[{\\\"name\\\":\\\"query_metric\\\"]}"'),
            ]),
            ("分析 MySQL 主从延迟", [
                ("user", "检查 MySQL 主从同步状态"),
                ("assistant", "已查询 db-master-01 和 db-slave-01 的复制状态", '{"tool_calls": "[{\\\"name\\\":\\\"query_mysql_replication\\\"]}"'),
            ]),
            ("查看告警统计", [
                ("user", "最近一周的告警统计"),
                ("assistant", "以下是最近7天告警汇总: 总共 45 条告警，其中 critical 12 条，warning 28 条", '{"tool_calls": "[{\\\"name\\\":\\\"query_alerts\\\"]}"'),
            ]),
        ]:
            session = ChatSession(user_id=user.id, title=topic, status="active", last_message_at=hours_ago(random.randint(1, 72)))
            db.add(session); db.flush()
            for role, content, *extra in msgs:
                tool_calls = extra[0] if extra else None
                msg = ChatMessage(session_id=session.id, role=role, content=content, tool_calls=tool_calls, created_at=hours_ago(random.randint(1, 72)))
                db.add(msg); db.flush()
                if role == "assistant" and tool_calls:
                    db.add(ToolInvocation(
                        session_id=session.id, message_id=msg.id,
                        tool_name=random.choice(["query_metric", "query_alerts", "query_logs", "execute_script"]),
                        status=random.choice(["success", "success", "success", "failed"]),
                        latency_ms=random.randint(50, 3000),
                        request_payload=json.dumps({"params": {"query": topic}}),
                        response_summary=json.dumps({"rows": random.randint(1, 50)}),
                    ))

    # ── Change Requests ──
    for i in range(15):
        asset = random.choice(list(asset_objs.values()))
        cr = ChangeRequest(
            title=f"{random.choice(['升级', '扩容', '重启', '迁移', '配置变更'])} {asset.name}",
            description=f"计划对 {asset.name} 进行{random.choice(['版本升级', '容量扩展', '服务重启', '机房迁移', '参数调整'])}",
            ci_type=asset.ci_type, asset_id=asset.id,
            change_type=random.choice(["normal", "normal", "normal", "emergency"]),
            priority=random.choice(["P0", "P1", "P2", "P3"]),
            status=random.choice(["pending", "pending", "approved", "in_progress", "completed", "completed", "rejected"]),
            risk_level=random.choice(["low", "medium", "high"]),
            planned_start=days_ago(random.randint(1, 14)),
            planned_end=days_ago(random.randint(0, 13)),
            requester_id=random.choice(demo_users).id,
            reviewer_id=random.choice(demo_users).id if random.random() > 0.3 else None,
            review_comment=random.choice(["审批通过", "需要更多评估", None, None, None]),
            created_at=days_ago(random.randint(1, 30)),
        )
        db.add(cr); db.flush()
        for step in range(random.randint(1, 4)):
            db.add(ChangeTask(
                change_id=cr.id, step_order=step,
                description=f"步骤 {step+1}: {random.choice(['备份数据', '停止服务', '执行变更', '验证状态', '启动服务'])}",
                command=random.choice(["systemctl stop nginx", "kubectl rollout restart", "ansible-playbook upgrade.yml", "echo 'done'"]),
                status=random.choice(["pending", "running", "completed", "completed", "failed"]) if cr.status == "completed" else "pending",
                executed_by=random.choice(demo_users).id if random.random() > 0.5 else None,
                created_at=cr.created_at + timedelta(hours=step),
            ))

    # ── Knowledge Base ──
    kb_entries = [
        ("CPU 使用率过高排查", "服务器 CPU 持续超过 90%", "应用程序异常或流量突增", "1. top 查看进程\n2. 检查慢查询\n3. 查看访问日志\n4. 考虑水平扩展", ["cpu", "性能"]),
        ("MySQL 主从延迟", "从库延迟持续增加", "主库写入压力大或从库性能不足", "1. 检查主库写入量\n2. 优化慢查询\n3. 升级从库配置\n4. 考虑读写分离", ["mysql", "database"]),
        ("容器 OOMKilled", "Pod 被 OOM Killer 终止", "内存 limit 设置过小", "1. 查看内存使用趋势\n2. 调整 resources.limits.memory\n3. 检查内存泄漏\n4. 配置 HPA", ["k8s", "container"]),
        ("磁盘空间不足处理", "磁盘使用率超过 85%", "日志文件或数据文件增长", "1. du -sh 定位大目录\n2. 清理过期日志\n3. 扩容磁盘\n4. 配置日志轮转", ["disk", "storage"]),
        ("502 Bad Gateway 排查", "Nginx 返回 502", "后端服务不可用或超时", "1. 检查后端服务端口\n2. 查看后端日志\n3. 检查连接池\n4. 调整 timeout 配置", ["nginx", "web"]),
        ("网络丢包排查", "ping 丢包率超过 5%", "网卡故障或带宽饱和", "1. ifconfig 检查错误计数\n2. mtr 追踪路径\n3. 检查带宽使用\n4. 更换网卡", ["network"]),
        ("K8s Pod CrashLoopBackOff", "Pod 反复重启", "启动命令失败或健康检查不通过", "1. kubectl logs 查看错误\n2. 检查启动命令\n3. 调整 liveness probe\n4. 查看 events", ["k8s", "pod"]),
        ("Redis 内存淘汰", "Redis 内存使用超限", "内存不足触发 LRU 淘汰", "1. 查看 maxmemory 配置\n2. 分析 key 大小\n3. 优化过期策略\n4. 扩容 Redis 集群", ["redis", "cache"]),
        ("Kafka 消息堆积", "消费者 lag 持续增加", "消费能力不足或生产者突增", "1. 查看消费组状态\n2. 增加消费者分区\n3. 检查消费逻辑\n4. 扩容 Kafka 集群", ["kafka", "mq"]),
        ("SSL 证书过期", "HTTPS 访问证书错误", "证书未及时续期", "1. 检查证书到期日\n2. 申请新证书\n3. 替换证书文件\n4. 重启 Web 服务", ["ssl", "security"]),
    ]
    for title, symptom, root_cause, solution, tags in kb_entries:
        if not db.query(KnowledgeBase).filter(KnowledgeBase.title == title).first():
            db.add(KnowledgeBase(
                title=title, symptom=symptom, root_cause=root_cause, solution=solution,
                tags=json.dumps(tags), created_at=days_ago(random.randint(10, 180)),
            ))

    # ── Runbooks ──
    runbook_entries = [
        ("Web 服务重启流程", "运维", "Web 服务无响应", "检查进程状态", "1. SSH 登录服务器\n2. systemctl status nginx\n3. systemctl restart nginx\n4. 验证 curl localhost\n5. 通知业务方", ["web", "nginx"], "high", "server"),
        ("数据库备份恢复", "运维", "数据损坏或误删除", "执行备份恢复流程", "1. 确认备份文件位置\n2. 停止应用写入\n3. 执行 mysqlbinlog 恢复\n4. 验证数据完整性\n5. 恢复应用", ["database", "mysql"], "critical", "database"),
        ("K8s 节点维护流程", "运维", "节点需要下线维护", "节点排空与维护", "1. kubectl cordon\n2. kubectl drain --ignore-daemonsets\n3. 执行维护操作\n4. kubectl uncordon\n5. 验证 Pod 调度", ["k8s", "node"], "medium", "vm"),
    ]
    for title, category, symptom, diagnosis, steps, tags, severity, asset_type in runbook_entries:
        if not db.query(Runbook).filter(Runbook.title == title).first():
            db.add(Runbook(
                title=title, category=category, symptom=symptom, diagnosis=diagnosis,
                steps=steps, tags=json.dumps(tags), severity=severity, asset_type=asset_type,
                created_at=days_ago(random.randint(10, 180)),
            ))

    # ── Script Tasks ──
    for i in range(8):
        db.add(ScriptTask(
            target_name=random.choice(list(asset_objs.keys())),
            script_content=random.choice([
                "#!/bin/bash\ndf -h\necho 'Done'",
                "#!/bin/bash\nuptime\nfree -m",
                "#!/bin/bash\nnetstat -tlnp | grep 80",
            ]),
            output=f"Task completed at {hours_ago(random.randint(0, 48))}",
            error="" if random.random() > 0.2 else "Exit code: 1",
            exit_code=0 if random.random() > 0.2 else 1,
            created_at=hours_ago(random.randint(0, 168)),
        ))

    # ── NetFlow Records ──
    for i in range(60):
        db.add(NetFlowRecord(
            src_ip=random.choice(["10.0.1.10", "10.0.1.11", "10.0.2.10", "192.168.1.10", "10.0.0.1"]),
            dst_ip=random.choice(["10.0.3.10", "10.0.4.10", "10.0.8.10", "10.0.11.10", "8.8.8.8"]),
            src_port=random.randint(1024, 65535),
            dst_port=random.choice([80, 443, 3306, 6379, 9092, 9200]),
            protocol=random.choice(["TCP", "TCP", "TCP", "UDP"]),
            bytes_sent=random.randint(100, 1000000),
            bytes_rcvd=random.randint(100, 10000000),
            start_time=hours_ago(random.randint(0, 720)),
            end_time=hours_ago(random.randint(0, 719)),
        ))

    # ── SystemPostureRecords ──
    if db.query(SystemPostureRecord).count() < 30:
        systems = [
            ("web-servers", "Web 服务器组", "prod", "应用"),
            ("api-servers", "API 服务器组", "prod", "应用"),
            ("db-cluster", "数据库集群", "prod", "存储"),
            ("redis-cache", "Redis 缓存", "prod", "中间件"),
            ("k8s-cluster", "K8s 集群", "prod", "容器"),
            ("lb-group", "负载均衡组", "prod", "网络"),
            ("mq-cluster", "消息队列集群", "prod", "中间件"),
            ("es-cluster", "ES 集群", "prod", "存储"),
            ("dev-env", "开发环境", "dev", "其他"),
            ("test-env", "测试环境", "test", "其他"),
        ]
        for day_offset in range(90):
            day = (now - timedelta(days=day_offset)).date()
            for sk, sn, env, domain in systems:
                base_sla = random.uniform(95, 99.99)
                base_health = random.uniform(60, 100)
                status = random.choices(
                    ["healthy", "healthy", "healthy", "degraded", "critical"],
                    weights=[60, 20, 10, 7, 3],
                )[0]
                if status == "degraded":
                    base_sla = random.uniform(90, 95)
                    base_health = random.uniform(40, 60)
                elif status == "critical":
                    base_sla = random.uniform(70, 90)
                    base_health = random.uniform(10, 40)

                db.add(SystemPostureRecord(
                    day=day, system_key=sk, system_name=sn,
                    environment=env, domain=domain, status=status,
                    sla_value=round(base_sla, 2),
                    health_score=round(base_health, 1),
                    alerts_count=random.randint(0, 20),
                    incidents_count=random.randint(0, 5),
                ))

    # ── K8s-related Assets (pod, deployment, node, service, namespace) ──
    if db.query(Asset).filter(Asset.ci_type == "pod").count() < 3:
        k8s_assets = [
            ("k8s-master-01", "node", "192.168.1.10", "online", ["k8s", "master"]),
            ("k8s-node-01", "node", "192.168.1.11", "online", ["k8s", "worker"]),
            ("k8s-node-02", "node", "192.168.1.12", "online", ["k8s", "worker"]),
            ("prod-ns", "namespace", "", "online", ["k8s", "namespace"]),
            ("staging-ns", "namespace", "", "online", ["k8s", "namespace"]),
            ("prod/web-nginx", "pod", "10.0.20.1", "online", ["k8s", "web"]),
            ("prod/api-gateway", "pod", "10.0.20.2", "online", ["k8s", "api"]),
            ("prod/user-svc-7f8b9", "pod", "10.0.20.3", "online", ["k8s", "api"]),
            ("prod/order-svc-6d2a1", "pod", "10.0.20.4", "online", ["k8s", "api"]),
            ("prod/cache-6379", "pod", "10.0.20.5", "online", ["k8s", "cache"]),
            ("web-deploy", "deployment", "", "online", ["k8s", "web"]),
            ("api-deploy", "deployment", "", "online", ["k8s", "api"]),
            ("user-svc-deploy", "deployment", "", "online", ["k8s", "api"]),
            ("k8s-svc-nginx", "service", "10.0.30.1", "online", ["k8s", "web"]),
            ("k8s-svc-api", "service", "10.0.30.2", "online", ["k8s", "api"]),
            ("k8s-cluster-prod", "cluster", "", "online", ["k8s", "cluster"]),
        ]
        for name, ci_t, ip, status, tags in k8s_assets:
            existing = db.query(Asset).filter(Asset.name == name).first()
            if not existing:
                a = Asset(name=name, type=ci_t, ci_type=ci_t, ip=ip, status=status, tags=json.dumps(tags),
                    ci_attributes=json.dumps({"k8s_cluster": "prod-cluster","namespace":"prod" if name.startswith("prod/") else "default"}))
                db.add(a); db.flush()

    # ── More MetricRecords for node/pod metrics ──
    if db.query(MetricRecord).filter(MetricRecord.name.like("node_cpu_%")).count() < 10:
        k8s_assets_q = db.query(Asset).filter(Asset.ci_type.in_(["node", "pod", "deployment"])).all()
        metric_names = ["node_cpu_usage", "node_memory_usage", "pod_restarts", "deployment_replicas", "pod_cpu_usage"]
        for a in k8s_assets_q:
            for mn in metric_names:
                for h in range(24):
                    db.add(MetricRecord(
                        name=mn, asset_id=a.id, value=round(random.uniform(10, 95), 2),
                        timestamp=hours_ago(h), unit="%" if "cpu" in mn or "memory" in mn else "count",
                    ))

    # ── K8s DataSource ──
    if not db.query(DataSource).filter(DataSource.type == "kubernetes").first():
        db.add(DataSource(name="生产 K8s 集群", type="kubernetes", endpoint="https://k8s-api.prod.local:6443",
            auth_config=json.dumps({"auth_type": "token", "token": "seed-k8s-token"}),
            status="unknown", enabled=False))

    # ── AutoRemediation (5) ──
    if db.query(AutoRemediation).count() < 3:
        actions = [
            ("CPU 过载重启", "restart_service", {"service": "nginx", "max_retries": 3}),
            ("磁盘清理", "clean_disk", {"path": "/var/log", "max_size_gb": 10}),
            ("内存扩容", "scale_up", {"replicas": 5, "deployment": "api-deploy"}),
            ("重启 Pod", "restart_pod", {"namespace": "prod", "label": "app=web"}),
            ("通知负责人", "notify_owner", {"channel": "dingtalk", "template": "alert"})]
        rule_ids = [r.id for r in db.query(AlertRule).limit(5).all()]
        for i, (name, act, params) in enumerate(actions):
            db.add(AutoRemediation(name=name, rule_id=rule_ids[i] if i < len(rule_ids) else rule_ids[0],
                action_type=act, params=json.dumps(params), enabled=True))

    # ── RemediationWorkflow (3) ──
    if db.query(RemediationWorkflow).count() < 2:
        rule_ids = [r.id for r in db.query(AlertRule).limit(3).all()]
        for i, (name, steps) in enumerate([
            ("CPU 自愈流程", [{"step": "check_cpu", "action": "restart_service"}, {"step": "verify", "action": "notify"}]),
            ("磁盘自愈流程", [{"step": "clean_logs", "action": "clean_disk"}, {"step": "verify_space", "action": "notify"}]),
            ("内存告警处理", [{"step": "scale_up", "action": "scale_up"}, {"step": "verify", "action": "notify"}]),
        ]):
            db.add(RemediationWorkflow(name=name, rule_id=rule_ids[i] if i < len(rule_ids) else None,
                steps=json.dumps(steps, ensure_ascii=False), enabled=True))

    # ── BlueGreenDeploy (2) ──
    if db.query(BlueGreenDeploy).count() < 1:
        db.add(BlueGreenDeploy(name="web-prod 蓝绿发布", namespace="prod", active_label="blue", standby_label="green",
            active_replicas=3, standby_replicas=3, status="active"))
        db.add(BlueGreenDeploy(name="api-prod 蓝绿发布", namespace="prod", active_label="blue", standby_label="green",
            active_replicas=5, standby_replicas=5, status="standby"))

    # ── DiscoveryJob (3) ──
    if db.query(DiscoveryJob).count() < 2:
        for name, jtype, target in [("内网资产扫描", "ssh", "192.168.1.0/24"),
            ("K8s 节点发现", "kubernetes", "prod-cluster"), ("云资产同步", "subnet", "10.0.0.0/8")]:
            db.add(DiscoveryJob(name=name, job_type=jtype, target=target, config=json.dumps({"timeout": 30}),
                status=random.choice(["completed", "completed", "failed"]),
                result_summary=json.dumps({"found": random.randint(5, 20), "new": random.randint(0, 5)}),
                finished_at=hours_ago(random.randint(1, 48))))

    # ── ExtCmdbConfig (3) ──
    if db.query(ExtCmdbConfig).count() < 2:
        for name, ctype, url in [("CMDB 生产", "cmdb", "https://cmdb.prod.local/api"),
            ("Zabbix", "zabbix", "https://zabbix.prod.local/api_jsonrpc.php"),
            ("阿里云", "aliyun", "https://ecs.aliyuncs.com")]:
            db.add(ExtCmdbConfig(name=name, cmdb_type=ctype, api_url=url, enabled=True, sync_interval=60))

    # ── ExtEventSource (3) ──
    if db.query(ExtEventSource).count() < 2:
        for name, stype, url in [("Zabbix 触发器", "zabbix", "https://zabbix.prod.local/api_jsonrpc.php"),
            ("Prometheus Alert", "prometheus", "https://prometheus.prod.local/api/v1/alerts"),
            ("AWS CloudWatch", "aws", "https://monitoring.ap-southeast-1.amazonaws.com")]:
            db.add(ExtEventSource(name=name, source_type=stype, api_url=url, enabled=True, sync_interval=300))

    # ── AlertSilenceSchedule (5) ──
    if db.query(AlertSilenceSchedule).count() < 3:
        rule_ids = [r.id for r in db.query(AlertRule).limit(5).all()]
        for i, (metric, cron, mins, reason) in enumerate([
            ("cpu_usage", "0 2 * * 0", 120, "周末维护窗口"),
            ("memory_usage", "0 3 * * 1-5", 60, "日常备份窗口"),
            ("disk_usage", "0 22 * * *", 480, "夜间批量任务"),
            ("network_latency", "0 10 * * 6", 240, "周六网络维护"),
            ("api_error_rate", "0 4 * * 1", 90, "周一API升级"),
        ]):
            db.add(AlertSilenceSchedule(rule_id=rule_ids[i % len(rule_ids)], metric_name=metric,
                cron_expr=cron, duration_minutes=mins, reason=reason, enabled=True))

    # ── AlertWebhook (3) ──
    if db.query(AlertWebhook).count() < 2:
        for name, url, secret in [("钉钉告警群", "https://oapi.dingtalk.com/robot/send", "ding-secret-001"),
            ("企微机器人", "https://qyapi.weixin.qq.com/cgi-bin/webhook/send", "wecom-secret-002"),
            ("飞书告警", "https://open.feishu.cn/open-apis/bot/v2/hook", "feishu-secret-003")]:
            db.add(AlertWebhook(name=name, url=url, secret=secret, retry_count=3, timeout=10, enabled=True))

    # ── KafkaPipeline (2) ──
    if db.query(KafkaPipeline).count() < 1:
        for name, brokers, topic, ptype in [("K8s 事件管道", "kafka-01:9092,kafka-02:9092", "k8s-events", "event"),
            ("应用日志管道", "kafka-01:9092,kafka-02:9092", "app-logs", "log"),
            ("告警事件流", "kafka-01:9092", "alerts", "alert")]:
            db.add(KafkaPipeline(name=name, brokers=brokers, topic=topic, group_id="aiops", pipeline_type=ptype,
                transform="raw", enabled=True))

    # ── FeatureStoreItem (10) ──
    if db.query(FeatureStoreItem).count() < 5:
        assets_list = db.query(Asset).limit(10).all()
        for a in assets_list:
            for fname in ["cpu_avg_1h", "mem_avg_1h", "alert_count_24h", "error_rate", "health_score"]:
                db.add(FeatureStoreItem(feature_name=fname, entity_type="asset", entity_id=a.id,
                    feature_value=round(random.uniform(0, 100), 2), source="seed"))

    # ── PredictionModel (5) ──
    if db.query(PredictionModel).count() < 3:
        assets_list = db.query(Asset).limit(5).all()
        for i, mn in enumerate(["cpu_usage", "memory_usage", "disk_usage", "network_latency", "api_error_rate"]):
            db.add(PredictionModel(name=f"{mn} 预测模型", metric_name=mn,
                asset_id=assets_list[i % len(assets_list)].id if assets_list else None,
                model_type=random.choice(["linear", "prophet", "arima"]),
                params=json.dumps({"window": 24, "period": 7}), enabled=True))

    # ── DashboardCardConfig (6) ──
    if db.query(DashboardCardConfig).filter(DashboardCardConfig.user_id == 1).count() < 3:
        cards = [("stats", "统计概览"), ("alert_chart", "告警趋势"), ("asset_pie", "资产分布"),
            ("incident_list", "最近故障"), ("health_gauge", "系统健康度"), ("ai_chat", "AI 助手")]
        for i, (ct, title) in enumerate(cards):
            db.add(DashboardCardConfig(user_id=1, card_type=ct, title=title, position=i, visible=True,
                config=json.dumps({"span": 2 if ct == "alert_chart" else 1})))

    # ── ReportSchedule (3) ──
    if db.query(ReportSchedule).count() < 2:
        for name, rtype, cron, ch in [("每日运维报告", "daily", "0 8 * * *", "email"),
            ("每周汇总", "weekly", "0 9 * * 1", "wecom"),
            ("月度SLA报告", "monthly", "0 10 1 * *", "email")]:
            db.add(ReportSchedule(name=name, report_type=rtype, cron_expr=cron, channel=ch,
                channel_config=json.dumps({"recipients": ["admin@aiops.local"]}), enabled=True))

    # ── ApiToken (3) ──
    if db.query(ApiToken).count() < 2:
        for name, perm in [("管理员令牌", "admin"), ("只读令牌", "read"), ("读写令牌", "write")]:
            token_str = "aio_" + hashlib.sha256(f"{name}-{random.random()}".encode()).hexdigest()[:32]
            db.add(ApiToken(name=name, token=token_str, permissions=perm, enabled=True))

    # ── AIProvider (2) + update AgentConfig ──
    if db.query(AIProvider).count() < 1:
        provider = AIProvider(name="OpenAI 兼容", provider_type="openai_compatible",
            base_url="https://api.openai.com/v1", default_model="gpt-4o-mini",
            temperature=0.2, max_tokens=10000, is_enabled=True)
        db.add(provider); db.flush()
        cfg = db.query(AgentConfig).first()
        if cfg and not cfg.default_provider_id:
            cfg.default_provider_id = provider.id

    # ── ServiceMeshConfig (2) ──
    if db.query(ServiceMeshConfig).count() < 1:
        db.add(ServiceMeshConfig(name="生产 Istio", mesh_type="istio",
            api_url="https://istio.prod.local:15000", enabled=True))
        db.add(ServiceMeshConfig(name="测试 Linkerd", mesh_type="linkerd",
            api_url="https://linkerd.test.local:9990", enabled=False))

    # ── NetFlowCollector (2) ──
    if db.query(NetFlowCollector).count() < 1:
        db.add(NetFlowCollector(name="核心交换机 sFlow", collector_type="sflow", listen_host="0.0.0.0", listen_port=6343, enabled=True))
        db.add(NetFlowCollector(name="边界路由器 NetFlow", collector_type="netflow", listen_host="0.0.0.0", listen_port=2055, enabled=False))

    # ── CiAttribute (8 models x 3 attrs) ──
    if db.query(CiAttribute).count() < 5:
        attr_templates = [
            ("cpu_cores", "CPU 核数", "integer", "4"),
            ("memory_gb", "内存(GB)", "integer", "16"),
            ("disk_gb", "磁盘(GB)", "integer", "500"),
            ("os_version", "操作系统", "string", "Linux"),
            ("ip_address", "IP 地址", "string", "192.168.1.1"),
            ("k8s_version", "K8s 版本", "string", "1.28"),
        ]
        ci_models = db.query(CiModel).all()
        for cm in ci_models:
            for j, (an, al, ft, dv) in enumerate(attr_templates[:3]):
                existing_attr = db.query(CiAttribute).filter(CiAttribute.ci_model_id == cm.id, CiAttribute.name == an).first()
                if not existing_attr:
                    db.add(CiAttribute(ci_model_id=cm.id, name=an, display_name=al, field_type=ft, default_value=dv, order=j))

    # ── AlertSuppression (5) ──
    if db.query(AlertSuppression).count() < 3:
        rules = db.query(AlertRule).limit(5).all()
        for rule in rules:
            db.add(AlertSuppression(rule_id=rule.id, rule_name=rule.name, metric_name=rule.metric_name,
                suppressed_count=random.randint(1, 10), reason=random.choice(["dedup", "storm", "silence"])))

    # Mark seed as applied
    marker_obj = SystemConfig(key="seed_data_applied", value=marker_v, description="Seed data version marker")
    db.add(marker_obj)

    db.commit()
    db.close()
    print("[seed] Demo data seeded successfully: 30+ assets, 10 rules, 80 alerts, 12 incidents, 45 k8s events, metric timeseries, 6 chats, 15 change requests, knowledge base, runbooks, netflow, posture records.")


if __name__ == "__main__":
    seed_all()
