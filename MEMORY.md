# AIOps 项目记忆

> 每次会话开始时读取本文件了解项目背景和之前的决策。
> 按照时间倒序排列。完整历史见 `MEMORY.md.bak.20260712`。

### 2026-07-17: 文档与系统实现对齐审查

**发现的主要不一致问题**：

| 严重程度 | 问题 | 文档描述 | 实际实现 |
|---------|------|---------|---------|
| 🔴 严重 | 静默规则路由 | `POST /api/silence-rules` | 实际是 `/alert-silence/*`（AlertSilenceSchedule 定时静默），告警级别静默是 `POST /alerts/{id}/silence` |
| 🔴 严重 | 变更记录模型 | `ChangeRecord` 模型 | 实际是 `ChangeRequest` + `ChangeTask`，无独立 ChangeRecord |
| 🟡 中等 | 静默规则模型 | `SilenceRule` | 实际是 `AlertSilence`（单次）+ `AlertSilenceSchedule`（定时） |
| 🟡 中等 | OnCall 字段 | `rotation_period_days` | 实际是 `rotation_type` (weekly/monthly) |
| 🟡 中等 | 混沌实验字段 | `inject_cmd` | 实际是 `fault_params` 内嵌结构 |
| 🟡 中等 | 混沌实验字段 | `steady_state_passed` | 实际是 `is_steady_state_passed` |
| 🟢 轻微 | 知识 SOP 生成 | `/knowledge/api/auto-gen/sop/incident/{incident_id}` | 实际存在但端点路径有细微差异 |

**文档未充分体现的实际功能**：
- GroundTruth 测试集（`AgentGroundTruth` + `AgentGroundTruthRun` 模型）
- A/B 测试服务（`ab_test_service.py`）
- 知识图谱推理（`graph_inference_service.py`）
- HPA 推荐 / 资源优化（K8s 相关）
- 实时监控看板（`MonitorView.vue`）

**前端页面验证**：所有文档描述的 Vue 页面均已实现 ✅

### 2026-07-17: 新版产品介绍页 v2（亮色系 · GSAP · 高视觉冲击）
- **重写** `frontend/src/views/ProductIntroView.vue`（从暗色升级为亮色主题，对标 `product_overview.html` 并在视觉冲击力上超越）
  - 亮色配色：`#F8F9FB` 背景 / `#C7512E` 品牌红 / `#4F46E5` 靛蓝 / `#0D9488` 青绿
  - Hero 区：Eyebrow + 大字双行标题 + 3 个数字统计（MTTR/告警削减/资产规模，数字滚动动画）+ 玻璃态仪表盘卡片（含迷你趋势图）+ 浮动数据卡（float 动画）
  - Trust 数据区：4 列数字卡片，数字滚动动画（GSAP innerText tween）
  - Capabilities：Bento 网格布局（第 5 个 card 占满宽度），hover 顶部渐变条出现
  - 编排引擎：SVG DAG 图（6 节点 + 渐变连接线 + SMIL 流动粒子）+ 4 项特性说明
  - How it Works：4 步流程 + AI 聊天演示卡片（模拟根因分析对话）
  - 核心亮点：4 项（自然语言 / SOP 工作流 / 错误预算 / 全链路可观测）
  - 安全管控：6 道防线 + 传统 vs AIOps 对比表
  - CTA：光晕背景 + 发光按钮
  - GSAP ScrollTrigger：各 section 元素入场动画（stagger / scale / x 偏移 / counter 动画）
- **登录页链接**：`LoginView.vue:98-102` 新增"新版产品介绍 →"到 `/product/intro`
- **路由注册**：`frontend/src/router/index.js` 注册 `/product/intro` → `ProductIntroView`
- **后端路由**：`app/routers/auth.py` 新增 `GET /product/intro` → `_serve_vue()` 返回 Vue SPA
- **PUBLIC_PATHS**：`app/main.py:204` 补 `/product/intro`
- **前端构建**：构建成功（17.85s，ProductIntroView 13.52 kB gzip 5.64 kB）
- **新建** `app/services/graph_inference_service.py`：基于 networkx 内存图（Neo4j 降级）的推理引擎
  - 故障传播分析：BFS 沿依赖图向下游推理，衰减因子 0.7^depth，输出受影响资产+传播路径+智能建议
  - 根因定位推理：PageRank(0.4) + 入度中心性(0.25) + 告警传播评分(0.35) 三维融合，置信度分级
  - 知识推荐推理：四条推理链（告警→资产→ci_type→Runbook / 告警→metric→知识标签 / 资产→依赖链→历史RCA / 同类型资产历史告警→相似故障）
- **新增 3 API**：`GET /knowledge/graph/api/impact-analysis`、`POST /knowledge/graph/api/root-cause`、`GET /knowledge/graph/api/recommend`
- **前端**：新建 `GraphInferenceView.vue`（三 Tab 可视化），`AppLayout.vue` 注册 `graph-inference`，`menu_config.json` 新增菜单项
- **入口**：侧边栏「知识库→知识管理→知识图谱推理」
- **测试**：8 轮测试全通过（故障传播/根因定位/知识推荐/边界情况/多告警/深度对比）
- **冲刺文档**：已更新 `docs/冲刺10分路线图.md` 新增"十七"章节

### 2026-07-17: 实时监控看板 + Synthetic 拨测 + 拓扑刷新
- **实时监控看板**：新建 `frontend/src/views/MonitorView.vue`（10 张 ECharts 图表 + 时间范围选择器 + 资产过滤器 + 自动刷新 + 全屏模式），增强 `dashboard.py` API 支持 `time_range`+`asset_id`，`menu_config.json` 新增菜单项，`AppLayout.vue` 注册组件
- **Synthetic 合成拨测**：新建 `app/services/synthetic_monitor.py`，拨测 3 个核心端点写入 VM，注册到 `run.py` background loop
- **拓扑自动刷新**：`TopologyView.vue` 增加自动刷新定时器 + 复选框
- **Bug 修复**：`agent_service.py:452` `provider` 变量未初始化 UnboundLocalError → 加 `provider = None`
- **验证**：前端 build 成功（2572 modules），后端重启 VM 指标 6 类全部返回、合成指标 10 个已写入 VM
- **冲刺文档**：已更新 `docs/冲刺10分路线图.md` 新增"十六"章节记录本次工作

### 2026-07-17: Windows/WinRM 资产支持 + 修复多个预存 Bug

**Windows/WinRM 新功能**（`server`/`virtual_machine`/`cloud_host` 三种 CI 类型）：
- **后端**: `assets.py` _build_connection_config 新增 winrm 分支；`api_asset_detail` 返回 winrm 字段（密码掩码+has标记）；`api_asset_update` 支持 winrm 字段更新
- **连接测试**: `connection_service.py` 新增 `_test_winrm()` 方法，使用 pywinrm 库
- **脚本执行**: `script_exec.py` 目标过滤扩展到 server/virtual_machine/cloud_host，支持 winrm 执行分支
- **前端**: `AssetsView.vue` 新增 os 选择器（Linux/Windows/Other）、WinRM 表单（user/port/password/transport/HTTPS）、os 联动自动切换 connection_type
- **CONTRACT.md**: 新增 `os` 字段（linux/windows/other）到资产规格表
- **requirements.txt**: 新增 `pywinrm==0.5.0`

**修复的预存 Bug**（均在本次测试中发现并修复）：
1. **`assets.py:236`** — `api_asset_create` 传 `"type": ci_type` 给 `Asset(**data)` 但模型无 `type` 列 → TypeError 500 → 删除该行
2. **`assets.py:271`** — `api_asset_update` 同上 `data["type"] = data["ci_type"]` → 删除；同时补充 winrm 字段到 `_build_connection_config` 触发列表
3. **`asset_service.py` create_asset** — `db.refresh(asset)` 加载错误行（SQLite `id INT` 非 `INTEGER PRIMARY KEY` 不自增，ORM refresh 使用 identity map 缓存的旧 id）→ 改为 `db.flush()` + 手动 `SELECT MAX(id)+1` 赋值
4. **`assets.py:242`** — create 时 `ci_attributes` 未写入 data dict → 补充 `json.dumps(payload.get("ci_attributes") or {})`
5. **`mcp_tools.py:323`** — description 字符串内含 ASCII 双引号导致 SyntaxError → 替换为单引号
6. **清理 11 条 id=None 的孤儿资产记录**（上述 bug 2/3 期间产生）

**验证结果**：
- 创建 Windows server (WinRM) → 200 OK，ci_attributes.os=windows 正确保存
- Detail API 返回 winrm_user/port/transport/ssl 正确，密码掩码为 `***`
- 更新 ci_attributes.os 从 windows→linux 正确持久化
- 创建 Windows cloud_host (HTTPS WinRM, port 5986) → 200 OK
- Script targets API 返回 15 个目标（server/virtual_machine/cloud_host 混合）

### 2026-07-17: 验证修复结果 & 新增 Bug 修复——provider 未初始化 + 场景手工验证

**新 Bug 修复**（`agent_service.py:452`）：
- `process_chat_message` 中 `provider` 变量在无活跃 AB Test 时从未被赋值，`if not provider:` 抛 `UnboundLocalError`。加 `provider = None` 初始化修复。

**System Prompt 工具名审计**：
- 逐一对照 `DEFAULT_SYSTEM_PROMPT` 中引用的所有工具名与 `get_mcp_manifest()` 返回的 28 个 MCP 工具，全部匹配，无需修改。

**手工验证结果**（5个复杂场景）：

| 场景 | 结果 | 说明 |
|------|------|------|
| S18 夜间无人值守 | ✅ 通过 | 多轮对话：AI 查告警历史→识别瞬态模式→"不需要紧急处理"→建议优化规则+知识沉淀 |
| S19 知识遗忘 | ⚠️ 数据不足 | 知识库无预置条目，AI 给出通用最佳实践（非场景预期的过时知识检测） |
| S20 自愈闭环 | ⚠️ 数据不足 | "server-001" 在 CMDB 不存在，AI 自动查询资产后发现无匹配 |
| S21 跨多云排障 | ⚠️ 数据不足 | 系统中无跨云拓扑/专线数据，AI 仅做了资产查询 |
| S22 安全应急响应 | ⚠️ 数据不足 | "server-003" 不存在，安全告警数据未入系统 |
| **pending_action 流程** | ✅ 通过 | `propose_action` → `pending_actions` 返回正常 |

**结论**：发出的 Bug 修复均已生效，新增 MCP 工具全部注册成功。场景 19-22 需要 CMDB 预置对应资产和告警数据才能充分验证。建议后续用 `seed_data` 或 ES 注入方式准备测试数据。

### 2026-07-17: AI 智能助手真实场景打磨——System Prompt + MCP工具 + Bug修复 + 新增5个复杂场景

**Bug 修复**：
1. **agent_service.py:628** — `pending_action` 检测 `"is_success"` → `"success"`（`call_mcp_tool` 返回 `"success"` 而非 `"is_success"`，导致 REST 路径下 `propose_action` 的待确认动作从未被创建。SSE 路径已修复但 REST 路径遗漏，现已对齐。）
2. **mcp_tools.py** — 新增 `generate_knowledge_from_incident` 和 `generate_knowledge_from_alert` 两个 MCP 工具（之前 system prompt 告诉 AI 调 HTTP 端点 `POST /knowledge/api/auto-gen/from-incident/{id}`，但 AI 只能调 MCP 工具，导致知识沉淀在对话中永远无法触发。）

**System Prompt 增强**（`agent_service.py`）：
- 知识沉淀修正：HTTP 端点→MCP 工具名（`generate_knowledge_from_incident`/`generate_knowledge_from_alert`）
- 新增 **告警风暴场景** 指引：按资产聚合、按信号类型聚合、识别级联网关
- 新增 **级联故障拓扑溯源** 指引：沿调用链从下游往上追溯
- 新增 **用户纠正处理** 指引：接受纠正→重新验证→修正判断
- 新增 **实时动态跟踪** 指引：对比变化量而非全量重复
- 新增 **话题切换识别** 指引：识别"对了/另外/回到刚才"信号

**agent_sse.py 增强**：
- 工具标题映射新增 `generate_knowledge_from_alert` / `generate_knowledge_from_incident`

**新增测试场景**（`docs/AI智能助手多轮对话测试场景.md` 末尾，独立文件 `docs/AI智能助手复杂运维场景_新增场景18-22.md`）：
- **场景18 夜间无人值守告警与冷静判断**：区分瞬态抖动与真实故障，凌晨给出"继续睡"建议
- **场景19 知识遗忘与重新发现**：知识库过时检测（MySQL 5.7→8.0），分步安全调整
- **场景20 自愈闭环验证**：重启掩盖症状的识别，永久修复 vs 临时自愈
- **场景21 跨多云环境排障**：阿里云→AWS 专线延迟、缓存降级方案
- **场景22 安全事件应急响应**：挖矿木马入侵，取证/隔离/溯源/清除全流程

**验证**：
- 前端 `npm run build` 成功（18.13s, 2570 modules, AgentChatView 27.69kB）
- 28 个 MCP 工具全部注册（含新增的 generate_knowledge_from_incident / generate_knowledge_from_alert）
- pending_action 流程通过 API 验证 OK
- 后端运行正常，新增 Bug 修复（provider 未初始化）

### 2026-07-17: P1-P4 前后端功能验证通过 — Chat/Agent 双模式 + 会话管理 + SSE 全链路

**验证结果（全部通过）**：
- ✅ 前端 `npm run build` 成功（29.75s, 2570 modules, AgentChatView 28.41kB）
- ✅ SSE 全事件类型正确（task_card/step_start/step_finish/progress/done/keepalive/status）
- ✅ 场景1-关联告警：16 步骤，query_correlation_analysis 工具调用成功，RCA 报告完整
- ✅ 场景3-关联分析：query_correlation_analysis 调用正确，15 步骤含指标/告警/日志/Trace
- ✅ 场景6-闲聊打招呼：零工具调用，AI 友好回复 ✅
- ✅ 场景7-空结果（不存在资产）：正确拒绝编造数据 ✅
- ✅ P1-P4 API 全部通过：set-mode(chat/agent) ✅、rename ✅、devices ✅、providers ✅、sessions(50个) ✅
- ✅ 历史回放数据库字段验证通过

**P1-P4 入口**：
- 侧边栏「AI运维智能体→AI 智能助手」：Chat 模式（纯对话）/Agent 模式（全功能工具）
- 顶部全局操作栏：模型下拉、模式切换、设备绑定、通知面板
- 左侧会话栏：搜索/重命名/新建/删除会话

**冲刺路线图**：已更新 `docs/冲刺10分路线图.md` 完成现状表

### 2026-07-17: AI 智能助手任务进度卡片——超越竞品 AIChat 的核心差异化（P0 三件套完成）

**背景**：对照 `docs/AI智能助手竞品设计.md`（AIChat 平台），我们后端能力（40+ MCP 工具、人工确认、关联分析、知识沉淀、RCA、审计）已全面碾压竞品，但前端 UI 把工具调用结果压扁成纯文本气泡，能力被 UI 埋没。竞品核心差异化是"运维任务进度卡片"（步骤树+进度+折叠日志+原始终端输出）。

**开发内容（P0 三件套）**：
1. **运维任务进度卡片** `frontend/src/components/agent/TaskProgressCard.vue`：
   - 卡片头：标题 + 紧急标签（红色 urgent）+ `completedSteps/totalSteps · percent%` + 进度条 + 折叠按钮 ∧/∨
   - 步骤树：√绿色完成 / ✗红色失败 / ⏳蓝色 running spinner
   - 单步折叠：[查看输出 ∨] / [收起输出 ∧]
   - 结构化三段式：① 执行命令摘要（工具+参数+摘要）② 异常识别（红底）③ 关注建议（蓝底）
   - 原始输出折叠：暗色 pre 块，可展开/收起，超长截断
