<div align="center">

**监控 · 告警 · 根因分析 · 自动化运维 · AI Agent · 值班 · SRE**

<h1>
  <img src="https://img.shields.io/badge/AIOps-智能运维平台-6366f1?style=for-the-badge&logo=&labelColor=1a1a2e" alt="AIOps"/>
</h1>

*从碎片化救火→一站式智能运维*

<br/>

<a href="https://github.com/ZF1411945427/AIOPS/stargazers"><img src="https://img.shields.io/github/stars/ZF1411945427/AIOPS?style=flat-square&logo=github&color=6366f1" alt="Stars"/></a>
<a href="https://github.com/ZF1411945427/AIOPS/network"><img src="https://img.shields.io/github/forks/ZF1411945427/AIOPS?style=flat-square&logo=github&color=10b981" alt="Forks"/></a>
<a href="LICENSE"><img src="https://img.shields.io/badge/License-Apache%202.0-blue?style=flat-square" alt="License"/></a>
<img src="https://img.shields.io/badge/Python-3.13+-3776AB?style=flat-square&logo=python&logoColor=white" alt="Python"/>
<img src="https://img.shields.io/badge/Vue-3-4FC08D?style=flat-square&logo=vue.js&logoColor=white" alt="Vue"/>
<img src="https://img.shields.io/badge/FastAPI-0.115-009688?style=flat-square&logo=fastapi&logoColor=white" alt="FastAPI"/>
<img src="https://img.shields.io/badge/81%20Routes-ff6b6b?style=flat-square" alt="Routes"/>
<img src="https://img.shields.io/badge/147%20E2E%20Tests-f59e0b?style=flat-square" alt="Tests"/>
<img src="https://img.shields.io/badge/3%20端-4FC08D?style=flat-square" alt="3 Clients"/>

<br/>

**⭐ 觉得有用？点个 Star 支持一下 →**

</div>

---

<div align="center">

### SRE 团队的日常是这样吗？

</div>

| 😫 痛点 | ✅ AIOps 解法 |
|---------|--------------|
| 日志、指标、告警、K8s 散落在 N 个系统 | **一个平台**收敛可观测性全栈数据 |
| 故障排查靠经验翻文档 | **AI Agent** 自然语言对话排障 + 6 种根因算法 |
| 告警轰炸，真假难辨 | **风暴检测 + 自动归并**，降噪 90% |
| 发现问题→手动修复→值班被叫醒 | **自愈规则 + Runbook**，告警触发自动修复 |
| 团队忙却难量化 | **SLO / Error Budget / 值班表**，SRE 完整闭环 |

> **一条链路走完运维全流程：** `📊 可观测性 → 🚨 告警 → 🧠 AI 分析 → ⚡ 自动化 → 📈 SRE 度量`

---

## ✨ 核心亮点

<table>
<tr>
<td width="50%" valign="top">

### 🖥️ 可观测性 — 360° 证据链

| 模块 | 能力 |
|------|------|
| **仪表盘** | 可配置 Dashboard，多图表组件，7×24 健康总览 |
| **指标监控** | 21 个系统指标 SSH 采集，趋势预测，异常检测 |
| **日志管理** | 日志采集，异常检测，日志聚类根因分析 |
| **链路追踪** | OTLP 接收，Jaeger 兼容，Java/Python/Go/Node/K8s 接入 |
| **拓扑发现** | 服务依赖拓扑，K8s 资源树，Service Mesh |

</td>
<td width="50%" valign="top">

### 🚨 告警与事件 — 全生命周期闭环

| 模块 | 能力 |
|------|------|
| **告警管理** | 规则配置，抑制静默，级别路由 |
| **告警聚合** | 风暴检测，自动归并，降噪 |
| **告警控制台** | 实时看板，确认/处理/关闭 |
| **事件中心** | 集群事件统计，异常事件检测，事件源配置 |
| **Webhook** | 外部系统对接，自定义回调 |

</td>
</tr>
<tr>
<td width="50%" valign="top">

### 🔍 根因分析 — 6 种算法引擎

| 算法 | 类型 | 适用场景 |
|------|------|----------|
| **PageRank** | 拓扑排序 | 从故障传播链定位关键节点 |
| **Granger** | 因果检验 | 指标间因果关系判定 |
| **DTW** | 时序相似度 | 指标曲线形态匹配 |
| **LogClu** | 日志聚类 | 日志异常模式发现 |
| **IDCE** | 异常子图 | 拓扑异常子图检测 |
| **PCADr** | 维度规约 | 高维指标降维归因 |

</td>
<td width="50%" valign="top">

### 🤖 自动化运维 — 从检测到修复

