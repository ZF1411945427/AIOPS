# AIOps 项目记忆

> 每次会话开始时读取。按时间倒序,最新在最上面。完整历史见 git log。

### 2026-07-30: 新增「暗色玻璃」全局主题 + 智能助手页适配
- **新增全局主题 `dark-glass`**: 顶栏 Brush 弹窗新增第三个主题选项「暗色玻璃」。`html[data-theme="dark-glass"]` 覆盖全部 CSS 变量:纯黑背景 `#000`、卡片 `rgba(255,255,255,0.04)` + `backdrop-filter: blur(20px)`、细白描边 `rgba(255,255,255,0.07)`、青绿强调色 `#00e096`
- **智能助手页适配**: AgentChatView.vue 全部硬编码色值通过 `!important` 全局覆盖，涵盖侧边栏/消息气泡/输入框/发送按钮/模式标签/子智能体/待办确认等所有组件，切到 dark-glass 主题时颜色正确切换
- **改动文件**: `AppLayout.vue`(弹窗加第三个选项)、`main.css`(新增 dark-glass 全局变量 ~300 行 + AgentChatView 适配 ~200 行)

### 2026-07-30: 顶栏外观设置弹窗→玻璃拟态风格改造
- **顶栏 Brush 弹窗重设计**: 去掉多余的全屏页面和菜单项，原样保留顶栏 Brush 图标交互。弹窗改用玻璃拟态风格（纯黑半透明背景 `rgba(10,10,10,0.92)` + `backdrop-filter: blur(32px)` + 细白描边 + 多层软阴影 + 青绿强调色 `#00e096`）
- **弹窗结构**: 顶部 SVG 齿轮图标 + 标题区域 → 主题模式（亮色/暗色，带发光圆点指示器）→ 强调色系（靛蓝/赤陶，带色块选中光晕）→ 玻璃拟态概念预览（3层亚克力磨砂方块 + 说明文字）
- **改动文件**: `AppLayout.vue`（弹窗模板）、`main.css`（`.glass-popover` + `.ap-*` 样式类）。新建的 `AppearanceSettingsView.vue` 已删除，菜单项已移除

### 2026-07-30: 自愈工作流大修 — 从不可用到真实可用
- **工作流 3 个致命硬伤修复**:
  1. **healthcheck 动作不存在** → 前端下拉菜单有但 `execute_action` 未实现，执行必报"未知操作类型"。新增 `healthcheck` 分支：SSH 执行 `systemctl is-active` 或 `uptime`；K8s 执行 `kubectl rollout status`/`get pod`；Docker 执行 `docker exec echo`
  2. **规则触发不走工作流** → `check_and_remediate` 只匹配 `AutoRemediation`（单动作规则），不匹配 `RemediationWorkflow`，工作流只能手动或 AI 推荐触发。修复：在 AutoRemediation 匹配失败后，按 `alert.rule_id` 匹配 `RemediationWorkflow.rule_id`，匹配成功则生成 `PendingAction(action_type="workflow")`
  3. **手动触发不按 rule_id 匹配** → `alerts.py` 的 `/api/{alert_id}/heal` 取第一个全局启用的工作流，而不是按告警规则匹配。修复：先按 `alert.rule_id` 匹配 `workflow.rule_id`，无匹配再回退到第一个全局启用工作流
- **前端编辑功能** → 原来只有创建/删除，无编辑。新增编辑按钮 + 编辑弹窗（复用创建弹窗，isEditing 模式），新增 `POST /api/{wf_id}/update` 后端端点
- **步骤参数预览** → 卡片上显示每个步骤的参数（如 `healthcheck`、`restart:nginx`、`clean:/var/log`），让用户不用点开就能看到完整步骤
- **dry-run 模拟模式** → 新增「🔍 模拟」按钮，调用 `POST /api/{wf_id}/run?dry_run=true`，不执行真实操作只返回模拟结果，弹窗展示每步的预期输出
- **日志 FK 修复** → `RemediationLog.remediation_id` 原 FK 指向 `auto_remediations.id`，但工作流日志写入的是 `workflow.id`，两表 ID 冲突。修复：改为无 FK 的普通列，新增 `remediation_type` 列（"rule"/"workflow"）区分来源
- **迁移** → `main.py` `_MIGRATIONS` 新增 `remediation_logs` + `remediation_effects` 的 `remediation_type` 列
- **操作手册** → `docs/自愈工作流操作手册.md` 含 3 种触发方式、6 种动作对比表、模拟/运行/日志查看流程、常见问题排查、3 个推荐模板
- **验证**: 前端构建通过；后端启动正常；workflow 创建 API 返回 `{"ok":true, "id":1}`；healthcheck 执行不崩溃（资产不可达时返回明确错误信息）
- **改动文件**: `remediation_service.py`(healthcheck 分支 + check_and_remediate 工作流匹配)、`remediation_workflow.py`(编辑 API + dry-run + remediation_type)、`alerts.py`(heal 按 rule_id 匹配 + remediation_type)、`models.py`(RemediationLog 修复 FK + 加 remediation_type)、`main.py`(迁移)、`RemediationWorkflowView.vue`(编辑/模拟/参数预览/全量重写)