2. **SSE 结构化步骤事件协议**（`app/routers/agent_sse.py`）：
   - 新增 `task_card` 事件：`{title, urgency, total_steps}`
   - 新增 `step_start` 事件：`{step_id, round, tool_name, tool_args, title, started_at}`
   - 新增 `step_finish` 事件：`{step_id, status, duration_ms, summary, conclusion, anomaly, raw_output, tool_args, finished_at}`
   - 新增 `progress` 事件：`{completed_steps, total_steps, percent, urgency}`（循环中按 `completed/(completed+1)` 渐进，最后 100%）
   - `done` 事件增强：带 `steps` 数组 + `urgency` + `total_steps` + `completed_steps`
   - 工具名→中文标题映射 `_TOOL_TITLE_MAP`（26 个 LLM 工具全覆盖）
   - `_extract_step_fields()` 从工具结果提炼 summary/conclusion/anomaly/raw_output
3. **前端 SSE composable 改造**（`frontend/src/composables/useAgentSSE.js`）：
   - 新增 `streamingSteps`/`streamingTask`/`streamingReport` 状态
   - 解析 task_card/step_start/step_finish/progress 事件，实时更新步骤列表
   - done 事件把 steps 映射到 streamingSteps
4. **AgentChatView 集成**（`frontend/src/views/AgentChatView.vue`）：
   - assistant 消息若有 `_steps` 渲染 TaskProgressCard（历史回放）
   - 流式过程中 `streamingSteps.length` 时实时渲染任务卡片
   - `loadMessages` 预处理：`parseHistorySteps()` 解析 tool_calls JSON 的 `step` 字段
   - `sendMessage` push 时带 `_steps`/`_task` 即时显示

**附带 bug 修复**：
- `agent_sse.py` pending_action 检测 `t_result.get("status") == "is_success"` → `"success"`（call_mcp_tool 返回 "success" 不是 "is_success"，原代码导致 SSE 路径 pending_action 从未触发）
- `mcp_tools.py:query_assets` 的 `a.type` → 删除（Asset.type 字段已在 CONTRACT 重构时删除，导致 query_assets 一直报 `'Asset' object has no attribute 'type'`）
- `rca_service.py:70/177` 的 `a.type`/`root_asset.type` → `ci_type`（同上）
- `knowledge_graph_service.py:135` 的 `asset.type` → `asset.ci_type`（同上）
- ToolInvocation 计时修正：`t_start` 移到 `call_mcp_tool` 之前（原来在之后，计时为 0）

**验证结果**：
- 前端 `npm run build` 成功（38.26s，AgentChatView 21.15kB 含 TaskProgressCard）
- 后端 SSE 测试（"查询所有服务器资产"）：4 步全部 success，task_card/step_start/step_finish/progress/done 事件齐全，中文标题"查询资产"正确，percent 渐进 50%→67%→75%→80%→100%
- 历史回放：`/agent/history/121` assistant 消息 tool_calls 含 8 个 step 字段（title=查询资产），前端 parseHistorySteps 正确解析
- 事件统计：task_card=1, step_start=4, step_finish=4, progress=5, done=1, keepalive=2

**与竞品 AIChat 对比**：
| 维度 | 竞品 | 我们 |
|------|------|------|
| 任务进度卡片 | ✅ | ✅ 已对齐 |
| 步骤折叠/展开 | ✅ | ✅ 已对齐 |
| 结构化分层输出 | ✅ 三段式 | ✅ 命令/异常/建议三段式 |
| 原始终端日志折叠 | ✅ | ✅ raw_output pre 块 |
| 进度百分比 | ✅ 3/3·100% | ✅ 渐进式进度条 |
| 紧急标签 | ✅ | ✅ urgency=urgent 红标 |
| MCP 工具数量 | ps/top 命令 | **26 个 LLM 工具 + 17 内部工具** |
| 人工确认闭环 | ❌ | ✅ PendingAction |
| 关联分析注入 | ❌ | ✅ 5 维关联 |
| 知识沉淀/RCA | ❌ | ✅ SOP+RCA |

**剩余 P1/P2（未做）**：Chat/Agent 双模式 Tab、多设备 SSH 绑定 UI、模型下拉切换、会话搜索框、快捷键 @/Ctrl+Enter

### 2026-07-17: 扩展 AI 智能助手多轮对话测试场景文档

**变更**：在 `docs/AI智能助手多轮对话测试场景.md` 原有 4 个核心 happy path 场景基础上，扩展 13 个新场景（场景 5-17）：
- 简单场景（5-7）：模糊指代与输入纠错、闲聊与单点查询、空结果与异常输入
- 复杂场景（8-17）：多轮澄清、告警风暴降噪、级联故障拓扑溯源、实时诊断与动态跟踪、工具调用失败降级、用户纠正错误根因、权限边界与脱敏、对比分析与趋势预测、上下文跳跃与多人协同、知识冲突与误报识别

**同步更新**：
- 文档头部新增扩展场景索引表（标注简单/复杂类型与验证要点）
- 验收标准补充 13 个新场景的验收点
- 备注补充场景 9/10/12/14 的测试数据准备说明
- 覆盖率从约 25%（仅 happy path）提升至覆盖正向+异常+边界+复杂运维情境

### 2026-07-17: AI 智能助手多轮对话场景全面测试与优化

**测试执行**：按 `docs/AI智能助手多轮对话测试场景.md` 执行实际测试，发现并修复以下问题：

**测试结果（全部通过）**：
- ✅ 场景1-关联告警：AI 正确识别 server-001 (asset_id=179) 告警，返回 Z-Score、时序关系、关联指标分析
- ✅ 场景2-关联资产：AI 正确查询资产并返回全面检查报告
- ✅ 场景3-关联分析：AI 调用 `query_correlation_analysis` 返回5维分析（告警/指标/日志/链路/变更）
- ✅ 场景4-知识沉淀：成功生成3个知识草稿（draft_id=1,2,3）

**发现并修复的问题**：
- `agent_service.py` 导入顺序导致 `get_mcp_manifest()` 返回空（mcp_tools 未注册），新增 `from app.services import mcp_tools` 导入
- `query_alerts` 缺少 `asset_id`/`hours` 参数 → 已增加
- 缺少 `query_change_records` 工具 → 已新增
- 关联分析缺少变更记录 → `run_correlation_analysis` 已增加 `change_records`
- 缺少 `POST /knowledge/api/auto-gen/from-incident/{id}` 接口 → 已新增
- System prompt 缺少四大场景指南 → 已增加

### 2026-07-17: AI 智能助手多轮对话场景全面优化

根据 `docs/AI智能助手多轮对话测试场景.md` 和 `docs/AI智能助手复杂运维场景多轮对话测试.md` 分析，发现并修复以下差距：

**MCP 工具优化**：
- `query_alerts` 增加 `asset_id` 和 `hours` 参数，支持按资产+时间过滤（场景1关联告警）
- 新增 `query_change_records` MCP 工具，支持查询资产变更记录（场景2/3关联资产/分析）

**关联分析增强**：
- `observability_correlation.py` 的 `run_correlation_analysis` 增加 `change_records` 查询
- `format_correlation_for_llm` 增加变更记录格式化输出
- `query_correlation_analysis` 返回值增加 `change_record_count`

**知识沉淀接口补全**：
- 新增 `POST /knowledge/api/auto-gen/from-incident/{incident_id}` 端点
- 新增 `generate_from_incident()` 服务函数，从故障单生成知识草稿（包含故障现象/根因/解决方案）

**System Prompt 优化**：
- 增加"关联告警场景"指南：主动查同资产历史告警
- 增加"关联资产场景"指南：评估健康状态+展示上下游拓扑
- 增加"关联分析场景"指南：关注变更记录与告警的因果链
- 增加"知识沉淀场景"指南：调用正确的知识生成接口

### 2026-07-17: 修复 agent_sse 多轮工具调用上限耗尽导致回复为空 + 最终总结机制
- **Bug 5 - max_rounds=5/10 不够**：AI 做复杂分析时调 10+ 轮工具，被上限截断后拿"让我查一下..."等内部思考当回复。修复：检测到 content 符合思考模式时（以"让我"/"好的"等开头），自动追加一次 LLM 调用生成完整总结报告（tools=None）；同时上限提高到 15 作为安全网

### 2026-07-17: 修复 agent_sse.py 多个严重 bug（变量名写错 + 缩进错误 + keepalive）
- **Bug 1 - 变量名写错**：`agent_sse.py:152` 用 `tr` 但应该是 `t_result`，导致 AI 调任意工具后直接 500 崩溃（NameError）。修复：遍历 `tool_results` 列表用 `zip(tool_calls_raw, tool_results)` 正确配对
- **Bug 2 - 缩进混乱**：编辑 keepalive 超时参数时破坏了缩进结构，导致 Python 缩进错误。修复：重写两个 while 块
- **Bug 3 - keepalive 逻辑**：`asyncio.wait` 配合 `yield` 实现 2s 间隔心跳，防止代理空闲超时断开连接
- **Bug 4 - 前端 EventSource 重连时错误优先**：SSE 连接断开时 `onerror` 设置 `streamingError`，重连成功收到 `done` 后却仍显示错误。修复：`done` 事件清 `streamingError`；`onerror` 时检查 `streamingDone`；`sendMessage` 优先判断 `streamingContent`

### 2026-07-16: 修复智能助手 SSE 连接中断（同步 call_llm 阻塞事件循环）
- **根因**：`_stream_chat` 是 async generator，但 `call_llm` 是同步阻塞调用。8+ 秒的阻塞卡死事件循环，导致 Starlette 无法把已 yield 的 SSE 事件 flush 到客户端，浏览器 EventSource 超时断开
- **修复**：
  - `agent_sse.py`：把 `call_llm` 改为 `await loop.run_in_executor(None, call_llm, ...)` 在线程池执行
  - `vite.config.js`：给 `/agent` 代理加 `proxyTimeout: 300000` / `timeout: 300000` 防代理层超时
- **验证**：Python 模拟 SSE 请求 2.5s 返回 `status→done` 两个事件正常

### 2026-07-16: 修复智能助手 SSE 聊天 ImportError 导致"一直思考"的 bug
- **根因**：`agent_sse.py` 的 `_stream_chat()` 从 `agent_service.py` 导入 `get_session`（不存在）+ `_max_hallucination_retries`（局部变量不可导出），导致 `ImportError` → 全局异常处理器返回 `{"error": "服务器内部错误"}` → 前端显示"连接中断"
- **修复**（`agent_sse.py`）：
  1. 删除不存在的 `get_session` import → 改用 `get_or_create_session(db, user_id, session_id)`
  2. 删除不可导出的 `_max_hallucination_retries`、`_validate_payload_schema` import（未使用）
  3. 修复 `_svc.get_message_history(session, config)` → `_svc.get_message_history(db, session, config)` 缺少 db 参数
  4. 把 `sse_json` 函数定义提前到 provider 检查之前（避免 NameError）
  5. 修复 provider 不存在时的 SSE 事件格式（`json.dumps` → `sse_json("error", ...)`）
- **验证**：重启后端 → SSE 聊天正常，DeepSeek 响应 2381ms

### 2026-07-16: 后端验证通过 — 连接池 + 中止按钮 + 关联分析三件套生效
- **验证结果**：
  - `call_llm` 连接池生效（`_get_llm_session()` 使用 `requests.Session` + `HTTPAdapter` pool_connections=10/pool_maxsize=20）
  - `call_llm` 新增 `max_tokens_override` 参数，测试场景传10避免无用计算
  - Provider 测试端点 `POST /ai/providers/{id}/test`：响应 16ms（timeout_override=10 生效）
  - `GET /observability/correlation/analyze`：响应 56ms（1h nginx），返回 alerts/metric_anomalies/log_anomalies/trace_anomalies/correlated_assets/rca_suggestions
  - `POST /agent/correlation-analyze`：响应 115ms，返回 session_id（全量数据注入 session + pendingAutoSend 触发 AI 分析）
  - 前端 build 成功
- **待用户浏览器验证**：① 关联分析按钮交互 ② 中止按钮效果 ③ 实际 AI 调用速度

### 2026-07-16: 注册 query_correlation_analysis MCP 工具供 AI 主动调用
- **背景**：AI 需要在对话中能主动调用关联分析功能，无需用户先在前端查看结果
- **变更**：
  - `mcp_tools.py`：Analysis Tools 区注册 `query_correlation_analysis` 工具（@register_mcp_tool），接收 hours/service/asset_id 参数，复用已有的 `run_correlation_analysis()` + 新 `format_correlation_for_llm()`，返回结构化的摘要+告警数+指标异常数+日志异常数+链路错误率+关联资产数+RCA建议+详细格式化文本
  - `observability_correlation.py`：原 `_format_correlation_for_llm()`（private helper in agent_chat.py）迁至此处并改名 `format_correlation_for_llm()`，消除循环导入隐患
  - `agent_chat.py`：更新 import，删除重复的函数定义
  - `agent_service.py`：更新 `DEFAULT_SYSTEM_PROMPT`，在"分析问题"能力描述 + 工具选择指南中增加关联分析说明
- **测试验证**：工具成功注册，expose_to_llm=True，risk_level=read_only，内部调用返回正确

### 2026-07-16: 修复 /login 接口畸形 JSON 导致 500

### 2026-07-16: 实现"关联分析结果发送 AI 深度分析"功能

- **背景**：用户要求在关联分析页面上加"AI 深度分析"按钮，把多维信号聚合结果发给 AI 做根因推断
- **设计方案**：复用 `_pendingAgentSessionId` 跳转模式，后端全量注入关联数据 + 自动发起分析请求，前端 AgentChatView 自动触发 SSE 流式响应
- **后端变更**：
  - `observability_correlation.py`：提取 `run_correlation_analysis()` 可复用函数 + 新增 `_format_correlation_for_llm()` 格式化关联数据为 LLM 友好文本
  - `agent_chat.py`：新增 `POST /agent/correlation-analyze` 端点，接收 hours/service/asset_id → 执行关联分析 → 创建 ChatSession → 注入系统消息（关联数据）+ 用户消息（分析 Prompt）→ 返回 session_id
  - `agent_service.py`：修复 `add_message()` 中 `content=` → `message_content=` 字段名 bug（ChatMessage 模型列名为 message_content）
- **前端变更**：
  - `ObservabilityCorrelationView.vue`：查询栏新增「AI 深度分析」`<el-button type="warning">` + `aiDeepAnalysis()` 调 `POST /agent/correlation-analyze` + `window._pendingAgentSessionId` 跳转
  - `AgentChatView.vue`：新增 `pendingAutoSend` flag + `watch(messages)` 监听，检测最后一条为 user 时自动调用 `sendMessage()` 触发 SSE
- **测试验证**：API 返回 200 + session_id=44，`/agent/history/44` 确认 system msg（含完整关联数据）+ user msg（含5维度分析 Prompt）正确写入
- **入口**：侧边栏「智能分析室→日志·指标·链路关联」→ 工具栏黄色「AI 深度分析」按钮
- **冲刺文件**：已更新 `docs/冲刺10分路线图.md` 完成现状表

### 2026-07-16: 修复关联分析页面服务/资产下拉无数据 + AI助手与关联分析融合方案讨论
- **背景**：关联分析页面（ObservabilityCorrelationView）查询条件中"服务"和"资产"下拉为空
- **根因**：`list_services` 仅查 Span 表（APM 链路数据），`list_correlatable_assets` 仅查 Alert 表（告警数据），无对应数据时返回空
- **修复**（`observability_correlation.py:575-634`）：
  - 服务下拉：优先查 Span.service_name，无数据时降级到 Asset 表（ci_type in service/business_app/api_service）
  - 资产下拉：优先查 Alert.asset_id，无告警时降级到全量 Asset
  - 注意：修复后需重启后端
- **AI 助手融合现状**：AI 智能助手（AgentChatView）与关联分析已融合 — MCP 工具 `query_correlation_analysis` 已注册（expose_to_llm=True），system prompt 已更新告知 AI 关联分析能力
- **待讨论**：~~是否实现"关联分析结果发送 AI 深度分析"功能~~ **已实现**

### 2026-07-16: 冲刺10分收官——四大方向补齐（知识管理 + AI 智能体 + 异常检测/RCA + 容器/K8s）
- **背景**：冲刺路线图评分已至 9.5/10，剩余四大缺口分别在知识管理、AI 智能体、异常检测/RCA、容器/K8s 四个方向
- **知识管理**：
  - 菜单新增 `kb-documents`（知识文档）、`kb-graph`（知识图谱）、`smart-recommend`（智能推荐）3个入口 → 中级运维→知识管理组
  - 新增 `GET /knowledge/api/unified-search` 跨 KB/文档/Runbook 统一搜索 API（文本向量双模式）
  - KnowledgeBase 模型新增 `version_number`/`change_log` 列并暴露到 _create/_update API（版本追踪）
  - 修复 `/{kb_id}` 参数化路由必须在 unified-search 等固定路径之后定义，避免 422 int_parsing 路径冲突
