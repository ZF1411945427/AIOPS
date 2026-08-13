# Ongrid 改造 · 新增功能页与操作总览

> 记录时间：2026-08-14
> 依据：`docs/20260813_系统赶超Ongrid差距分析与赶超计划.md` 与 `MEMORY.md`（2026-08-13~14 改造批次）
> 本文档是「所有 **Ongrid 改造**新增的功能页、已有页增强、后端模块/API、以及对应操作」的 **Single Source of Truth(操作侧)**。
> 字段契约见 `CONTRACT.md`，改造状态见赶超计划文档。

---

## 一、改造批次与范围

对标 Ongrid（`docs/20260720_竞品对比_Ongrid差距分析与优化方向.md`），本系统 2026-08-13~14 完成以下改造：

| 系列 | 内容 | 状态 |
|------|------|------|
| **A** | Agent 内核加固：工具装饰器横切链(A2)/独立子代理(A3)/LLM reviewer 写操作审查门(A4) | ✅ |
| **B** | 工作流自动触发 + 并行 fan-out(B1/B2/B4) + cron 调度(B3) + notify/agent 节点(B5) | ✅ |
| **C** | 告警自动调查闭环(incident-investigator + 结构化报告 + 回写)(C1/C2/C3) | ✅ |
| **F1/F2** | SKILL.md 技能库 + 技能市场 Marketplace | ✅ |
| **F3** | Secrets Vault 凭据保险库 | ✅ |
| **F5** | K8s 多集群 data plane + Edge 升级协作器 | ✅ |
| **F6** | 网络设备管理(SNMP 校验/轮询/邻居发现/链路映射) | ✅ |
| **Topology** | 服务调用拓扑(架构巡检图新增连线图 + 拓扑视图 Tab3) | ✅ |
| **G1/P2-1** | 告警规则类型化(metric_raw/anomaly/forecast/burn_rate) | ✅ |
| **P1-5** | 外部 MCP 服务器连接 | ✅ |
| **P2-5** | 代码/git 知识库 + 代码搜索 | ✅ |
| **P2-3** | 命令策略沙箱 cmdpolicy 接线 | ✅ |
| **P3-2** | log_rca / idice 算法实装 | ✅ |
| **D2** | Prometheus `/metrics` 自监控端点 | ✅ |
| **D3** | 结构化日志 + trace_id 全链路 | ✅ |
| **G2** | 本地向量嵌入(确认已本地 BGE，离线可用) | ✅ |
| **E1/E2/E4** | Casbin RBAC + 多租户隔离 | ⏸ 暂缓(未做) |

> 注：具体缺口状态与评分见 `docs/20260813_系统赶超Ongrid差距分析与赶超计划.md`。

---

## 二、新增功能页（菜单入口 + 操作）

以下均为本次改造在 `系统配置 → 系统管理` 下新增的独立页面。

### 1. 凭据保险库（secret-vault / `/secret-vault`）
- **作用**：集中加密存储连接凭据(密码/Token/API Key/私钥)，数据库只存 Fernet 密文；连接配置只存 `{{secret:name}}` 引用，运行时自动解密注入。
- **操作**：
  1. 新建凭据：填引用名/类型(密码/Token/API Key/私钥/自定义)/作用域/描述/值。
  2. 列表值列只显示 `••••••••`；重名创建被拦截。
  3. 编辑留空值=不更新原值。
  4. 「🧪 引用解析测试」验证 `{{secret:name}}` 替换；「📎 数据源引用一览」看引用是否有效/失效。
  5. DataSource(SSH/K8s)敏感字段可直接填 `{{secret:name}}`，测试连接时自动解析。

### 2. 技能库（skills / `/skills`）
- **作用**：SKILL.md 可执行技能注册表；Agent 通过 `list_skills`/`use_skill` 调用，全流程审计。
- **操作**：查看/启用/禁用内置技能(如 `log-troubleshooter`)、新建/编辑技能(SKILL.md frontmatter + 指令正文)、▶️ 手动执行、⬇️ 导出 zip、⬆️ 导入 zip、查看「执行审计」记录。

### 3. 技能市场（skill-market / `/skill-market`）
- **作用**：技能 zip 打包私服分发(marketplace/packages)。
- **操作**：把技能「发布到市场」→ 市场卡片出现为包 → 其它节点「⬇️ 安装」→ 「🗑️ 删除包」。

### 4. 多集群管理（multicluster / `/multicluster`）
- **作用**：把多个 K8s DataSource 聚合成命名集群，controller/node 双角色，每集群独立 telemetry 通道。
- **操作**：「+ 注册集群」填集群名/角色/关联 DataSource/数据面状态/遥测通道；✅ 检查数据面；👁️ 查看该集群独立遥测(事件+资产分类)。

