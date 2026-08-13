# Topology 拓扑改造 · 功能页与操作手册

> 记录时间：2026-08-14
> 依据：2026-08-13「服务调用拓扑(对标 Ongrid Topology)」改造 + 后续优化
> 本手册是「根据 Topology 改造新增/增强的功能页与操作」的 **Single Source of Truth(操作侧)**。
> 目标读者：交付/售前演示人员、运维使用者。字段契约见 `CONTRACT.md`，开发记忆见 `MEMORY.md`。

---

## 一、改造总览

对标 Ongrid 的 **Topology(拓扑/连线图)** 能力，本系统改造了**两个页面**，各承担不同视角：

| 页面 | 菜单入口 | 定位 |
|------|---------|------|
| **架构巡检图** `FireMapView.vue` | 值班驾驶舱 → 监控总览 → 架构巡检图 (`/firemap`) | 全局/业务域视角，健康驾驶舱 + 分层架构 + 服务调用连线 |
| **拓扑视图** `TopologyView.vue` | 资源管理 → 资产管理 → 拓扑视图 (`/topology`) | 三类拓扑(资产/网络/服务调用) 独立页，含自动刷新 |

另外：
- **服务调用拓扑** 新增 `topology_service.build_service_call_topo`(Span 表 trace_id+parent_span_id 聚合跨服务调用边) —— 两个页面共用同一后端。
- **资源拓扑图**(`/containers/topology`，K8s 多维图) 属 K8s 资源域，非本次服务调用改造核心，仅相关。

---

## 二、架构巡检图 FireMapView（值班视角）

### 页面定位
「架构巡检图 · 全域 Entity 健康驾驶舱」。两种模式：
- **overview**：全域概览
- **domain**：进入某业务域后下钻

### 服务调用拓扑面板（改造新增核心）
- **位置**：进入业务域(domain 模式)后，分层架构卡下方的「**架构拓扑 · 分层实体 · 调用连线 · 自动排版**」面板。
- **数据来源**：`GET /topology/api/service-calls?hours=168&min_calls=1`（近 7 天、最小调用量 1）。
- **分层配色**(`LAYER_STYLE`)：接入层 / 服务调用层 / 应用层 / 数据库 / 中间件 / 基础设施。
- **节点**：圆角卡片，按层着色。
- **边**：宽度固定 2，**颜色按错误率** —— 错误率 ≥30% 红、≥5% 橙、否则灰(`#94a3b8`)。
- **图例**：健康/警告/严重/离线 + 调用(低错误/警告/严重)。

### 操作步骤
1. 打开值班驾驶舱 → 架构巡检图。
2. 点击某业务域进入下钻。
3. 查看分层架构卡 + 下方服务调用连线面板（自动排版力导向图）。
4. 依据颜色读健康：绿<5%、黄5~30%、红≥30%（服务调用层同此阈值）。

---

## 三、拓扑视图 TopologyView（三类拓扑独立页）

页面标题「拓扑视图」，共 **3 个 Tab** + 每 Tab 可选「自动刷新」。

### Tab1 资产拓扑
- **数据**：`GET /topology/api/asset-by-node`（K8s 子资源过滤，cluster+node 维度）。
- **操作**：
  - 类型下拉筛选 + 名称搜索 + 「仅异常」过滤。
  - 「+ 新增关系」`POST /topology/api/relations/create`；删除关系 `POST /topology/api/relations/{id}/delete`。
  - 「刷新」/「自动刷新」。
  - **单击节点 → 右侧「关联资产 (N)」**：当前为**单跳直接邻居**(`connectedNodes`)，非多跳影响面。

### Tab2 网络拓扑
- **数据**：`GET /topology/api/network?mode=...`。
- **两种子模式**：
  - 「📡 网络设备关系」：只显示网络设备及其资产关系。
  - 「🗂️ IP 网段拓扑」：按 /24 网段聚类。

### Tab3 服务调用拓扑（改造新增核心）
- **数据**：`GET /topology/api/service-calls?hours=&min_calls=1`。
- **操作**：
  - 时间范围选择：**1h / 6h / 24h / 7d / 全部**(默认 24h)。
  - 「刷新」/「自动刷新」。
- **节点着色**(`svcNodeColor`)：`critical→#ef4444`、`warning→#E6A23C`、健康→`#67C23A`；健康阈值 = 错误率 <5% / 5~30% / ≥30%。
- **边表现**：**宽度 = 调用量**(`1 + (call_count/maxCalls)*5`)，**颜色 = 错误率**(≥30% 红 / ≥5% 橙 / 否则灰)；选中的边变蓝紫 `#6366f1`。

### 自动刷新（改造增强）
- 复选框「自动刷新」；开启后**每 30 秒**自动拉当前 Tab 数据（`autoRefresh` ref，间隔 30000ms）。

---

## 四、后端端点清单

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

> 核心函数：`topology_service.build_service_call_topo(db, hours=168, min_calls=1)`(约 line 299)——按 `trace_id+parent_span_id` 还原跨服务调用、只统计跨服务(`parent.service_name != child.service_name`)、过滤最小调用量、返回 `{nodes, edges, stats}`。

---

## 五、验证与通过标准

- [ ] 架构巡检图进入业务域后显示「服务调用连线」面板，节点按层着色、边按错误率着色
- [ ] 拓扑视图三 Tab 可切换；Tab3 服务调用按时间窗口(1h~全部)刷新
- [ ] 调用量大 → 边宽，错误率高 → 边红/橙；选中边高亮
- [ ] 自动刷新勾选后每 30s 更新
- [ ] 资产拓扑支持新增/删除关系、类型/搜索/仅异常过滤
- [ ] 网络拓扑支持「设备关系 / IP 网段」两模式
- [ ] `/topology/api/service-calls` 返回 `{nodes,edges,stats}`，空时返回空结构不报错

---

## 六、已知缺口（待补，勿写成已有）

- **T2 Blast Radius(爆炸半径/N 跳影响面)** **未实现**（计划标注 ❌ 待补）：
  - 后端无 `expand`/N 跳 BFS 扩散接口；仅 `topology_path.py:bfs_path` 做**两个节点间**单条最短路径。
  - 前端「关联资产」为**单跳**直接邻居，非多跳。
  - 计划中「`service_topo_service` 加 `expand` API」待落地。
- **`topology-path` 页面**(`TopologyPathView.vue`)已注册但**无菜单入口**(孤儿页，可通过 `window._navigateTo('topology-path')` 触达)。

---

## 相关文档索引
- 改造决策/实现细节：`MEMORY.md` → `### 2026-08-13: 服务调用拓扑(对标 Ongrid Topology)实现`
- 对标差距与追赶状态：`docs/20260813_系统赶超Ongrid差距分析与赶超计划.md` → `### F. Topology(拓扑/连线图)专项对比`
- 字段契约：`CONTRACT.md`
- 前端页面：`frontend/src/views/TopologyView.vue`、`frontend/src/views/FireMapView.vue`
- 后端服务/路由：`app/services/topology_service.py`、`app/routers/topology.py`、`app/routers/topology_path.py`