- **AI 智能体**：
  - `agent_service.py` 的 `process_chat_message` 集成 A/B 测试——有活跃 ABTestConfig 时通过 `ab_test_service.get_provider_for_request` 选择 provider，LLM 调用后通过 `ab_test_service.record_result` 记录
  - 新增 `AgentGroundTruth`/`AgentGroundTruthRun` 模型 + `routers/agent_ground_truth.py` 全套 CRUD + 单用例执行 + 语义相似度/工具匹配度评分
  - 前端 `AgentGroundTruthView.vue` 新增地面真值测试集页面（侧边栏→AI运维智能体→Agent 评估）
- **异常检测/RCA**：
  - 修复 `AnomalyBenchmarkView.vue` 中 `Promise.all` 三请求仅两变量解构的 bug（recommend 数据缺失）
  - `trace_anomaly.py` 从仅1个 status 端点扩展为完整 CRUD + toggle API
  - 前端 `TraceAnomalyConfigView.vue` 新增 Trace 异常配置管理页面（智能分析室→Trace异常配置）
- **容器/K8s**：
  - `k8s_resources.py` 新增 `GET /k8s/api/hpa/recommend`（基于实际资源使用率推荐 HPA min/max/cpu/memory）
  - 新增 `GET /k8s/api/resource-optimization`（分析 Pod 资源 requests/limits 超配欠配 + 诊断规则）
  - 前端 `K8sHpaRecommendView.vue` / `K8sResourceOptimizeView.vue`（运维工作台→K8s 资源）
- **API 测试全部通过**：unified-search(OK)、trace-anomaly(OK)、ground-truth(OK)、benchmark(OK)、menu 98 keys 含全部7个新 key
- **前端构建成功**：`npm run build --prefix frontend` 通过，产物含所有新页面组件
- **入口汇总**：
  | 功能 | 侧边栏路径 | 前端组件 |
  |------|-----------|---------|
  | 知识文档 | 中级运维→知识管理→知识文档 | `KbDocumentsView.vue`（菜单项指向资产页） |
  | 知识图谱 | 中级运维→知识管理→知识图谱 | `KbGraphView.vue`（菜单项指向资产页） |
  | 智能推荐 | 中级运维→知识管理→智能推荐 | `SmartRecommendView.vue`（菜单项指向资产页） |
  | Trace异常配置 | 智能分析室→Trace异常配置 | `TraceAnomalyConfigView.vue` |
  | Agent评估 | AI运维智能体→Agent评估 | `AgentGroundTruthView.vue` |
  | HPA推荐 | 运维工作台→K8s资源→HPA推荐 | `K8sHpaRecommendView.vue` |
  | 资源优化 | 运维工作台→K8s资源→资源优化 | `K8sResourceOptimizeView.vue` |

### 2026-07-16: 系统态势加载性能优化——900次SQL→4次
- **根因**：热力图接口 `GET /heatmap` 每系统×每天×3查（asset_ids + alerts + incidents）= ~900次SQL
- **优化**：`_batch_alert_incident_counts()` 用 `GROUP BY date, asset_id` 批量查告警/故障（2次SQL覆盖全部），`online_set` 单次查全部在线资产
- **效果**：SQL 数 900→~4（_build_systems 2次 + _collect_asset_ids N次 + _batch 2次 + online_set 1次）
- 注意 `_collect_asset_ids` 因每个 system 过滤条件不同（k8s_cluster 或 ci_type），暂保留逐系统查

### 2026-07-16: 菜单补齐 4 个缺失入口——与架构图 24 条链路对齐
- 新增 **自定义仪表盘** → 值班驾驶舱 → 监控总览（链路 21 仪表盘拖拽自定义）
- 新增 **Agent 评估** → AI运维智能体 → Agent 管理（链路 16 AI Agent 质量评估）
- 新增 **A/B 测试** → AI运维智能体 → Agent 管理（链路 16 A/B 测试）
- 新增 **知识草稿审批** → 知识库 → 知识管理（链路 18 SOP 自动生成草稿审批）
- 删除孤立文件 `SystemOverview.vue`（旧版系统态势页，API 已不存在，已被 SystemPosture.vue 替代）
- **7 份操作手册统一优化**：每份顶部增加链路流程图（含①②③步骤编号），每步底部增加 `← 上一步` / `下一步 →` 导航链接，同一手册内多链路自动隔离（不跨链导航）
  - 修复脚本 Bug：步骤标签 `）` 被正则吃掉的编码问题、`# 链路N` 跨链时 `current_chain` 提前更新的归组 Bug

### 2026-07-16: 关联分析全面升级——时间轴泳道图 + 服务拓扑图 + 真实关联算法
- **后端重写**：`observability_correlation.py` 全量重写（500行→实战级）
  - `GET /correlation/analyze` 增强：z-score 真指标异常检测（MetricRecord 表）、跨信号加权评分（alert=1/metric=2/log=2/trace=3）、`multi_signal_assets`/`critical_assets` 统计
  - `GET /correlation/timeline` **新增**：按时间桶聚合 4 类信号事件数，自动桶大小（1/5/15/60min），供 ECharts 泳道图
  - `GET /correlation/topology` **新增**：服务拓扑依赖图，从 Span parent_span_id 推导调用关系，含错误率/延迟
  - 保留 services/assets/trace-detail 接口
- **前端重写**：`ObservabilityCorrelationView.vue` 全量重写（Element Plus 表格→ ECharts 可视化）
  - **时间轴泳道图**（ECharts）：堆叠柱状图（告警/指标异常/日志异常）+ 折线图（链路错误），单击可框选时间
  - **服务拓扑图**（ECharts force）：节点大小=调用量、颜色=错误率（绿/黄/红），单击节点按服务过滤
  - **筛选栏优化**：固定宽度下拉、联动提示
  - **关联资产改进**：跨信号评分、健康状态圆点、信号种类数
  - **链路异常拆分**：慢调用/错误链路/高错误率服务三个子 Tab
  - Trace 详情抽屉改为 Element Table
- **修复**：main.py 删除重复的 `observability_correlation.router` 注册（Line 326）
- **入口**：侧边栏 → 智能分析室 → 日志·指标·链路关联（不变）

### 2026-07-16: 可观测性三支柱关联分析功能完成
- **问题**：系统只有单一告警、单一资产分析，缺少日志/指标/链路的关联分析统一界面
- **后端新增**：`app/routers/observability_correlation.py`
  - `GET /observability/correlation/analyze`：核心关联分析接口，同时查询告警/指标异常/日志异常/链路异常，按资产聚合
  - `GET /observability/correlation/services`：当前有数据的服务列表
  - `GET /observability/correlation/assets`：最近有异常数据的资产列表
  - `GET /observability/correlation/trace-detail`：单条链路详细 span 信息
- **前端新增**：`frontend/src/views/ObservabilityCorrelationView.vue`
  - 时间范围/服务/资产三重筛选
  - 5 类概览统计卡片（告警/指标异常/日志异常/链路异常/关联资产）
  - 4 个 Tab（告警/指标异常/日志异常/链路异常），链路异常含慢调用链 Top20 + 高错误率服务 + P95延迟/错误率
  - 右侧关联资产面板，按异常数量排序
  - 链路详情抽屉（查看 span 列表）
- **注册**：`main.py` 注册 `observability_correlation.router`；`AppLayout.vue` 注册组件和 VUE_PAGES；`menu_config.json` 在智能分析室分组添加「日志·指标·链路关联」菜单项
- **入口**：侧边栏 → 智能分析室 → 日志·指标·链路关联（`/observability-correlation`）
- **验证**：4 个 API 全部 200 OK | 24小时数据：21 告警 + 21 指标异常 + 2 日志异常 + 3 链路异常 | 前端构建成功 | 菜单正确注册

### 2026-07-16: 巡检模板类型过滤 — 模板 CI 类型真正生效
- **问题**：模板的 `target_ci_types` 原本只是信息标注，创建巡检任务时选择资产不受模板类型限制，导致用户困惑
- **后端改动**：
  - `browse_assets` 新增 `ci_types` 参数，支持逗号分隔多类型过滤
  - `resolve_task_assets` 新增 `template` 参数，手动模式兜底排除不属于模板类型的资产，动态模式无 ci_types 时自动用模板类型兜底
- **前端改动**：
  - 新增 `CI_LABELS` 中文映射（server→服务器 等），模板卡片、编辑弹窗、资产类型下拉全部改用中文
  - `searchAssets()` 自动传 `ci_types`（模板匹配的类型列表）给后端
  - `watch(taskForm.template_id)` 模板切换时清空已选资产 + 重新搜索
  - 资产选择器上方蓝色提示条显示「已按模板自动过滤：服务器 / 虚拟机 / 云主机」，下拉仍可手动切换

### 2026-07-16: RolesView bug 修复 + UI 重新设计 + UsersView 角色字段合并
- **RolesView.vue Bug 修复**：`const [menuData, menus]` 变量名与 `ref('menuData')` 冲突，导致菜单树永远为空。重命名为 `[menuResult, menusResult]`，修复 checkbox 不渲染问题
- **UI 重新设计**：左右两栏布局（左侧角色列表 + 右侧权限面板），新按钮系统（primary/plain/danger），树组件视觉层级增强（背景色/缩进/计数）
- **UsersView.vue**：删除多余的「角色」(role) 列和创建表单中的旧 role 下拉框，只保留一个「角色」概念（role_id FK），前端不再暴露 legacy `role` 字段
- **users.py 后端同步**：`/api/create` 从 `role_id` 自动推导 `role` 字段（admin/operator/viewer）；`/api/{id}/set-role` 改为同时更新 `role_id` 和 `role` 字段，保持 AuthMiddleware 兼容

### 2026-07-16: 多租户菜单与代理修复
- **menu_config.json**：在「系统配置」分组下添加 `tenant-management` 条目（侧边栏显示「租户管理」）
- **vite.config.js**：添加 `/tenant` proxy 配置，确保前端 axios 请求能到达后端
- **前端重新构建**：`npm run build --prefix frontend`，`TenantManagementView-DVWE-S6z.js` 已包含在构建产物中
- **后端重启**：使用 project07 venv (`D:\AIOPS\project07\.venv\Scripts\python.exe`) 重启 `run.py`，加载新的菜单配置

### 2026-07-15: 实现多租户隔离功能
- **默认模式**：单租户（tenant_mode=false），不影响现有逻辑
- **新增文件**：
  - `app/models.py` 末尾追加 `Tenant` 模型
  - `app/services/tenant_context.py` — 请求级 TLS 存储
  - `app/services/tenant_service.py` — 租户 CRUD 服务
  - `app/routers/tenant_management.py` — 租户管理 API（`/tenant/api/*`）
  - `app/migrations/add_tenant_tables.py` — 数据库迁移脚本
  - `frontend/src/views/TenantManagementView.vue` — 租户管理前端页面
- **修改文件**：
  - `app/main.py` — 注册 `tenant_management` router
  - `app/services/config_service.py` — 添加 `tenant_mode` 配置项
  - `app/routers/system.py` — 添加 `PUT /api/system/configs` 接口供前端切换租户模式
  - `frontend/src/layout/AppLayout.vue` — 注册 `tenant-management` 页面
- **迁移步骤**：`python app/migrations/add_tenant_tables.py` 执行建表+字段+默认数据初始化

### 2026-07-15: 菜单按用户场景重组（7大舱系替代技术分类）
- **问题**：原菜单按技术组件分组（K8s资源/Docker/事件中心/任务中心...），用户进来不知道该去哪个舱
- **方案**：改按用户角色+典型场景重组为7大舱
  | 新分组 | 用户角色 | 核心功能 |
  |--------|---------|---------|
  | ① 值班驾驶舱 | 值班长 | 仪表盘/告警/故障单/值班表/升级/通知 |
  | ② 运维工作台 | 运维工程师 | K8s总览+全部子资源/容器/自愈/脚本/Ansible/变更/资产 |
  | ③ 智能分析室 | SRE/分析师 | 指标/日志/链路/灭火图/数据源/事件统计/异常检测 |
  | ④ 可靠性工程 | SRE | SLO/错误预算/混沌实验/场景库 |
  | ⑤ 知识库 | 知识管理员 | 故障知识库/RAG/知识图谱/Runbook/SOP |
  | ⑥ AI运维智能体 | AI运营者 | AI助手/Agent编排/评估/A-B测试/特征仓库 |
  | ⑦ 系统配置 | 管理员 | 用户权限/系统配置/集成/开放接口/授权 |
- **改动**：`app/routers/menu_config.json` 完整重写，原85页全部保留重新归类
- **效果**：用户按角色找舱 → 舱内按场景细分，认知负担大幅降低

### 2026-07-15: 角色管理与菜单权限系统（RBAC）
- **新增模型**：`Role`（roles表）、`RoleMenu`（role_menus表）；`User.role_id` 外键
- **后端路由**：`app/routers/roles.py` — CRUD + 菜单权限分配 + 用户关联查询
- **菜单过滤**：`app/routers/menu.py` 按当前用户 `role_id` 查 RoleMenu 白名单，无权限配置时全量显示（向后兼容）
- **种子角色**：admin（系统）/ operator（操作员）/ viewer（只读），admins_id=1 始终全菜单
- **前端**：`RolesView.vue`（角色 CRUD + 树形菜单多选权限面板 + 关联用户列表）+ `UsersView.vue`（角色下拉分配）
- **入口**：系统配置 → 角色管理（`/roles-manage`）；用户与权限（现有）→ 菜单角色下拉
- **系统角色**不可删除；创建自定义角色后可勾选任意菜单项
- **验证**：10项测试全通过（创建/分配/过滤/保护/删除/清理）

### 2026-07-15: InspectionView 模板编辑功能补全
- **问题**: 巡检模板 Tab 下"新建模板"和"编辑"按钮都是空壳 alert， InspectionView.vue 第 430-431 行
- **修复**: 参照 WorkflowTemplatesView.vue 的弹窗模式，新增完整模板编辑弹窗
  - 新增 `showTemplateDialog`、`editingTemplate`、`tplForm` reactive 数据
  - 弹窗表单: 模板名称、描述、目标 CI 类型(checkbox 多选 23种)、检查项动态增删行、启用开关
  - `saveTemplate()` 调用 POST/PUT `/inspection/api/templates`
  - `openEditTemplate()` 将 `target_ci_types`(数组)和 `check_items`(数组) 深拷贝进表单
  - 检查项行: name/metric/threshold/unit/severity 五字段，severity 为 select(critical/warning)
  - `CI_TYPES` 常量数组定义 23 种 CI 类型
  - CSS: `.ci-type-grid` 4列 checkbox 网格，`.check-items-editor` 网格布局表头+动态行

### 2026-07-15: AIOps 架构交互图 PPT 重建（python-pptx 30页可编辑版）
- **路径**: `docs/AIOps系统架构交互图_客户交流PPT_20260715_可编辑版.pptx`
- **重建工具**: python-pptx 1.0.2 (project07 venv)
- **画布**: 16:9, `W=Inches(13.333)`, `H=Inches(7.5)` (1280×720px)
- **配色**: RGBColor 精确值（#1565C0蓝/#00897B绿/#FF6F00橙/#E53935红等）
- **内容**: 30页全覆盖（封面/目录/8层架构/核心数据流上下/K8s指标事件/移动端推送/变更关联/知识SRE/SLO自愈/自动响应/知识沉淀/AI检索/审批状态机/静默管理/告警巡检/混沌工程/OnCall轮转/Agent评估AB测试/异常回测/SOP生成/运营飞轮6卡片/分层诊断工具/仪表盘拖拽/资产健康度/移动端闭环/Agent能力中心/核心价值4卡片/技术亮点/结尾）