### 2026-07-30: 新增「暗色玻璃」全局主题 + 智能助手页适配
- **AI 方案状态消失 Bug 修复**: `RemediationView.vue` 的 `restoreAiState()` 原从 `pendingActions`(按 `pendingFilter` 过滤)恢复,但已执行/取消的 PA 不在列表中 → 刷新后 AI 按钮变回 idle。改为独立 `async restoreAiState()`,单独请求 `/remediation/api/ai-pending?status=all` 获取全状态 PA 匹配,不受筛选影响
- **功能1 自愈→智能助手转交通道**: 后端新增 `POST /agent/transfer-from-remediation`(注入告警+诊断报告+AI方案上下文→创建 Agent 会话→自动发起深度分析)。前端 PA 卡片加"🔄 转交智能助手"按钮(pending/failed/executed 三态均可用),用 `window._pendingAgentSessionId` 跳转打开对应会话
- **功能2 执行成功自动沉淀知识**: `confirm_ai_action` 单步+workflow 两条路径,执行成功后将 alert 置 resolved 并调 `knowledge_autogen_service.generate_draft(alert_id)` 自动生成知识草稿(失败静默不阻塞)
- **功能3 风险分类器复用**: `mcp_tools.py` 的 `propose_action` 对 `run_command` 类型新增确定性分类器覆盖 — 调 `remediation_service._classify_command_risk` 按 SQL 命令语义硬判定,取分类器与 LLM 评估中更高者,防 LLM 降级高危命令
- **功能4 CI-Type-Aware 执行通道复用**: `mcp_tools.py` 的 4 个 `execute_*` 工具移除 `connection_type != "ssh"` 硬限制,改为传 `db` 给 `execute_action` 让其按 ci_type 自动分派 SSH/K8s/Docker 通道
- **功能5 关联分析注入**: `ai_self_heal_analyze` 的 user_prompt 新增 `correlation_section`,调 `run_correlation_analysis(db, hours=1, asset_id)` 获取同期告警/指标异常/日志异常/变更记录注入,让自愈 AI 看到多维数据而非仅本机诊断
- **功能6 预置诊断命令包 MCP 工具**: `mcp_tools.py` 新增 `run_preset_diagnosis` 工具(expose_to_llm=True, read_only),复用自愈 `DIAGNOSIS_COMMAND_PACKS` + `run_diagnosis`,按 metric_name 自动匹配诊断包执行,AI Agent 可一键跑完整诊断命令集
- **验证**: 前端构建通过;后端重启后 `/agent/transfer-from-remediation` 返回 `{"session_id":1}`;`/agent/api/capabilities` 含 `run_preset_diagnosis` + `query_correlation_analysis`
- **二次修复(自检发现3个缺点已修复,3个限制已优化)**:
  1. `_RISK_MAP` 缺 critical → execute_run_command/script 注册为 critical 但分类器覆盖逻辑 `_RISK_MAP.get("critical",2)` 返回 2(medium) → critical 被降级为 high。修复:加 critical:4
  2. `execute_action` 的 run_command 分支仍有 `channel != "ssh"` 限制 → 功能4移除 mcp_tools 限制后 K8s/Docker 资产仍被底层拒绝。修复:K8s/Docker 通道放行只读命令(分类器 auto_exec=True),变更命令拒绝并提示用 restart/scale
  3. `run_preset_diagnosis` 无 alert_id 时调 `run_diagnosis(alert_id=0)` → run_diagnosis 第一步查 Alert 失败返回"告警不存在"。修复:无 alert_id 时直接用 DIAGNOSIS_COMMAND_PACKS+_remote_exec 执行不存报告;有 alert_id 时走 run_diagnosis 存报告
- **3个限制优化**:
  1. 自动沉淀知识不再强制置 resolved → `generate_draft` 加 `force=True` 参数跳过 status 检查,调用方传 `force=True` 不改变告警状态语义
  2. 关联分析加短时缓存 → `_get_correlation_cached(asset_id, hours=1)` 60 秒内复用,避免每次 AI 分析重复查询
  3. script 动作扩展到 K8s/Docker → 新增 `_k8s_exec_command`(kubectl exec)+`_docker_exec_command`(宿主机 SSH docker exec),K8s/Docker 也可执行脚本

### 2026-07-29: 规则自愈 AI 分析前端超时修复(axios 默认 30s 掐断 LLM 请求)
- **根因**:`RemediationView.vue` 的 4 个 AI/诊断请求未传 timeout,用 axios 全局默认 `timeout:30000`(30s)。而 diagnose 接口 SSH 跑多条诊断命令(30s+),ai-analyze 调 GLM-5.2 推理(25~90s,后端 `timeout_override=120`),均超 30s → 前端 axios 主动断开 → "请求超时"。后端其实仍在跑但 `ai_self_heal_analyze` 无入口日志,故日志看不到请求
- **对比**:其他 LLM 页面(IncidentsView/DiagnosticToolsView/AlertsView/AgentGroundTruthView)均正确传 `{timeout:130000}`,唯独 RemediationView 漏传
- **修复**:`RemediationView.vue` 4 处加 `{ timeout: 130000 }`:`restoreDiagnosisState`(451)、`runDiagnoseGroup`(482)、`aiAnalyzeGroup`(504 diagnose+505 ai-analyze)、`reanalyze`(618 ai-reanalyze)。构建通过
- **教训**:凡调 LLM(call_llm)或 SSH 诊断的接口,前端 axios 必须显式传 timeout≥130000,不能用全局默认 30s;否则"前端先断、后端还在跑"的静默超时极难排查

