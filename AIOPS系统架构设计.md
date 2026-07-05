# AIOps 智能运维系统 — 架构设计文档

> 最后更新: 2026-07-05

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

## 十、AI 助手能力增强：知识库 RAG 化 + SOP 工作流引擎

> 当前 AI 助手已具备 MCP 工具调用、ReAct 多轮循环、"提议-确认"闭环、链式推进、幻觉检测等能力，但缺乏"记忆"（知识库语义检索）和"骨架"（SOP 工作流编排）。本章设计知识库 RAG 化升级与 SOP 工作流引擎，使 AI 助手从"问答助手"升级为"自主运维 Agent"。

### 10.1 背景与目标

#### 10.1.1 现状痛点

| 模块 | 现状 | 问题 |
|------|------|------|
| **知识库** | `KnowledgeBase` 表仅 6 字段（title/symptom/root_cause/solution/tags/severity）；`query_knowledge` 工具仅 `ilike` 模糊匹配 | 无文档上传、无向量化、无 Embedding、无语义检索。AI 拿不到精准经验，无法做根因建议 |
| **工作流** | `change_workflow` 是人工填单走审批的状态机，与 AI 助手完全脱钩 | AI 只有对话驱动的单步 ReAct，无 SOP 编排能力。固定流程（如"磁盘告警→查盘→清理→验证→关告警"）需逐步问用户 |

#### 10.1.2 增强目标

```
问答助手（当前）  →  自主运维 Agent（目标）
  │                    │
  ├─ 单步 ReAct        ├─ ReAct + 知识库 RAG 检索（有记忆）
  └─ 一问一答          └─ ReAct + SOP 工作流编排（有骨架）
```

- **知识库 RAG 化**：AI 助手能语义检索历史故障处置经验、运维文档，回答"该怎么做"
- **SOP 工作流引擎**：AI 助手能 `propose_workflow` 一键触发整套运维剧本，自动执行多步骤、关键节点人工确认

### 10.2 整体架构

```
┌──────────────────────────────────────────────────────────────────┐
│                     AI 智能助手（Agent 管道）                     │
│   用户提问 → Action Router → ReAct 循环 → 工具调用 → 两阶段回答    │
└───────┬──────────────────────────────────┬───────────────────────┘
        │                                  │
        ▼                                  ▼
┌───────────────────────┐      ┌────────────────────────────────┐
│   知识库 RAG 检索      │      │     SOP 工作流引擎             │
│  (AI 的"记忆")         │      │  (AI 的"骨架")                 │
│                       │      │                                │
│  文档上传 → 切片       │      │  SOP 模板编排 (DAG)            │
│  → Embedding 向量化    │      │  ↓                             │
│  → 向量库存储          │      │  AI 触发 propose_workflow      │
│  → 语义检索 (Top-K)    │      │  ↓                             │
│  → 重排序 (Rerank)     │      │  节点逐步执行                  │
│  → 注入 LLM 上下文     │      │  ├─ 只读步骤: 自动执行          │
│                       │      │  ├─ 写操作步骤: 人工确认        │
│  query_knowledge_rag  │      │  └─ 失败: 自动重试/回滚         │
│  (MCP 工具)            │      │  ↓                             │
│                       │      │  propose_workflow (MCP 工具)    │
└──────────┬────────────┘      └───────────────┬────────────────┘
           │                                   │
           ▼                                   ▼
┌───────────────────────┐      ┌────────────────────────────────┐
│  向量存储层            │      │  工作流执行引擎                │
│  pgvector / Chroma    │      │  节点调度 + 状态机 + 审计日志   │
│  + 关系存储 (SQLite)   │      │  + 与现有 execute_* 工具复用    │
└───────────────────────┘      └────────────────────────────────┘
```

### 10.3 知识库 RAG 化设计

#### 10.3.1 数据模型扩展

在现有 `KnowledgeBase` 基础上新增文档管理与向量索引模型：

```python
# ─── 文档管理（支持上传 markdown/pdf/word/txt）───
class KbDocument(Base):
    __tablename__ = "kb_documents"

    id = Column(Integer, primary_key=True, index=True)
    kb_id = Column(Integer, ForeignKey("knowledge_base.id"), nullable=True)  # 可关联到知识条目，也可独立
    title = Column(String(256), nullable=False)
    source_type = Column(String(32), default="manual")  # manual / upload / alert_case / incident_case
    file_path = Column(String(512), default="")         # 上传文件原始路径
    content = Column(Text, default="")                  # 全文内容
    chunk_count = Column(Integer, default=0)            # 切片数量
    status = Column(String(32), default="pending")      # pending / indexed / failed
    created_by = Column(Integer, ForeignKey("users.id"), nullable=True)
    created_at = Column(DateTime, default=lambda: datetime.now())
    updated_at = Column(DateTime, default=lambda: datetime.now(), onupdate=lambda: datetime.now())


# ─── 文档切片 + 向量索引 ───
class KbChunk(Base):
    __tablename__ = "kb_chunks"

    id = Column(Integer, primary_key=True, index=True)
    document_id = Column(Integer, ForeignKey("kb_documents.id"), nullable=False)
    chunk_index = Column(Integer, nullable=False)       # 切片序号
    content = Column(Text, nullable=False)              # 切片文本
    embedding = Column(Text, default="")                # 向量 JSON 字符串（SQLite 兼容）；pgvector 用 vector 类型
    token_count = Column(Integer, default=0)
    # 元数据用于过滤检索
    tags = Column(String(256), default="")
    asset_type = Column(String(32), default="")
    severity = Column(String(32, default="warning"))
    created_at = Column(DateTime, default=lambda: datetime.now())
```

**字段设计要点：**
- `KbDocument.source_type` 区分手工录入、文件上传、告警自动归档、故障单自动归档，支持知识库自动沉淀
- `KbChunk.embedding` 在 SQLite 阶段用 JSON 字符串存储向量（兼容现有架构）；升级 PostgreSQL 后改用 `pgvector` 原生类型，提升检索性能
- `KbChunk` 保留 `tags/asset_type/severity` 元数据，支持检索时按业务维度过滤