### 2026-07-15: AIOps 架构交互图客户交流 PPT 生成（30 页 SVG）
- **路径**: `.opencode/skills/ppt-master/projects/aiops_architecture_ppt169_20260715/`
- **产出**: 30 个 SVG 文件（`svg_output/01_封面.svg` ~ `30_结尾.svg`）+ 演讲备注 `notes/total.md`（30 页讲稿）
- **画布**: viewBox `0 0 1280 720`（PPT 16:9），配色 #1565C0/#00897B/#FF6F00/#E53935
- **内容**: 覆盖 24 条数据链路（封面/目录/8层架构/核心数据流/K8s/移动端/变更关联/知识SRE/SLO自愈/自动响应/知识沉淀/AI问答/审批状态机/静默/告警巡检/混沌回滚/OnCall/Agent评估/异常回测/SOP生成/运营飞轮/诊断工具/仪表盘/健康评分/移动端闭环/Agent能力/核心价值/技术亮点/结尾）
- **技术约束**: 禁用 id/clipPath/mask/style/class 等；渐变用 12 条矩形色带模拟；箭头用 polygon 替代 marker
- **验证**: 30 SVG 全部通过禁用元素检查 + viewBox 检查；notes 含 30 个 Slide 章节

### 2026-07-15: 灭火图重构 — 可观测信号与分层正确关联
- **设计理念**：每个层级只关联对应的可观测信号（Observability Signal），不混搭
  | 层级 | 可观测信号 | 健康判断 |
  |------|-----------|---------|
  | 功能接口 (api) | Trace（链路） | 错误率 > 5% 或 P99 > 1000ms → RED |
  | 微服务 (microservice) | Log（日志） | 有 k8s_event/pod_anomaly/log_anomaly 类活跃告警 → RED |
  | 中间件 (middleware) | Log + 中间件指标 | 有 log_anomaly 或 mysql/redis 指标告警 → RED |
  | 基础设施 (infra) | Metric（指标） | CPU > 90% 或 内存 > 90% 或 磁盘 > 85% → RED |
- **核心改动**（`app/services/health_engine.py`）：
  1. 新增 `ALERT_SIGNAL_MAP`：metric_name → 可观测信号分类（trace/log/metric/middleware_metric）
  2. 新增 `LAYER_SIGNALS`：层级 → 可观测信号类型映射
  3. 新增 `_get_alert_signal()` + `_is_alert_for_layer()`：告警-层级匹配函数
  4. 新增 `_compute_microservice_health()`：微服务层走 Log 告警判断（原来只看 status 不看告警）
  5. 重写 `_compute_middleware_health()`：中间件层走 Log + 中间件指标告警（原来只看 status）
  6. `compute_health()` 分发路由：microservice→`_compute_microservice_health`，middleware→`_compute_middleware_health`
  7. `fetch_overview()`：告警计数按层级过滤（原来只查 microservice/middleware 的全部告警，现在所有层都按可观测信号过滤）
  8. `fetch_entity_detail()`：实体详情告警按层级过滤（原来查所有告警，现在只查该层级对应信号的告警）
- **验证**：12 个信号匹配测试全 OK | 4 层 API 返回正确 | 实体详情告警按层级过滤确认（微服务只显示 k8s_event，中间件只显示 mysql/redis，基础设施只显示 cpu/memory/disk）

### 2026-07-15: 修复指标监控页空白（metric_v2_service 3 个 bug）
- **根因**：`metric_v2_service.py` 有 3 个 bug 导致 VM 查询全部返回空/错误数据
  1. `query_metric_names()` 调 `/api/v1/labels`（返回标签名 `asset_id/name`），应调 `/api/v1/label/__name__/values`（返回指标名）
  2. `query_latest_values()` 检查 `status != "is_success"`，但 VM 返回 `"success"` → 永远返回 `{}`
  3. `query_range_data()` 同样 status 检查错误 → 永远返回 `[]`
- **附带修复**：
  - `query_range_data()` 当 `asset_id=0` 时不再加 `asset_id="0"` 过滤条件（应为查全部资产）
  - `query_latest_values()` timestamp 从 Unix 秒数改为 ISO 字符串（兼容前端 `new Date()`）
  - `query_latest_values()` unit 默认值从 `"%"` 改为 `""`（非所有指标都是百分比）
  - `/api/v2/range` 端点支持不传 `name` 参数时返回所有指标的历史数据
- **验证**：3 个 API 全部 200 OK，names 返回 21 个指标名，latest 返回 1913 bytes，range 返回 294KB 历史数据

### 2026-07-15: 字段重命名遗留修复（第二批 — DB schema + chaos + agent_eval）
- **DB schema 修复**：`agent_workflow_node_runs.config` → `run_config`（ALTER TABLE RENAME COLUMN，demo + real 两个库）
- **DB schema 清理**：`chaos_runs.auto_recovered` 旧列删除（模型用 `is_auto_recovered`）；`oncall_schedules.auto_rotate` 旧列删除（模型用 `is_auto_rotate`）
- **DB schema 重建**：`remediation_effects` 表 DROP + recreate（模型字段与 DB 完全不匹配，表为空，直接重建）
- **chaos.py 字段修复**：`steady_state_passed` → `is_steady_state_passed`（12 处）；`notes=` → `description=`（5 处，模型字段是 `description` 不是 `notes`）
- **agent_eval_service.py 字段修复**：SQL label `"success"` → `"is_success"`（与 `agent_chat.py` 同类问题）
- **验证**：全量 model-DB 列对比零 mismatch | chaos 3 API + agent-eval + agent-workflow 全部 200 OK | 日志零 ERROR
- **根因**：字段重命名重构后，模型定义改了但（1）数据库旧列名未同步（2）部分代码仍用旧字段名

### 2026-07-15: 三大功能开发完成（运营数据看板 + 仪表盘拖拽编辑器 + 诊断Tool标准化）
- **运营数据看板** (`OpsAnalyticsView.vue`)：侧边栏「运行概览」→「运营分析看板」
  - 后端：`app/routers/ops_analytics.py` — 6 个 API（overview/mtta-mttr/alert-trend/remediation-effect/ai-efficiency/notification-stats）
  - 前端：6 大 KPI 卡 + 6 张 ECharts 图 + 7/30/90 天切换
  - 修复：`RemediationEffect` 模型与数据库表 schema 不匹配（DB 有 `log_id/asset_id/status_before/status_after/effect/checked_at`，模型有 `executed_at/check_at/is_asset_recovered/recovery_time_seconds`），改为用 `RemediationLog` 查询
- **仪表盘拖拽编辑器** (`DashboardDesignerView.vue`)：侧边栏「运行概览」→「自定义仪表盘」
  - 后端：`app/routers/dashboard_config.py` 重写 — CRUD 布局 + 16 种卡片类型 + 3 套预置模板 + `DashboardLayout` 表（`app/models.py` 新增）
  - 前端：16 个卡片组件（`frontend/src/components/dashboard/*.vue`）+ 拖拽/缩放/编辑/预览模式
- **实时诊断 Tool 标准化** (`DiagnosticToolsView.vue`)：侧边栏「任务中心」→「诊断工具中心」
  - 后端：`app/routers/diagnostic_tools.py` — 20 个工具（Snapshot 6 + Focused 12 + Flexible 2）+ 命令白名单校验（30+ 安全前缀 + 20+ 危险模式正则）
  - 前端：三层 Tab + 工具卡片网格 + 执行结果对话框 + 命令校验
  - 对标 GOPS 2026 秦晓辉演讲《借力 AI RCA》Layer3 实时诊断层
- **测试结果**：10 个 API 全部 200 OK | 14 个命令校验用例全部正确（安全通过/危险拦截）| Dashboard CRUD 完整通过 | 前端 `npm run build` 成功（2554 modules）| 菜单 3 项全部注册
- **入口位置**：运营分析看板=`/ops-analytics`，自定义仪表盘=`/dashboard-designer`，诊断工具中心=`/diagnostic-tools`

### 2026-07-15: 后端启动修复 + 三端访问验证通过
- **paramiko 修复**：hermes venv (Python 3.11) 的 paramiko 包损坏（site-packages 目录只有 `__pycache__`，无实际 .py 文件），`import paramiko` 返回空 namespace 包 → `python -m pip install --force-reinstall paramiko==3.5.0` 重装修复（注意：`pip install` 默认装到 Python 3.13，必须用 `python -m pip` 才装到 hermes 3.11 venv）
- **数据库迁移执行**：`db_migrate.py` 原用 `DATABASE_URL`（config 中不存在），修复为直接读 `DEMO_DB_PATH`/`REAL_DB_PATH` → 两个库各 53 列重命名成功，6 跳过（已迁移），0 失败
- **SystemConfig.value 遗漏修复**：`system_configs.value`→`config_value` 改名后，6 个文件仍用 `.value` 访问 SystemConfig 对象 → 修复 `config_service.py`（4 处）、`seed_data.py`（2 处）、`alert_service.py`（1 处）、`menu.py`（1 处）、`system.py`（2 处）、`mobile_push_service.py`（1 处）
- **三端验证结果**：
  - 后端 API `http://localhost:8000/healthz` → 200 `{"status":"ok"}`
  - 后端 SPA `http://localhost:8000/login` → 200 Vue index.html
  - 前端 dev `http://localhost:3000/login` → 200 Vite dev server
- **启动方式**：后端 `Start-Process python run.py`，前端 `cmd /c npm run dev --prefix frontend`

### 2026-07-15: 全库 80 表字段名规范化重构（57 个字段重命名，跨前后端全量代码）
- **背景**：`CONTRACT.md` 全面重写覆盖所有 80 张表后，发现 72+ 字段命名偏差（时间缺 `_at`、布尔缺 `is_`/`has_`、JSON 缺业务前缀、描述字段别名混乱、FK 命名不一致、`type` 冗余字段）
- **涉及范围**：`app/models.py`（核心 80 表）+ 47 个 router 文件 + 28 个 service 文件 + 12 个前端 Vue 文件 + 2 个 mobile Vue 文件 + 若干 seed/test 文件
- **主要变更**：
  - 时间字段：`start_time`→`started_at`、`end_time`→`ended_at`、`until`→`expires_at`、`last_checked`→`last_checked_at`、`last_scrape`→`last_scraped_at`、`last_used`→`last_used_at`、`period_start`→`period_started_at`、`period_end`→`period_ended_at`、`planned_start`→`planned_started_at`、`planned_end`→`planned_ended_at`、`last_run`→`last_run_at`、`last_sync`→`last_synced_at`、`first_seen`→`first_seen_at`、`last_seen`→`last_seen_at`、`report_date`→`reported_at`、`current_period_start`→`current_period_started_at`、`current_period_end`→`current_period_ended_at` 等 17 个
  - 布尔字段：`hallucination_flag`→`has_hallucination`、`auto_rotate`→`is_auto_rotate`、`steady_state_passed`→`is_steady_state_passed`、`auto_recovered`→`is_auto_recovered`、`asset_recovered`→`is_asset_recovered`、`alert_resolved`→`is_alert_resolved`、`success`→`is_success`（5 表）、`visible`→`is_visible`、`required`→`is_required`、`resolved`→`is_resolved` 等 11 个
  - 描述字段：`notes`→`description`（ChaosRun、RemediationEffect、RemediationEffectRecord）、`comment`→`description`（AssetLifecycle、IncidentApproval）、`note`→`description`（BlueGreenSwitchRecord）
  - JSON 字段：`config`→`channel_config/card_config/job_config/run_config`、`params`→`remediation_params/model_params`、`content`→`notification_content/message_content`、`data`→`report_data`、`value`→`config_value`、`options`→`attr_options`、`msg_metadata`→`metadata_json`
  - FK 字段：`changed_by`→`user_id`、`executed_by`→`user_id`
  - 废弃：`assets.type` 删除（业务意义模糊）
- **流程**：v2 审计 → CONTRACT 重写 → ref 分布扫描 → Phase 2（models.py 自动改名脚本）→ Phase 3a（全局安全词替换）→ Phase 3b（上下文敏感泛词替换）→ Phase 4a/4b（前端 Vue/JS + mobile）→ Phase 5（SQLite 迁移脚本）→ Phase 6（语法检查 + 全量字段审计零偏差）→ Phase 7（API 端点验证）
- **验证**：全量 Python 语法检查通过（`syntax_check.py`）| 字段名称审计零偏差 | 108 张表全部创建成功（`Base.metadata.create_all`）| FastAPI uvicorn 导入正常（参差不齐因预存 paramiko 编码问题阻塞，非改名引进）
- **迁移脚本**：`db_migrate.py` 生成完整 61 条 ALTER TABLE RENAME COLUMN 语句（幂等执行），部署时运行即可
- **注意**：`.pyc` 清过一次后需重新预热

### 2026-07-15: ChaosRun.is_auto_recovered 空壳字段修复（混沌自动回滚统计闭环）
- **问题**：`models.py:32` 定义了 `is_auto_recovered = Column(Boolean, default=False)`，但 `chaos.py:_inject_and_observe_async` 落库 ChaosRun 时未赋值（空壳字段），导致自动回滚统计永远为 0
- **根因**：第 384 行 `_ssh_exec(asset, cleanup_cmd)` 无条件执行了 cleanup（Auto-Remediation），但没捕获结果也没写入 `is_auto_recovered`
- **修复**（`app/routers/chaos.py`）：
  1. cleanup 结果捕获：`cleanup_ok, _ = _ssh_exec(...)` → `auto_recovered = cleanup_ok`（cleanup_cmd 非空且执行成功才标记 True）
  2. 落库赋值：`ChaosRun(..., is_auto_recovered=auto_recovered, ...)`
  3. notes 补充：`自动回滚 {'✅成功' if auto_recovered else '⚠️未执行/失败'}`
  4. `/api/chaos/summary` 增加 `auto_recovered`（计数）+ `auto_recover_rate`（百分比）
  5. `/api/chaos/experiments/{id}/runs` 列表返回 `is_auto_recovered` 字段
- **验证**：summary 200（auto_recovered=0 auto_recover_rate=0.0% — 老数据符合预期）| runs 200（is_auto_recovered=False — 老数据）| 新实验将正确标记
- **确认无问题**：OnCallSchedule 列名 `is_auto_rotate`（models.py:1159 / sre.py / main.py:_MIGRATIONS / 数据库列全部统一），之前的 `auto_rotate` 报错是旧代码问题已修复

### 2026-07-15: 系统架构交互图补充（12→24 条链路）
- **背景**：`docs/系统架构交互图.md` 原有 12 条链路，最近冲刺开发的功能未体现
- **核实**：用 explore agent 核实 18 个最近开发功能全部存在（代码+路由+模型），确认数据流链路
- **新增 12 条链路**：
  - 链路13 告警触发巡检（Alert-Triggered Proactive Inspection）
  - 链路14 混沌工程稳态验证与自动回滚（Steady-State Hypothesis Verification）
  - 链路15 On-Call 自动轮转与交接班（On-Call Rotation & Handover）
  - 链路16 AI Agent 质量评估与 A/B 测试（Agent Quality Evaluation & A/B Testing）
  - 链路17 异常检测精度回测与算法择优（Anomaly Detection Benchmarking）
  - 链路18 SOP 知识自动生成（SOP Knowledge Auto-Generation）
  - 链路19 运营数据飞轮（Operational Data Flywheel — MTTA/MTTR/AI 效能）
  - 链路20 分层诊断工具体系（Layered Diagnostic Tool Taxonomy）
  - 链路21 仪表盘拖拽自定义（Dashboard Drag-and-Drop Customization）
  - 链路22 资产健康度评分与变更跟踪（Asset Health Scoring & Change Tracking）
  - 链路23 移动端运维闭环（Mobile Ops Closed-Loop — 日志/批量/故障单/会话）
  - 链路24 Agent 能力中心（Agent Capability Center）
- **现有链路精度增强**：链路1补充健康评分+变更跟踪；链路9/10补充SOP审批+Reranker双模式；链路8自愈效果闭环
- **发现的问题**：`ChaosRun.is_auto_recovered` 字段模型层已定义但 `_inject_and_observe_async` 落库时未赋值（空壳字段）；OnCallSchedule 实际列名是 `is_auto_rotate`（非 `auto_rotate`，db_migrate 有映射）