### 2026-07-29: 自愈 AI 迭代诊断循环(Agentic Diagnostic Loop)+ 菜单改名 + .gitignore
- **菜单改名**: "灭火图"→"架构巡检图"（`menu_config.json` + `FireMapView.vue` 标题/副标题）
- **.gitignore**: 新增 `tools/public_key.pem`（`tools/private_key.pem`、`license.lic` 原有）
- **迭代诊断循环**: `ai_self_heal_analyze` 从 One-shot 改为最多 5 轮迭代。每轮 AI 判断 `diagnosis_sufficient`，不够则推荐 `next_tools`（最多 5 个/轮），系统自动执行只读诊断工具（复用 `diagnostic_tools.py` 工具池），补诊结果存入 `DiagnosisReport`（带 `round_num`），下一轮 AI 基于累积证据再分析，直到根因确定或达上限
- **后端改动**: 
  - `models.py`: `DiagnosisReport` 加 `round_num` 字段（0=初诊，1..N=补诊）
  - `main.py`: `_MIGRATIONS` 加 `diagnosis_reports.round_num` 列
  - `remediation_service.py`: 新增 `_execute_diagnostic_tool()` 复用 diagnostic_tools 工具池+SSH 通道；`ai_self_heal_analyze` 加迭代循环（MAX_ROUNDS=5, MAX_TOOLS_PER_ROUND=5）；`get_ai_pending_actions` 返回所有轮次诊断命令（按 round_num 分组）
  - system_prompt 加 `diagnosis_sufficient` + `next_tools` 字段
- **前端改动**: `RemediationView.vue` 诊断过程折叠面板按轮次分组展示（"静态初诊"/"第N轮 AI 补诊"标签），加 `groupedByRound()`/`diagnosisRounds()` 辅助函数 + `.diag-round-label` CSS
- **设计**: 对标 GOPS 2026 秦晓辉 Layer3 实时诊断层 + AI 反馈闭环（Agentic Diagnostic Loop with Tool Calling），业界标杆 Dynatrace Davis Causal AI Engine

### 2026-07-28: SVG拓扑连线+资产依赖关系49条+链路面板
- **SVG拓扑连线**: FireMap 域视图内,`fm-canvas-wrapper` 包裹层卡片 + 动态创建的 SVG overlay。`drawRelations()` 通过 `data-eid` 查找实体卡片 DOM 位置,用三次贝塞尔曲线(Cubic Bezier)连接有依赖关系的卡片。故障实体间的线变红(`#ef4444`,stroke-width 2.5),正常线灰色(0.45透明度)。`resize`/`toggleLayer` 时自动重绘
- **资产依赖关系**: DB `asset_relations` 表写入49条关系。Docker域: nginx→5个mall(proxies_to)→nacos/mysql/redis/rabbitmq(depends_on)→vm-132(runs_on)。mall-search 额外→ES/Mongo。裸机域: nginx-bare→2个mall-bare→共享中间件
- **后端改动**: `fetch_overview()` 返回 `relations` 字段(仅本域内的依赖);`fetch_entity_detail()` 中 parent/children 带 `relation_type`
- **前端改动**: `FireMapView.vue` 模板中 layer 循环改为 `template v-for="layer in groupedLayers"` 支持 data group 和普通层分支;所有 `.entity-node` 加 `:data-eid="e.id"`;`loadDomainDetail`/`toggleLayer`/`resize` 后 `nextTick` 触发 `drawRelations()`
- **命名修正**: "接口层"→"接入层";LAYER_LABELS 中 3-db="数据库" 3-mq="中间件";get_layer() fallback 返回新值("microservice"→"2","infra"→"4");LAYER_MAP 全部映射到新值
- **卡片居中**: `.layer-entities` 加 `justify-content: center`;`.layer-header` 改 `justify-content: center`;大卡片 `width:100%` 但由 `fm-layers align-items:center` 控制自适应