#### 10.3.2 文档处理流水线

```
上传文档 (md/pdf/word/txt)
   │
   ▼
┌─────────────┐    ┌─────────────┐    ┌─────────────┐    ┌─────────────┐
│ 文档解析     │ →  │ 文本切片     │ →  │ Embedding   │ →  │ 向量入库     │
│ (unstructured│    │ (Chunking)  │    │ (向量化)    │    │ (持久化)    │
│  /pypdf)     │    │ 512 token   │    │ BGE/OpenAI  │    │ SQLite/     │
└─────────────┘    │ 128 重叠    │    │ /本地模型    │    │ pgvector    │
                   └─────────────┘    └─────────────┘    └─────────────┘
```

| 阶段 | 技术选型 | 说明 |
|------|---------|------|
| **文档解析** | `unstructured` / `pypdf` / `python-docx` | 支持 markdown/pdf/word/txt，提取纯文本 |
| **文本切片** | 递归字符切分（LangChain `RecursiveCharacterTextSplitter`） | 512 token / 128 重叠，保留语义完整性 |
| **Embedding** | `BAAI/bge-small-zh-v1.5`（本地 sentence-transformers）或 OpenAI `text-embedding-3-small` | 本地模型零成本、数据不出域；OpenAI 效果更优 |
| **向量入库** | SQLite（JSON 字符串）→ pgvector（升级路径） | 阶段一兼容现有架构，阶段二升级 |

#### 10.3.3 语义检索流程

```
用户提问 / 告警触发
   │
   ▼
┌─────────────┐    ┌─────────────┐    ┌─────────────┐    ┌─────────────┐
│ Query       │ →  │ 向量检索     │ →  │ 重排序       │ →  │ 上下文构造   │
│ Embedding   │    │ Top-K=10    │    │ (Rerank)    │    │ 注入 LLM     │
│             │    │ 余弦相似度   │    │ Top-N=3     │    │              │
└─────────────┘    └─────────────┘    └─────────────┘    └─────────────┘
```

1. **Query 向量化**：把用户问题或告警描述用同一 Embedding 模型转向量
2. **向量检索**：在 `KbChunk` 表中按余弦相似度检索 Top-K（默认 10），支持按 `tags/asset_type/severity` 元数据过滤
3. **重排序**（可选）：用 cross-encoder 模型对 Top-K 重排序取 Top-N（默认 3），提升精度
4. **上下文构造**：把 Top-N 切片内容拼接到 LLM prompt，生成回答

**SQLite 阶段的检索实现**（无原生向量索引，用 Python 内存计算）：
```python
def vector_search(query_embedding: List[float], top_k: int = 10, filters: dict = None) -> List[KbChunk]:
    chunks = db.query(KbChunk).all()
    # 元数据过滤
    if filters:
        chunks = [c for c in chunks if matches_filters(c, filters)]
    # 余弦相似度排序
    scored = [(cosine_sim(query_embedding, json.loads(c.embedding)), c) for c in chunks]
    scored.sort(key=lambda x: -x[0])
    return [c for _, c in scored[:top_k]]
```

> 注：此方案适合知识库 <1 万切片。超过后建议升级 pgvector + IVFFlat 索引。

#### 10.3.4 MCP 工具集成

新增 `query_knowledge_rag` MCP 工具替代现有 `query_knowledge` 的 `ilike` 匹配：

```python
@register_mcp_tool(
    name="query_knowledge_rag",
    description="语义检索运维知识库（RAG）。支持按症状、故障类型、资产类型语义匹配历史处置经验与运维文档，返回最相关的知识条目与文档切片。",
    input_schema={
        "type": "object",
        "properties": {
            "query": {"type": "string", "description": "检索问题或故障描述"},
            "asset_type": {"type": "string", "description": "资产类型过滤（可选）"},
            "severity": {"type": "string", "description": "严重级别过滤（可选）"},
            "top_k": {"type": "integer", "description": "返回数量", "default": 5},
        },
        "required": ["query"],
    },
    risk_level="read_only",
)
def query_knowledge_rag(db, user_id=None, **kwargs):
    query = kwargs["query"]
    top_k = kwargs.get("top_k", 5)
    filters = {k: kwargs[k] for k in ("asset_type", "severity") if kwargs.get(k)}
    # 1. Query 向量化
    query_emb = embed_text(query)
    # 2. 向量检索
    chunks = vector_search(query_emb, top_k=top_k, filters=filters)
    # 3. 返回结果（含原文 + 来源文档 + 相似度）
    return {
        "count": len(chunks),
        "items": [
            {
                "document_title": chunk.document.title,
                "content": chunk.content,
                "similarity": round(chunk._score, 3),
                "tags": chunk.tags,
            }
            for chunk in chunks
        ],
    }
```

**与告警自动关联**：告警触发时自动用告警 `metric_name + message` 调 `query_knowledge_rag`，把匹配的处置经验推送通知，实现"告警即推荐"。

### 10.4 SOP 工作流引擎设计

#### 10.4.1 设计思路

```
现有 change_workflow（人填单走审批）  ← 保留，作为"变更管理"功能
        ↑ 区别
SOP 工作流引擎（新）                   ← 新增，作为"AI 驱动的自动化剧本"
  - 模板化：预置高频运维 SOP（磁盘清理/服务重启/扩缩容/故障自愈）
  - 可编排：DAG 节点图，节点间有依赖关系
  - AI 触发：AI 助手通过 propose_workflow 一键触发
  - 自动执行：只读步骤自动跑，写操作步骤人工确认
  - 复用现有：节点动作复用 execute_* MCP 工具
```

#### 10.4.2 数据模型