| 模块 | 能力 |
|------|------|
| **自愈规则** | 告警触发自动修复，条件+动作编排 |
| **Runbook** | 运维手册模板，步骤化排障指引 |
| **远程脚本** | SSH 批量命令执行，脚本模板管理 |
| **变更审批** | 蓝绿发布，变更工作流，审批链 |
| **通知管理** | 多渠道通知（短信/邮件/电话/Webhook） |

</td>
</tr>
<tr>
<td width="50%" valign="top">

### 📊 SRE 可靠性工程 — 完整实践闭环

| 模块 | 能力 |
|------|------|
| **错误预算** | SLO→Error Budget 映射，健康/警告/严重状态 |
| **预算消耗** | 1h/6h/24h 多窗口 Burn Rate 预警 |
| **SLO 配置** | 服务级目标管理，窗口期可配置 |
| **SLA 协议** | 达成率计算，处罚规则，运行/停机统计 |
| **值班表** | 周/月轮值排班，当前值班状态看板 |
| **升级策略** | 多级别升级，等待时间，通知渠道联动 |
| **可用性报表** | 一键生成，健康度汇总，历史趋势追踪 |

</td>
<td width="50%" valign="top">

### 💬 AI Agent — 自然语言驱动

| 能力 | 说明 |
|------|------|
| **对话排障** | 自然语言查询系统状态，多轮上下文 |
| **工具调用** | MCP 工具动态注册与编排 |
| **Skill 约束** | 输出格式标准化，行为可控 |
| **多模型** | OpenAI、Anthropic、MiniMax 等适配 |

</td>
</tr>
</table>

---

## 🏗️ 产品架构

```
┌──────────────────────────────────────────────────────────────────────┐
│                          用户体验层                                    │
│     🖥️ Vue 3 SPA     📄 Jinja2 传统页面     💬 AI 对话助手           │
├──────────────────────────────────────────────────────────────────────┤
│                            能力域                                      │
│  ┌──────────┐ ┌──────────┐ ┌──────────┐ ┌──────────┐ ┌──────────┐  │
│  │ 🔍 可观测 │ │ 🚨 告警  │ │ 🧠 根因   │ │ ⚡ 自动化 │ │ 📊 SRE  │  │
│  │ 指标/日志 │ │ 规则/静默 │ │ PageRank │ │ Remed.   │ │错误预算  │  │
│  │ Trace/拓扑│ │ 聚合/风暴 │ │ Granger  │ │ Runbook  │ │SLA/SLO  │  │
│  │ 接入指引  │ │ Webhook  │ │ DTW/IDCE │ │ 脚本执行 │ │值班升级  │  │
│  └──────────┘ └──────────┘ └──────────┘ └──────────┘ └──────────┘  │
├──────────────────────────────────────────────────────────────────────┤
│                          AI Agent 层                                   │
│     🤖 对话排障    📦 MCP 工具调用    🎯 Skill 约束    🧩 多模型适配  │
├──────────────────────────────────────────────────────────────────────┤
│                            数据层                                      │
│  📦 SQLite    🔍 Elasticsearch    ☸️ K8s API    🔑 SSH    📈 Prometheus │
└──────────────────────────────────────────────────────────────────────┘
```

---

## 🛠️ 技术栈

<div>
<img src="https://img.shields.io/badge/Python%203.13-3776AB?style=flat-square&logo=python&logoColor=white"/>
<img src="https://img.shields.io/badge/FastAPI-009688?style=flat-square&logo=fastapi&logoColor=white"/>
<img src="https://img.shields.io/badge/SQLAlchemy-D71F00?style=flat-square&logo=sqlalchemy&logoColor=white"/>
<img src="https://img.shields.io/badge/Vue%203-4FC08D?style=flat-square&logo=vue.js&logoColor=white"/>
<img src="https://img.shields.io/badge/Vite-646CFF?style=flat-square&logo=vite&logoColor=white"/>
<img src="https://img.shields.io/badge/Element%20Plus-409EFF?style=flat-square&logo=element&logoColor=white"/>
<img src="https://img.shields.io/badge/ECharts-AA344D?style=flat-square&logo=apacheecharts&logoColor=white"/>
<img src="https://img.shields.io/badge/SQLite-003B57?style=flat-square&logo=sqlite&logoColor=white"/>
<img src="https://img.shields.io/badge/Docker-2496ED?style=flat-square&logo=docker&logoColor=white"/>
<img src="https://img.shields.io/badge/Kubernetes-326CE5?style=flat-square&logo=kubernetes&logoColor=white"/>
<img src="https://img.shields.io/badge/Elasticsearch-005571?style=flat-square&logo=elasticsearch&logoColor=white"/>
</div>

---

## 🚀 快速开始