### 2026-07-28: 灭火图4层分层模型(接口/应用/数据/基础设施)
- **4层分层模型**: FireMap 域内视图按 4层 展示: 1接口层(Nginx/API Gateway) → 2应用层(微服务/business_app) → 3组件层(数据库左卡片 + 中间件右卡片,左右并排) → 4基础设施层(VM/Node/Cluster)
- **实现方案**: 资产 `ci_attributes` JSON 加 `layer` 字段(1/2/3-db/3-mq/4),`get_layer()` 优先读属性再 fallback 旧 `LAYER_MAP`。不改表结构,零 migration
- **后端改动**: `health_engine.py` — `LAYER_LABELS`/`LAYER_ORDER`/`LAYER_SIGNALS` 改为新 key;`get_layer()` 加属性读取;`compute_health()` 用 `_LAYER_TO_COMPUTE` 映射表代替 if-else;`fetch_entity_detail()` 兼容新旧 layer 值
- **前端改动**: `FireMapView.vue` — 第3层(3-db+3-mq)用 `fm-layer-row.data-layer` flex 并排,`layer === '4'` 和 `layer === '1'` 兼容旧值;CSS 加 `.fm-layer-row` 样式
- **资产打标**: 全部69资产 `ci_attributes.layer` 已写入。nginx→1,business_app/deployment/pod/service→2,database→3-db,middleware(非nginx)→3-mq,VM/node/cluster/namespace→4
- **验证结果**: 三个域 API 返回均正确。Docker域 5层全有(1/2/3-db/3-mq/4),裸机域共享中间件(无独立VM),K8s域仅有第2层(44微服务)+第4层(9基础设施)。前端构建成功

### 2026-07-27: 灭火图按业务域划分(3域多域交叉)+资产编辑页加业务域字段+aiops.db修复+菜单迁移+告警全清理
- **灭火图业务域划分**: 69 资产按三套业务靶场划分为3域,共享中间件多域交叉。K8s平台组件并入K8s在线商城(53实体),共享中间件(MySQL/Redis/ES/Mongo/Nacos/RabbitMQ,6实体)同时属于Docker微服务电商(13实体)+裸机单体电商(9实体)。后端加 `_extract_domains()` 返回列表,`fetch_domains`/`fetch_overview` 多域展开,一个资产可出现在多个域
- **资产编辑页加业务域字段**: `AssetsView.vue` 基本信息区加「业务域」输入框,支持逗号分隔多域。`buildPayload` 写入 `ci_attributes.domain`,`openEdit` 从 `ci_attributes` 读回。构建后生效
- **修复 html 闭合 Bug**: 有多余 `</div>` 和缺少 `</div>` 导致 vite build 报 `Element is missing end tag`
- **手动的业务域管理方法**: 进资产管理→编辑→业务域字段。写 `K8s在线商城` 归单域,写 `Docker微服务电商,裸机单体电商` 归多域。清空回到默认域。新域名自动出现
- **aiops.db 严重损坏修复**: `database disk image is malformed`,B-tree 页面级损坏。写 `_fix_db.py` 逐表容错导出→重建→导入→索引。120表重建,860行恢复。**metric_records 全丢**,表结构在,60s内采集写入新数据。备份 `db/aiops.db.malformed_bak_*`
- **灭火图菜单迁移**: 从「智能分析室→异常检测」移到「值班驾驶舱→监控总览」首位。改 `menu_config.json`,必须重启后端
- **告警数据全清**: aiops.db+aiops_real.db 告警相关表清空

### 2026-07-27: License公钥重导+K8s资产状态修复+离线资产告警抑制+AI自愈JSON容错
- **License 验签失败修复**: `tools/public_key.pem` 与 `private_key.pem` 不配对(历史"重新生成RSA密钥对"只更新一半)。用现有私钥重导公钥,同步更新 `license_service.py` 硬编码 `PUBLIC_KEY_PEM`。license 现为 active(剩358天)
- **K8s 资产关机仍 online 修复**: `_sync_k8s_asset` 只更新 attrs 不更新 status;node 同步未采集 Ready 条件;`probe_assets` 跳过无 IP 资产。修复:① attrs 的 status 字段映射资产状态 ② node 同步采集 `node.status.conditions` Ready ③ `scrape_source` 失败时该集群所有 K8s 资产标 offline
- **离线资产仍触发告警修复**: `check_rules`(alert_service.py) 从 metric_records 读最新指标判断触发,未检查资产 online/offline。离线资产历史高值(如内存95%)反复触发告警。修复:遍历前查 offline 资产 ID 集合,跳过其指标
- **AI 自愈 JSON 解析失败修复**: GLM-5.2 返回的 JSON 字符串值含未转义双引号(如 `"SSH 连接失败"`),`json.loads` 报 `Expecting ',' delimiter`。`strict=False` 无效(引号匹配问题非控制字符)。新增 `_parse_lenient_ai_json()`:按已知字段名定位,用下一个字段名/闭合括号作值边界截取
- **LLM 超时修复**: GLM-5.2 推理 25-90s,provider `timeout_seconds=30` 太短。调至 90s
- **数据清理**: 清空全部告警(13)+pending_actions(12)+diagnosis_reports(10)供重新测试;K8s 集群 k8s-prod-131 下 57 个资产标 offline

### 2026-07-27: 诊断折叠面板 Bug 验证 + 前端重建
- **验证结论**: "查看诊断过程"折叠面板 bug 实际不存在。API 返回 PA #10 有 4 条 diagnosis_commands;前端 v-if 条件正确;构建文件含诊断代码。之前记录的 bug 可能是后端未运行时测试导致
- **操作**: 前端重新构建(`npm run build --prefix frontend`),后端重启(`python run.py`)
- **提醒**: 验证 API 时必须先登录获取 session cookie,否则 AuthMiddleware 会重定向到 /login 返回 SPA HTML

## 关键信息(始终保留)