```python
# ─── SOP 模板（可复用的运维剧本）───
class WorkflowTemplate(Base):
    __tablename__ = "workflow_templates"

    id = Column(Integer, primary_key=True, index=True)
    name = Column(String(128), nullable=False)
    description = Column(Text, default="")
    category = Column(String(64), default="generic")  # disk / service / scaling / healing / custom
    trigger_type = Column(String(32), default="manual")  # manual / alert_auto / scheduled
    trigger_condition = Column(Text, default="")          # JSON：触发条件（告警 metric+阈值）
    nodes = Column(Text, default="[]")                    # JSON：节点定义（DAG）
    edges = Column(Text, default="[]")                    # JSON：边定义（依赖关系）
    risk_level = Column(String(32), default="medium")
    enabled = Column(Boolean, default=True)
    created_at = Column(DateTime, default=lambda: datetime.now())
    updated_at = Column(DateTime, default=lambda: datetime.now(), onupdate=lambda: datetime.now())


# ─── 工作流执行实例 ───
class WorkflowRun(Base):
    __tablename__ = "workflow_runs"

    id = Column(Integer, primary_key=True, index=True)
    template_id = Column(Integer, ForeignKey("workflow_templates.id"), nullable=True)
    session_id = Column(Integer, ForeignKey("chat_sessions.id"), nullable=True)  # 触发的 AI 会话
    title = Column(String(256), nullable=False)
    status = Column(String(32), default="pending")  # pending / running / paused / completed / failed / aborted
    context = Column(Text, default="{}")            # JSON：运行时上下文（asset_id、告警信息等）
    trigger_source = Column(String(32), default="ai")  # ai / manual / alert_auto
    started_at = Column(DateTime, nullable=True)
    completed_at = Column(DateTime, nullable=True)
    created_at = Column(DateTime, default=lambda: datetime.now())


# ─── 节点执行记录 ───
class WorkflowNodeRun(Base):
    __tablename__ = "workflow_node_runs"

    id = Column(Integer, primary_key=True, index=True)
    run_id = Column(Integer, ForeignKey("workflow_runs.id"), nullable=False)
    node_id = Column(String(64), nullable=False)     # 对应 template.nodes[].id
    node_name = Column(String(128), default="")
    action_type = Column(String(64), nullable=False) # 对应 execute_* 工具后缀
    payload = Column(Text, default="{}")             # JSON：执行参数
    status = Column(String(32), default="pending")   # pending / running / awaiting_confirm / completed / failed / skipped
    result = Column(Text, default="")                # JSON：执行结果
    requires_confirm = Column(Boolean, default=False)
    started_at = Column(DateTime, nullable=True)
    completed_at = Column(DateTime, nullable=True)
    created_at = Column(DateTime, default=lambda: datetime.now())
```

**节点定义 JSON 结构（`WorkflowTemplate.nodes`）：**
```json
[
  {
    "id": "node_1",
    "name": "检查磁盘占用",
    "action_type": "run_command",
    "payload_template": {"command": "df -h", "asset_id": "{{context.asset_id}}"},
    "requires_confirm": false,
    "retry_count": 0
  },
  {
    "id": "node_2",
    "name": "清理磁盘",
    "action_type": "clean_disk",
    "payload_template": {"path": "/tmp", "asset_id": "{{context.asset_id}}"},
    "requires_confirm": true,
    "retry_count": 1
  },
  {
    "id": "node_3",
    "name": "验证清理结果",
    "action_type": "run_command",
    "payload_template": {"command": "df -h", "asset_id": "{{context.asset_id}}"},
    "requires_confirm": false,
    "retry_count": 0
  }
]
```

#### 10.4.3 状态机与执行引擎

```
WorkflowRun 状态机:
  pending → running → [paused (等待人工确认)] → running → completed
                                              ↓
                                           failed / aborted

NodeRun 状态机:
  pending → running → awaiting_confirm (写操作) → completed
                    ↓                          ↓
                  completed (只读)           failed (确认拒绝→整个 Run aborted)
```

**执行引擎核心逻辑：**
1. **拓扑排序**：按 DAG 依赖关系确定节点执行顺序
2. **节点调度**：依次执行节点，渲染 `payload_template`（Jinja2 模板，注入 `context` 与上游节点 `result`）
3. **只读自动执行**：`requires_confirm=false` 的节点直接调 `execute_*` 工具
4. **写操作暂停等待**：`requires_confirm=true` 的节点创建 `PendingAction`，状态置 `awaiting_confirm`，用户确认后继续
5. **失败处理**：节点失败按 `retry_count` 自动重试；超过重试次数则整个 Run 置 `failed`，可手动 `abort`
6. **审计**：每个节点执行结果落库 `WorkflowNodeRun`，完整可追溯

#### 10.4.4 MCP 工具集成

```python
@register_mcp_tool(
    name="list_workflow_templates",
    description="列出可用的 SOP 工作流模板",
    input_schema={"type": "object", "properties": {"category": {"type": "string"}}},
    risk_level="read_only",
)
def list_workflow_templates(db, user_id=None, **kwargs):
    ...

@register_mcp_tool(
    name="propose_workflow",
    description="提议执行一个 SOP 工作流。不直接执行，创建待确认工作流实例。AI 助手处理多步骤运维任务时应优先用此工具，而非逐步 propose_action。",
    input_schema={
        "type": "object",
        "properties": {
            "template_id": {"type": "integer", "description": "SOP 模板 ID（可选，无则需提供 nodes）"},
            "title": {"type": "string", "description": "工作流标题"},
            "context": {"type": "object", "description": "运行时上下文（asset_id、告警信息等）"},
            "nodes": {"type": "array", "description": "自定义节点（无 template_id 时必填）"},
            "edges": {"type": "array", "description": "自定义边（无 template_id 时必填）"},
        },
        "required": ["title"],
    },
    risk_level="advisory",
)
def propose_workflow(db, user_id=None, **kwargs):
    # 创建 WorkflowRun + 首批 NodeRun，返回 _pending_workflow
    # 与 propose_action 类似，由前端展示确认按钮
    ...
```

#### 10.4.5 预置 SOP 模板

