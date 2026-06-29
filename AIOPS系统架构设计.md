# AIOps 智能运维系统 — 架构设计文档

> 最后更新: 2026-06-23

---

## 一、整体架构分层

```
┌──────────────────────────────────────────────────────────────┐
│                     可视化与交互层                             │
│      Dashboard · 容器看板 · 报表 · ChatOps · 移动端          │
├──────────────────────────────────────────────────────────────┤
│                      运维控制面                                │
│  ┌──────────┐ ┌──────────┐ ┌──────────┐ ┌──────────────┐   │
│  │ 发版引擎  │ │ 容器管理 │ │ 扩缩容   │ │ 日志终端     │   │
│  │ 蓝绿/灰度 │ │ exec/日志│ │ 滚动更新 │ │ WebSocket    │   │
│  └──────────┘ └──────────┘ └──────────┘ └──────────────┘   │
├──────────────────────────────────────────────────────────────┤
│                      业务智能层                                │
│  ┌─────────┐ ┌──────────┐ ┌──────────┐ ┌───────────┐       │
│  │ 异常检测 │ │ 根因分析 │ │ 故障预测 │ │ 告警智能  │       │
│  └─────────┘ └──────────┘ └──────────┘ └───────────┘       │
├──────────────────────────────────────────────────────────────┤
│                      数据处理层                                │
│   数据清洗 · 特征提取 · 归一化 · 时间窗口聚合 · 关联         │
├──────────────────────────────────────────────────────────────┤
│                      数据采集与集成层                           │
│  传统指标 │ 日志 │ 事件 │ 调用链 │ 容器指标 │ CMDB │ API     │
├──────────────────────────────────────────────────────────────┤
│                 容器编排与基础设施层                            │
│  K8s 多集群 │ Docker │ cAdvisor │ containerd │ Service Mesh  │
└──────────────────────────────────────────────────────────────┘
```

---

## 二、模块详细说明

### 1. 数据采集与集成层

| 子模块 | 说明 | 数据源示例 |
|--------|------|-----------|
| **日志采集** | 多来源日志采集、实时流式接入 | Filebeat / Fluentd / Logstash → Kafka |
| **指标采集（传统）** | 服务器/虚机/中间件指标 | Prometheus / Telegraf / SSH / SNMP |
| **容器指标采集** | 容器/Pod/集群资源指标 | K8s Metrics Server / cAdvisor / kube-state-metrics / Docker SDK |
| **K8s 事件采集** | 集群事件监听（Pod 调度/驱逐/OOM） | K8s Watch API / EventRouter / kube-eventer |
| **事件采集** | 告警事件、变更事件、故障单 | Zabbix / 自研事件总线 / Webhook |
| **调用链采集** | 分布式追踪数据 | Jaeger / Zipkin / SkyWalking / OpenTelemetry |
| **网络流采集** | 网络流量与性能 | sFlow / NetFlow / IPFIX |
| **Service Mesh** | 网格级指标和调用链 | Istio / Linkerd 指标 + 链路 |
| **CMDB 对接** | 资产配置与拓扑关系 | 对接已有 CMDB API，或内置 CI 模型 |
| **API 集成** | 对接外部系统 | REST / gRPC / MQ / WebSocket |

### 2. 数据处理与存储层

| 子模块 | 功能 | 技术选型建议 |
|--------|------|-------------|
| **实时流处理** | 数据清洗、过滤、格式归一化、实时聚合 | Flink / Kafka Streams / Spark Streaming |
| **离线批处理** | 历史数据重算、模型训练数据准备 | Spark / Pandas |
| **时序存储** | 指标数据存储与查询 | VictoriaMetrics / ClickHouse / InfluxDB / TDengine |
| **日志存储** | 全文检索与分析 | Elasticsearch / OpenSearch |
| **调用链存储** | Trace 数据存储与检索 | Elasticsearch / Jaeger 后端 |
| **关系存储** | CMDB 资产关系、运维知识 | PostgreSQL / Neo4j（图库） |
| **特征仓库** | 复用特征，供 ML 模型使用 | Redis / Feast |

### 3. 异常检测模块