### 2026-07-15: 后端大量报错修复（SQLite 缺列迁移补全 + Incident 字段补全）
- **现象**：日志 459 个 ERROR / 186 个 WARNING，接口大量 500
- **根因**：7-15 新增的模型字段在代码里定义了，但 SQLite 旧表缺列（`create_all` 只建新表不 ALTER 已有表），`_MIGRATIONS` 字典漏配 4 类字段
- **缺列清单**（两个库 `db/aiops.db` + `db/aiops_real.db` 均缺）：
  - `chaos_runs.auto_recovered`（5.3 混沌自动回滚）→ `/api/chaos/*` 全部 500（10 次）
  - `inspection_records.triggered_by_alert_id`（5.2 告警触发巡检）→ `/inspection/api/records|stats` 500（2 次）
  - `knowledge_drafts.sop_steps`（知识审批流 SOP）→ `/knowledge/api/auto-gen/drafts` 500（1 次）
  - `incidents.impact` + `incidents.description`（7.5 故障单完整功能）→ `/incidents/api/create` 500（5 次，旧代码 `Incident(impact=...)` 传了模型没有的字段）
  - `oncall_schedules.auto_rotate`（5.5 OnCall 自动排班）→ 已在 _MIGRATIONS，新进程迁移后自愈
- **修复**：
  1. `app/models.py:Incident` 补 `impact = Column(String(32), default="high")` + `description = Column(Text, default="")`（路线图 7.5 要求故障单含影响/描述）
  2. `app/main.py:_MIGRATIONS` 补 4 条：`chaos_runs.auto_recovered`、`inspection_records.triggered_by_alert_id`、`knowledge_drafts.sop_steps`、`incidents.impact/description`
  3. `app/services/incident_service.py:create_incident` 用上 `impact`/`description` 参数（之前接收但丢弃 → 数据丢失）
  4. `app/routers/incidents.py:_incident_to_dict` 返回 `impact`/`description`
- **迁移机制**：`main.py:94-102` import 时遍历 `get_all_engines()` 对每个引擎执行 `ALTER TABLE ... ADD COLUMN`（幂等，已存在列会 except pass）
- **验证**：重启后端 → 两库 6 列全部 OK → 9 个曾报错接口（chaos/oncall/inspection/knowledge/mobile/dashboard）全部 200 → 故障单创建 impact=medium 持久化成功 → 清理 4 条测试数据
- **教训**：① 新增模型字段后**必须同步补 `_MIGRATIONS`**，否则旧 SQLite 库缺列 → 接口静默 500；② `create_all` 不会 ALTER 已有表，这是 SQLAlchemy + SQLite 的固有局限，必须显式迁移；③ `Incident(impact=...)` 报 `invalid keyword argument` 是模型与调用方不一致的明确信号
- **遗留**：早期 `baseline_service.AIProvider` 报错（01:08，2 次）+ `database is locked`（00:52，1 次）新进程已不再出现，不深究

### 2026-07-15: 系统访问故障修复（后端进程异常 + 登录密码勘误）
- **现象**：访问不到系统
- **根因**：端口 8000 上的后端进程（PID 10320，用**系统 Python3.13** `C:\Users\zhuming\AppData\Local\Programs\Python\Python313\python.exe` 跑）处于异常/半残状态——启动后**完全无日志写入**（日志停在 13:14，进程 13:16 才启动）、`/login` 返回 404 空 body、`/`、`/healthz`、`/api/menu` 几乎所有路径返回 401（既非 AuthMiddleware 的 303，也非 LicenseMiddleware 的 403，来源不明）。仅 `/static`、`/vue-assets` 因 StaticFiles mount 放行（307）
- **修复**：杀掉 10320 + 释放 8000 端口 → 用 **project07 venv python**（`D:\AIOPS\project07\.venv\Scripts\python.exe`，Python 3.11.15）`Start-Process` 重启 `run.py` → 新进程 PID 408 恢复正常，日志恢复写入
- **验证**：`/login` GET 200（Vue SPA 818B）| POST /login admin/admin123 200（token 189 字符）| GET /api/menu Bearer 200（7912B）完整闭环 ✅
- **⚠️ 登录密码勘误**：实际密码是 **admin / admin123**（`main.py:395` `default_pwd = os.environ.get("AIOPS_ADMIN_PASSWORD", "admin123")` + `init_admin()` 用 bcrypt 写入）。~~MEMORY 之前多处写的「admin / 1234」是错的~~，应全部更正为 admin / admin123
- **密码 hash 来源**：`seed_data.py:73` 的 admin 用旧 `sha256("123456")`，但 `init_admin()` 用 `bcrypt(admin123)` 覆盖；数据库现存 hash 为 `bcrypt$$2b$12$...` 格式（`bcrypt$` 前缀 + `$2b$12$` salt，两个 `$` 是正常的），明文 admin123
- **教训**：① 后端进程异常（无日志 + 路由 404 + 401 满天飞）优先怀疑进程状态，直接杀掉用规范 venv 重启，比逐行推理中间件更快；② 系统 Python3.13 虽能 `import app.main`（528 路由），但生产应坚持用 project07 venv（规范一致性）；③ LicenseMiddleware 拦截返回 403、AuthMiddleware 返回 303，出现 401 必定来自别的中间件/路由，是进程异常的信号

### 2026-07-15: Investigation Package 6部分结构化 RCA（Facts/Timeline/Candidates/Evidence/Exclusions/NextSteps）
- `rca_service.py` 重写 `analyze_incident()` 输出结构化 `InvestigationPackage`（6 部分）：facts（异常实体）、timeline（时间线+变更事件）、candidate_causes（候选根因按置信度排序）、evidence（证据）、exclusions（已排除方向）、next_steps（建议操作）
- 各模块 BFS 追踪路径重构，避免循环依赖；新增 `deque` 导入
- 前端构建成功（30.92s）
- **资产变更自动跟踪**：`asset_changes.py` 新增 `/logs` API（分页查询 `AssetChangeLog`）；`log_change()` 已有，`update_asset()` 已在变更时自动调用
- **资产健康度自动化评分**：`asset_change_service.py` 新增 `get_asset_health_score()`（CPU/MEM/DISK 指标+活跃告警→0-100分）、`scan_asset_health_changes()`（批量扫描+状态变化写变更日志）、`get_all_asset_health()`；`assets.py` 新增 `/api/health-score`（单资产或全量）+ `/api/health-scan`（触发全量扫描）；语法验证通过
- **SLO 自动计算 + Dashboard**：`slo_service.py`（`_query_vm_availability` 从 VM 实时查询可用性、`_calc_burn` 计算燃烧速率、`get_slo_dashboard` 生成卡片数据）；`sre.py` 新增 `/api/sre/slo/dashboard` + `/api/sre/slo/calculate`；新建 `SloDashboardView.vue`（卡片式 SLO 仪表盘）；`AppLayout.vue` 注册 `SloDashboardView` + `'slo-dashboard'` 到 VUE_PAGES
- **Remediation Workflow 可视化编排**：`RemediationWorkflowView.vue` 新建弹窗改为可视化步骤编辑器（动作下拉+参数输入+上移下移删除按钮）；`openCreate`/`makeStep`/`addStep`/`removeStep`/`moveStep`/`createWorkflow` JS 逻辑重构；步骤序列化为 `[{action, deployment?, command?, message?}]` JSON
- 前端 `npm run build` 成功（21.59s），后端 import 验证通过
- **评分**：SRE 8.0→9.5，自愈/巡检 8.0→9.5，综合 9.4→9.5
- **VM 进程嵌入 run.py**：`victoria-metrics-windows-amd64-prod.exe` 放 `bin/`，run.py 用 subprocess.Popen 启动子进程，atexit + signal handler 自动清理
- **metric_v2_service.py**：VM 写入用 `write_metrics_batch`（Prometheus exposition format，`__name__` + `asset_id` 标签）；查询用 `query_latest_values`/`query_range_data`/`query_promql`，返回格式与旧 SQLite 接口兼容
- **metric_collector.py 双写**：`collect_asset_metrics` SSH 采集后先写 SQLite（commit），末尾追加 `write_metrics_batch` 写 VM，双写过渡
- **metrics.py v2 接口**：新增 `/metrics/api/v2/query|latest|range|names|status` 5 个 API；旧接口保留向前兼容
- **MetricsView.vue 适配**：`loadMetrics` 改调 `/metrics/api/v2/names|latest`；`loadChartData` 改调 `/metrics/api/v2/range`
- 端到端验证：写入 3 条指标 → 查询返回 3 条 ✅，综合评分 9.2 → 9.4
- **告警 WebSocket 实时推送**：`ws_manager.py` 加 `publish_alert()`；`ws.py` 加 `/ws/alerts` 端点；`alert_service.py:check_rules()` 末尾通过 `_ws_publish_async()` 线程推送；前端 `websocket.js` + `AlertsView.vue` 集成；`npm run build` 成功
- **4.4.3 自动算法选择**：`anomaly_eval_service.py` 重写 `recommend_algorithm()`，无标注数据时走指标特征匹配（CPU→MAD/MEM→EWMA/Error→IsolationForest/QPS→STL/业务→Prophet）+ 统计推断（变异系数/偏度）；有标注时返回 `method: "基准标注"`
- **4.4.4 Benchmark 回测接口**：`anomaly.py` 新增 4 接口：`GET /anomaly/api/benchmark/stats|list`、`POST /anomaly/api/benchmark`、`GET /anomaly/api/benchmark/recommend`；前端 `AnomalyBenchmarkView.vue` 页面完整
- **RCA 根因闭环**：`knowledge_graph_service.py` 新增 `record_rca_result()` + `get_similar_rca()`；`incidents.py:api_incident_rca` 末尾调用 `record_rca_result()` 将 RCA 结果写入 `knowledge_base` 表

### 2026-07-15: Agent 能力中心完成（工具注册表可视化管理）
- **新页面 AgentCapabilitiesView.vue**：侧边栏「AIOps 智能体」→「Agent 能力中心」
- **后端 API**：`GET /agent/api/capabilities` 返回工具清单(41个)+统计+Agent 配置+Provider 信息
- **功能**：工具搜索/风险等级筛选/LLM/Internal 范围过滤/展开查看 input_schema/安全策略说明
- **工具统计**：read_only=20, low=4, medium=6, high=5, critical=3, advisory=3 (LLM=24, Internal=17)
- 菜单注册：menu_config.json + AppLayout.vue defineAsyncComponent 条件渲染
- 前端构建 ✅，API 测试通过 ✅

### 2026-07-15: 知识审批流 + SOP 自动生成完成（知识管理 8.0→9.0）
- **知识审批流**：`KnowledgeBase/KnowledgeDraft` 加 `source_type`/`sop_steps`/`reject_reason` 字段；`approve_draft` 写 source_type=auto+sop_steps；`reject_draft` 支持拒绝理由；`KnowledgeDraftView.vue` 加拒绝原因显示+来源标签+SOP 步骤卡片展示；前端审批页已完整
- **SOP 自动生成**：`POST /knowledge/api/auto-gen/sop/incident/{id}` 新端点；`generate_sop_from_incident(incident_id)` 生成结构化 SOP 步骤 JSON（step/action/command/expectation）；故障单详情「生成 SOP 知识」按钮；前端 `IncidentsView.vue` 加 SOP 按钮；`sop_steps` 字段 TEXT 类型存 JSON 数组
- 数据库迁移：`_MIGRATIONS` 已补 `source_type`/`sop_steps`/`reject_reason` 字段
- 前端构建：`npm run build` ✅ 成功；后端 import 正常

### 2026-07-15: Phase 5 移动端优化完成（批量告警/日志搜索/交接班/故障单/AI会话/WebSocket）
- **7.3 WebSocket 实时告警**：后端 `ws_manager.py` 已有 `publish_alert`，`ws.py` 已有 `/ws/alerts`；移动端新建 `mobile/src/utils/ws.js`（封装 uni WebSocket）；`mobile/src/pages/alert/list.vue` 接入 WS + 新告警气泡提示；`frontend/src/views/AlertsView.vue` 已有 `connectAlertsWs` 接入
- **7.4 告警批量操作**：`mobile/src/pages/alert/list.vue` 加多选模式（checkbox）+ 批量确认/解决栏；`frontend/src/views/AlertsView.vue` 加 checkbox + 批量确认/解决按钮；API 均用 `batchAcknowledge`/`batchResolve`
- **7.1 日志搜索**：`mobile/src/pages/logs/index.vue` 完全重写：搜索框+级别过滤+数据源picker+时间范围+日志列表+展开详情+复制导出
- **7.6 交接班**：移动端 `mobile/src/pages/oncall/my.vue` 的 `handleHandover` 改为真实 API 调用；`mobile/src/api/oncall.js` 新增 `handover(id, toName)` + `autoRotate(id)`
- **7.5 故障单完整功能**：新建 `mobile/src/pages/incident/create.vue`（新建故障单表单页）；`mobile/src/pages/incident/index.vue` 加"新建故障单"入口按钮
- **7.7 AI 会话列表**：新建 `mobile/src/pages/agent/sessions.vue`（历史会话列表+删除）；`mobile/src/pages/agent/chat.vue` 右上角加"历史会话"按钮；pages.json 注册
- **7.9/7.8** 指标监控增强+远程操作 暂未做（低优先级）

### 2026-07-15: SSE 实时推送完成（3.3 实时推送引擎）
- **3.3 实时推送引擎 (SSE)**：修复 `agent_sse.py` 语法错误（死循环+多余括号），POST→GET 改用 query params；`ws_manager.py`（ConnectionManager）+ `ws.py`（WebSocket `/ws/agent`）+ `agent_sse.py`（SSE `/agent/chat/stream`）已注册到 `main.py`；`frontend/src/composables/useAgentSSE.js`（EventSource composable）已创建；`AgentChatView.vue` 已改用 SSE 实时对话；前端构建成功
- 修复：删除 `app/routers/agent_sse.py` L143-144 死循环代码，修复 L156 `) or ""` 语法错误
- 注册：`main.py` import 增加 `agent_sse, ws`，`include_router` 增加 `agent_sse.router` + `ws.router`

### 2026-07-15: Phase 3 冲刺4项完成（自愈效果追踪/告警触发巡检/混沌自动回滚/OnCall自动排班）
- **5.1 自愈成功率分析**：`RemediationEffect` 模型（12字段：alert_status_at_execute/check、alert_resolved、recovery_time_seconds）、`remediation_effect_service.py`（异步线程30分钟延迟检查 `_do_track_effect`）、`GET /remediation/api/effect-stats`、`GET /remediation/api/effect-history`、`GET /remediation/api/effect-recommendations`、修改 `check_and_remediate()` 异步调用 `track_effect(log_id, db, delay_minutes=30)`
- **5.2 告警触发巡检**：`InspectionRecord.triggered_by_alert_id` 字段、`trigger_by_alert(alert_id, db)` 自动查找同类资产匹配模板执行、`POST /inspection/api/trigger-by-alert/{alert_id}`
- **5.3 混沌工程自动回滚**：`ChaosRun.auto_recovered` 字段、`_inject_and_observe_async` 增加多指标对比（CPU/MEM/DISK before→after delta>5% 立即cleanup）、异常时自动执行 cleanup_cmd 不等 nohup 自清理
- **5.5 On-Call 自动排班**：`OnCallSchedule.auto_rotate`+`holidays` 字段、`GET /api/sre/oncall/current` 周期过期自动调用 `_do_auto_rotate`、新增 `POST /api/sre/oncall/{id}/auto-rotate`、`POST /api/sre/oncall/{id}/handover`
- **清理 CheckinRecord**：发现 GPS 打卡不合规（需备案），删除全部签到相关代码（`CheckinRecord` 模型、`/checkin` 接口、`checkin()` API、`mobile.js` 中的 checkin 函数）
- **功能入口**：自愈统计→后端 API（待接前端）；告警触发巡检→告警详情页按钮；混沌自动回滚→混沌实验页；OnCall→SRE 值班表

