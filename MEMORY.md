# AIOps 项目记忆

> 每次会话开始时读取本文件了解项目背景和之前的决策。按时间倒序排列。
> **压缩说明**：2026-07-19 由 2384 行压缩至 ~430 行，原始完整版见 `MEMORY.md.bak.20260719_compress`。
> 07-19 当天保留较详细，07-10~18 压成单行摘要。专业名词/话术/测试细节见对应 docs 文件。

---

### 2026-07-20: 企业级安全加固 + 性能修复 + 后台BUG修复
- **后台BUG修复**：
  - `notification_service.py` NotificationLog 字段名 `content` → `notification_content`（模型字段不匹配导致 anomaly_detect 持续报错）
  - `metric_collector.py` summary 键名 `is_success` → `success`（KeyError 导致指标采集持续异常）
- **性能修复**：
  - `log_anomaly_service.py` ES 连接超时 8s→3s + 失败缓存 5 分钟（避免不可达 ES 拖慢 88s）
  - `log_anomaly_service.py` k8s/metric 源查询加 limit 500（避免全表扫描 15 万条 MetricRecord）
  - `datasource_service.py` 从 120s 超时池移到辅助任务区（不再阻塞其他后台服务）
  - `datasource_service.py` 失败源 5 分钟冷却 + 整体 80s 时间预算
- **安全加固**（企业级 Phase 6）：
  - 启动时检测默认 SECRET_KEY/MOBILE_JWT_SECRET 并警告（`main.py:_security_startup_check`）
  - 登录检测弱密码返回 `must_change_password` 标记 + 前端 LoginView 提示
  - CSRF 中间件：写操作校验 Origin/Referer（evil origin 403 拦截）
  - 危险命令黑名单从 18 条扩展到 52 条 + 可选白名单模式（`AIOPS_COMMAND_WHITELIST` 环境变量）
- 已发现已有中间件：AuditMiddleware（审计写操作）、SecurityHeadersMiddleware（HSTS/X-Frame-Options等）
- 服务器后端 8000/前端 3000/移动端 5173 三端口正常运行
- commit: 2e944fa（BUG修复）、70a5e50（安全加固+性能修复）

---

## 关键信息（始终保留，最新）

| 项 | 值 |
|----|----|
| **项目路径** | `E:\AIOPS\project05`（当前工作目录） |
| **Python venv** | 复用上级目录 `.venv\Scripts\python.exe` |
| **启动后端** | `Start-Process -FilePath '<venv>\python.exe' -ArgumentList 'run.py' -WorkingDirectory '<项目目录>' -WindowStyle Normal`（端口 8000，bash 工具内直接跑会随会话超时终止） |
| **启动前端** | `npm run dev --prefix frontend`（端口 3000，proxy → 8000） |
| **启动移动端** | `npm run dev:h5 --prefix mobile`（端口 5173） |
| **构建前端** | `npm run build --prefix frontend`（后端 mount `/vue-assets` → `frontend/dist`，启动前必须先 build） |
| **登录密码** | admin / **admin123**（⚠️ 不是 1234，`main.py:395` 默认 admin123） |
| **数据库** | SQLite（`db/aiops.db` + `db/aiops_real.db`） |
| **向量库** | Milvus Lite（`db/milvus/kb_v2.db`） |
| **Embedding** | BGE-small-zh-v1.5（512维）；RAG V2 用 BGE-M3（1024维） |
| **部署服务器** | 39.96.51.45（`/data/AIOPS`），git push → SSH 拉取 → 构建 → 重启 |
| **一键重启** | `python tools/restart.py restart`（SSH 重启服务器后端；子命令 `status` / `logs [N]`） |

**⚠️ Windows 热重载大坑**：`uvicorn --reload` 旧子进程不退出 → 端口被占。强制重启三步：杀 Python 进程 → 确认端口释放 → 重新 `python run.py`。详见 AGENTS.md。