| 项 | 值 |
|----|----|
| 项目路径 | `E:\AIOPS\project05` |
| Python venv | 上级目录 `.venv\Scripts\python.exe` |
| 启动后端 | `Start-Process python.exe -ArgumentList 'run.py' -WorkingDirectory '<项目>'`(端口 8000,bash 内直接跑会随会话超时终止) |
| 启动前端 | `npm run dev --prefix frontend`(端口 3000 → 8000) |
| 启动移动端 | `npm run dev:h5 --prefix mobile`(端口 5173) |
| 构建前端 | `npm run build --prefix frontend`(启动前必须先 build) |
| 登录密码 | admin / **admin123**(⚠️ 不是 1234) |
| 数据库 | SQLite(`db/aiops.db` + `db/aiops_real.db`) |
| 向量库 | Milvus Lite(`db/milvus/kb_v2.db`) |
| Embedding | BGE-small-zh-v1.5(512维);RAG V2 用 BGE-M3(1024维) |
| 部署服务器 | 39.96.51.45(`/data/AIOPS`),git push → SSH 拉取 → 构建 → 重启 |
| 一键重启 | `python tools/restart.py restart`(子命令 `status` / `logs [N]`) |

**⚠️ Windows 热重载大坑**:`uvicorn --reload` 旧子进程不退出 → 端口被占。强制重启三步:杀 Python 进程 → 确认端口释放 → 重新 `python run.py`。端口 LISTENING ≠ 服务可用,CLOSE_WAIT 堆积 + curl 超时是死锁信号;杀进程用 `Win32_Process` 命令行区分项目 python vs VSCode 插件 python。

**⚠️ License 机制**:`LicenseMiddleware` 拦截非白名单路径,无 `license.lic` → 403。换机器需 `tools/generate_license.py` + `tools/private_key.pem` 重新签发(指纹绑定本机 MAC/CPU/磁盘/主机名)。

---

## 重要架构决策(长期有效)

### AI 自愈 + 工作流协同(分级自愈)
- 已知场景走 Playbook(多步骤全自动),未知场景走 AI 单步
- `remediation_service.py`:`ai_self_heal_analyze` 注入启用的 RemediationWorkflow 列表,AI 返回 workflow_id 经校验后 action_type='workflow';`confirm_ai_action` 循环执行 workflow.steps,失败即停
- workflow 容错:restart 缺 service 用 asset.name 补;clean 缺 path 补 /tmp
- `PendingAction.alert_id` 关联告警;危险命令黑名单 `_DANGEROUS_CMD_RE` 52 条正则,`execute_action` 入口拦截

### 自愈引擎成熟度演进(三阶段)
1. **确定性风险分类器**:`_classify_command_risk` 按 SSH 白名单(ps/cat/grep/df 等只读)/变更黑名单(restart/kill/rm/scale 等)/未知三档硬判定,只读自动执行,变更入审批。LLM 自评风险不可靠,必须确定性规则兜底
2. **资产类型感知分派(CI-Type-Aware Dispatch)**:`_ci_channel` 返回 ssh/k8s/docker,`execute_action` 按通道分派;K8s 走 rollout/scale API,Docker 走 docker restart,SSH 走 systemctl。展示层 `_build_rule_command` 与执行层一致(Display-Execution Parity)
3. **诊断先行(Evidence-Driven Approval)**:`DiagnosisReport` 模型 + `DIAGNOSIS_COMMAND_PACKS`(按指标预定义只读命令) + `run_diagnosis` 自动跑诊断 → 注入 AI prompt → 生成 PendingAction 附 `diagnosis_report_id`/`root_cause`/`diagnosis_reasoning`/`impact`/`command_explanation` → 审批人看「诊断证据→根因→修复逻辑→命令解释」四段式推理链
4. **失败闭环(Failure Feedback Loop)**:`reanalyze_with_failure_context` 注入原始诊断+失败命令+错误输出 → AI 分析失败原因 → 换思路生成新 PendingAction → 审批 → 执行 → ... ;前端失败卡片显示「🔄 换个思路」按钮;设计原则:不是推翻重来,而是带着失败经验继续
5. **部署知识赋能(Deployment Knowledge)**:`KbDocument.asset_id` FK 绑定文档到具体资产;AssetsView 上传/管理部署报告;AI 分析(`ai_self_heal_analyze` + `reanalyze_with_failure_context`)时查询该资产关联的已索引部署文档注入 prompt,让 AI 基于实际安装方式/服务名/配置路径给出正确修复命令,避免"猜服务名"导致修复失败

### fail-safe 审批闸门 + 双路径并行
- `check_and_remediate` 不再自动 SSH,改为生成 `PendingAction(source=rule)`,末尾调 `auto_ai_analyze_alerts` 生成 `PendingAction(source=ai)`(限流 1 条/轮防 token 爆炸)
- 同告警下规则方案与 AI 方案并排,前端按 `source` 着色(规则蓝/AI 紫),人工择优;`confirm_ai_action` 按 source 区分参数路径
- **关键教训**:审批展示层与执行层参数补全逻辑必须一致;缺关键参数宁可拒绝执行也不能用资产名/IP 兜底(`systemctl restart 39.106.16.32` 比报错更危险);AI 必须输出可执行具体参数(Parameter Concretization),不能只给 action 类型