| 检测类型 | 算法/方法 | 应用场景 |
|---------|-----------|---------|
| **指标异常检测** | 3σ / MAD / EWMA / STL / Prophet / LSTM / Transformer | CPU、内存、响应时间等指标 |
| **日志异常检测** | 关键词匹配 / 正则阈值 / LogAnomaly / Drain 模板提取 | 系统日志、应用日志 |
| **调用链异常检测** | 延时分布异常 / 结构异常 / 根因定位 | 微服务调用链 |
| **KPI 异常检测** | 移动平均趋势 + 周期分片 + 残差 3σ | 业务 KPI |
| **多维度下钻** | HotSpot / iDice 算法 | 多维属性异常定位 |
| **Pod 异常检测** | 从 K8sEvent 检测 CrashLoopBackOff / OOMKilling / Failed / BackOff | Pod 健康监控 |
| **容器异常检测** | Pod 重启频率 / OOMKilled / CrashLoopBackOff | 容器稳定性监控 |
| **集群异常检测** | Node NotReady / DNS 解析失败 / CNI 异常 | K8s 集群健康 |
| **资源争抢检测** | 同节点 Pod 相互资源压制识别（OOM / CrashLoop / NodeNotReady） | 容器资源隔离异常 |

### 4. 根因分析模块

| 子模块 | 说明 | 核心技术 |
|--------|------|---------|
| **拓扑分析（传统）** | 基于 CMDB 依赖关系定位 | BFS/DFS 因果推导，PageRank |
| **拓扑分析（容器）** | K8s 资源依赖链：Pod→Service→Deployment→Node→Cluster | 多级拓扑传播 + 告警分数传播 |
| **拓扑传播 RCA** | 沿资产父子关系树递归累加告警严重度分数 | 深度优先遍历 + 分数归一化 |
| **调用链根因分析** | 从 Trace 中定位故障服务 | 延时分解 / 错误传播分析 |
| **指标关联分析** | 多指标间格兰杰因果/互相关 | Granger Causality / Pearson / DTW |
| **日志根因定位** | 故障日志与异常事件关联 | 日志聚类 + 时间窗口关联 |
| **PCADR** | 基于 PCA 的根因分析 | SVD 主成分分解 + PC1 贡献度排序 |
| **K8s 事件关联** | 集群事件与告警/指标关联定位 | 时间窗口 + 事件类型匹配 |

### 5. 告警管理模块

| 功能 | 说明 |
|------|------|
| **告警收敛** | 相同/相似告警合并，风暴抑制（1 分钟内 >N 条则抑制 5 分钟） |
| **告警去重** | 基于规则+指标的 5 分钟时间窗去重 |
| **告警关联** | 因果/时序关联 → 生成故障单 |
| **告警升级** | 按严重级别 + 超时升级（支持多级 escalation） |
| **升级通知** | 升级时自动发送通知到所有匹配严重级别的启用的通知渠道 |
| **静默/抑制** | 维护窗口静默 + cron 表达式排班静默（croniter） |
| **静默排班** | 基于 cron 的周期性静默 + 持续时长（分钟） |
| **通知渠道** | 钉钉/企微/邮件/Webhook/日志 |
| **通知模板** | 可自定义消息模板（变量: alert_id, metric_name, severity 等） |
| **告警回调 Webhook** | POST JSON 回调外部系统，支持 secret 鉴权 + 自动重试 |

### 6. 故障预测模块

| 预测类型 | 方法 | 输出 |
|---------|------|------|
| **容量预测** | 线性回归 + SVG 趋势图 | 磁盘、内存、连接数未来利用率 + 预计阈值时间 |
| **趋势预测** | 时序预测模型 | 业务指标趋势 |
| **剩余寿命预测** | 7 日 MetricRecord 线性回归斜率 → 推算至阈值 | 剩余小时/天数，按资产+指标选择 |
| **故障概率预测** | 当前值/阈值比率 0-100% | 列出有触发告警的资产的 CPU/内存/磁盘故障概率 |

### 7. CMDB（配置管理数据库）

| 组件 | 说明 |
|------|------|
| **CI 模型定义** | CI 类型、属性、关系元模型 |
| **CI 模型元管理** | 动态 CRUD CI 类型、属性定义（字段类型、必填、默认值、枚举选项） |
| **资产发现（传统）** | SSH / Agent / API 自动发现服务器、网络设备 |
| **资产发现（容器）** | K8s API 自动发现 Cluster/Node/Namespace/Pod/Service/Deployment/StatefulSet/DaemonSet/PVC/PV |
| **关系管理** | 拓扑依赖（应用→服务→Pod→Node，Deployment→ReplicaSet→Pod） |
| **标签管理** | 标签聚合、按标签筛选、批量分配/移除 |
| **变更跟踪** | 字段级 diff（旧值/新值/操作人/时间） |
| **调用链视图** | BFS 遍历 parent-child + AssetRelation 边 → 资产依赖树 |
| **健康评分** | 加权评分 = 资产在线率 − 告警扣分 − 故障单扣分 + 确认加分 |
| **生命周期管理** | 资产从上线到退役全生命周期 |

**容器 CI 类型：**