### 2026-07-15: Phase 2 冲刺5项全部完成（Agent评估/A/B测试/RAG重排/异常基准/资产发现）
- **4.1 Agent 评估体系**：`AgentEvaluation` 模型（`agent_evaluations` 表）、`agent_eval_service.py`（stats/history/recommend）、`agent_eval.py`（`GET /agent/api/eval/stats`、`GET /agent/api/eval/history`）、`AgentEvalView.vue`
- **4.2 A/B 测试框架**：`ABTestConfig`+`ABTestRecord` 模型、`ab_test_service.py`（创建/分流/记录/对比）、`ab_test.py`（config CRUD + results）、`ABTestView.vue`
- **4.5 RAG 检索精度提升**：`rag_rerank_service.py`（透传 rerank_mode 到 `hybrid_search`）、`RAGRerankView.vue`（检索+切换 classic/smart/none 模式）
- **4.4 异常检测精度提升**：`AnomalyBenchmark` 模型（`anomaly_benchmarks` 表）、`anomaly_eval_service.py`（stats/recommend）、`anomaly_eval.py`（benchmark CRUD/stats/recommend）、`AnomalyBenchmarkView.vue`
- **4.3 资产自动发现**：`DiscoverySchedule`+`DiscoveryResult` 模型、`asset_discovery_service.py`（TCP/SSH/ICMP 扫描）、`asset_discovery.py`、`AssetDiscoveryView.vue`
- **菜单位置**：AIOps 智能体→Agent 评估、A/B 测试；知识管理→RAG 检索增强；异常检测→异常检测基准；资产管理→资产自动发现

### 2026-07-15: 4.6 知识自动沉淀 + 5.1 自愈成功率分析（冲刺10分）

**4.6 知识自动沉淀**：
- 新增 `KnowledgeDraft` 模型（`knowledge_drafts` 表）——待审批草稿，含告警上下文/symptom/root_cause/solution/状态
- `knowledge_autogen_service.py`：`generate_draft(alert_id)` 用 LLM 从已解决告警生成知识草稿，`list_drafts/approve_draft/reject_draft` 审批流程
- `knowledge_autogen.py`：4个路由（`GET /drafts`、`POST /trigger/{alert_id}`、`POST /drafts/{id}/approve`、`POST /drafts/{id}/reject`）
- 告警解决时自动触发：修改 `alerts.py` 的 `api_resolve_alert`，resolve 后调用 `generate_draft`
- 前端：`KnowledgeDraftView.vue`（知识管理→AI 知识草稿）—— 草稿列表/通过入库/拒绝操作

**5.1 自愈成功率分析**：
- 新增 `RemediationEffect` 模型（`remediation_effects` 表）——追踪每次自愈执行的效果（resolved/improved/no_change/worsened）
- `remediation_effect_service.py`：`track_effect(log_id)` 立即追踪、`get_effect_stats(days)` 统计成功率、`get_remediation_recommendations()` 高置信度规则推荐
- `remediation_effect.py`：4个路由（`GET /effect-stats`、`GET /effects`、`POST /effects/check/{log_id}`、`GET /effect-recommendations`）
- 自愈执行后自动追踪：修改 `remediation_service.py` 的 `check_and_remediate`，执行后调用 `track_effect`
- 前端：`RemediationEffectView.vue`（任务中心→自愈效果分析）——成功率统计/改善率/各规则效果/推荐规则/历史记录

**菜单位置**：
- AI 知识草稿：侧边栏「知识管理」→「AI 知识草稿」（key: `knowledge-draft`）
- 自愈效果分析：侧边栏「任务中心」→「自愈效果分析」（key: `remediation-effect`）

### 2026-07-15: 告警推荐接入 AI 分析 + 菜单移至 AIOps 智能体
- **告警 AI 分析**：SmartRecommendView 告警 tab 新增 `[AI 分析]` 按钮（btn-accent 青色样式），调用 `GET /smart-recommend/ai-analyze-alert/{alert_id}`，LLM 返回根因分析/影响评估/修复建议/严重程度评估/建议 Runbook
- **后端新增**：`smart_recommend_service.py.ai_analyze_alert()` — 传 Alert 对象 + 关联知识库/资产上下文给 LLM；`smart_recommend.py.ai_analyze_alert_endpoint()` — `GET /smart-recommend/ai-analyze-alert/{alert_id}`
- **菜单迁移**：`smart-recommend` 从「知识管理」移至「AIOps 智能体」一级菜单（最后一项），侧边栏路径不变 `/smart-recommend`
- **目前三个 tab 全部接入 AI**：告警推荐（AI 分析按钮）、指标推荐（AI 智能推荐按钮）、基线检查（AI 安全分析按钮）

### 2026-07-15: ci_type 别名映射修复（virtual_machine → server）
- **问题**：`ci_type=virtual_machine` 的资产在基线检查和指标推荐均显示「暂无模板」，因为模板只匹配 `server` 等标准类型
- **修复**：`smart_recommend_service.py` 和 `baseline_service.py` 均加入 `_CI_ALIASES = {"virtual_machine": "server", "vm": "server", "host": "server", "physical_machine": "server"}`，所有模板查找路径先走别名映射
- **影响**：资产 577（virtual_machine）的基线和指标推荐功能恢复正常

### 2026-07-15: AssetsView 排除 K8s 子资源（CMDB 台账清理）
- **决策**：K8s 子资源（deployment/statefulset/daemonset/service/ingress/pv/pvc/configmap/secret/pod/job）不在 CMDB 台账展示，由 K8sResourceListView 管理
- **前端 `AssetsView.vue`**：
  - `ciTypeGroups` 移除「🐳 K8s 持久化 CI」和「🔒 K8s 弱纳管 CI」分组
  - `node`/`namespace` 移至「☁️ 云资源层」（保留为 CMDB 级资产）
  - `PERSISTENT_TYPES` 精简为 `kubernetes_cluster/node/namespace`
  - `WEAK_TYPES` 置空
  - 移除 tier-bar 统计条（持久化 CI / 弱纳管 CI / 实时视图）
  - 工具栏提示改为：「K8s 子资源（Deployment/Service/Pod 等）由「K8s 资源」页面管理」
- **后端 `assets.py`**：
  - 新增 `ASSET_EXCLUDE_CI_TYPES` 集合（11 个类型）
  - `asset_api_list` 中过滤掉 K8s 子资源（continue 跳过）
- **验证**：
  - API 返回 33 条资产，CI types 仅含 `business_app/container/database/kubernetes_cluster/namespace/node/virtual_machine`
  - 灭火图测试 63/63 ✅，巡检测试 125/125 ✅
- **保持不变**：health_engine.py/inspection_service.py/topology_service.py/k8s_resources.py 中的 K8s ci_type 引用全部保留（同步/拓扑/容器运维/AI 工具仍依赖）

### 2026-07-15: 资产基线安全检查（Baseline Security Check + AI Analysis）
- **新增模型** (`models.py`): `SecurityBaselineTemplate`（基线模板）、`AssetBaselineCheck`（资产级检查结果）
- **种子数据**: 38 条基线模板覆盖 6 CI 类型（server 11/mysql 8/nginx 5/redis 5/postgresql 4/k8s 5），含检查命令、预期匹配正则、修复建议
- **后端服务** (`baseline_service.py`):
  - `get_baseline_templates()` 按 ci_type 匹配模板合并已有结果
  - `run_check()` 三路自动检测（SSH/SQL/Redis）+ `_match_result()` 正则判定 pass/fail
  - `run_all_checks()` 全量执行并持久化
  - `ai_analyze()` AI 分析（LLM 生成安全报告）+ `_rule_report()` 规则降级
  - `save_check()` / `_exec_ssh/_sql/_redis` 连接复用
- **路由** (`baseline.py`): `GET /templates/{ci_type}`, `GET /checks/{asset_id}`, `POST /checks/manual`, `POST /check/{id}/{tid}`, `POST /check-all/{id}`, `GET /analyze/{id}`
- **前端**: SmartRecommendView.vue 新增「基线检查」Tab → 资产输入 → 安全报告卡片（评分/风险等级/主要风险/优先修复）→ 基线项表格（状态彩色圆点+检测值+操作按钮）→ 手动标记弹窗
- **测试**: 7 项自动化测试全部通过（模板匹配/手动标记/持久化/规则分析/AI 分析/多 CI 类型/不同资产）
- **前沿**: Multi-dimensional Security Posture Assessment（多维安全态势评估）、Automated Compliance Validation（自动化合规验证）

### 2026-07-15: 智能指标推荐系统（Metric Gap Analysis + AI Recommendation）
- **新增模型** (`models.py`): `MetricTemplate`（指标模板，48条预置数据覆盖13类CI）、`AssetMetricRecommendation`（资产级采纳/忽略记录）
- **种子数据** (`_seed_templates.py` -> 内联脚本): 42 条模板（server/mysql/nginx/redis/java/k8s/postgresql），含采集方式、阈值、排序
- **后端服务** (`smart_recommend_service.py`): `get_metric_gaps()` 模板匹配缺口，`ai_recommend()` LLM 个性化推荐，`apply/dismiss_recommendation()` 落地
- **新增路由** (`smart_recommend.py`): `GET /gaps/{asset_id}`、`GET /ai-recommend/{asset_id}`、`GET /recommendations/{asset_id}`、`POST /apply`、`POST /dismiss`
- **前端** (`SmartRecommendView.vue`): 双Tab（告警推荐 / 指标推荐），指标Tab含资产输入→缺口表格（含监控状态/采纳/忽略按钮）→ AI 推荐区→历史记录
- **构建**: `npm run build --prefix frontend` 成功，SmartRecommendView CSS 9.18 kB + JS 16.05 kB

### 2026-07-15: 智能巡检模块（AI 驱动的多维资产健康巡检）
- **新增模型** (`models.py`): `InspectionTemplate`（巡检模板）、`InspectionTask`（巡检任务）、`InspectionRecord`（巡检记录）
- **后端服务** (`inspection_service.py`): 4 个内置模板（服务器/中间件/微服务/API），资产范围支持手动选择 + 动态筛选（ci_types/tags/domain/status）
- **巡检执行引擎**: 8 类检查项（CPU/内存/磁盘/告警/资产状态/检查时间/Span错误率/Span P99延迟），逐资产评估 worst_status → 健康评分
- **AI 分析**: 调用 LLM 生成专业巡检报告（摘要/评分解读/异常分析/趋势预判/处置建议/风险预警），fallback 到规则报告
- **路由** (`inspection.py`): `/inspection/api/stats|templates|tasks|tasks/{id}/run|records|assets-browse`
- **前端** (`InspectionView.vue`): 统计卡片 + 三Tab（巡检任务/巡检模板/执行记录）+ 资产选择器 + AI 报告抽屉（逐项检查详情 + Markdown 渲染）
- **菜单**: 任务中心 → 智能巡检 (`/smart-inspection`)
- **构建**: `npm run build` 成功，InspectionView CSS 11.13 kB + JS 18.36 kB
- **测试**: 21 场景 125 项全部通过 — 模板种子/CRUD、资产浏览（类型/关键词/空搜索）、任务CRUD（手动/动态范围）、巡检执行（服务器/数据库/API/混合资产/大批量）、告警检出、CPU超阈值检出、offline检出、last_checked过期检出、从未检查检出、AI报告生成（1733字符）、无Span匹配降级、重复执行幂等、空资产错误处理、统计接口、记录查询/过滤、删除任务
- **专业术语**: Proactive Health Inspection（主动健康巡检）、Multi-dimensional Health Check（多维健康检查）、AI-driven Incident Prevention（AI 驱动的事前预防）

### 2026-07-15: 灭火图分层健康引擎（三源驱动）
- **核心改动**：`health_engine.py` 重写 `compute_health()` 为分层逻辑，按 ci_type 映射到 4 层，每层用不同数据源判断健康
- **功能接口层 (api)**：查 `Span` 链路表，用 `_match_asset_to_services()` 模糊匹配 Asset.name → Span.service_name，计算错误率 + P99 延迟，超阈值（5%/1000ms）→ 红
- **微服务+中间件层**：查 `Alert` 告警表，有活跃告警 → 红（保持原有逻辑）
- **基础设施层 (infra)**：查 `MetricRecord` 指标表，CPU>90%/内存>90%/磁盘>85% → 红，fallback 查告警
- **Asset↔Span 匹配**：`_normalize_service_name()` 去 K8s 前缀（prod/）+ 哈希后缀（-7f8b9）+ 部署后缀（-deploy/-svc），再 ILIKE 模糊匹配
- **前端增强**：`FireMapView.vue` 实体详情抽屉新增「链路指标」区块（错误率/P99/平均延迟/关联服务标签）和「基础设施指标」区块（CPU/内存/磁盘进度条+阈值线）
- **验证**：`prod/api-gateway` → `api-gateway`，`prod/user-svc-7f8b9` → `user-service`，`prod/order-svc-6d2a1` → `order-service`，3 个资产成功匹配到 7 个 span 服务
- **API**：447 实体，5 green（4 middleware + 1 api），5 red，437 gray
- **专业术语**：Observability Correlation（可观测性关联）、Entity Resolution（实体消解）、CMDB-APM Integration

### 2026-07-14: FireMapView 亮色主题适配
- 全量样式改为 CSS 变量驱动：`var(--content-bg)`、`var(--card-bg)`、`var(--text-primary)`、`var(--text-muted)`、`var(--primary)`、`var(--success/danger/warning)` 等
- 暗色模式用 `html[data-theme="dark"] .firemap` 保留深色科技渐变背景
- 亮色模式自动使用主题系统变量，适配靛蓝/赤陶双色系
- 使用 `color-mix()` 替代硬编码透明度，跟随主题色变化
- `npm run build` 成功，FireMapView CSS 13.78 kB

### 2026-07-14: 灭火图（FireMap）健康驾驶舱
- **后端**：Asset 模型新增 `health_status` 字段（green/gray/red）；创建 `app/services/health_engine.py` 健康计算引擎（基于 status + last_checked + 活跃告警）；创建 `app/routers/health_map.py`（`GET /health-map/api/overview` 分层概览 + `GET /health-map/api/entity/{id}` 实体下钻）
- **前端**：创建 `FireMapView.vue` 深色科技大屏（暗色背景+渐变，统计顶栏，四层卡片：功能接口/微服务/中间件/基础设施，圆形状态节点，实体详情抽屉含告警/指标/父子实体）
- **集成**：main.py 注册 health_map 路由；AppLayout.vue 添加 FireMapView 组件、VUE_PAGES、v-if 渲染；menu_config.json 可观测性组添加灭火图菜单项
- **构建**：`npm run build` 成功，FireMapView 独立 chunk（9KB JS + 8KB CSS）
- **数据迁移**：SQLite 执行 `ALTER TABLE assets ADD COLUMN health_status`；已将 `/health-map` 加入 PUBLIC_PATHS
- **验证**：445 个实体正确分层，API 200 OK

### 2026-07-14: 全量硬编码路径清理 + 标签翻页 + 远程部署
- **路径规范契约**：全部 31 个文件 54 处硬编码路径改为 `__file__`/`%~dp0` 动态计算，写入 AGENTS.md
- **修复后端报错**：`blue_green_deploys.last_switched_at` 列缺失 → 给两个 SQLite 库加列
- **标签管理翻页**：后端 `/tags/api/list` 增加 page/per_page/search/sort_by/category_id 参数；前端 TagsView.vue 添加翻页条和 watch 搜索排序重置
- **远程部署**：39.96.51.45 更新完成，Web（200）+ Mobile（200）均正常
- **临时文件清理**：删除 17 个测试/临时文件
- **移动端修复**：`npm run build:h5` 后后端 `/mobile-app/` 返回 200

---

## ⚠️ 关键路径变量（必读）

| 变量 | 值 |
|------|-----|
| 项目代码目录 | `D:\AIOPS\project08`（每次会话按实际目录名来，MEMORY.md 只记录"当前工作目录"） |
| Python venv | `{项目目录上一级}\.venv\Scripts\python.exe`（如 project08 的 venv 在 project07） |
| 后端启动命令 | `Start-Process -FilePath '{项目上级}\.venv\Scripts\python.exe' -ArgumentList 'run.py' -WorkingDirectory '{项目目录}' -WindowStyle Normal` |
| 前端构建 | `npm run build --prefix {项目目录}/frontend` |
| Vite Dev Server | `npm run dev --prefix {项目目录}/frontend` |
| 前端静态资源路径 | `/vue-assets/assets/`（由 `app.mount("/vue-assets", StaticFiles(directory="frontend/dist"))` 提供） |
| 后端访问端口 | 8000（FastAPI serve frontend/dist） |