### 5. Edge 升级（upgrade-jobs / `/upgrade-jobs`）
- **作用**：edge 代理批量升级任务协调器(状态机/批次/verify/回滚，持久化)。
- **操作**：「+ 新建升级任务」填目标版本/关联集群/策略(batch|all_at_once)/每批数量 → ▶️ 执行 → 看进度与步骤/日志；失败自动回滚批次。

### 6. 网络设备（network-devices / `/network-devices`）
- **作用**：交换机/路由器/防火墙等网络设备 SNMP 纳管(校验/接口轮询/邻居发现/主机-端口链路映射)。
- **操作**：「+ 添加设备」填 name/IP/类型/SNMP 版本/community/端口 → 🔍 连通校验 → 📊 接口轮询 → 🕸️ 邻居发现 → 👁️ 详情 → 「🔗 主机链路映射」反查主机接入的交换机端口。

---

## 三、已有页面增强（改造）

### 1. 拓扑视图 TopologyView + 架构巡检图 FireMapView（服务调用拓扑）
- **新增**：`TopologyView.vue` Tab3「服务调用拓扑」(时间窗口 1h/6h/24h/7d/全部，节点健康着色 `<5%/5~30%/≥30%`，边宽=调用量、边色=错误率) + 「自动刷新」(30s)。
- **新增**：`FireMapView.vue` 业务域下钻「架构拓扑 · 分层实体 · 调用连线」面板(分层着色)。
- 详见 `docs/Topology拓扑改造功能页与操作手册.md`。

### 2. 告警规则页 AlertRulesView（规则类型化）
- **新增**：「规则类型」下拉(metric_raw/anomaly/forecast/burn_rate) + 表格「类型」列。
- 操作：新建/编辑规则时选类型；anomaly 用均值±z·σ、forecast 用线性外推、burn_rate 用错误预算消耗速率。

### 3. Slack 等既有页面
- 本次对 `SubAgentsView`(独立 persona 子代理)、`AgentWorkflowEditor`(notify/agent 节点)、`IncidentsView`(自动调查报告)、`ReportsView`、`AssetsView`、`K8sOfflineDeployView` 等做了能力增强，非新增页，详见对应 MEMORY 条目。

---

## 四、新增后端模块 / API（无页面，供调用/Agent）

| 模块 | 作用 | 主要 API |
|------|------|---------|
| `services/secret_vault.py` | 凭据加密 CRUD | `/api/vault/*` |
| `services/skill_registry.py` | 技能注册表/审计/打包 | `/api/skills/*`、`/api/marketplace/*` |
| `services/multicluster_service.py` | 多集群注册表/遥测 | `/api/k8s-clusters/*` |
| `services/upgrade_service.py` | 升级任务状态机 | `/api/upgrade-jobs/*` |
| `services/snmp_client.py` + `network_service.py` | SNMP 客户端 + 设备管理 | `/api/network/*` |
| `services/mcp_external.py` | 外部 MCP(JSON-RPC) 客户端 | `/api/mcp/*` |
| `services/git_knowledge_service.py` | git 克隆/索引/代码搜索 | `/api/git-knowledge/*` |
| `services/rca_algos_service.py` | log_rca / idice 实装 | `/log-rca/analyze/{id}`、`/idice/attribute/{id}` |
| `services/auto_investigator.py` | 告警自动调查 worker | `/incidents/api/reports/investigation` |
| `services/reviewer_agent.py` | LLM 写操作审查门 | 内部 |
| `services/tool_registry.py` | 工具装饰器横切链 | 内部 |
| `services/workflow_cron_scheduler.py` | 工作流 cron 调度 | 内部 |
| `services/mcp_tools.py` | 新增 `list_skills`/`use_skill`/`search_code` 等 MCP 工具 | 内部 |
| `main.py /metrics` | Prometheus 自监控 | `GET /metrics` |
| `logger.py` | trace_id 全链路 + JSON 模式 | 内部 |

---

## 五、验证入口

- 后端：`python run.py`(FastAPI :8000)，重启请按**:8000 端口 listener 杀进程**再 Start-Process(否则新代码不生效，新路由返回 SPA HTML 即为旧进程残留)。
- 前端：`npm run build --prefix frontend` 后在 `http://localhost:3000`(dev) 或 `http://localhost:8000`(SPA) 访问。
- 自监控：`GET /healthz`、`GET /readyz`、`GET /metrics`(Prometheus text)。
- 手动测试步骤：见 `docs/20260813_新功能测试手动操作手册.md`(各功能节) + `docs/Topology拓扑改造功能页与操作手册.md`。

---

## 相关文档索引
- 改造状态/缺口：`docs/20260813_系统赶超Ongrid差距分析与赶超计划.md`
- 手动测试手册：`docs/20260813_新功能测试手动操作手册.md`
- 拓扑专项手册：`docs/Topology拓扑改造功能页与操作手册.md`
- 开发记忆：`MEMORY.md`
- 字段契约：`CONTRACT.md`