| CI 类型 | 属性示例 | 父级关系 |
|---------|---------|---------|
| **Cluster** | k8s_version, api_endpoint, region | — |
| **Node** | cpu, memory, kubelet_version, os_image | 属于 Cluster |
| **Namespace** | name, labels, status | 属于 Cluster |
| **Deployment** | replicas, strategy, image | 属于 Namespace |
| **StatefulSet** | replicas, service_name | 属于 Namespace |
| **DaemonSet** | node_selector | 属于 Namespace |
| **Service** | cluster_ip, type, ports | 属于 Namespace |
| **Ingress** | rules, tls | 属于 Namespace |
| **Pod** | phase, node, restarts, qos_class, ip | 属于 Deployment / 直接创建 |
| **Container** | image, resources, ports, state | 属于 Pod |
| **PersistentVolume** | capacity, storage_class, access_modes | 属于 Cluster |
| **PersistentVolumeClaim** | requested_size, storage_class | 属于 Namespace |

**传统资产类型：**

| CI 类型 | 属性示例 |
|---------|---------|
| **物理服务器** | cpu, memory, disk, nic, ipmi_ip |
| **虚拟机** | vcpu, vmem, hypervisor, host |
| **网络设备** | switch/router, ports, vlan |
| **中间件** | type, version, port, config |

**建议**：优先对接已有 CMDB，如需自建则从最小 CI 模型开始，逐步扩展。

### 8. 容器运维控制面

| 子模块 | 功能 | 技术实现 |
|--------|------|---------|
| **多集群管理** | 集群注册、证书管理、集群状态监控 | K8s 客户端 + 集群凭证加密存储 |
| **Pod 日志** | 实时日志流、多容器切换、日志搜索 | K8s API + WebSocket 流式推送 |
| **容器终端** | 浏览器内 exec 进入容器交互 | K8s exec API + WebSocket 终端模拟 |
| **Pod 详情** | Yaml/状态/事件/资源监控展示 | K8s API 只读查询 |
| **Deployment 管理** | 创建/更新/回滚/暂停/恢复 | K8s Deployment API + 操作审计 |
| **StatefulSet/DaemonSet** | StatefulSet / DaemonSet 列表查看 | K8s AppsV1Api |
| **扩缩容** | 手动扩缩容 + HPA 配置（创建/更新/删除） | K8s Scale API + AutoscalingV1Api |
| **发版引擎** | 滚动更新、蓝绿发布、金丝雀发布 | K8s Deployment + 金丝雀 Deployment 创建/提升 |
| **配置管理** | ConfigMap/Secret 查看与在线编辑 | K8s ConfigMap/Secret API + replace |
| **存储管理** | PVC/PV 状态查看与管理 | K8s PersistentVolume / PersistentVolumeClaim API |
| **网络管理** | Service/Ingress 查看与配置 | K8s Network API |

**发版引擎详细说明：**

| 发布模式 | 策略 | 适用场景 |
|---------|------|---------|
| **滚动更新** | 逐步替换 Pod，可设置 maxSurge/maxUnavailable | 普通应用升级 |
| **蓝绿发布** | 保持旧版本 Service，新版本就绪后切换流量标签 | 关键服务，需快速回滚 |
| **金丝雀发布** | 新版本先接收少量流量，逐步放量至 100% | 灰度验证，逐步放量 |
| **回滚** | 回退到上一版本或指定 revision | 发版异常时快速恢复 |

### 9. 知识库与运维图谱
| 功能 | 说明 |
|------|------|
| **故障知识库** | 历史故障记录 + 处理方案（Case-based Reasoning） |
| **知识图谱** | CI + 关系 + 故障 + 变更构成的图结构展示 |
| **智能推荐** | 对告警按 metric/tag/severity/asset-type/symptom 多维度打分 → 推荐知识库条目 |
| **Runbook 管理** | 标准化故障处理流程（分类/严重级别/标签/症状/诊断/修复步骤） |

### 10. 智能运维编排

| 功能 | 说明 |
|------|------|
| **自动化响应** | 告警触发自动操作（重启/扩缩容/回滚） |
| **故障自愈** | 基于规则 + 策略的自动化恢复 |
| **自愈工作流** | 多步骤自愈（restart/clean/scale/notify/healthcheck），每步记录执行日志 |
| **ChatOps** | 在即时通讯中接受指令、查询、操作（REST 命令接口: /alerts /alert /assets /change /report /pods） |
| **变更编排** | 变更申请→提交审批→通过/驳回→执行→完成/回滚 + 执行步骤管理 |

### 11. 可视化与交互