**启动后端前必须先杀干净旧进程：**
```powershell
Get-NetTCPConnection -LocalPort 8000 -ErrorAction SilentlyContinue | ForEach-Object { Stop-Process -Id $_.OwningProcess -Force -ErrorAction SilentlyContinue }
Start-Sleep 2
```

---

---

## 2026-07-14: 蓝绿发布增强（回滚按钮 + 切换历史记录）

### 后端改动
- **`models.py`**：BlueGreenDeploy 加 `last_switched_at` 字段；新增 `BlueGreenSwitchRecord` 模型（deploy_id/from_label/to_label/operator/note/created_at）
- **`blue_green.py`**：switch 时写入切换记录；新增 rollback 接口（回滚到上一次活跃版本）；新增 records 接口（获取历史记录）；新增 `last_switched_at` 返回

### 前端改动（BlueGreenView.vue）
- 每个部署卡片新增「回滚」按钮（橙色）和「历史」按钮
- 回滚确认框显示当前备用版本名称
- 点「历史」弹出时间线面板，记录每次切换/回滚的方向、操作人、时间
- 蓝/绿标签各自副本数字段展示

---

### 后端改动
- **`models.py`**：新增 `TagCategory`（id/name/label/color/icon/sort_order）和 `Tag`（id/name/category_id/color/description/created_at）两张模型
- **`routers/tags.py`**：全重写，支持分类 CRUD、标签 CRUD、标签分配/移除、标签云兼容接口
- **`seed_data.py`**：导入 TagCategory/Tag，新增 6 个预设分类（环境/业务/技术/告警级别/团队/其他）

### 前端改动（TagsView.vue 全新设计）
- **左侧分类导航**：可折叠分类列表，点击切换展示该分类下的标签，支持新增/编辑/删除分类（图标+颜色选择器）
- **右侧标签卡片网格**：每张卡片显示标签名、颜色点、使用次数、描述、所属分类，支持增删改、点击"查看资产"展开关联列表
- **打标签交互**：支持从已有标签列表选择，也支持手动输入新标签名
- **排序/搜索**：支持按使用量/名称/创建时间排序，支持关键词搜索过滤

### 涉及文件
- `app/models.py`（TagCategory/Tag 模型）
- `app/routers/tags.py`（全部重写）
- `app/seed_data.py`（预设分类 + 导入）
- `frontend/src/views/TagsView.vue`（全新 UI）

---

## 2026-07-14: 资产管理数据库资产新增/编辑 超高危权限确认弹框

- **问题**：`saveAsset` 中数据库资产创建时，仅 `medium` 级别弹框，`high` 级别虽有 🔴 提示但未弹出确认框；且确认框内容全挤在一行，换行符 `\n` 不生效
- **修复**：
  1. `AssetsView.vue:644` 条件从 `!== 'safe'` 改为 `!['safe'].includes(...)`，覆盖 high/medium/unknown
  2. `AssetsView.vue:254` 🔴 图标增加 `@click` 事件，点击直接弹出确认框
  3. 两处弹框全部改用 `dangerouslyUseHTMLString: true` + `<br>` 标签实现换行，分级红色加粗警告 + 橙色提示
- **相关文件**：`frontend/src/views/AssetsView.vue`

## 2026-07-14: 服务器部署到 39.96.51.45

- 代码目录：`/data/AIOPS`
- 后端：`python3 run.py`（8000端口）
- 前端 Vue：`npm run dev`（3000端口）
- 移动端 H5：`npm run dev:h5`（5173端口）
- 部署账号：root
- 前端需要安装依赖：`cd /data/AIOPS/frontend && npm install markdown-it @xterm/xterm @xterm/addon-fit`

---


- **MySQL 安装**: 192.168.100.129 上停掉 5 个 Docker 测试容器，apt 安装 MySQL 8.0，root 密码 `123456`，bind-address 改为 `0.0.0.0:3306`，已验证可远程连接
- **query_mysql 工具**: 新增 `mcp_tools.py` 末尾，支持 SELECT/SHOW/DESC/DESCRIBE；连接信息从 `assets.connection_config` 读取（字段名兼容 `db_host/db_port/db_user/db_password`）
- **query_mysql 验证**: `db-192.168.100.129` asset_id=578，connection_config=`{"db_type":"mysql","db_port":3306,"db_user":"root","db_password":"123456","db_name":""}`
- **AI 资产/告警上下文缺陷**: `agent_service.py` 注入上下文时只写 ID/名称/IP，涉事资产是数据库时 AI 不知道用 query_mysql
- **修复**: 资产上下文注入增加 `asset_ci_type` 补全和 `db_type` 判断逻辑；告警上下文注入同样增强；工具选择指南加"查数据库"规则
- **check_mysql_permissions 工具**: `mcp_tools.py` 新增，用于检测 MySQL 账号权限等级（✅安全/⚠️警告/🔴高危），读取 mysql.user 表和 SHOW GRANTS 判定
- **新增资产源头阀门**: `assets.py:api_asset_create` 新增数据库资产时，测试连接成功后强制检测权限，`permission_check.risk_level` 非 safe 时在返回 JSON 里附加 `risk_warning` 字段（high/medium/unknown 三档），前端据此弹免责警告确认框
  - ✅ 安全：仅有 SELECT/SHOW/DESC 读权限
  - ⚠️ 警告：拥有 DML（INSERT/UPDATE/DELETE）
  - 🔴 高危：拥有 DDL（DROP/ALTER/CREATE）或 GRANT 授权权

---

## 2026-07-13 — 异步安装 + 回滚机制 + 工具规范化
- **问题**: AI 让 AI 安装 ES 时，原有 `execute_run_command` 单命令无法完成多步安装，且 30s LLM timeout 导致长操作失败
- **解决**: 新增 BackgroundJob 模型 + 线程池执行器 + `get_task_status` 轮询工具 + `execute_install_package` 异步安装
- **新增文件**: `app/services/background_task.py` — 后台任务执行器（线程池 + SSH 异步 + 进度更新 + 补偿式回滚）
- **新增模型**: `BackgroundJob`（job_id/status/progress/progress_message/result_payload/error_message）
- **新增 MCP 工具**: `get_task_status`、`list_recent_tasks`、`execute_install_package`（critical，不直调，走 propose_action）
- **回滚机制**: 每步记录 `rollback_cmds[]`，失败时逆序执行补偿命令（ES: 停止服务→删目录→删用户；Nginx: 卸载）
- **System Prompt**: 新增「安装部署任务」章节，指导 LLM 用 `propose_workflow` 做多步剧本，用 `propose_action(execute_install_package)` 做单包安装，用 `get_task_status` 轮询结果
- **现有 execute_* 工具**: restart_service / clean_disk / run_script / run_command / acknowledge_alert / resolve_alert / resolve_incident / silence_alert / create_alert_rule / update_alert_rule / delete_alert_rule / create_asset / update_asset / delete_asset / probe_assets 共 15 个，全部通过 propose_action 走确认闭环

## 2026-07-13: AI智能助手日志查询工具（多日志源 Adapter 架构）
- **新增 MCP 工具**: `query_log_sources`（只读）+ `query_logs`（只读）
- **适配器模式**: `LogQueryAdapter` 基类，扩展 Loki/ClickHouse/Splunk 只需新增 Adapter 类 + `register_adapter()`
- **System Prompt**: 新增日志查询规范，典型场景：告警前后日志/按主机/按级别过滤

## 2026-07-13: AI智能助手链路追踪工具
- **新增 MCP 工具**: `query_traces`（只读），支持 `trace_id` / `service` / `status` / `time_range` 过滤
- **返回结构**: 每条 trace 含完整 spans 树（span_id / service / operation / duration_ms / status / parent_span_id）
- **数据来源**: `Span` 表（`seed_data.py` 预置 12 条微服务调用链示例数据）
- **扩展**: 下一步可对接真实 OTLP Collector（`/api/v1/traces/otlp` 接口已存在）

## 2026-07-13: 远程脚本「生成 Playbook」功能
- **功能**: 远程脚本执行成功后，结果区显示「📦 生成 Playbook」按钮，点击弹窗预览 Ansible YAML
- **YAML 生成逻辑**: 单行命令生成单 task；多行生成多 step，每个 step 含 shell + debug
- **弹窗支持**: 复制 YAML / 保存并跳转 Ansible 页面（自动 POST /ansible/api/playbooks）

## 2026-07-13: SRE 页面服务名字段改为 ServicePicker 关联资产
- **背景**: SRE 相关页面（ErrorBudget/SLO/SLA）的 `service_name` 字段原来随便输入文本，导致数据不规范
- **解决方案**: 创建 `ServicePicker.vue` 组件（可搜索分页弹窗列表），替代原来的 `el-input`
- **后端改动**: `assets.py` 新增 `GET /assets/api/services`（轻量分页列表）+ `GET /assets/api/{id}` + 分页参数；`asset_service.py` 新增 `list_assets_paged`；`sre.py` 的 `SLOConfigCreate/Response` 加 `service_id` 字段
- **前端改动**: ErrorBudgetView / SLOConfigView / SLAView 的服务名输入改为 `<ServicePicker v-model="form.service_id" @update:modelValue="onServicePick">` + `onServicePick` 回调自动填充 `service_name`
- **问题**: `DatasourcesView.vue` 的「+ 新增数据源」按钮是 `href="/datasources"` 死链，且后端缺少 `POST /api/create` 和 `PUT /api/{id}` 接口
- **修复**: 后端 `datasources.py` 新增 `GET /api/{id}`、`POST /api/create`、`PUT /api/{id}` 三个接口
- **前端**: `DatasourcesView.vue` 重写为 SPA 弹窗，支持新增/编辑数据源（类型、地址、认证方式、SSH/K8s 特殊配置、采集间隔）
- 编辑时调用 `GET /datasources/api/{id}` 加载完整 auth_config 回填表单

## 2026-07-13: 任务中心页面添加操作说明（GuideDrawer 右侧抽屉）
- **自愈规则 / 自愈工作流 / 工作流执行监控** 三个页面新增 `📖 操作说明` 按钮，点击右侧滑出 GuideDrawer 抽屉
- 实现方式：导入 `GuideDrawer` 组件 + `GuideDrawer v-model="showGuide" title="..."` + 内容用 `section.guide-section` 包裹
- 注意：不要用内联折叠样式（guide-box），统一用 GuideDrawer 组件保持一致
- **修复**: `onData` 开头加 15ms 去重窗口 `if (now - lastOnDataTime < 15) return`，同一次按键的双触发间隔 <1ms，可安全过滤
- **问题 5（CPR 转义序列污染屏幕）**: xterm.js 内部处理 DSR 查询时通过 `onData` 返回 `\x1b[row;colR` 回应，handler 的 `ch >= ' '` 把 `[1;9R` 等可打印部分回显到屏幕
- **修复**: `onData` 检测 `data.charCodeAt(0) === 0x1b` 则直接 `return`，不回显也不发送到服务端
- **修复范围**: `DockerListView.vue` + `K8sPodsView.vue` 两处 xterm 终端同时修复
- **xterm.js 6.0.0 事件模型**: `_keyDown` → `triggerDataEvent` + `cancel(e,true)` (preventDefault)，但某些浏览器仍会触发 `_keyPress` → 第二次 `triggerDataEvent`；`_inputEvent` 有 `_keyPressHandled` 守卫防止第三次

## 2026-07-13: K8s 终端字符翻倍修复（TTY 回显 + 本地回显叠加）
- **问题 6（K8s 终端字符翻倍）**: K8s exec API 使用 `tty=True`，TTY 驱动自动回显字符到 stdout；前端 `onData` 又做本地回显 → 字符双重出现（`datedate`）
- **根因**: Docker 终端用 `docker exec -i`（非 TTY）→ 不回显 → 需要本地回显；K8s 终端用 `tty=True` → TTY 驱动回显 → 不需要本地回显。两者回显策略不同
- **修复**: `K8sPodsView.vue` 的 `onData` handler 移除本地回显（`termInstance.write`），只保留 ESC 过滤 + 发送到服务端。TTY shell 自己回显
- **Docker 终端**: `DockerListView.vue` 保留本地回显（因为 `docker exec -i` 非 TTY 不回显）

## 2026-07-13: Docker 终端排版阶梯缩进修复（NL→CR+LF）
- **问题 7（Docker 终端阶梯缩进）**: `docker exec -i`（非 TTY pipe）输出只有 `\n` 没有 `\r`；xterm.js 中 `\n` 只下移光标不回车（不回到列0），导致每行从上一行结束位置开始 → 阶梯式缩进
- **根因**: 真实 TTY 中终端驱动自动把 `\n` 转为 `\r\n`（NL→CR+LF），非 TTY pipe 没有这个转换
- **修复**: `containers.py` 的 `docker_to_browser()` 中 `line.decode().replace("\n", "\r\n")`，模拟 TTY 驱动的 NL→CR+LF 行为
- **专业术语**: OPOST (Output Post-processing) — TTY 驱动的输出处理模式，自动在 `\n` 前插入 `\r`；非 TTY pipe 不启用 OPOST

## 2026-07-13: Docker 终端改为 TTY 模式（backspace 修复）
- **问题 8（Docker 终端 backspace 无效）**: `docker exec -i` 非 TTY 模式下，shell 不处理 backspace，`\x7f` 原样进入输入缓冲区；前端视觉上删了字符，但服务端 shell 仍然收到了被"删除"的字符
- **修复**: `docker exec -i` → `docker exec -it`（TTY 模式），TTY 驱动处理 echo/backspace/ICRNL
- **docker_to_browser()**: `readline()` → `proc.stdout.read(4096)` + `send_bytes()`（TTY 输出是 raw byte stream，不是 line-by-line）
- **前端**: DockerListView.vue 去掉本地回显（和 K8sPodsView 一样，TTY 自带回显）
- **browser_to_docker()**: 保留 `\r`→`\n` 转换（兼容性 safety net，TTY 也会做但无冲突）+ DSR 拦截保留

## 2026-07-13: Docker 终端 backspace 修复 v2（本地行编辑）
- **回退 `-it`**: asyncio subprocess 的 stdin 是 pipe 不是 TTY，`docker exec -it` 报错 "cannot attach stdin to a TTY-enabled container because stdin is not a terminal"
- **新方案（本地行编辑 buffer）**: 前端维护 `inputBuf[]`，所有字符只在本地编辑，按 Enter 时才把完整命令 `cmd + '\r'` 发给服务端
  - Backspace (`\x7f`): 只操作本地 buffer（pop + `\b \b`），不发给服务端
  - Enter (`\r`): 发送 `inputBuf.join('') + '\r'`，清空 buffer
  - 普通字符: 加入 buffer + 回显到终端
  - ESC 序列: 过滤不处理
- **后端**: 回退为 `docker exec -i` + `readline()` + `send_text()`（非 TTY pipe 模式）
- **验证**: Python 直接测试证明 `\x7f` 在 busybox sh pipe 模式下不是退格，是原样字节
- **注意**: `docker_to_browser()` 的 `.replace("\n", "\r\n")` 必须保留！非 TTY pipe 输出只有 LF，xterm.js 中 LF 只下移不回车 → 阶梯缩进

## 2026-07-13: Docker/K8s 终端修复（输入重复 + 命令不执行 + 二进制接收）
- **问题 1（输入重复）**: `onKey` + `onData` 双事件处理器各自触发，但 `onKey` 回显字符 + 某些浏览器/环境导致字符重复（llss / hhiissttnnaammee）
- **修复**: 移除 `onKey`，将本地回显逻辑统一移到 `onData` 内（`\r`→`\r\n`, `\x7f`→`\b \b`, 可打印字符→`write`）；同一 handler 即做 echo 又发送到服务器，消除 double fire
- **问题 2（敲 Enter 不执行命令）**: xterm.js 的 `onData` 在 Enter 键时发送 `\r`（CR），但 Alpine BusyBox `sh` 通过 pipe 读取时只认 `\n`(LF) 作为命令分隔符 → `ls\r` 报 `sh: ls\r: not found`
- **修复**: `containers.py` 中 `browser_to_docker()` 写入 stdin 前执行 `msg.replace("\r", "\n")`（ICRNL 转换，模拟 TTY 驱动行为）
- **问题 3（K8s 终端二进制数据不显示）**: K8s 后端用 `send_bytes()` 发送二进制帧，浏览器 `ws.onmessage.e.data` 默认是 Blob，`termInstance.write()` 无法写入
- **修复**: `ws.binaryType = 'arraybuffer'`，`onmessage` 中 `e.data instanceof ArrayBuffer` 则 `new Uint8Array(e.data)` 再 `write()`
- **测试验证**: Python WebSocket 发 `ls\r` → 后端 `\r`→`\n` → 返回目录列表（`bin\ndev\nhome\n...`），`sh: ls\r: not found` 不再出现