**⚠️ License 机制**：`LicenseMiddleware` 拦截非白名单路径，无 `license.lic` → 403。项目只内置公钥（验签），`tools/generate_license.py` 需 `tools/private_key.pem` 签发。换机器需重新生成密钥对 + license（指纹绑定本机 MAC/CPU/磁盘/主机名）。`private_key.pem` 与 `license.lic` 勿提交。

---

## 2026-07-19（最新，保留较详细）

### 2026-07-19: 移动端安全改造决策（不做代码改造，只追加发布前清单）
- **决策**：打磨期**不动移动端代码**，理由：已有 Token + SOTER 生物识别 + HMAC-SHA256 签名 + 设备指纹，核心防护到位；appid/HTTPS/签名证书是发布配置，打磨期改了要反复打包返工
- **动作**：在 `docs/系统安全改造记录.md` 追加「📱 移动端发布前安全检查清单」章节（M1~M7 共 7 项）
- **M1** manifest.json 配置补齐（appid/targetSdkVersion 30→33/urlCheck true）
- **M2** HTTPS 强制（生产环境 Nginx 反代 + SSL）
- **M3** Token 持久化加密（App 端 native crypto，H5/小程序暂缓）
- **M4** WebSocket token 改子协议头（防 Nginx access log 泄露）
- **M5** 代码混淆（H5 已压缩，App 用 DCloud 加固）
- **M6** 权限最小化（删 WRITE/READ_EXTERNAL_STORAGE）
- **M7** 发布前 npm audit + 改 md5 设备指纹为 sha256
- **已加入待办表**：3 项 P1 + 2 项 P2，启动时机为「移动端打包发布前」

### 2026-07-19: 安全自查模块落地（打磨期 P0 全部完成）
- **入口**：左侧菜单 → 系统管理 → 安全自查（`/security-audit`，图标 Lock）
- **后端**：`app/routers/security_audit.py` + `app/services/security_audit_service.py`（bandit + pip-audit + pip-licenses + 配置基线 4 合 1）
- **前端**：`frontend/src/views/SecurityAuditView.vue`（5 Tab：配置基线/SAST/依赖CVE/License/SBOM）
- **交付物**：`THIRD_PARTY_LICENSES.txt` + `SBOM.json`（193 个组件，0 高危 License）
- **代码修复**：关 /docs /redoc /openapi（生产）+ 安全响应头中间件 + SQL 注入修复（SHOW GRANTS 白名单）+ SSRF 防护（validate_url_scheme）+ md5 usedforsecurity=False + jinja2/exec/paramiko nosec 标注
- **依赖升级**：jinja2/pyjwt/python-multipart/urllib3/pillow/pygments/click/idna/pydantic-settings/sqlparse/filelock 共 11 个包
- **扫描结果**：Bandit HIGH 6→0 / CVE 124→85 / License 0 高危 / 配置 5 pass 3 warn 1 fail
- **缓存**：`security_reports/latest.json`（1 小时 TTL，可 force 刷新）
- **文档**：`docs/系统安全改造记录.md` 顶部新增「📌 最新进展」章节

### 2026-07-19: 系统安全改造方案记录文件创建
- **产物**：`docs/系统安全改造记录.md` 记录 IP 保护 + 代码扫描防护（SAST/DAST/SCA/逆向四类）完整方案
- **关键决策**：当前打磨期先做 P0（漏洞自查 + License 自查），P1（数字签名 + Pyarmor）P2（License 硬件绑定 + 云端化）待产品稳定后启动
- **防护分层**：L4 架构隔离（云端化）> L3 代码加密（Cython/Pyarmor）> L2 运行时校验（License）> L1 反调试