| 功能 | 说明 | 可选技术 |
|------|------|---------|
| **全局看板** | 系统健康总览（健康评分/TopN/告警趋势/资产类型分布） | 自研 + Chart.js |
| **Dashboard 配置** | 用户自定义看板卡片显示/隐藏 | 基于 User 的卡片可见性配置 |
| **K8s 资源监控大盘** | Node/Pod/Deployment 统计卡片 + CPU/重启率 Chart.js 折线图 | Chart.js + MetricRecord |
| **拓扑可视化** | 资产/服务依赖关系图 | D3.js / G6 / Cytoscape.js |
| **D3.js 拓扑图** | 力导向图，节点颜色=CI类型+告警状态，拖拽/缩放/点击跳转 | D3.js v7 |
| **调用链视图** | BFS 资产依赖树表 | 自研表格 |
| **告警控制台** | 告警列表、批量确认/解决、筛选预设保存/加载、事件关联展示 | 自研 |
| **风暴抑制管理** | 阈值配置 + 抑制历史查看 | 自研 |
| **告警事件关联** | K8s 事件↔告警关联关系表 + 自动关联 | AlertEventLink 关系表 |
| **报告系统** | 日报/周报/月报自动生成 + 定时发送 | 自研 + Cron 调度 |
| **ChatOps 页面** | 类聊天界面执行运维命令 | 自研 |

### 12. API 与开放平台

| 接口 | 说明 |
|------|------|
| **数据接入 API** | 外部系统推送日志、指标、事件 |
| **查询 API** | 指标/日志/告警/CMDB 统一查询 |
| **告警回调** | 告警通知 Webhook（支持 secret + 重试 + 测试） |
| **操作 API** | 远程执行脚本、服务操作 |
| **ChatOps 命令** | POST /chatops/command 解析 /alerts /alert /assets 等运维指令 |
| **ES 同步** | 一键将 K8s 事件同步到 Elasticsearch 持久化 |
| **OpenAPI** | 第三方基于 Token 调用（read/write/admin 三级） |

---

## 三、推荐 MVP 路线

```
Phase 1 ─── ✅ 数据采集（日志+指标+SSH） + 基础告警 + 简单看板
Phase 2 ─── ✅ 异常检测 + 告警收敛 + CMDB 对接
Phase 3 ─── ✅ 根因分析 + 调用链 + 拓扑可视化
Phase 4 ─── ✅ 容器采集（K8s/Docker） + 容器看板 + 多集群管理
Phase 5 ─── ✅ 容器控制面（Pod/Deployment/Service/ConfigMap/HPA/PVC/PV）
Phase 6 ─── ✅ 发版引擎（蓝绿/金丝雀发布）
Phase 7 ─── ✅ 故障预测 + 知识库 + 运维图谱
Phase 8 ─── ✅ 智能编排 + ChatOps + 自动化自愈
```

---

## 四、技术栈推荐

| 领域 | 当前使用 | 可选升级 |
|------|----------|---------|
| **编程语言** | Python (FastAPI) | Go（采集 Agent） |
| **Web 框架** | FastAPI + Jinja2 服务端渲染 | + Celery 异步任务 |
| **数据库** | SQLite（SQLAlchemy ORM） | PostgreSQL / MySQL |
| **时序存储** | MetricRecord 表（SQLite） | VictoriaMetrics / ClickHouse |
| **搜索引擎** | Elasticsearch（仅 ES 同步接口） | 全量日志接入 |
| **消息队列** | — | Kafka |
| **流处理** | — | Flink / Kafka Streams |
| **任务调度** | 后台线程 loop（10s 间隔） | Airflow / Celery Beat |
| **可视化** | 自研 Jinja2 + Chart.js + D3.js + Vue 3 SPA | Vue 3 + Element Plus + Vite |
| **ML 框架** | NumPy（PCA/SVD/线性回归） | scikit-learn / Prophet / PyTorch |
| **图数据库** | — | Neo4j |
| **容器化** | Docker + Kubernetes | Helm Charts / Operator |
| **容器 SDK** | kubernetes==31, docker-py | — |
| **前端交互** | Chart.js + D3.js v7 | xterm.js / WebSocket |

---

---

## 五、AI Agent 智能体架构（新增 — AIOps 转型核心）

> 借鉴自 SxDevOps 项目的 Agent 管道架构，将传统 AIOps 平台升级为 AI Agent 驱动的智能运维系统。

### 5.1 整体 Agent 管道

```
用户提问 → Action Router → Agent Mode (Direct/ReAct/Plan+ReAct)
  → Preflight (权限/风险/依赖检查)
    → Skill + SOP (领域知识约束)
      → MCP / Tool Registry (平台内置 + 外部工具)
        → Structured Facts (日志/指标/链路/告警/事件)
          → 两阶段回答 (结论 + 证据 + 风险 + 建议)
            → Pending Action (写操作需用户确认)
              → 平台 API 执行 (RBAC + 参数校验 + 超时)
                → 反馈 (任务中心/事件中心/审计)
```

