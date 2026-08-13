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

### 1. 拓扑/连线图（TopologyView + FireMapView）★ 专项

对标 Ongrid 的 **Topology(拓扑/连线图)**，改造了**两个页面**，各承担不同视角：

| 页面 | 菜单入口 | 定位 |
|------|---------|------|
| **架构巡检图** `FireMapView.vue` | 值班驾驶舱 → 监控总览 → 架构巡检图 (`/firemap`) | 全局/业务域视角，健康驾驶舱 + 分层架构 + 服务调用连线 |
| **拓扑视图** `TopologyView.vue` | 资源管理 → 资产管理 → 拓扑视图 (`/topology`) | 三类拓扑(资产/网络/服务调用) 独立页，含自动刷新 |

**服务调用拓扑** 核心：`topology_service.build_service_call_topo(db, hours=168, min_calls=1)`(约 line 299)——按 `trace_id+parent_span_id` 还原跨服务调用、只统计跨服务调用、过滤最小调用量，返回 `{nodes, edges, stats}`。两个页面共用同一后端。

#### 3.1.1 架构巡检图 FireMapView（值班视角）
- 定位：「架构巡检图 · 全域 Entity 健康驾驶舱」，两种模式(overview 全域 / domain 业务域下钻)。
- **服务调用拓扑面板**：进入业务域(domain)后，分层架构卡下方「架构拓扑 · 分层实体 · 调用连线 · 自动排版」面板，数据 `GET /topology/api/service-calls?hours=168&min_calls=1`。
- 分层配色：接入层/服务调用层/应用层/数据库/中间件/基础设施；节点圆角卡片按层着色。
- 边：宽度固定 2，**颜色按错误率** ≥30% 红 / ≥5% 橙 / 否则灰(`#94a3b8`)。
- **操作**：值班驾驶舱 → 架构巡检图 → 点业务域下钻 → 看分层架构卡 + 下方服务调用连线面板；按颜色读健康(绿<5%/黄5~30%/红≥30%)。

#### 3.1.2 拓扑视图 TopologyView（三类拓扑独立页）
页面标题「拓扑视图」，共 **3 个 Tab** + 每 Tab「自动刷新」。

- **Tab1 资产拓扑**：`GET /topology/api/asset-by-node`(K8s 子资源过滤，cluster+node 维度)。
  - 操作：类型下拉 + 名称搜索 + 「仅异常」过滤；「+ 新增关系」`POST /topology/api/relations/create` / 删除 `POST /topology/api/relations/{id}/delete`；「刷新」/「自动刷新」。
  - 单击节点 → 右侧「关联资产 (N)」为**单跳直接邻居**（非多跳影响面）。
- **Tab2 网络拓扑**：`GET /topology/api/network?mode=...`。
  - 两模式：「📡 网络设备关系」(只显示网络设备及其关系) / 「🗂️ IP 网段拓扑」(按 /24 聚类)。
- **Tab3 服务调用拓扑**（改造核心）：`GET /topology/api/service-calls?hours=&min_calls=1`。
  - 时间范围：**1h / 6h / 24h / 7d / 全部**(默认 24h)。
  - 节点着色 `svcNodeColor`(817)：`critical→#ef4444` / `warning→#E6A23C` / 健康→`#67C23A`；阈值=错误率 <5% / 5~30% / ≥30%。
  - 边：**宽度=调用量**(`1+(call_count/maxCalls)*5`)，**颜色=错误率**；选中边变 `#6366f1`。
- **自动刷新**：复选框开启后**每 30 秒**刷新当前 Tab(`autoRefresh` ref，30000ms)。

#### 3.1.3 后端端点清单（拓扑）
| 方法 | 路径 | 说明 |
|------|------|------|
| GET | `/topology/api/list` | 通用资产树/关系 |
| GET | `/topology/api/asset-by-node` | Tab1 资产拓扑 |
| GET | `/topology/api/network?mode=` | Tab2 网络拓扑(devices/subnets) |
| GET | `/topology/api/service-calls?hours=&min_calls=` | Tab3 服务调用拓扑 |
| POST | `/topology/api/relations/create` | 新增关系 |
| POST | `/topology/api/relations/{id}/delete` | 删除关系 |
| POST | `/topology/api/path/find` | 单条 BFS 最短连通路径(body: source_id, target_id) |
| GET | `/containers/topology/graph` | K8s 资源拓扑(相关) |

#### 3.1.4 拓扑验证/通过标准
- [ ] 架构巡检图进入业务域后显示服务调用连线面板，节点按层着色、边按错误率着色
- [ ] 拓扑视图三 Tab 可切换；Tab3 服务调用按时间窗口(1h~全部)刷新
- [ ] 调用量大 → 边宽，错误率高 → 边红/橙；选中边高亮
- [ ] 自动刷新勾选后每 30s 更新
- [ ] 资产拓扑支持新增/删除关系、类型/搜索/仅异常过滤
- [ ] 网络拓扑支持「设备关系 / IP 网段」两模式
- [ ] `/topology/api/service-calls` 返回 `{nodes,edges,stats}`，空时返回空结构不报错

#### 3.1.5 拓扑已知缺口（待补，勿写成已有）
- **Blast Radius(爆炸半径/N 跳影响面)** **未实现**（计划 T2，❌）：后端无 `expand`/N 跳 BFS；仅 `topology_path.py:bfs_path` 做两个节点间单条最短路径；前端「关联资产」为单跳直接邻居。
- **`topology-path` 页面**(`TopologyPathView.vue`)已注册但**无菜单入口**(孤儿页，可通过 `window._navigateTo('topology-path')` 触达)。

### 2. 告警规则页 AlertRulesView（规则类型化）
- **新增**：「规则类型」下拉(metric_raw/anomaly/forecast/burn_rate) + 表格「类型」列。
- 操作：新建/编辑规则时选类型；anomaly 用均值±z·σ、forecast 用线性外推、burn_rate 用错误预算消耗速率。

### 3. 其它既有页面
- 对 `SubAgentsView`(独立 persona 子代理)、`AgentWorkflowEditor`(notify/agent 节点)、`IncidentsView`(自动调查报告)、`ReportsView`、`AssetsView`、`K8sOfflineDeployView` 等做了能力增强，非新增页，详见对应 MEMORY 条目。

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
- 手动测试步骤：见 `docs/20260813_新功能测试手动操作手册.md`(各功能节)；拓扑操作见本文档「三、1 拓扑」。

---

## 相关文档索引
- 改造状态/缺口：`docs/20260813_系统赶超Ongrid差距分析与赶超计划.md`
- 手动测试手册：`docs/20260813_新功能测试手动操作手册.md`
- 开发记忆：`MEMORY.md`
- 字段契约：`CONTRACT.md`