| 模板名 | 触发场景 | 节点流程 |
|--------|---------|---------|
| **磁盘告警处置 SOP** | `disk_usage > 90%` 告警 | 查盘(df) → 定位大文件(du) → 清理(/tmp或/var/log) → 验证(df) → 关告警 |
| **服务重启 SOP** | 服务无响应告警 | 查进程(ps) → 重启(systemctl restart) → 验证(ps+curl) → 关告警 |
| **Pod 重启循环处置 SOP** | CrashLoopBackOff 事件 | 查 Pod 日志(logs) → 查事件(events) → 重启Pod(delete pod) → 验证(kubectl get) |
| **扩容 SOP** | CPU/内存持续高位告警 | 查当前副本数 → 扩容(scale) → 验证副本数 → 观察5分钟指标 |
| **数据库慢查询处置 SOP** | 慢查询告警 | 查进程列表(show processlist) → 杀慢查询(kill) → 验证 |

### 10.5 与现有 change_workflow 的关系

```
┌─────────────────────┐     ┌─────────────────────────┐
│ change_workflow     │     │ SOP 工作流引擎（新）     │
│ (变更管理)          │     │ (AI 驱动自动化剧本)      │
├─────────────────────┤     ├─────────────────────────┤
│ 人填单 → 审批 → 执行│     │ AI 触发 → 自动执行       │
│ 关注"变更是否被授权"│     │ 关注"运维动作自动完成"   │
│ draft→approve→done  │     │ DAG 节点编排             │
└──────────┬──────────┘     └────────────┬────────────┘
           │                              │
           └──────────┬───────────────────┘
                      ▼
          高危变更可联动：SOP 工作流中
          requires_confirm 的写操作节点，
          可自动生成 change_workflow 变更单
          走审批流，审批通过后继续执行
```

**二者并存，不替换：**
- `change_workflow`：保留，用于"人工发起的变更审批"
- `SOP 工作流引擎`：新增，用于"AI 触发的自动化运维"
- 联动点：SOP 工作流的高危节点可自动创建 `ChangeRequest`，审批通过后继续执行

### 10.6 实施路线图

```
Phase 1 (1周) ── 知识库 RAG 基础
├── KbDocument / KbChunk 数据模型 + 迁移
├── 文档上传接口（/knowledge/documents/upload）
├── 文档解析 + 切片（unstructured + RecursiveCharacterTextSplitter）
├── Embedding 集成（BGE 本地模型 / OpenAI）
└── 向量入库 + 语义检索 query_knowledge_rag 工具

Phase 2 (1周) ── 知识库自动沉淀
├── 告警解决后自动归档为 KbDocument（source_type=alert_case）
├── 故障单关闭后自动归档为 KbDocument（source_type=incident_case）
├── 告警触发自动调 query_knowledge_rag 推荐处置经验
└── 前端知识库页面增加文档上传 + RAG 检索入口

Phase 3 (1.5周) ── SOP 工作流引擎核心
├── WorkflowTemplate / WorkflowRun / WorkflowNodeRun 数据模型
├── DAG 拓扑排序 + 执行引擎
├── 节点 payload_template 渲染（Jinja2）
├── 只读节点自动执行 + 写操作节点 PendingAction 确认
├── propose_workflow / list_workflow_templates MCP 工具
└── 5 个预置 SOP 模板（磁盘/服务/Pod/扩容/慢查询）

Phase 4 (1周) ── AI 助手集成 + 前端
├── AI 助手 system_prompt 增加 SOP 工作流使用引导
├── 前端工作流执行监控页（节点状态图 + 实时日志）
├── 工作流模板管理页（CRUD + 可视化节点编辑）
└── 告警自动触发 SOP 工作流（trigger_type=alert_auto）

Phase 5 (可选) ── 升级与优化
├── 升级 PostgreSQL + pgvector（向量索引性能）
├── Rerank 模型集成（cross-encoder 提升精度）
├── 工作流节点支持并行执行（DAG 多分支）
└── 工作流执行历史分析与模板推荐
```

### 10.7 技术选型

| 组件 | 阶段一（兼容现有） | 阶段二（性能升级） |
|------|------------------|------------------|
| **向量存储** | SQLite + JSON 字符串 | PostgreSQL + pgvector + IVFFlat |
| **Embedding 模型** | `BAAI/bge-small-zh-v1.5`（本地，512维，零成本） | 同左 / OpenAI `text-embedding-3-small` |
| **文档解析** | `unstructured` + `pypdf` + `python-docx` | 同左 |
| **文本切片** | LangChain `RecursiveCharacterTextSplitter` | 同左 |
| **Rerank** | （跳过，Top-K 直接用） | `BAAI/bge-reranker-base` cross-encoder |
| **模板渲染** | Jinja2（复用现有 `template_utils`） | 同左 |
| **DAG 调度** | 自研拓扑排序 + 状态机 | 可选 LangGraph / Temporal |
| **前端可视化** | Element Plus + 自研节点状态图 | 可选 AntV X6 / G6 DAG 可视化 |

### 10.8 预期收益

| 指标 | 当前 | 目标 | 提升 |
|------|------|------|------|
| 知识库检索准确率 | `ilike` 关键词（低） | 语义检索 Top-3 命中率 >80% | 显著提升 |
| 告警处置建议可用性 | 无 | 自动推荐历史处置经验 | 从无到有 |
| 多步运维操作人工介入 | 每步确认 | 仅写操作确认，只读自动执行 | 介入次数 -60% |
| 固定 SOP 执行时间 | 人工逐步操作 15min | AI 触发自动执行 3min | -80% |
| 知识库自动沉淀 | 人工录入 | 告警/故障单自动归档 | 零成本积累 |

### 10.9 与现有系统的复用关系

| 现有能力 | 复用方式 |
|---------|---------|
| `execute_*` MCP 工具 | SOP 工作流节点动作直接复用，无需重写 |
| `PendingAction` 确认流 | SOP 工作流写操作节点复用确认机制 |
| `propose_action` 工具 | `propose_workflow` 复用其设计模式（advisory 风险等级 + _pending_ 字段返回） |
| `template_utils.parse_json_config` | 节点 payload 解析复用 |
| `change_workflow` | 高危 SOP 节点联动生成变更单 |
| `knowledge_graph_service.recommend_kb_for_alert` | 升级为 RAG 检索后保留打分逻辑作为 Rerank 信号 |