### 5.2 核心模型

| 模型 | 说明 | 对应 sxdevops 参考 |
|------|------|-------------------|
| `AIProvider` | LLM 提供商配置 (OpenAI-compatible)，含 base_url/api_key/模型/温度/超时 | `AIOpsModelProvider` |
| `AgentConfig` | Agent 配置：默认提供商/系统提示词/欢迎语/建议问题/是否允许执行/需要确认 | `AIOpsAgentConfig` |
| `ChatSession` | 用户会话：标题/状态/上下文/最后消息时间 | `AIOpsChatSession` |
| `ChatMessage` | 会话消息：角色(user/assistant/system)/类型(text/analysis/action/error)/内容/引用/工具调用 | `AIOpsChatMessage` |
| `MCPServer` | MCP 服务注册：类型(http/stdio/platform_builtin)/地址/鉴权/启用工具列表 | `AIOpsMCPServer` |
| `MCPTool` | 平台内置工具注册：名称/描述/参数 schema/处理函数/风险等级 | 平台内置工具概念 |
| `PendingAction` | 待确认动作：类型/风险等级/参数/状态(待确认/已确认/已取消/已执行) | `AIOpsPendingAction` |
| `ToolInvocation` | 工具调用记录：工具名/状态/耗时/请求/响应 | `AIOpsToolInvocation` |

### 5.3 Action Router — 意图路由

Action Router 是 Agent 管道的入口，负责：
1. 解析用户问题 + 页面上下文 → 识别意图
2. 确定 Agent 模式：**Direct**（直接回答）、**ReAct**（推理→行动→观察循环）、**Plan+ReAct**（多步规划→执行）
3. 选择适用的 Action Handler

| Action | 触发条件 | 输出 |
|--------|---------|------|
| 告警根因分析 | 用户问"分析告警"、页面上下文含 alert_id | 根因资产 + 传播路径 + 建议 |
| 变更影响分析 | 涉及发布/变更查询 | 变更影响范围 + 关联告警 |
| 日志查询生成 | 需要查询日志 | 结构化日志查询参数 |
| K8s 诊断 | Pod/集群异常问题 | 诊断结论 + 证据 + 修复步骤 |
| 自愈推荐 | 告警触发、用户求建议 | 自愈方案 + 风险等级 + 待确认动作 |
| 任务生成 | 用户要求执行操作 | 任务参数 + 待确认动作 |
| SLO/健康分析 | 服务/资产健康查询 | 健康评分 + 趋势 + 建议 |

### 5.4 MCP (Model Context Protocol) 工具注册

MCP 是标准化工具调用协议，所有平台功能注册为工具供 LLM 调用：

| 内置 MCP 工具 | 功能 | 风险等级 |
|--------------|------|---------|
| `query_alerts` | 查询告警列表/规则 | 只读 |
| `query_assets` | 查询资产/拓扑 | 只读 |
| `query_metrics` | 查询指标趋势/最新值 | 只读 |
| `query_traces` | 查询调用链 | 只读 |
| `query_logs` | 查询日志 | 只读 |
| `get_incident_rca` | 根因分析 | 只读 |
| `get_knowledge` | 知识库查询/推荐 | 只读 |
| `list_k8s_pods` | K8s Pod 列表 | 只读 |
| `execute_script` | SSH 远程执行脚本 | 执行 |
| `create_alert_rule` | 创建告警规则 | 写入 |
| `scale_deployment` | 扩缩容 Deployment | 写入 |
| `rollback_deployment` | 回滚 Deployment | 写入 |
| `restart_service` | 重启服务/Pod | 执行 |
| `send_notification` | 发送通知 | 写入 |

### 5.5 Skills / SOP 约束

Skill 是领域知识约束包，限制 AI 在该领域的行为边界：

| Skill | 适用 Action | 约束内容 |
|-------|-----------|---------|
| 告警证据收集 | 告警根因分析 | 必须采集关联指标/日志/事件作为证据 |
| K8s 故障排查 | K8s 诊断 | 按 Pod→Deployment→Node→Cluster 逐层排查 |
| 日志查询指南 | 日志查询生成 | 指定时间窗口 + 关键字 + 级别过滤 |
| 变更影响分析 | 变更影响分析 | 对比变更前后指标/告警变化 |
| 自愈风险守卫 | 自愈推荐 | 高风险操作必须经用户确认 |
| 回答格式化 | 所有 | 结论 + 证据 + 风险 + 建议 四段式输出 |