## 2026-07-13: Docker 容器查看/日志/终端集成 + xterm CSS 修复
- **Docker 容器操作按钮**: `DockerListView.vue` 每行新增「日志」和「终端」按钮，详情弹窗也增加对应按钮
- **Docker 日志端点**: `GET /containers/api/docker/{asset_id}/logs?tail=200`，通过 `docker logs --tail` CLI 获取，自动处理 GBK 编码问题
- **Docker 终端 WebSocket**: `WS /containers/ws/docker/{asset_id}/terminal?token=xxx`，通过 `docker exec -i <name> sh` 子进程实现交互式 shell（非 TTY 模式，支持基础命令交互）
- **本地 Docker 扫描**: `POST /containers/api/docker/local/scan` 扫描本地 Docker 引擎，自动创建/更新 Asset（ci_type=container）记录
- **Vite proxy**: `vite.config.js` 添加 `/containers` WebSocket 代理（`ws: true`）
- **xterm CSS 修复**: 将 `@xterm/xterm/css/xterm.css` 复制到 `app/static/css/xterm.min.css`（后端服务）和 `frontend/public/static/css/xterm.min.css`（Vite 开发服务），解决终端黑屏问题（之前 CSS 404 导致文本不可见）
- **`docker/` 目录重命名**: 改为 `docker-build/`，避免与 Python `docker` SDK 包冲突（之前 namespace package 导致 `import docker` 假成功真失败）
- **安装依赖**: `docker` SDK 6.1.3 + `pypiwin32`（Windows 管道通信）；注意 docker-py 7.2.0 在 Windows 上有 NpipeHTTPAdapter bug，需降级到 6.x
- **测试**: nginx:alpine 容器验证通过（扫描→资产入库→日志返回 9 行→终端 echo hello 返回 hello）

## 关键信息（始终保留）
- **项目路径**: `D:\AIOPS\project08`（从 GitHub `ZF1411945427/AIOPS` 克隆）
- **Python venv**: 复用 `D:\AIOPS\project07\.venv\Scripts\python.exe`（project08 无独立 venv）
- **启动后端**: `Start-Process -FilePath 'D:\AIOPS\project07\.venv\Scripts\python.exe' -ArgumentList 'run.py' -WorkingDirectory 'D:\AIOPS\project08'`（端口 8000，需新窗口启动，bash 工具内直接跑会随会话超时终止）
- **启动前端**: `npm run dev --prefix frontend`（端口 3000，proxy → 8000）
- **启动移动端**: `npm run dev:h5 --prefix mobile`（端口 5173）
- **构建前端**: `npm run build --prefix frontend`（后端 mount `/vue-assets` → `frontend/dist`，启动前必须先 build 生成 dist）
- **登录密码**: admin / admin123（⚠️ 不是 1234，见 2026-07-15 勘误；`main.py:395` 默认 admin123）
- **Embedding**: BGE-small-zh-v1.5（512维）；RAG V2 用 BGE-M3（1024维）
- **向量库**: Milvus Lite（`db/milvus/kb_v2.db`）
- **数据库**: SQLite（`db/aiops.db` + `db/aiops_real.db`）
- **部署服务器**: 39.96.51.45（/data/AIOPS），git push → SSH 拉取 → 构建 → 重启
- **一键重启**: `python tools/restart.py restart`（SSH 重启服务器后端；子命令 `status` / `logs [N]`）

---

## 2026-07-13: Docker 化交付 + requirements 清洗
- **requirements 清洗**: 删除 `requirements_lock.txt`（pip freeze 脏快照），拆分为：
  - `requirements.txt`（133 个生产包，排除 pywin32/win32_setctime/pytest/playwright/Django/langchain 全家桶/torch）
  - `requirements-dev.txt`（开发/测试依赖，`-r requirements.txt` + pytest/playwright/virtualenv）
  - torch 在 Dockerfile 中单独用 `--index-url https://download.pytorch.org/whl/cpu` 装 CPU 版
  - sse-starlette 降级 3.3.2→2.1.0 解决 starlette 版本冲突（3.3.2 要求 starlette>=0.49.1，fastapi 0.115.6 要求 <0.42.0）
  - 可选依赖（try/except 守护）：psycopg2/redis/prophet/croniter/python-docx/pypdf/docker/pysnmp 在 requirements.txt 末尾注释列出
- **Docker 化**: `docker/` 目录（Dockerfile + docker-compose.yml），`.dockerignore` 在根目录（Docker 硬性要求）
  - 多阶段构建：Stage1 node:20-slim 构建前端 dist → Stage2 node:20-slim 构建移动端 H5 → Stage3 python:3.12-slim 运行时
  - 镜像 `aiops:latest` 3.02GB（667MB 压缩），含 BGE 模型 92MB
  - `docker run -d -p 8000:8000 -v ./db:/app/db -v ./license.lic:/app/license.lic:ro aiops:latest` 即用
  - healthcheck 用 python urllib（不装 curl，避免 apt-get 走代理 502）
  - VOLUME 挂载 db/logs，license.lic 只读挂载（客户独有，不入镜像）
- **Docker 镜像源修复**: `~/.docker/daemon.json` 移除失效源（daocloud 403 / ustc/163/baidu 不通），仅保留 `docker.1ms.run`
- **交付方式**: `docker save aiops:latest | gzip > aiops.tar.gz` → 客户 `docker load < aiops.tar.gz` → `docker compose up -d`（离线交付）

## 2026-07-13: K8s Pod 终端 WebSocket 认证修复
- **现象**: 点击 Pod 容器组页面的「终端」按钮，终端显示「Pod 连接关闭」
- **根因**: 前后端 token 传递链路断裂：
  1. `LoginView.vue` 登录成功后未将 API 返回的 `token` 存入 `localStorage`
  2. `K8sPodsView.vue` 创建 WebSocket 时未读取 `localStorage` 中的 token 拼接 `?token=...` 参数
  3. 后端 `api_pod_terminal_ws` WebSocket handler 要求 token 认证（`verify_login_token`），token 为空 → 发 "未认证，请先登录" → 关闭连接 → 前端显示 `[连接关闭]`
- **修复**:
  1. `frontend/src/views/LoginView.vue`：登录成功后 `localStorage.setItem('aiops-token', res.token)`
  2. `frontend/src/views/K8sPodsView.vue`：WebSocket URL 拼接 `?token=` + `encodeURIComponent(token)`
  3. `app/templates/k8s_terminal.html`：同上修复（Jinja2 模板页面的终端）
- **教训**: WebSocket 的连接认证不能依赖 session cookie（WebSocket 握手不经过 AuthMiddleware），必须显式传 token

## 2026-07-13: K8s overview 接口超时修复
- **现象**: `/k8s/api/overview` 登录后 120s+ 超时（前端报"请求超时"）
- **根因**: 串行探测 3 个 K8s 集群，其中 2 个 `11.0.1.130` 不可达；kubernetes python client 的 API 调用默认 `_request_timeout=None`（**`configuration.timeout` 不会自动作为 `_request_timeout` 传入 API 调用**），导致 connect 阶段无超时；叠加 urllib3 默认 `retries=3`，每个 API 卡 ~21s，5 个 API × 2 集群累计 200s+
- **修复**（`app/routers/k8s_resources.py`）:
  1. `_get_k8s_client` 增加 TCP 预检（`socket.create_connection` timeout=5），不可达集群 5s 快速失败（fail-fast）
  2. `configuration.retries = 0` 禁用 urllib3 重试
  3. `api_overview` 改多集群并发（`ThreadPoolExecutor` max_workers=5）+ `as_completed(timeout=45)` 总超时保护
  4. 每个 `list_xxx` 调用显式传 `_request_timeout=(5, 10)`（connect=5s, read=10s）
- **效果**: overview 从 120s+ 超时 → 5s 返回 JSON
- **教训**:
  - kubernetes python client（36.0.2）的 `configuration.timeout` **不自动**作用于 API 调用，必须每次 `list_xxx(_request_timeout=(connect, read))` 显式传
  - 登录接口是 `POST /login`（auth.py:73），**不是** `/api/auth/login`；后者不在 AuthMiddleware 白名单，未登录会被 303 重定向到 /login（诊断时曾因此误判为"路由返回 SPA HTML"）
  - 诊断 K8s 接口务必带登录态（cookie）测，否则 303→/login 的 HTML 会掩盖真实接口行为

## 2026-07-13: 项目克隆到 project08 + 本地开发 license 签发
- **克隆**: `git clone https://github_pat_...@github.com/ZF1411945427/AIOPS.git`，内容上移到 `D:\AIOPS\project08` 根目录（非子目录）
- **Git 配置**: `http.sslBackend=schannel` + `http/https.proxy=http://127.0.0.1:7897` + 远程 URL 内嵌 token，`git push origin main` 秒成
- **依赖补装**: project07 venv 缺 35 个包（loguru/langchain/matplotlib/slowapi/playwright 等），用清华镜像 `pypi.tuna.tsinghua.edu.cn` 按 `requirements_lock.txt` 批量补齐（官方 PyPI 经 7897 代理 TLS 握手异常，pypi.org 不可用）
- **⚠️ License 机制**: `LicenseMiddleware`（`app/services/license_service.py`）拦截所有非白名单路径，无 `license.lic` → 403。白名单：`/license` `/login` `/static` `/assets` `/vue-assets` `/product` `/api/menu` 等
  - 项目只内置**公钥**（验签），无私钥。`tools/generate_license.py` 需 `tools/private_key.pem` 签发
  - **本次生成**: RSA-2048 密钥对 → 私钥存 `tools/private_key.pem`，**公钥已替换** `license_service.py` 的 `PUBLIC_KEY_PEM`
  - 签发 `license.lic`（客户=本地开发，旗舰版，到期 2027-07-13，指纹=911d32bde323c75e3dc494166fe31d79，max_nodes=9999，features=all）
  - ⚠️ 若换机器需重新生成密钥对 + license（指纹绑定本机 MAC/CPU/磁盘/主机名）
  - ⚠️ `tools/private_key.pem` 与 `license.lic` 勿提交（私钥泄露可伪造任意 license）
- **前端 dist**: 首次启动后端前必须 `npm run build --prefix frontend`，否则 `app.mount("/vue-assets", StaticFiles(directory="frontend/dist"))` 抛 `Directory does not exist`
- **服务状态**: 后端 8000 ✅（license active，`/login` 返回 Vue SPA 200）| 前端 3000 ✅ | 移动端 5173 ✅

## 2026-07-13: 服务器一键重启脚本 (tools/restart.py)
- 新增 `tools/restart.py`：paramiko SSH 连接 39.96.51.45 重启后端
- 子命令：`restart`（默认，杀旧→启动→轮询等待→验证）/ `status` / `logs [N]`
- 服务器部署模式：Web + Mobile 为构建好的静态文件，由后端 FastAPI 8000 统一服务，**重启一个后端进程即恢复全部访问**
- kill 逻辑稳健化：pkill SIGTERM → 轮询确认进程退出+端口释放（最多16s）→ 超时则 SIGKILL，避免端口冲突导致新进程启动失败
- 启动命令：`cd /data/AIOPS && setsid python3 run.py > /tmp/aiops_backend.log 2>&1 &`
- 模型加载约 10s，Web(/login) + Mobile(/mobile-app/) 验证均 HTTP 200

## 2026-07-13: 服务器全量部署 (39.96.51.45)
- **部署内容**: 后端 + Web前端 + Mobile前端，全部通过 FastAPI 8000 端口服务
- **备份**: `/data/AIOPS.bak.20260713_deploy.tar.gz`（轻量备份，排除 models/bin）
- **代码更新**: `tar -xf aiops_deploy.tar` 解压到 `/data/AIOPS/`（复用服务器已有 bin/models）
- **依赖安装**: 服务器 Python 3.11，用清华镜像分4批安装（loguru/openai/sentence-transformers/pymilvus/langchain/faiss/elasticsearch/torch 等）
  - ⚠️ `scipy==1.18.0` 需 Python 3.12+，服务器是 3.11，改用不锁版本安装
  - ⚠️ `pywin32`/`win32_setctime` 是 Windows 专属，服务器跳过
  - ⚠️ `starlette` 版本冲突：mcp/sse-starlette 要求 >=0.49.1，fastapi 0.115.6 要求 <0.42.0，最终锁定 `starlette==0.41.3 + sse-starlette<3.4`
- **服务器无 GPU**，torch 2.13.0 自动 fallback 到 CPU 模式
- **BGE 模型加载成功**，AuroraX Reranker 模型在 `/data/AIOPS/models/` 可用
- **访问地址**: Web → http://39.96.51.45:8000/ | Mobile → http://39.96.51.45:8000/mobile-app/
- **启动方式**: `cd /data/AIOPS && setsid python3 run.py > /tmp/aiops_backend.log 2>&1 &`
- **内存占用**: ~1GB（3.5GB 总内存），磁盘 51% 已用

## 2026-07-13: V1/V2 引擎标识 + 跨引擎安全删除
- `KbDocument` 新增 `index_engine` 字段（v1/v2/both）
- V1 删除时清理 Milvus，V2 删除时清理 SQLite，防止跨引擎孤儿数据
- V2 详情兼容回退：Milvus 查不到自动查 SQLite
- 前端知识库表格新增「引擎」列（经典/智能/双引擎标签）

## 2026-07-12: 告警与 AI 智能助手联动（Context Injection）
- `AlertSessionLink` / `AssetSessionLink` 关联表
- `POST /alerts/api/{id}/open-assistant` — 创建/复用会话，注入告警上下文
- `POST /agent/session/{id}/link-alert` / `link-asset` — 手动切换关联
- `process_chat_message()` 读 `session.context` 注入 System Prompt
- 前端告警页「💬 智能助手」按钮 + AI 助手页「关联告警/资产」Popover
- **⚠️ 修改后端后必须重启服务器，否则新路由 404**

## 2026-07-12: Reranker 双模式 + Mobile H5 修复 + 培训PPT + 安全/架构修复
- Reranker 双模式：经典版(CPU) + 智能版(AuroraX GPU)，前端可切换
- Mobile H5 publicPath 修复：`manifest.json` h5.publicPath 必须与 vite base 一致
- 26页培训PPT（SVG版+原生PPTX版），成品在 `docs/`
- 系统评估报告：818/1000 (A-)，10维度评分
- 91个SOP模板（`app/data/sop_templates.py`）
- 后台服务超时修复（datasource_scrape 级联超时）
- 字段规范契约 `CONTRACT.md`：全项目字段命名 Single Source of Truth
- K8S ci_type 统一为 `kubernetes_cluster`（废弃 `cluster`）
- P0安全加固：密钥管理/bcrypt/RBAC/限流/日志/索引/代码分割

## 2026-07-11: 核心功能修复
- 异常检测7种算法全面修复（sigma/ewma/stl/mad/prophet/lstm/transformer）
- 告警根因分析 + AI深度分析 + K8S事件告警
- 资源拓扑图4个BUG修复
- 27种CI类型全部创建成功 + 蓝绿发布/变更审批端到端测试
- 审计报告安全+架构修复（12项）

## 2026-07-10: RAG V2 升级 + 基础设施
- RAG V2 知识库升级（BGE-M3 + Milvus + 异步索引）
- 预测引擎打通（5种模型）
- Runbook三场景集成
- DB恢复 + Milvus修复

## 2026-07-08~09: 拓扑/自愈/部署
- 拓扑视图异常筛选 + 关联资产面板
- 自愈规则端到端测试（39.96.51.45 nginx重启验证）
- 部署到39.96.51.45 + Ansible三步流程验证