---

## 十一、智能体编排工作流平台（Coze 风格 — AI 原生可视化编排）

> 最后更新: 2026-07-05

### 11.1 定位与核心区别

| 维度 | 第十章 SOP 工作流引擎 | 第十一章 智能体编排工作流平台 |
|------|---------------------|---------------------------|
| **本质** | 固定运维动作链（DF→清理→验证） | AI 原生可视化编排平台（类 Coze/Dify） |
| **节点类型** | 仅 execute_* 运维动作 | 8 种异构节点（LLM/知识库/工具/条件/代码/HTTP...） |
| **编排方式** | JSON 配置 DAG | **可视化画布拖拽**（Vue Flow）+ JSON 持久化 |
| **变量传递** | Jinja2 渲染 payload | 运行时上下文 + 节点输出引用 `{{ nodes.llm1.output.text }}` |
| **AI 在环** | AI 仅触发，不参与执行 | **LLM 节点在流程中推理**，条件分支由 AI 输出决定路由 |
| **目标用户** | 运维工程师（选模板） | AI 应用开发者（拖拽搭建智能体） |
| **类比** | Ansible Playbook | Coze / Dify / LangFlow |

**核心价值**：把"AI 助手"从单一对话升级为**可编排的智能体应用平台**——用户在画布上拖拽 LLM 节点、知识库节点、工具节点、条件分支，搭建定制化 AI 智能体工作流，一键发布为可调用的 AI 应用。

### 11.2 核心概念

```
工作流 (AgentWorkflow)
├── 节点 (Node) — 8 种类型
│   ├── start    — 开始节点：定义输入参数 schema
│   ├── end      — 结束节点：定义输出映射
│   ├── llm      — LLM 推理节点：prompt + 模型 + 温度 + system prompt
│   ├── knowledge — 知识库 RAG 节点：语义检索 Top-K
│   ├── tool     — 工具节点：调用 MCP 工具（query_*/execute_*）
│   ├── condition — 条件分支节点：if-elif-else 路由
│   ├── code     — 代码节点：Python 沙箱执行数据处理
│   └── http     — HTTP 请求节点：调用外部 API
├── 边 (Edge) — 节点依赖 + 条件分支路由
├── 变量 (Variable) — 运行时上下文 + 节点输出引用
└── 触发 (Trigger) — 对话 / API / 定时 / 告警
```

### 11.3 节点类型详细设计

#### 11.3.1 Start 节点
```json
{
  "id": "start",
  "type": "start",
  "data": {
    "inputs": [
      {"key": "question", "type": "string", "required": true, "desc": "用户问题"},
      {"key": "context", "type": "object", "required": false, "desc": "上下文"}
    ]
  }
}
```
- 定义工作流输入参数 schema
- 运行时 inputs 注入 `runtime_context.nodes.start.output`

#### 11.3.2 End 节点
```json
{
  "id": "end",
  "type": "end",
  "data": {
    "outputs": [
      {"key": "answer", "value": "{{ nodes.llm1.output.text }}"}
    ]
  }
}
```
- 定义工作流输出映射
- 通过 Jinja2 引用上游节点输出

#### 11.3.3 LLM 推理节点（核心）
```json
{
  "id": "llm1",
  "type": "llm",
  "data": {
    "provider_id": 1,
    "model": "gpt-4o",
    "system_prompt": "你是 AIOps 运维专家，根据告警信息分析根因",
    "user_prompt": "告警: {{ nodes.start.output.question }}\n上下文: {{ nodes.knowledge1.output.docs }}",
    "temperature": 0.3,
    "max_tokens": 2000
  }
}
```
- 调用 `call_llm(provider, messages)` 复用现有 LLM 调用
- prompt 用 Jinja2 渲染，引用上游节点输出
- 输出 `{"text": "...", "usage": {...}}` 存入上下文

#### 11.3.4 知识库 RAG 节点
```json
{
  "id": "knowledge1",
  "type": "knowledge",
  "data": {
    "query": "{{ nodes.start.output.question }}",
    "kb_id": 1,
    "top_k": 5,
    "score_threshold": 0.7
  }
}
```
- 复用 `query_knowledge_rag` MCP 工具
- 输出 `{"docs": [...], "query": "..."}`

#### 11.3.5 工具节点
```json
{
  "id": "tool1",
  "type": "tool",
  "data": {
    "tool_name": "query_alerts",
    "parameters": {"severity": "{{ nodes.start.output.severity }}", "limit": 10}
  }
}
```
- 调用 `call_mcp_tool(tool_name, parameters)` 复用 13+ MCP 工具
- 输出工具返回结果

#### 11.3.6 条件分支节点
```json
{
  "id": "cond1",
  "type": "condition",
  "data": {
    "branches": [
      {"condition": "{{ nodes.llm1.output.text contains '严重' }}", "target": "escalate"},
      {"condition": "{{ nodes.llm1.output.text contains '轻微' }}", "target": "auto_fix"},
      {"condition": "default", "target": "notify"}
    ]
  }
}
```
- 求值 Jinja2 表达式，路由到匹配分支
- 输出 `{"matched_branch": "escalate"}`

#### 11.3.7 代码节点
```json
{
  "id": "code1",
  "type": "code",
  "data": {
    "code": "result = {'count': len(inputs['alerts']), 'summary': f\"共{len(inputs['alerts'])}条告警\"}",
    "inputs_mapping": {"alerts": "{{ nodes.tool1.output.alerts }}"}
  }
}
```
- Python 沙箱执行（`exec` + 受限 globals，禁用 import os/subprocess/socket）
- 输入通过 `inputs_mapping` 映射，代码访问 `inputs` dict
- 输出代码中 `result` 变量

#### 11.3.8 HTTP 请求节点
```json
{
  "id": "http1",
  "type": "http",
  "data": {
    "method": "POST",
    "url": "https://api.example.com/notify",
    "headers": {"Content-Type": "application/json"},
    "body": {"message": "{{ nodes.llm1.output.text }}"},
    "timeout": 10
  }
}
```
- 调用外部 API
- 输出 `{"status_code": 200, "body": "..."}`