### 5.6 Pending Action 确认流

```
Agent 输出建议 → 创建 PendingAction (状态=待确认)
  → 前端提示用户确认/取消
    → 确认 → 执行平台 API → 记录 ToolInvocation → 更新 PendingAction 状态
    → 取消 → 记录取消原因
```

所有写操作（创建/更新/删除/执行）强制走此流程，**Agent 不能绕过**。

### 5.7 实现优先级

```
Phase 1 ─── ✅ LLM Provider 管理 + Agent 基础配置
Phase 2 ─── ✅ Chat Session + 消息历史 + 核心 Agent 管道
Phase 3 ─── ✅ MCP 工具注册（部分内置工具已完成）+ 两阶段回答
Phase 4 ─── ✅ Pending Action 确认流 + 前端 Chat 界面（浮动气泡 + 内嵌仪表盘）
Phase 5 ─── ✅ 将现有功能注册为 MCP 工具（告警/资产/指标/K8s等）
Phase 6 ─── ✅ Agent 自愈 + 告警自动处置
Phase 7 ─── ⏳ 运维知识库 + SOP 约束体系深化
```

### 5.8 技术实现

| 组件 | 实现方式 |
|------|---------|
| LLM 调用 | `httpx` / `requests` 调用 OpenAI-compatible API |
| 工具注册 | Python 装饰器 `@register_mcp_tool()` 自动收集 |
| 会话管理 | SQLAlchemy ORM 存入 SQLite |
| 实时通信 | Server-Sent Events (SSE) 或 WebSocket |
| 加密存储 | `cryptography.fernet` 加密 API Key |
| 前端集成 | Vue 3 SPA（frontend/dist/）+ FastAPI 单一端口服务，iframe 内嵌 Jinja2 页面 |

---

## 六、前端架构（Vue 3 SPA + FastAPI 单一端口）

### 6.1 整体架构

```
浏览器 ──→ FastAPI (:8000)
             ├── GET /              → Vue SPA (frontend/dist/index.html)
             ├── GET /assets/*      → Vue 构建静态资源 (JS/CSS)
             ├── GET /metrics 等   → Jinja2 模板（iframe 内嵌）
             └── 其他 /api/*        → REST API
```

### 6.2 Vue SPA 结构

| 路径 | 说明 |
|------|------|
| `src/layout/AppLayout.vue` | 主布局：侧边栏（el-menu）+ 顶栏 + 内容区 |
| `src/views/DashboardView.vue` | 仪表盘（内嵌 AI 聊天 + 统计卡片） |
| `src/views/AgentChatView.vue` | AI 智能助手完整页面 |
| `src/views/AgentAudit.vue` | 智能体审计（工具调用记录） |
| `src/views/OperationAudit.vue` | 操作审计（变更/生命周期） |
| `src/components/AIOpsChatWidget.vue` | 右下角浮动 AI 气泡 + 滑出面板 |
| `src/stores/app.js` | Pinia store（侧边栏折叠状态） |
| `src/assets/main.css` | 设计系统（从 sxdevops 移植） |

### 6.3 设计系统（sxdevops 精确移植）

- **品牌渐变**：`linear-gradient(135deg, #67b7ab 0%, #5586b6 58%, #49639a 100%)`
- **侧边栏**：188px 宽，渐变背景，el-menu + el-sub-menu 精确覆盖
- **顶栏**：60px 高，渐变背景，折叠按钮 + 品牌渐变面包屑
- **卡片**：`border-radius: 12px`，`box-shadow: 0 1px 3px rgba(0,0,0,0.06)`
- **字体**：Inter + 系统字体

### 6.4 混合渲染策略

| 页面类型 | 渲染方式 | 说明 |
|---------|---------|------|
| 仪表盘/AI助手/审计 | Vue 原生 | 流畅交互 + AI 功能 |
| 指标/告警/资产等 | iframe Jinja2 | 保留全部已有功能，无需重写 |

---

## 七、CMDB 在 AIOps 中的位置

```
         ┌──────────────────────┐
         │    CMDB (配置管理)    │
         │  ┌────┐ ┌────┐ ┌───┐ │
         │  │ CI │ │关系│ │变 │ │
         │  │    │ │    │ │更 │ │
         │  └────┘ └────┘ └───┘ │
         └────────┬─────────────┘
                  │ 提供拓扑与依赖关系
                  ▼
    ┌───────┐ ┌───────┐ ┌───────┐
    │异常检测│ │根因分析│ │故障预测│
    └───────┘ └───────┘ └───────┘
```

CMDB **不是 AIOps 的必选项**，但它是根因分析和拓扑可视化的核心依赖。没有 CMDB，根因分析只能依赖调用链，无法感知底层基础设施依赖关系。