```bash
# 1️⃣ 克隆项目
git clone https://github.com/ZF1411945427/AIOPS.git
cd AIOPS

# 2️⃣ 安装后端依赖 & 启动 (端口 8000)
pip install -r requirements.txt
python run.py

# 3️⃣ 新终端 — 启动前端 (端口 3000)
cd frontend && npm install && npm run dev
```

> 🔐 **默认账号**：`admin` / `admin123`
>
> 🖥️ Vue SPA → http://localhost:3000 &nbsp;|&nbsp; 📄 Jinja2 → http://localhost:8000 &nbsp;|&nbsp; 📱 Mobile H5 → http://localhost:8000/mobile-app

```bash
# 4️⃣ 新终端 — 启动移动端 H5（UniApp，端口 8000，由 FastAPI 托管）
cd mobile && npm install && npm run build:h5
```
> 移动端构建产物由 FastAPI 的 `/mobile-app` 路由托管，无需单独启动 dev server。

### 🗄️ 双数据库模式

顶栏按钮一键切换，互不影响：

| 数据库 | 场景 | 内容 |
|--------|------|------|
| `db/aiops.db` | 🎮 Demo 展示 | 内置预设演示数据 |
| `db/aiops_real.db` | 🔬 真实测试 | 空库，无残留模拟数据 |

---

## 📁 项目结构

```
AIOPS/
├── app/                           # FastAPI 后端 (81 路由 + 28 服务)
│   ├── main.py                    # 应用入口 & 中间件
│   ├── models.py                  # ORM 模型 (~30 张表)
│   ├── routers/                   # 路由模块
│   │   ├── sre.py                 # SLO / Error Budget / SLA / 值班 / 升级
│   │   ├── agent_chat.py          # AI Agent 对话
│   │   ├── pagerank_rca.py        # PageRank 根因分析
│   │   ├── trace_ingest.py        # OTLP/Jaeger 链路接收
│   │   ├── k8s_resources.py       # K8s 资源管理
│   │   └── ... (76 more)
│   ├── services/                  # 业务逻辑层
│   ├── templates/                 # 117 个 Jinja2 模板
│   ├── static/                    # 静态资源
│   └── seed_data.py               # Demo 种子数据
├── frontend/                      # Vue 3 + Vite (桌面 SPA)
│   ├── src/views/                 # 14+ 页面视图
│   ├── src/layout/                # 主布局 (悬浮药丸侧边栏)
│   ├── src/stores/                # Pinia 状态管理
│   └── dist/                      # 构建产物
├── mobile/                        # UniApp + Vue3 (移动端 H5)
│   ├── src/pages/                 # 17 个移动端页面
│   ├── src/api/                   # API 适配层 (token 登录 + Axios)
│   ├── src/components/            # 通用组件 (ChatBubble 等)
│   ├── src/static/                # Tab 图标等静态资源
│   └── dist/build/h5/             # 移动端构建产物
├── tools/                         # 运维工具
│   └── deploy.py                  # 一键部署 (all/backend/frontend/mobile)
├── db/                            # SQLite 数据库 (demo + real)
├── tests/
│   └── e2e/                       # Playwright E2E 测试 (147 用例)
├── 功能测试/                       # 功能测试文档 & 脚本
├── sxdevops-其他人的项目，用来借鉴的/  # 参考项目
├── requirements.txt               # Python 依赖
├── run.py                         # 后端启动入口
└── README.md                      # 你正在看的这个文件 😄
```

---

## 📐 部署架构

```
┌──────────────────────────────────────────────────┐
│                    浏览器                         │
│  :3000 Vue SPA  │  :8000 Jinja2  │  /mobile-app  │
└────────────────────────┬─────────────────────────┘
                         │
┌────────────────────────▼─────────────────────────┐
│              FastAPI + Uvicorn                     │
│    AuthMiddleware · SessionMiddleware               │
│    DEMO/REAL 双数据库自动切换                       │
│    /assets/ 自动合并 mobile + frontend 构建产物     │
└────┬──────────┬──────────┬───────────────────────┘
     │          │          │
┌────▼───┐ ┌───▼────┐ ┌──▼────────────┐
│ SQLite │ │   ES   │ │  SSH/K8s      │
│ (WAL)  │ │ :9200  │ │  Agent        │
└────────┘ └────────┘ └───────────────┘

> **移动端 H5**：UniApp 构建 → FastAPI `/mobile-app` 路由托管
> `/assets/` 路径同时查找 mobile 和 frontend 构建产物（`_MultiStaticFiles` 多目录回退）
```

---

## 🚢 一键部署

使用 `tools/deploy.py` 将任意组件部署到远程服务器：