### 11.4 变量传递机制

**运行时上下文 (Runtime Context)** 是核心数据结构：
```python
runtime_context = {
    "workflow_id": 1,
    "run_id": 1,
    "inputs": {"question": "...", "severity": "critical"},
    "nodes": {
        "start": {"output": {"question": "...", "severity": "critical"}},
        "knowledge1": {"output": {"docs": [...], "query": "..."}},
        "llm1": {"output": {"text": "根因是...", "usage": {...}}},
        "cond1": {"output": {"matched_branch": "escalate"}},
        "end": {"output": {"answer": "根因是..."}}
    }
}
```

**引用规则**（Jinja2）：
- `{{ nodes.<node_id>.output.<key> }}` — 引用任意节点输出
- `{{ inputs.<key> }}` — 引用工作流输入（等价 `nodes.start.output`）
- 支持过滤器：`{{ nodes.llm1.output.text | upper }}`、`{{ nodes.tool1.output.alerts | length }}`

**条件表达式**（条件分支节点专用）：
- 简化语法：`{{ nodes.llm1.output.text contains '严重' }}`
- 编译为 Python：`'严重' in nodes['llm1']['output']['text']`
- 支持：contains / eq / ne / gt / lt / in / startswith

### 11.5 执行引擎设计

```
start_workflow_run(inputs)
  ├─ 1. 创建 WorkflowRun + 全部 NodeRun (status=pending)
  ├─ 2. 注入 inputs 到 runtime_context.nodes.start.output
  ├─ 3. 拓扑排序节点
  └─ 4. 调度循环 _advance_run():
       ├─ 遍历拓扑序节点
       ├─ 跳过非 pending 节点
       ├─ 检查依赖完成（含条件分支路由）
       ├─ 渲染节点 config (Jinja2 + runtime_context)
       ├─ 分发到节点执行器:
       │   ├─ start_executor → 注入 inputs
       │   ├─ end_executor → 渲染输出映射
       │   ├─ llm_executor → call_llm(provider, messages)
       │   ├─ knowledge_executor → call_mcp_tool('query_knowledge_rag')
       │   ├─ tool_executor → call_mcp_tool(tool_name, params)
       │   ├─ condition_executor → 求值分支表达式
       │   ├─ code_executor → exec 沙箱
       │   └─ http_executor → requests.request
       ├─ 节点输出存入 runtime_context.nodes[node_id].output
       ├─ 条件分支节点：激活匹配分支的下游边，禁用其他分支
       └─ 全部完成 → finalize run
```

**节点执行器统一接口**：
```python
def execute_node(node_type: str, node_data: dict, runtime_context: dict, db: Session) -> dict:
    """返回 {"output": {...}, "status": "completed|failed", "error": "..."}"""
    executor = NODE_EXECUTORS.get(node_type)
    if not executor:
        return {"output": {}, "status": "failed", "error": f"未知节点类型: {node_type}"}
    return executor(node_data, runtime_context, db)
```

**失败处理策略**：
- 节点失败 → 标记 failed，下游节点 skipped
- 不自动重试（区别于 SOP 引擎），由调用方决定是否重试
- 失败信息存入 NodeRun.error，前端可查看

### 11.6 数据模型

```sql
-- 智能体工作流编排定义
agent_workflows:
  id, name, description, category, nodes(JSON), edges(JSON),
  inputs_schema(JSON), outputs_schema(JSON),
  enabled, published_version, created_by, created_at, updated_at

-- 工作流执行实例
agent_workflow_runs:
  id, workflow_id, workflow_snapshot(JSON),  -- 执行时的 workflow 快照
  session_id,  -- 关联 ChatSession（对话触发时）
  status,  -- pending/running/completed/failed/aborted
  inputs(JSON), runtime_context(JSON),  -- 输入 + 运行时上下文
  outputs(JSON),  -- end 节点输出
  trigger_source,  -- chat/api/schedule/alert
  started_at, completed_at, created_at

-- 节点执行记录
agent_workflow_node_runs:
  id, run_id, node_id, node_type, node_name,
  config(JSON),  -- 渲染后的节点配置
  status,  -- pending/running/completed/failed/skipped
  output(JSON), error,
  started_at, completed_at, created_at
```

### 11.7 可视化画布（Vue Flow）

**技术选型**：`@vue-flow/core` — Vue 3 原生、d3-based、社区活跃、支持自定义节点

**画布布局**：
```
┌─────────────────────────────────────────────────────────────┐
│ 工具栏: [保存] [发布] [运行测试] [清空]              工作流名  │
├──────────┬────────────────────────────────┬─────────────────┤
│ 节点面板  │                                │ 属性配置抽屉      │
│          │       Vue Flow 画布             │                  │
│ ▸ 开始    │   ┌─────┐    ┌─────┐          │ 节点: LLM推理     │
│ ▸ 结束    │   │start│───→│llm1 │          │ ─────────────── │
│ ▸ LLM    │   └─────┘    └──┬──┘          │ 模型: gpt-4o     │
│ ▸ 知识库  │                ↓              │ 温度: 0.3        │
│ ▸ 工具    │            ┌─────┐            │ System:          │
│ ▸ 条件    │            │kb1  │            │ [textarea]       │
│ ▸ 代码    │            └──┬──┘            │ User:            │
│ ▸ HTTP   │               ↓               │ [textarea]       │
│          │           ┌─────┐             │                  │
│          │           │end  │             │                  │
│          │           └─────┘             │                  │
└──────────┴────────────────────────────────┴─────────────────┘
```

**交互**：
- 从节点面板拖拽节点到画布
- 节点间拖拽连线（source handle → target handle）
- 点击节点 → 右侧抽屉显示属性配置
- 运行测试 → 输入测试数据 → 后端执行 → 画布节点实时显示状态
- 保存 → 持久化 nodes/edges 到 agent_workflows 表

**自定义节点组件**：每种节点类型一个 Vue 组件，显示图标+名称+状态色

### 11.8 触发方式