---

## 八、SRE 功能开发计划（下一步）

### 8.1 当前 SRE 能力评估

| 状态 | 数量 | 占比 |
|------|------|------|
| ✅ 完全覆盖 | 40 | 67% |
| ⚠️ 部分覆盖 | 7 | 11% |
| ❌ 未覆盖 | 12 | 20% |

**已覆盖 47 个功能，领先大多数运维平台。**

### 8.2 未覆盖功能清单（按优先级排序）

#### 🔴 高优先级（P0）

| 功能 | 说明 | 工作量 | 依赖 |
|------|------|--------|------|
| **Error Budget** | 错误预算管理，超预算自动限制变更 | 3人天 | metrics, incidents |
| **Burn Rate** | SLO 消耗速率监控看板 | 2人天 | Error Budget |
| **On-Call** | 值班轮值表、值班通知、升级 | 5人天 | alerts, notifications |
| **SLO管理** | 服务等级目标配置与追踪 | 3人天 | metrics |
| **升级策略** | 自动升级策略配置 | 2人天 | alerts |

#### 🟡 中优先级（P1）

| 功能 | 说明 | 工作量 | 依赖 |
|------|------|--------|------|
| **SLA管理** | 服务等级协议管理 | 2人天 | SLO管理 |
| **负载测试** | 压力测试工具 | 5人天 | containers |
| **资源优化** | 闲置资源检测与告警 | 3人天 | k8s_monitor |

#### 🟢 低优先级（P2）

| 功能 | 说明 | 工作量 | 依赖 |
|------|------|--------|------|
| **数据备份** | 定时备份与恢复 | 3人天 | 无 |
| **灾备恢复** | 灾难恢复演练 | 5人天 | 数据备份 |
| **故障演练** | Chaos Engineering | 5人天 | 无 |
| **成本监控** | 云成本分析报表 | 3人天 | k8s_monitor |

### 8.3 功能详细设计

#### 8.3.1 Error Budget（错误预算）

```
┌─────────────────────────────────────────────────────────┐
│                    Error Budget 模块                    │
├─────────────────────────────────────────────────────────┤
│  配置层                                                  │
│  ├── SLO 配置 (可用性 99.9% → 错误预算 0.1%)            │
│  ├── 时间窗口 (30天滚动)                                 │
│  └── 服务/应用选择                                       │
│                                                         │
│  计算层                                                  │
│  ├── 可用性 = (总请求 - 失败请求) / 总请求               │
│  ├── 已消耗预算 = (1 - 可用性) × 时间窗口                │
│  └── 剩余预算 = 预算 - 已消耗                           │
│                                                         │
│  动作层                                                  │
│  ├── 超预算告警 → 限制变更                              │
│  ├── 邮件/钉钉通知                                      │
│  └── API 阻断变更                                       │
└─────────────────────────────────────────────────────────┘
```

**数据模型：**
```python
class ErrorBudget(BaseModel):
    id: int
    service_name: str          # 服务名
    slo_target: float           # 目标可用性 0.999
    window_days: int           # 窗口天数 30
    total_requests: int        # 总请求数
    error_requests: int        # 错误请求数
    budget_consumed: float     # 已消耗预算 %
    status: str               # healthy/warning/critical
    created_at: datetime
```

#### 8.3.2 On-Call（值班管理）

```
┌─────────────────────────────────────────────────────────┐
│                     On-Call 模块                        │
├─────────────────────────────────────────────────────────┤
│  值班表                                                  │
│  ├── 值班人员轮值表                                      │
│  ├── 值班周期 (周/月)                                   │
│  ├── 值班时间 (白班/夜班)                               │
│  └── 替班/交接                                           │
│                                                         │
│  通知                                                   │
│  ├── 告警分派规则                                       │
│  ├── 多级升级 (15min/30min/1h)                         │
│  ├── 通知渠道 (短信/电话/钉钉)                         │
│  └── 升级模板                                           │
│                                                         │
│  统计                                                   │
│  ├── MTTR (平均修复时间)                               │
│  ├── 值班工作量                                         │
│  └── 告警响应率                                         │
└─────────────────────────────────────────────────────────┘
```

**数据模型：**
```python
class OnCallSchedule(BaseModel):
    id: int
    team_name: str           # 团队名
    schedule: str            # 轮值表 JSON
    rotation_type: str       # weekly/monthly
    current_oncall: str      # 当前值班人
    
class EscalationPolicy(BaseModel):
    id: int
    name: str                # 策略名
    levels: list            # 升级级别
    wait_minutes: list       # 每级等待时间
    notify_channels: list    # 通知渠道
```