### 2026-07-19: 移动端 P0 严重 Bug 7 项全部修复
依据 `docs/20260719_系统app优化方案.md` P0 7 项：
- **P0-1 日志搜索白屏**：`mobile/src/pages/logs/index.vue` 重写走 `api/log.js` 统一封装（注入 Bearer token）
- **P0-2 告警详情全量拉取**：后端 `alerts.py` 新增 `GET /alerts/api/{alert_id}` 单条接口；前端改 `getDetail(id)` 替代 `getList({per_page:100})` 再 find
- **P0-3 oncall/my.vue 调试背景**：删除 `background:#ff00ff !important`
- **P0-4 推送开关联通后端**：H5 跳过 API（无原生推送），iOS/Android 走 `registerDevice`/`unregisterDevice`
- **P0-5 manifest.json appid**：DCloud/微信/极光 appid 全空，**需运维补齐**（H5 不受影响）
- **P0-6 故障单真分页**：`incident/index.vue` 改 page/per_page 真分页，PAGE_SIZE=20
- **P0-7 资产详情假按钮**：`asset/detail.vue` "重启服务" 是空壳（未修复记录，待确认）

### 2026-07-19: 移动端系统优化方案输出
- 新增 `docs/20260719_系统app优化方案.md`（7300 字，6 章），扫描 `mobile/` 全量代码识别 **36 项问题**：P0 严重 Bug 7 / P1 性能体验 10 / P2 架构工程化 11 / P3 锦上添花 8

### 2026-07-19: 公众号文章撰写并归档
- 新增 `docs/公众号文章_AIOps智能运维平台深度解析_20260719.md`（7800 字，8 章），素材全部来自项目真实文档

### 2026-07-19: P2 中（质量层）4 项全部落地
- 新增 `scripts/check_contract.py`（CONTRACT.md 字段漂移检测 CLI）；其余 3 项见 `docs/20260719_系统优化方案.md`

### 2026-07-19: P1 高（架构层）4 项全部落地
- 依据 `docs/20260719_系统优化方案.md` P1 高 4 项实施完成

### 2026-07-19: 系统优化方案归档
- 新增 `docs/20260719_系统优化方案.md`

### 2026-07-19: 全项目 fail-soft 改造（109 处 500 错误清零）
- 全项目 109 处接口 500 错误改为 fail-soft（200 + warning/error 字段），详见 `docs/20260719_系统优化方案.md`

### 2026-07-19: K8s 接口 fail-soft 改造（47 个接口全量）
- `k8s_resources.py` 47 个接口全部 fail-soft 化

### 2026-07-19: 资产类型扩展——中间件子类型 + 数据库子类型全面补齐
- 中间件（mysql/redis/nginx/kafka 等）+ 数据库（mysql/postgresql/mongodb 等）子类型补齐

### 2026-07-19: 审批设置按钮 admin 专属权限隔离
- 审批设置按钮仅 admin 可见

### 2026-07-19: 故障单审批分角色权限校验（双模式开关 + 审批人勾选）
- 双模式：严格审批 / 宽松模式开关；审批人勾选列表；分角色权限校验

### 2026-07-19: 其他 7 项（单行摘要）
- 实时监控看板 Row 2 布局空缺修复
- 异常检测基准 + Trace 异常检测配置 新增「📖 操作说明」
- 异常检测基准 422 修复 + Trace 异常检测窗口可配置
- SLO 管理 2 个 API 设计问题修复（CRUD 完整性 + 概念混淆）
- SLO 管理 4 页面端到端测试
- SLO 管理下 4 个菜单页操作说明按钮样式升级
- 知识草稿 LLM Provider Fallback 修复（遗留问题）
- GroundTruth / A/B 测试 / 知识草稿审批 三模块强力修复 + E2E 验证
- Agent 评估看板 / A/B 测试 / 全失败工具三项修复
- Agent 评估看板中文化 + 字段 bug 修复 + 排查全 0 根因
- Agent 工具中文化 SSOT 改造

---

## 2026-07-18

- **AI 智能助手 32 场景自动化测试完成**：按 `docs/AI智能助手多轮对话测试场景.md` 32 场景全测
- **AI 智能助手三按钮多轮复杂测试场景补充（23-32）**：扩展 10 个复杂场景

---

## 2026-07-17