### Edge Agent 反向隧道(P2)
- edge agent 主动 WebSocket 拨出 + HTTP 轮询获取命令 + WS 回传结果 + WebSSH PTY
- 关键决策:用 HTTP 轮询(非 WS 推送)避开 Starlette/uvicorn Windows 上 WS 跨协程 send 的已知问题
- `EdgeSession`/`EdgeCommandLog` + `Asset.edge_agent_id`;文件 `edge_tunnel_service.py`/`edge_tunnel.py`/`webssh.py`/`edge_agent/edge_agent.py`/`EdgeTunnelView.vue`
- 入口:资产管理 → Edge 隧道管理;资产列表 → 🖥 终端按钮

### 子专家分派 + IM 双向通道(P1)
- `SubAgent` 模型 + 6 预置子专家(general/SRE/网络/数据库/中间件/K8s)
- `sub_agent_service.py`:关键词路由(零 LLM)+ 工具白名单过滤 + system_prompt 注入
- `agent_sse.py` 读 session.sub_agent → 路由 → 过滤工具 → 注入 prompt → SSE 推 `sub_agent` 事件
- IM ChatOps:`NotificationChannel` 加 `bidirectional`/`callback_token`/`callback_secret`/`default_sub_agent`;`im_chatops_service.py` 飞书/钉钉/企微签名校验 + 指令解析(/ai /alert /help)
- 入口:AI 运维智能体 → 子智能体管理 / IM 双向通道

### 竞品差距优化(P0)
- `MCPToolDef` 加 `location`(cloud/edge/hybrid) + `category`(15 分类) + `safe`/`read_only`/`ai_only` 派生属性(45 工具全补齐)
- `promql_parser.py`:parse_promql + PromQLQuery,`query_metrics` 支持 topk/bottomk/rate/avg_over_time + 标签过滤 + 嵌套聚合
- `/agent/api/capabilities` 返回 location_counts/category_counts/safe_count;入口 AI 运维智能体 → Agent 能力中心

### 灭火图分层健康引擎
- `compute_health()` 分层:api→Span / microservice+middleware→Alert / infra→Metric
- `_normalize_service_name` 去 K8s 前缀+哈希后缀;`health_engine.py` + `health_map.py`;Asset 加 `health_status`

### RAG V2
- BGE-M3(1024维)+ Milvus + 异步索引;`KbDocument.index_engine` 区分 V1/V2;V1 删 Milvus V2 删 SQLite

### 拓扑视图双 Tab
- Tab1 资产拓扑(K8s 节点维度):后端 `build_asset_topo_by_node` + `K8S_CHILD_FILTER` 过滤子资源收敛
- Tab2 网络拓扑双模式:devices(显式 AssetRelation)/ subnets(IP 网段聚类,父节点 roundRect)
- 教训:认证中间件拦截无 token 请求重定向 SPA(非 401),验证后端接口必须带 `Authorization: Bearer`;CI Roll-up 应在后端做避免前端过滤大图卡顿

---

## 字段规范与契约

### CONTRACT.md(字段命名 SSoT)
- 资产/连接配置/CI类型/数据源字段以 `CONTRACT.md` 为唯一数据源
- 新增/修改字段先改 CONTRACT.md 再同步前后端;敏感字段(密码/Token)后端返回 `***` + `has_*`,前端编辑置空、保存空值=不更新
- `scripts/check_contract.py` 检测字段漂移;违反契约会静默数据丢失

### 全库字段名规范化(57 字段重命名)
- 时间加 `_at` / 布尔加 `is_`/`has_` / JSON 加业务前缀 / FK 统一 `user_id` / 删除 `assets.type`
- `db_migrate.py` 61 条 ALTER TABLE;**新增模型字段必须同步补 `_MIGRATIONS`,`create_all` 不 ALTER 已有表**

### 路径规范契约
- 所有文件路径基于 `__file__`(Python)或 `%~dp0`(.bat)动态计算,禁止硬编码绝对路径
- 违反会导致换机器/目录后路径全部失效

### CSS 变量契约
- 全局 `main.css` 定义 `--text-primary`/`--card-bg`/`--primary` 等
- 页面 scoped CSS 必须复用全局变量名,不要自创别名;仅靠 fallback 值多主题下会失效

---

## 关键教训(按主题)

### 后端/Python
- **乱码溯源三层验证**:源文件字节 `open('f','rb').read()` + DB 存储字节 `hex(message)` + API 响应字节,区分历史脏数据 vs 运行时编码 vs 源码污染;Mojibake 特征是 UTF-8 字节被按 GBK 解码
- **Edit 工具对含 PUA 不可见字符的乱码行匹配失败**,改用 python 按行号重写;bash 里 `python -c "..."` 写含 `\n` 字符串会被双重转义 → 复杂修复脚本应 Write 到 .py 文件再执行
- **Python 局部变量分支条件赋值**,后续引用必须在入口处先初始化默认值
- **写查询脚本前先 `PRAGMA table_info` 确认列名**,不要凭记忆猜