| 触发方式 | 实现 | 适用场景 |
|---------|------|---------|
| **对话触发** | AI 通过 `run_agent_workflow` MCP 工具触发，关联 ChatSession | 用户在 AI 助手对话中触发智能体 |
| **API 触发** | `POST /agent-workflow/api/runs/{id}/execute` | 外部系统集成 |
| **定时触发** | 后台线程 Cron 调度（复用现有 background_loop） | 定时巡检 |
| **告警触发** | 告警发生时匹配 workflow.trigger_condition | 自动化响应 |

### 11.9 与 AI Agent 管道集成

**MCP 工具**：
- `list_agent_workflows` — 列出已发布工作流
- `run_agent_workflow` — 执行工作流，返回 run_id

**会话集成**：
- 对话触发时关联 `session_id`
- 工作流执行进度可通过 `GET /agent-workflow/api/runs/{id}` 轮询
- 前端聊天界面可嵌入工作流执行状态卡片

**与 SOP 工作流引擎（第十章）的关系**：
- **并存**：SOP 引擎管固定运维动作链，Agent Workflow 管 AI 原生编排
- **复用**：Agent Workflow 的 tool 节点复用 execute_* MCP 工具
- **演进**：SOP 模板可逐步迁移为 Agent Workflow（用 LLM 节点替代固定命令）

### 11.10 实施路线图

| Phase | 内容 | 工时 |
|-------|------|------|
| **Phase 1** | 后端：数据模型 + 执行引擎 + 8 节点执行器 + API | 已落地 |
| **Phase 2** | 前端：Vue Flow 画布 + 节点面板 + 属性抽屉 + 运行测试 | 已落地 |
| **Phase 3** | 集成：MCP 工具 + 菜单注册 + AI Agent 管道集成 | 已落地 |
| **Phase 4** | 增强：定时触发 + 告警触发 + 工作流版本管理 + 模板市场 | 待规划 |

### 11.11 预置工作流模板

| 模板名 | 节点编排 | 场景 |
|--------|---------|------|
| **智能告警分析** | start→query_alerts→knowledge RAG→LLM 根因分析→end | 告警自动根因分析 |
| **智能运维问答** | start→knowledge RAG→LLM 问答→end | 运维知识问答 |
| **故障自愈决策** | start→query_alerts→LLM 决策→condition(自愈/升级/通知)→分支→end | AI 决策故障处置 |
| **变更影响评估** | start→query_change→knowledge RAG→LLM 评估→end | 变更前影响分析 |
| **巡检报告生成** | start→query_metrics→LLM 总结→end | 自动巡检报告 |

### 11.12 与现有系统的复用关系

| 现有能力 | 复用方式 |
|---------|---------|
| `call_llm(provider, messages)` | LLM 节点直接复用，支持多 provider |
| `query_knowledge_rag` MCP 工具 | 知识库节点复用 RAG 检索 |
| 13+ `execute_*`/`query_*` MCP 工具 | 工具节点复用全部 MCP 工具 |
| `AIProvider` 多模型配置 | LLM 节点按 provider_id 选择模型 |
| `call_mcp_tool` 调度框架 | 工具/知识库节点复用调度 |
| `ChatSession` 会话管理 | 对话触发关联会话 |
| 第十章 SOP 引擎拓扑排序 | Agent Workflow 复用 DAG 调度思路 |

---

## 十二、K8s 资源声明式管理 + Helm 应用管理（新增）

### 12.1 K8s 资源创建落地

在原 Deployment/HPA 创建能力基础上，补齐 K8s 原生资源的声明式创建与删除，覆盖容器编排全生命周期。

| 资源类型 | API 端点 | K8s API | 说明 |
|---------|---------|---------|------|
| **Namespace** | `POST /k8s/api/namespaces/create` | CoreV1Api.create_namespace | 集群级资源，无 namespace 段 |
| **StatefulSet** | `POST /k8s/api/statefulsets/create` | AppsV1Api.create_namespaced_stateful_set | 有状态应用，含 service_name/headless 关联 |
| **DaemonSet** | `POST /k8s/api/daemonsets/create` | AppsV1Api.create_namespaced_daemon_set | 守护进程，每节点一副本 |
| **Service** | `POST /k8s/api/services/create` | CoreV1Api.create_namespaced_service | ClusterIP/NodePort/LoadBalancer 三型 |
| **Ingress** | `POST /k8s/api/ingresses/create` | NetworkingV1Api.create_namespaced_ingress | 七层路由，自动 TLS secret 生成 |
| **ConfigMap** | `POST /k8s/api/configmaps/create` | CoreV1Api.create_namespaced_config_map | 键值配置，支持查看/编辑/创建 |
| **Secret** | `POST /k8s/api/secrets/create` | CoreV1Api.create_namespaced_secret | data 值后端 Base64 编码存储 |
| **PVC** | `POST /k8s/api/pvcs/create` | CoreV1Api.create_namespaced_persistent_volume_claim | 存储卷声明，含 storage_class/access_mode |

每个资源均提供 `POST /k8s/api/{type}/{cluster}/{namespace}/{name}/delete` 删除端点。前端 `K8sResourceListView.vue` 按资源类型条件渲染创建表单（form-grid 双列网格）+ 行内删除按钮（ElMessageBox 确认）。

### 12.2 Helm 应用管理

通过 subprocess 包装 Helm CLI 实现 Release 全生命周期管理，KUBECONFIG 通过临时文件注入（从数据源 auth_config 解析 kubeconfig 写 tempfile，执行后清理）。

| 功能 | API | Helm 命令 |
|------|-----|----------|
| 仓库管理 | `GET/POST /helm/api/repos` | `helm repo list/add/remove/update` |
| Release 列表 | `GET /helm/api/releases` | `helm list -A -o json` |
| Chart 搜索 | `GET /helm/api/charts` | `helm search repo -o json` |
| 安装/升级 | `POST /helm/api/install\|upgrade` | `helm install/upgrade -f values.yaml` |
| 卸载/回滚 | `POST /helm/api/uninstall\|rollback` | `helm uninstall/rollback` |
| 历史与状态 | `GET /helm/api/history\|status` | `helm history/status -o json` |