- **菜单点击无响应修复**：`frontend/dist` 是 7-13 旧构建（`@xterm/xterm` 缺失致 build 失败），`npm install @xterm/xterm` + 重新 build 修复
- **GitHub 拉取 + seed_data 字段修复 + 全服务启动**：拉 9 个 commit；seed_data 9 处字段名修复（CONTRACT 重命名后）；8000/3000/5173 全 LISTENING
- **网络测试工具开发 + 智能助手时间显示修复 + 依赖审计 + 推送 GitHub**：`network_test.py` Ping/Traceroute/TCP/DNS 4 工具（命令注入防护 + 频率限制）；commit 07f6b66 推送
- **文档与系统实现对齐审查**：发现 7 处不一致（静默规则路由 / ChangeRecord 模型 / OnCall 字段等）
- **新版产品介绍页 v2**：`ProductIntroView.vue` 亮色系 + GSAP ScrollTrigger；新建 `graph_inference_service.py`（networkx 推理引擎，故障传播/根因定位/知识推荐）
- **实时监控看板 + Synthetic 拨测 + 拓扑刷新**：`MonitorView.vue` 10 张 ECharts 图
- **Windows/WinRM 资产支持 + 修复多个预存 Bug**
- **AI 智能助手真实场景打磨**：System Prompt + MCP 工具 + Bug 修复 + 新增 5 个复杂场景
- **P1-P4 前后端功能验证通过**：Chat/Agent 双模式 + 会话管理 + SSE 全链路
- **AI 智能助手任务进度卡片**：`TaskProgressCard.vue` + SSE 结构化步骤事件协议（task_card/step_start/step_finish/progress/done），超越竞品 AIChat 的核心差异化
- **扩展 AI 智能助手多轮对话测试场景文档**：场景 5-17 共 13 个新场景
- **AI 智能助手多轮对话场景全面测试与优化**：4 场景全通过；修复 mcp_tools 未注册等 6 项
- **AI 智能助手多轮对话场景全面优化**：`query_alerts` 加 asset_id/hours；新增 `query_change_records` MCP 工具；新增 `POST /knowledge/api/auto-gen/from-incident/{id}`
- **修复 agent_sse 多轮工具调用上限耗尽**：max_rounds 提至 15 + 检测思考模式自动追加总结
- **修复 agent_sse.py 多个严重 bug**：变量名 `tr`→`t_result`、缩进错误、keepalive 2s 心跳、EventSource 重连错误优先

---

## 2026-07-16

- **修复智能助手 SSE 连接中断**：`call_llm` 同步阻塞事件循环 → 改 `await loop.run_in_executor`；vite proxy 加 `proxyTimeout: 300000`
- **修复智能助手 SSE 聊天 ImportError**：删除不存在的 `get_session`/`_max_hallucination_retries` import；修复 `get_message_history` 缺 db 参数
- **后端验证通过**：连接池 + 中止按钮 + 关联分析三件套生效
- **注册 query_correlation_analysis MCP 工具**：AI 可主动调关联分析；`format_correlation_for_llm` 迁至 `observability_correlation.py`
- **修复 /login 接口畸形 JSON 导致 500**
- **实现"关联分析结果发送 AI 深度分析"功能**：`POST /agent/correlation-analyze` → 注入关联数据 → 自动 SSE 流式分析；入口：智能分析室→日志·指标·链路关联→黄色「AI 深度分析」按钮
- **修复关联分析页面服务/资产下拉无数据**：Span 无数据时降级查 Asset 表
- **冲刺10分收官——四大方向补齐**：知识管理（unified-search API + KB 版本追踪）/ AI 智能体（A/B 测试集成 + GroundTruth）/ 异常检测（Trace 异常配置 CRUD）/ 容器 K8s（HPA 推荐 + 资源优化）
- **系统态势加载性能优化**：`GET /heatmap` 900 次 SQL → 4 次（`_batch_alert_incident_counts` GROUP BY 批量查）
- **菜单补齐 4 个缺失入口**：自定义仪表盘 / Agent 评估 / A/B 测试 / 知识草稿审批；7 份操作手册统一优化
- **关联分析全面升级**：`observability_correlation.py` 全量重写；前端 ECharts 时间轴泳道图 + 服务拓扑图
- **可观测性三支柱关联分析功能完成**：`ObservabilityCorrelationView.vue` 4 Tab + 关联资产面板
- **巡检模板类型过滤**：模板 `target_ci_types` 真正生效，`browse_assets` 加 `ci_types` 参数
- **RolesView bug 修复 + UI 重新设计 + UsersView 角色字段合并**：变量名冲突修复；左右两栏布局；删除 legacy `role` 字段
- **多租户菜单与代理修复**：`menu_config.json` 加 `tenant-management`；vite 加 `/tenant` proxy