```bash
# 查看帮助
python tools/deploy.py --help

# 部署全部（自动备份 + 上传 + 重启）
python tools/deploy.py all

# 单独部署组件
python tools/deploy.py backend    # 仅后端 Python 代码
python tools/deploy.py frontend   # 仅 Vue SPA 构建产物
python tools/deploy.py mobile     # 仅 UniApp H5 构建产物
```

> 部署脚本支持：远程 SSH 连接、自动备份 `tar.gz`、`setsid` 重启（防 PTY 断开后进程退出）、端口释放检测。

---

## 🎯 适用场景

| 场景 | 一句话 |
|------|--------|
| 👨‍💻 **SRE 值班** | 一个页面看清所有服务健康度，告警实时推送，点击即 AI 分析 |
| 🔍 **故障排查** | 输入 "看看 orders 服务最近怎么了"，AI Agent 自动查指标+日志+拓扑 |
| 📊 **团队度量** | SLO 仪表盘、Error Budget 消耗、值班表、可用性报表一键生成 |
| ⚡ **日常运维** | SSH 批量执行脚本、K8s 资源管理、自愈规则编排，全在浏览器完成 |
| 📱 **手机巡检** | UniApp 移动端 H5，扫码识别资产、AI 对话、告警确认，随时随地 |
| 🧪 **Demo 演示** | 内置种子数据 + 双数据库一键切换，随时演示 / 真实测试互不影响 |

---

## 📸 系统截图

<table>
  <tr>
    <td><img src="docs/screenshots/login.png" alt="登录页" width="400"/></td>
    <td><img src="docs/screenshots/dashboard.png" alt="仪表盘" width="400"/></td>
  </tr>
  <tr>
    <td align="center">🔐 登录页 — Vue SPA 渲染</td>
    <td align="center">📊 仪表盘 — 全局健康总览</td>
  </tr>
  <tr>
    <td><img src="docs/screenshots/topology.png" alt="拓扑视图" width="400"/></td>
    <td><img src="docs/screenshots/agent.png" alt="AI 智能助手" width="400"/></td>
  </tr>
  <tr>
    <td align="center">🔗 拓扑视图 — 服务依赖关系</td>
    <td align="center">🤖 AI Agent — 自然语言排障</td>
  </tr>
  <tr>
    <td><img src="docs/screenshots/posture.png" alt="系统态势" width="400"/></td>
    <td></td>
  </tr>
  <tr>
    <td align="center">🌡️ 系统态势 — SLO + 热力图</td>
    <td></td>
  </tr>
</table>

---

## 📈 功能覆盖一览

<details>
<summary><b>81 个路由模块全列表（点击展开）</b></summary>

| 分类 | 模块 |
|------|------|
| **认证 & 用户** | `auth` · `users` · `tokens` · `audit` |
| **可观测性** | `dashboard` · `dashboard_config` · `metrics` · `logs` · `log_anomaly` · `log_rca` · `traces` · `traces_api` · `trace_view` · `trace_ingest` · `trace_anomaly` · `trace_rca` · `topology` · `topo_graph` · `topology_path` · `discovery` · `netflow` · `service_mesh` |
| **告警 & 事件** | `alerts` · `alert_console` · `alert_events` · `alert_silence` · `alert_storm` · `alert_webhooks` · `events` · `event_sources` · `correlation` · `hotspot` · `cluster_anomaly` |
| **根因分析** | `pagerank_rca` · `granger` · `dtw` · `idice` · `drain` · `pcadr` |
| **自动化运维** | `remediation` · `remediation_workflow` · `runbooks` · `script_exec` · `blue_green` · `change_workflow` · `lifecycle` |
| **SRE** | `sre` · `system_posture` · `reports` · `report_schedules` |
| **AI Agent** | `agent_chat` · `ai_providers` · `chatops` · `smart_recommend` |
| **资产 & CMDB** | `assets` · `asset_changes` · `ci_models` · `ext_cmdb` · `tags` |
| **容器 & K8s** | `containers` · `k8s_resources` · `k8s_monitor` |
| **数据源 & 集成** | `datasources` · `es_integration` · `kafka_pipeline` · `feature_store` |
| **预测 & 异常** | `predictions` · `predictions_enhanced` · `prediction_models` · `trend_prediction` · `anomaly` |
| **通知** | `notifications` · `notification_templates` |
| **系统** | `system` · `settings` · `menu` · `api_v1` · `knowledge` · `knowledge_graph` |

</details>

---

## 🤝 开源协议

本项目基于 **Apache License 2.0** 开源，欢迎 [⭐ Star](https://github.com/ZF1411945427/AIOPS/stargazers) 与 [🍴 Fork](https://github.com/ZF1411945427/AIOPS/fork)。

<br/>

<div align="center">

**[⬆ 回到顶部](#)**

<sub>Built with ❤️ for SRE and DevOps teams</sub>

</div>