前端 `HelmView.vue` 三 Tab（Release 列表/仓库管理/安装应用），支持 values YAML 编辑、chart 关键词防抖搜索、回滚 revision 选择。Helm CLI 未安装时所有 API 友好降级返回 `helm_missing` 错误。

---

## 十三、Ansible 运维操作平台（新增）

将 Ansible 纳入平台运维执行能力，补足「批量脚本/配置下发/编排执行」场景，与现有「远程脚本」（单机 SSH）形成互补。

### 13.1 数据模型

| 模型 | 表名 | 关键字段 |
|------|------|---------|
| `AnsibleInventory` | ansible_inventories | name(unique)、content(YAML 主机清单)、description |
| `AnsiblePlaybook` | ansible_playbooks | name(unique)、content(YAML playbook)、description |
| `AnsibleRun` | ansible_runs | inventory_id/playbook_id、output、error、exit_code、status(pending/running/completed/failed)、created_at/finished_at |

### 13.2 执行引擎

通过 subprocess 调用 `ansible-playbook` CLI：
1. 将 inventory content 与 playbook content 写入临时 `.yml` 文件（tempfile.NamedTemporaryFile）
2. 拼接命令 `ansible-playbook -i inventory.yml playbook.yml -e '<extra_vars_json>'`
3. `subprocess.run(capture_output=True, text=True, timeout=300)` 同步执行
4. 捕获 stdout/stderr/returncode，更新 AnsibleRun 记录状态
5. 执行后 `os.unlink` 清理临时文件

### 13.3 API 清单（prefix=/ansible）

| 端点 | 功能 |
|------|------|
| `GET/POST/PUT/DELETE /api/inventories` | 主机清单 CRUD |
| `GET/POST/PUT/DELETE /api/playbooks` | Playbook 模板 CRUD |
| `POST /api/run` | 执行（选 inventory + playbook + extra_vars） |
| `GET/DELETE /api/runs[/{id}]` | 执行历史与详情 |
| `GET /api/status` | 检测 ansible-playbook 安装情况 |
| `POST /api/test-inventory` | `ansible all -m ping` 测试清单连通性 |

前端 `AnsibleView.vue` 三 Tab（执行历史/主机清单/Playbook 模板），YAML 编辑区等宽字体，执行 output 用 pre 块等宽展示，status 彩色 badge（completed 绿/failed 红/running 蓝/pending 灰）。ansible 未安装时优雅降级。

---

## 十四、授权许可证控制（防破解 · 商业化出售）

平台支持商业化分发，通过 RSA 非对称签名许可证 + 机器指纹绑定 + 时钟防回拨实现有效期控制与防破解。

### 14.1 防破解设计六重防护

| 防护层 | 机制 | 防御目标 |
|--------|------|---------|
| **RSA 非对称签名** | 私钥离线签发，公钥硬编码验签 | 防伪造许可证（攻击者无私钥无法签发合法 lic） |
| **机器指纹绑定** | MAC+CPU+磁盘序列号+主机名 SHA256 取 32 位 | 防拷贝（许可证绑定单机，换机失效） |
| **时钟防回拨** | 持久化 last_check_time，当前时间 < 上次 - 60s 即锁定 | 防改系统时间绕过到期 |
| **离线验证** | 纯本地验签，不依赖网络/服务器 | 防断网绕过 |
| **中间件拦截** | `LicenseMiddleware` 拦截所有 API，过期/无效返回 403 | 单点管控全局生效 |
| **多点校验** | 中间件(每请求) + 登录 + 后台定期 | 防单一校验点被 patch |

### 14.2 许可证格式

```
BASE64(payload_json) + "." + BASE64(rsa_signature)
```
- payload: `{customer, edition(标准版/企业版/旗舰版), issued_at, expire_at, fingerprint, max_nodes, features[]}`
- signature: 对 payload_json 的 UTF-8 字节做 RSA-SHA256(PKCS1v15) 签名
- 验签: 公钥 `verify(signature, payload_bytes, PKCS1v15(), SHA256())`

### 14.3 机器指纹采集（跨平台）

| 维度 | Windows | Linux |
|------|---------|-------|
| MAC | `uuid.getnode()` 12 位 hex | 同 |
| CPU | `platform.processor()` | `/proc/cpuinfo` model name |
| 磁盘 | `wmic diskdrive get serialnumber` | `lsblk -dno SERIAL` |
| 主机名 | `platform.node()` | 同 |

拼接 `mac|cpu|disk|host` 后 `sha256().hexdigest()[:32]`。

### 14.4 中间件链路

```
Session → License → Auth → GZip → 路由
```
- LicenseMiddleware 放行路径: `/license`、`/login`、`/static`、`/api/menu` 等
- 授权状态: `active`(有效) / `expired`(过期) / `invalid`(无效/未授权) / `locked`(时钟异常)
- 非 active 状态返回 `403 {detail, license_status}`，前端 request.js 拦截 403+license_status 自动跳授权页

### 14.5 离线签发工具

`tools/generate_license.py` 使用 `tools/private_key.pem`（离线保管，已 gitignore）签发许可证：
```
python tools/generate_license.py --customer "XX公司" --edition 企业版 \
  --expire 2027-12-31 --fingerprint <机器指纹> --max-nodes 100 \
  --features "aiops,sre,chaos" --output license.lic
```
客户在「授权管理」页上传 `.lic` 文件激活。公钥硬编码于 `license_service.py`，私钥绝不随产品分发。

### 14.6 商业化分发流程

1. 售前：客户提供机器指纹（授权页「复制指纹」或 `GET /license/api/fingerprint`）
2. 签发：用私钥 + 客户指纹 + 期限生成 `.lic`
3. 交付：随产品分发 `.lic`，客户上传激活
4. 到期：API 返回 403，平台锁定，引导续期
5. 防破解：私钥不外泄 → 无法伪造；指纹绑定 → 无法拷贝；时钟防回拨 → 无法改时间

---

*最后更新: 2026-07-06*