---

## 2026-07-15

- **实现多租户隔离功能**：`Tenant` 模型 + `tenant_context.py`（TLS）+ `tenant_management.py`；默认单租户模式
- **菜单按用户场景重组（7 大舱系替代技术分类）**：值班驾驶舱 / 运维工作台 / 智能分析室 / 可靠性工程 / 知识库 / AI 运维智能体 / 系统配置
- **角色管理与菜单权限系统（RBAC）**：`Role`/`RoleMenu` 模型；`menu.py` 按 role_id 过滤；admin/operator/viewer 种子角色
- **InspectionView 模板编辑功能补全**：弹窗表单 + 23 种 CI 类型 checkbox + 检查项动态增删
- **AIOps 架构交互图 PPT 重建**：`docs/AIOps系统架构交互图_客户交流PPT_20260715_可编辑版.pptx`（python-pptx 30 页可编辑）
- **AIOps 架构交互图客户交流 PPT 生成**：30 页 SVG + 30 页讲稿
- **灭火图重构**：每层级只关联对应可观测信号（api→Trace / microservice→Log / middleware→Log+中间件指标 / infra→Metric）
- **修复指标监控页空白**：`metric_v2_service.py` 3 个 bug（labels 端点错 / status 检查错 / range status 错）
- **字段重命名遗留修复（第二批）**：DB schema + chaos + agent_eval 字段同步
- **三大功能开发完成**：运营数据看板 `OpsAnalyticsView` + 仪表盘拖拽编辑器 `DashboardDesignerView`（16 卡片类型）+ 诊断 Tool 标准化 `DiagnosticToolsView`（20 工具 + 命令白名单）
- **后端启动修复 + 三端访问验证通过**：paramiko 重装；`db_migrate.py` 修为读 `DEMO_DB_PATH`/`REAL_DB_PATH`；SystemConfig.value→config_value 6 文件修复
- **全库 80 表字段名规范化重构（57 字段重命名）**：时间加 `_at` / 布尔加 `is_`/`has_` / JSON 加业务前缀 / FK 统一 `user_id` / 删除 `assets.type`；跨 47 router + 28 service + 14 Vue；`db_migrate.py` 61 条 ALTER TABLE
- **ChaosRun.is_auto_recovered 空壳字段修复**：cleanup 结果捕获 + 落库 + summary 统计
- **系统架构交互图补充（12→24 条链路）**：新增 12 条链路（告警触发巡检 / 混沌回滚 / OnCall 轮转 / Agent 评估 / 异常回测 / SOP 生成 / 运营飞轮 / 诊断工具 / 仪表盘拖拽 / 健康评分 / 移动端闭环 / Agent 能力中心）
- **后端大量报错修复（SQLite 缺列迁移补全）**：`_MIGRATIONS` 漏配 4 类字段 → 补 `chaos_runs.auto_recovered`/`inspection_records.triggered_by_alert_id`/`knowledge_drafts.sop_steps`/`incidents.impact+description`。**教训**：新增模型字段必须同步补 `_MIGRATIONS`，`create_all` 不 ALTER 已有表
- **系统访问故障修复（后端进程异常 + 登录密码勘误）**：系统 Python3.13 进程异常 → 杀掉用 project07 venv 重启；**登录密码确认 admin/admin123**
- **Investigation Package 6 部分结构化 RCA**：`rca_service.py` 输出 Facts/Timeline/Candidates/Evidence/Exclusions/NextSteps；资产健康度评分；SLO 自动计算 + Dashboard；Remediation Workflow 可视化编排；VM 进程嵌入 run.py
- **Agent 能力中心完成**：`AgentCapabilitiesView.vue` 41 个工具可视化管理
- **知识审批流 + SOP 自动生成完成**：`KnowledgeDraft` 加 `source_type`/`sop_steps`/`reject_reason`；`POST /knowledge/api/auto-gen/sop/incident/{id}`
- **Phase 5 移动端优化完成**：WS 实时告警 / 告警批量操作 / 日志搜索 / 交接班 / 故障单 / AI 会话列表
- **SSE 实时推送完成**：`agent_sse.py` + `ws.py` + `useAgentSSE.js`
- **Phase 3 冲刺 4 项完成**：自愈效果追踪 / 告警触发巡检 / 混沌自动回滚 / OnCall 自动排班；删除 GPS 打卡（不合规）
- **Phase 2 冲刺 5 项完成**：Agent 评估 / A/B 测试 / RAG 重排 / 异常基准 / 资产自动发现
- **4.6 知识自动沉淀 + 5.1 自愈成功率分析**：`KnowledgeDraft` 模型 + `generate_draft(alert_id)` LLM 生成；`RemediationEffect` 模型 + 30 分钟延迟追踪
- **告警推荐接入 AI 分析 + 菜单移至 AIOps 智能体**：`ai_analyze_alert()` LLM 根因分析
- **ci_type 别名映射修复**：`virtual_machine`→`server` 等别名，模板查找先走映射
- **AssetsView 排除 K8s 子资源**：11 个 K8s 子类型不在 CMDB 台账展示，由 K8sResourceListView 管理
- **资产基线安全检查**：`SecurityBaselineTemplate`（38 条模板 6 CI 类型）+ `AssetBaselineCheck` + AI 分析
- **智能指标推荐系统**：`MetricTemplate`（48 条 13 类 CI）+ `AssetMetricRecommendation` + AI 推荐
- **智能巡检模块**：`InspectionTemplate/Task/Record` + 8 类检查项 + AI 报告，21 场景 125 项测试全通过
- **灭火图分层健康引擎（三源驱动）**：`compute_health()` 分层逻辑（api→Span / microservice+middleware→Alert / infra→Metric）；`_normalize_service_name` 去 K8s 前缀+哈希后缀