#### 8.3.3 Burn Rate（预算消耗速率）

```
┌─────────────────────────────────────────────────────────┐
│                   Burn Rate 看板                       │
├─────────────────────────────────────────────────────────┤
│                                                         │
│  服务 A:  ████████████░░░░░░░░░░  45%  ✅ 健康        │
│  服务 B:  ████████████████████░░░  78%  ⚠️ 警告        │
│  服务 C:  ████████████████████████ 100% ❌ 耗尽        │
│                                                         │
│  趋势图:                                               │
│  │    ╭──╮                                           │
│  │╭───╯  ╰───╮                                       │
│  │╯          ╰───╮                                   │
│  └─────────────── → 时间                               │
└─────────────────────────────��───────────────────────────┘
```

### 8.4 开发路线图

```
Phase 1 (2周)
├── Error Budget 核心逻辑
├── Burn Rate 看板
└── 基础告警

Phase 2 (2周)
├── On-Call 值班表
├── 升级策略
└── 多渠道通知

Phase 3 (2周)
├── SLO/SLA 配置
├── 报表导出
└── 资源优化

Phase 4 (可选)
├── 数据备份
├── 故障演练
└── 成本监控
```

### 8.5 预期收益

| 指标 | 当前 | 目标 | 提升 |
|------|------|------|------|
| MTTR | 30min | 15min | 50% |
| 变更失败率 | 5% | 1% | 80% |
| 告警响应时间 | 10min | 2min | 80% |
| 值班满意度 | 60% | 90% | 50% |
| SLO 达成率 | 无数据 | 95% | — |

### 8.6 参考资料

- [Google SRE Book](https://sre.google/sre-book/table-of-contents/)
- [SRE vs DevOps](https://www.atlassian.com/itsm/sre-vs-devops)
- [Error Budget 实践](https://www.atlassian.com/itsm/error-budgets)

---

*最后更新: 2026-06-28*


---

## 九、SRE 功能菜单分组设计

### 9.1 方案对比

| 方案 | 描述 | 优点 | 缺点 |
|------|------|------|------|
| 方案 1 | 独立 SRE 菜单 | 显性强调、便于扩展 | 新增一个顶级菜单 |
| 方案 2 | 分散到现有菜单 | 无需新增菜单 | 分散、难找 |

### 9.2 推荐: 方案 1 - 独立 SRE 菜单

```python
{
    "key": "sre", "label": "SRE 可靠性", "icon": "CircleCheck",
    "items": [
        # Error Budget 模块
        {"key": "error-budget", "label": "错误预算", "type": "vue", "path": "error-budget"},
        {"key": "burn-rate", "label": "预算消耗", "type": "vue", "path": "burn-rate"},
        
        # SLO/SLA 模块
        {"key": "slo-config", "label": "SLO 配置", "type": "vue", "path": "slo-config"},
        {"key": "sla-config", "label": "SLA 协议", "type": "vue", "path": "sla-config"},
        
        # On-Call 模块
        {"key": "oncall-schedule", "label": "值班表", "type": "vue", "path": "oncall-schedule"},
        {"key": "escalation-policy", "label": "升级策略", "type": "vue", "path": "escalation-policy"},
        
        # 可用性报表
        {"key": "availability", "label": "可用性报表", "type": "vue", "path": "availability"},
    ]
}
```

### 9.3 菜单与功能映射

| 菜单 Key | 菜单名 | 对应功能 | 优先级 |
|---------|--------|---------|--------|
| error-budget | 错误预算 | Error Budget 管理 | P0 |
| burn-rate | 预算消耗 | Burn Rate 看板 | P0 |
| slo-config | SLO 配置 | SLO 定义与追踪 | P0 |
| sla-config | SLA 协议 | SLA 协议管理 | P1 |
| oncall-schedule | 值班表 | 值班轮值表 | P0 |
| escalation-policy | 升级策略 | 自动升级策略 | P0 |
| availability | 可用性报表 | 可用性追踪 | P1 |

### 9.4 现有菜单 vs SRE 菜单

```
现有菜单结构:
├── 运行概览
├── AIOps 智能体
├── 可观测性
├── 事件中心
├── 告警管理
├── 资产管理
├── 拓扑视图
├── 容器与 K8s
├── 知识库
├── 自愈规则
├── 系统配置
└── API 文档

新增:
└── SRE 可靠性  ← 新增
```

### 9.5 图标选择

推荐使用 Element Plus 图标:
- `CircleCheck` - 可靠性
- `Timer` - 预算
- `TrendCharts` - Burn Rate
- `Calendar` - 值班
- `Phone` - 升级通知

---

*最后更新: 2026-06-28*