### 前端/Vue
- **新增 Vue 页面**:无需改 router/index.js,但需改 AppLayout 注册组件 + activeView 分支 + menu_config.json + role_menus 四处
- **FastAPI + Vue SPA 404**:所有非根 Vue 路由必须在 `main.py` 加 catch-all 兜底,且必须在所有 `include_router` 之后,否则拦截 API
- **menu_config.json**:分组 key 不能与叶子 key 相同(否则点击无响应);`menu.py` 启动时缓存到内存,改 menu_config.json 后必须重启后端
- **axios timeout**:LLM 调用需 `{ timeout: 130000 }`(后端 120s 留余量);loading 状态按 id 跟踪(`ref({})`)不要用单个全局 ref
- **event.currentTarget 失效**:DOM 事件传播结束置 null,闭包内需入口处缓存

### 采集/告警/自愈
- **采集命令取 `100-id`** 比 `us` 列更全面(覆盖 sy/wa/hi/si/st);故障注入可观测缺口:注入的故障、采集的指标、告警判断三者维度必须对齐
- **规则匹配应精确关联**(rule_id 外键),`rule_id IS NULL` 不应作为"匹配所有告警"通配语义(Wildcard Rule Trap)
- **跨 OS 脚本传输必须做换行符规范化**(CRLF→LF),且在危险命令检测之前做,否则 `rm -rf /\r` 可能绕过正则
- **跨 OS 采集需抽象层**(LinuxCollector/WindowsCollector)+ `Asset.os_type` 字段;"无数据"≠"异常",评分不能二元扣分
- **K8s Python Client**:`configuration.timeout` 不自动作用于 API 调用,需 TCP 预检 5s + `configuration.retries=0` + `_request_timeout=(5,10)`
- **SSH banner 限流重试**:诊断命令包连续新建 SSH 连接时触发 132 机器 `MaxStartups` 限流 → `Error reading SSH protocol banner`;解法:`run_diagnosis` 改为共享单个 SSH 连接执行所有诊断命令(不再每条命令新建连接);`_remote_exec` 保留 `retries=2` 兜底重试;同时应考虑在服务器端调大 `MaxStartups`（`sshd_config`）

### 知识库/部署报告
- **AI 修复"猜服务名"根治**:AI 建议 `systemctl restart elasticsearch` 但实际是 Docker 安装 → 根因是 AI 不知道资产部署方式;解法:KbDocument.asset_id FK + 资产部署报告上传 → AI prompt 注入实际部署信息;设计原则:"诊断先行"之后是"知识赋能",让 AI 有足够上下文才能给出正确命令
- **KnowledgeDocumentsView 资产筛选**:下拉框 + loadList() 传 asset_id 参数;AssetsView 从资产维度管理部署报告,KnowledgeDocumentsView 从文档维度查看所有/筛选资产

### uni-app H5
- `manifest.json` 的 `h5.publicPath` 优先级高于 `vite.config.js` 的 `base`,缺失会覆盖
- `uni.switchTab` 忽略 query 参数,跨 tab 传参用 `getApp().globalData`
- `src/pages/` 下页面组件有深层编译缓存,改动不生效时先验证 `main.js`

### WebSocket/移动端
- WS 不能依赖 session cookie,需 `?token=` 拼接;移动端登录后 `localStorage.setItem('aiops-token')`
- SSE keepalive 2s 心跳 + `run_in_executor`;`agent_sse` max_rounds 提至 15

### opencode 性能维护
- SQLite WAL 不自动 checkpoint,定期 `wal_checkpoint(TRUNCATE)` + `VACUUM`;`scripts/cleanup_opencode.py --keep N`

---

## 近期变更摘要(2026-07)

### 2026-07-27(部署知识赋能 + 告警聚合降噪 + SSH 复用)
- 部署报告与资产绑定:KbDocument 加 `asset_id` FK → 查询资产部署文档注入 AI prompt
- KnowledgeDocumentsView 加资产下拉筛选(按 `asset_id` 过滤文档列表)
- V2 文档列表/上传/创建接口均支持 `asset_id` 参数
- `ai_self_heal_analyze` + `reanalyze_with_failure_context` 均注入资产部署知识文档(最多 5 篇,每篇截断 2000 字)
- AssetsView 已有部署报告上传/管理抽屉(上一会话完成)
- SSH 连接复用:run_diagnosis 共享单个 SSH 连接执行所有诊断命令,不再每条命令新建连接,根治 MaxStartups 限流 banner 错误;_remote_exec 保留 retries=2 兜底
- 告警聚合降噪:RemediationView 待处理告警按 metric_name+asset_name 聚合,折叠展开,消除同类告警刷屏