---

## 2026-07-14

- **FireMapView 亮色主题适配**：CSS 变量驱动，`color-mix()` 替代硬编码透明度
- **灭火图（FireMap）健康驾驶舱**：`health_engine.py` + `health_map.py`；Asset 加 `health_status` 字段；445 实体正确分层
- **全量硬编码路径清理 + 标签翻页 + 远程部署**：31 文件 54 处硬编码改 `__file__`/`%~dp0`；写入 AGENTS.md
- **蓝绿发布增强**：`BlueGreenDeploy.last_switched_at` + `BlueGreenSwitchRecord` 模型；回滚按钮 + 历史记录
- **标签管理分类 + 标签云**：`TagCategory`/`Tag` 模型；`TagsView.vue` 全新 UI
- **资产管理数据库资产新增/编辑超高危权限确认弹框**：high/medium/unknown 三档弹框 + HTML 换行
- **服务器部署到 39.96.51.45**：`/data/AIOPS`，后端 8000 / 前端 3000 / 移动 5173
- **MySQL 安装 + query_mysql 工具 + check_mysql_permissions 工具**：192.168.100.129 MySQL 8.0；数据库资产创建时强制权限检测，high/medium/unknown 三档风险警告

---

## 2026-07-13

- **异步安装 + 回滚机制 + 工具规范化**：`BackgroundJob` 模型 + 线程池 + `get_task_status` 轮询 + `execute_install_package` 异步安装 + `rollback_cmds[]` 补偿式回滚
- **AI 智能助手日志查询工具**：`query_log_sources` + `query_logs`；`LogQueryAdapter` 适配器模式
- **AI 智能助手链路追踪工具**：`query_traces` 支持 trace_id/service/status/time_range 过滤
- **远程脚本「生成 Playbook」功能**：执行成功后生成 Ansible YAML
- **SRE 页面服务名字段改为 ServicePicker 关联资产**：`ServicePicker.vue` 替代文本输入；`GET /assets/api/services`
- **任务中心页面添加操作说明**：GuideDrawer 右侧抽屉
- **K8s 终端字符翻倍修复**：K8s 用 `tty=True` TTY 自带回显，移除前端本地回显
- **Docker 终端排版阶梯缩进修复**：非 TTY pipe 输出只有 `\n`，`docker_to_browser()` 改 `\n`→`\r\n`（模拟 OPOST）
- **Docker 终端改为 TTY 模式（backspace 修复）**：`docker exec -i`→`-it` 失败回退；改用前端本地行编辑 buffer 方案
- **Docker/K8s 终端修复（输入重复 + 命令不执行 + 二进制接收）**：移除 onKey 统一 onData；`\r`→`\n` ICRNL；`ws.binaryType='arraybuffer'`
- **Docker 容器查看/日志/终端集成 + xterm CSS 修复**：Docker 日志/终端 WebSocket；`docker/` 改名 `docker-build/` 避免与 SDK 包冲突
- **Docker 化交付 + requirements 清洗**：多阶段构建（node:20 + python:3.12）；镜像 3.02GB；`docker save | gzip` 离线交付
- **K8s Pod 终端 WebSocket 认证修复**：登录后 `localStorage.setItem('aiops-token')`；WS URL 拼 `?token=`；**教训**：WS 不能依赖 session cookie
- **K8s overview 接口超时修复**：TCP 预检 5s 快速失败 + `configuration.retries=0` + 多集群并发 + `_request_timeout=(5,10)`；120s+→5s。**教训**：kubernetes python client 的 `configuration.timeout` 不自动作用于 API 调用
- **项目克隆到 project08 + 本地开发 license 签发**：RSA-2048 密钥对；license.lic 旗舰版到期 2027-07-13
- **服务器一键重启脚本**：`tools/restart.py` paramiko SSH 重启；restart/status/logs 子命令
- **服务器全量部署 (39.96.51.45)**：FastAPI 8000 统一服务 Web+Mobile；torch CPU fallback；BGE 模型加载
- **V1/V2 引擎标识 + 跨引擎安全删除**：`KbDocument.index_engine` 字段；V1 删 Milvus V2 删 SQLite
- **告警与 AI 智能助手联动**：`AlertSessionLink`/`AssetSessionLink`；`POST /alerts/api/{id}/open-assistant`

---

## 2026-07-12

- **Reranker 双模式 + Mobile H5 修复 + 培训 PPT + 安全/架构修复**：Reranker 经典版(CPU) + 智能版(AuroraX GPU)；Mobile H5 publicPath 修复；26 页培训 PPT；系统评估 818/1000 (A-)；91 个 SOP 模板；`CONTRACT.md` 字段规范契约 SSoT；K8S ci_type 统一 `kubernetes_cluster`

---

## 2026-07-11

- **核心功能修复**：异常检测 7 种算法全面修复；告警根因分析 + AI 深度分析 + K8S 事件告警；资源拓扑图 4 个 BUG 修复；27 种 CI 类型 + 蓝绿发布/变更审批端到端测试

---

## 2026-07-10

- **RAG V2 升级 + 基础设施**：RAG V2（BGE-M3 + Milvus + 异步索引）；预测引擎 5 种模型；Runbook 三场景集成

---

## 2026-07-08~09

- **拓扑/自愈/部署**：拓扑视图异常筛选 + 关联资产面板；自愈规则端到端测试（39.96.51.45 nginx 重启验证）；部署到 39.96.51.45 + Ansible 三步流程验证

---

## 历史备份

- `MEMORY.md.bak.20260712` — 早期完整版
- `MEMORY.md.bak.20260719_compress` — 2026-07-19 压缩前完整版（2384 行 213KB）