### 2026-07-26(自愈诊断先行 + 三架构靶场)
- 自愈引擎"诊断先行"改造:`DiagnosisReport` + `DIAGNOSIS_COMMAND_PACKS` + `run_diagnosis` + AI prompt 注入诊断数据 + 前端诊断折叠面板 + 推理链/命令解释展示
- 第7次会话状态盘点:10 条 pending_actions(6待审+1自动成功+3 SSH失败);列名是 `action_payload`/`action_type` 非 `command`/`action_taken`
- 确定性风险分类器 + 只读命令自动放行:26 用例通过,LLM 自评风险不可靠
- 告警规则 vs 异常检测页加对比横幅(静态阈值 vs 动态基线)
- 新增 AlertRulesView + 6 个 API;补齐数据库驱动(psycopg2/redis/oracledb/pymssql/pymongo)
- namespace 从 CMDB 移除保留拓扑依赖;修复资产列表"全部"只显示1条(SQL 分页+Python 过滤反模式);修复 K8s 资产创建 `connection_result` 未初始化
- K8s admin ServiceAccount 创建(K8s 1.24+ 不自动生成 token);平台数据全清(24585 行,VACUUM 5968KB→1260KB)
- 三架构靶场部署完成:131=K8s microservices-demo(12 pod),132=Docker mall-swarm + 裸机 mall;访问 K8s http://11.0.1.131:30443,Docker http://11.0.1.132/(admin/macro123),裸机 http://11.0.1.132:81
- 关键:mall-swarm 前端 baseURL 须含 `/mall-admin` 前缀匹配 Gateway 路由;Nacos 2.1 需 9848/9849 gRPC 端口;`--network host` 模式容器需用 localhost 非 docker hostname

### 2026-07-25(自愈资产感知 + 拓扑Tab化 + 多功能补齐)
- 自愈资产类型感知改造(三通道分派 ssh/k8s/docker);修复自愈 workflow 用资产名/IP 当 service 名生成废命令(参数具体化 + 禁止语义兜底)
- 修复自愈待审批 workflow 步骤只显示 action 名不显示真实命令(审批透明化);修复 `_build_rule_command` 不支持带后缀 action_type
- 告警消息乱码根治(alert_service + notification_service 两层编码污染);修复通配规则风暴(rule_id IS NULL 通配)
- 拓扑视图大改 Tab 化(资产拓扑 K8s 节点维度 + 网络拓扑双模式)
- 自愈改 fail-safe 审批闸门 + 双路径并行择优(规则+AI 并排)
- 诊断工具中心补 AI 解读层(`POST /api/diagnostic-tools/analyze` 6 段 RCA)
- Ansible 主机清单支持从资产生成;远程脚本多行命令 CRLF 修复;恢复 Ansible 编排菜单;新增「资源管理」一级菜单
- 智能巡检评分模型修复(无数据→unknown 不扣分,按 severity 加权);AI 深度分析结果缓存;通知渠道启停;自定义仪表盘;合并 DashboardView 到 MonitorView;菜单搜索框

### 2026-07-24
- AI 自愈端到端 6 轮 70 用例通过;PendingAction 加 `alert_id`;自愈规则 action label 中文化

### 2026-07-21
- 拓扑树默认只展开集群级;GuideDrawer 覆盖 10 个 K8s/容器页;CSRF 修复;K8s 集群概览卡片级状态色

### 2026-07-20
- 企业级安全加固(默认密钥检测+弱密码标记+CSRF+危险命令黑名单 52 条+白名单模式);性能修复(ES 超时 3s+失败缓存 5 分钟);NotificationLog.content→notification_content

### 2026-07-19
- 安全自查模块(bandit+pip-audit+pip-licenses+配置基线 4 合 1);移动端 P0 7 项修复;全项目 fail-soft 改造(109 处 500 清零);K8s 47 接口 fail-soft 化

### 2026-07-17~18
- AI 助手 32 场景测试 + SSE 中断修复;`agent_sse` max_rounds 15;GitHub 拉取 + 网络测试工具;产品介绍页 v2 + graph_inference;MonitorView 10 张 ECharts

### 2026-07-16
- SSE 实时推送;关联升级 ECharts 时间轴泳道图;系统态势 900 次 SQL→4 次(GROUP BY);多租户隔离;菜单按场景重组 7 大舱系 + RBAC

### 2026-07-15
- 全库 80 表字段规范化(57 字段重命名);运营数据看板 + 仪表盘拖拽编辑器 + 诊断工具(20 工具);智能巡检 + 资产基线 38 条模板 + 指标推荐 48 条模板;知识审批流 + SOP 自动生成;Investigation Package 6 部 RCA;Phase 5 移动端 + Phase 3 自愈/巡检/混沌/OnCall + Phase 2 Agent评估/RAG重排

### 2026-07-14
- 灭火图健康驾驶舱 + 全量硬编码路径清理(31 文件 54 处→`__file__`/`%~dp0`);蓝绿发布 + 标签管理 + 服务器部署;MySQL 工具 + 数据库资产权限检测三档

### 2026-07-13
- 异步安装 + 回滚机制;AI 助手日志/链路追踪工具 + 远程脚本生成 Playbook;Docker 化交付(3.02GB)+ K8s/Docker 终端 WS 修复;V1/V2 引擎标识 + 跨引擎安全删除;告警与 AI 助手联动

### 2026-07-10~12
- Reranker 双模式(经典 CPU + 智能 GPU)+ Mobile H5 publicPath 修复;RAG V2 + 预测引擎 5 模型 + Runbook 三场景;CONTRACT.md 字段规范契约;异常检测 7 算法修复 + 告警根因分析 + K8S 事件告警;拓扑/自愈/部署
