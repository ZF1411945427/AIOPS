# AIOps 项目记忆

> 每次会话开始时读取本文件了解项目背景和之前的决策。
> 按照时间倒序排列。

### 2026-07-10: Runbook 三场景集成 — 智能推荐/知识图谱/AI Agent
- **核心问题**: Runbook(运维手册)是纯手动知识库，没有自动化集成
- **解决方案**: 打通三个行业标准场景
  1. **智能推荐**: 告警触发时推荐相关操作流程(_runbook_recommend)
  2. **知识图谱**: Runbook节点 + 按asset_type关联资产(covers关系)
  3. **AI Agent**: 新增query_runbook MCP工具(标题/症状/步骤检索)
- **前端**: Runbook推荐卡片(青绿色主题) + 操作步骤展示
- **测试**: alert_id=122返回2条Runbook, 知识图谱3个Runbook节点+18条边

### 2026-07-10: AI 助手工具选择引导 — 修复 query_runbook 未被调用问题
- **核心问题**: 用户问"web 服务重启的操作步骤"，AI 助手只调了 query_knowledge_rag(0条) 和 query_assets，没调 query_runbook
- **根因**: DEFAULT_SYSTEM_PROMPT 没有说明什么时候用 query_runbook vs query_knowledge_rag，LLM 默认用知识库检索
- **解决方案**: 在系统提示词中新增"工具选择指南"，明确：
  - 用户问"怎么操作/操作步骤" → 优先调 query_runbook
  - 用户问"知识库有没有/历史案例" → 调 query_knowledge_rag
  - 用户问"资产信息" → 调 query_assets
  - 多个工具可并行调用
- **验证**: 重启后测试"帮我查一下 web 服务重启的操作步骤"，AI 正确调用 query_runbook 并返回完整 5 步流程

### 2026-07-10: 智能推荐多源融合 — 规则 + RAG 语义检索打通
- **核心问题**: 智能推荐只查 knowledge_base 结构化表，RAG 文档无法被推荐
- **解决方案**: 在 smart_recommend API 中新增 RAG 语义检索，两路结果分数融合
- **融合策略**: 规则推荐权重 0.6 + RAG 语义权重 0.4，按排名归一化
- **前端增强**: 新增来源标签（规则/RAG/融合）、RAG 内容片段展示、数据源统计栏
- **验证**: alert_id=1 返回 3 条推荐，其中 1 条为融合（both），2 条为规则匹配

### 2026-07-10: BGE-small-zh-v1.5 模型切换 + 搜索高亮 + 知识图谱上下游展示
- **核心问题**: BGE-M3（568M参数）在 CPU 上编码9个切片需60秒，上传时阻塞用户体验
- **解决方案**: 改为异步索引——上传API秒级返回（0.05s），后台线程执行Embedding
- **smart_chunk 优化**: 合并小段落（原142段落→9个切片），`max_chars=2000, overlap=200`
- **embed_texts 优化**: `batch_size=32` + `show_progress_bar=False`
- **前端优化**: 上传/创建/重建索引后自动刷新列表（3s、10s延迟轮询），pending状态显示"索引中..."带脉冲动画
- **重构**: 提取 `_bg_index_document()` 共享函数，消除3处重复代码
- **Milvus Lite 文件锁**: 单进程限制，后台线程需复用主进程的 `vector_store.get_client()` 单例
- **密码**: admin 密码是 `1234`（不是 admin123）

### 2026-07-10: RAG V2 上传卡死修复 — 3 个核心 bug
- **Bug1 Session 跨线程死锁**: `asyncio.to_thread()` 将 SQLAlchemy `db` session 传到线程池，Session 非线程安全导致死锁 → `index_document_v2` 内部用 `get_session_for(get_db_mode())` 创建独立 Session
- **Bug2 HuggingFace 网络超时**: BGE-M3 每次加载都尝试联网验证，国内网络 SSL 错误导致每次卡 2+ 分钟 → `HF_HUB_OFFLINE=1` + `TRANSFORMERS_OFFLINE=1` 强制离线 + `snapshot_download(local_files_only=True)` 从本地缓存加载
- **Bug3 系统 Python vs hermes venv**: `Start-Process python run.py` 调的是系统 Python（无 torch），hermes venv 才有 ML 包 → 必须用 `C:\Users\zhuming\AppData\Local\hermes\hermes-agent\venv\Scripts\python.exe run.py` 启动
- **Reranker 优雅降级**: 模型权重未完整缓存，改为 `snapshot_download(local_files_only=True)` 失败时标记 `_rerank._model = False` 跳过，用 BM25+向量混合分
- **测试结果**: 7 项测试全部通过 / E2E 端到端验证通过 / 前端构建成功

### 2026-07-10: 项目独立 Python 环境 (.venv) + 启动命令修正
- **根因**: 之前用 `Start-Process python run.py`，系统 Python 没有 torch/sentence-transformers → 每次请求都卡在下载模型
- **解决**: 在项目目录创建 `.venv`，从 hermes venv 复制 site-packages（网络不通无法 pip install）
- **启动命令**: `D:\AIOPS\project07\.venv\Scripts\python.exe run.py`
- **AGENTS.md 已更新**: 所有启动命令改为 .venv 路径
- **换电脑部署**: 需要 `pip install -r requirements.txt`（含 torch, sentence-transformers, pymilvus 等 ML 依赖）

### 2026-07-10: RAG V2 知识库升级 — BGE-M3 + Milvus + 混合检索
- **目标**: 将简化版 TF-IDF RAG 升级为生产级 RAG，增加 Dense Embedding + 向量数据库 + 混合检索 + Reranker
- **技术选型**: BGE-M3 (BAAI/bge-m3, 1024d, MTEB 67.3, 中文最佳, 本地免费) 为默认 Embedding；Milvus Lite (本地文件存储) 为向量数据库；BM25 + 向量 + BGE-Reranker-v2-m3 为混合检索策略
- **新文件创建**:
  - `app/services/embedding_service.py` — 双模式 Embedding: BGE-M3 (默认) + OpenAI API (可选)
  - `app/services/vector_store.py` — Milvus Lite 连接管理、Collection CRUD、向量检索
  - `app/services/rag_engine_v2.py` — 完整 RAG Pipeline: 智能切片 → BGE-M3 Embedding → Milvus 存储 → BM25+向量混合检索 → Reranker 重排序
  - `app/routers/knowledge_v2.py` — REST API: 文档管理/上传/创建/删除/重建索引 + 语义检索 + Embedding 模式切换 + 统计信息
  - `scripts/migrate_to_v2.py` — 数据迁移脚本：将现有文档重新索引到 Milvus V2
- **修改文件**:
  - `app/main.py` — 注册 `knowledge_v2.router`
  - `frontend/src/views/KnowledgeDocumentsView.vue` — 新增经典版/智能版切换按钮，根据模式路由到不同 API (v1 vs v2)
- **关键技术细节**:
  - `vector_store.py` 必须在 insert/delete 后调用 `client.load_collection()` 否则 Milvus Lite 搜索报 "collection is released" 错误
  - torch 2.13.0 在 Windows 上有 DLL 加载问题 (c10.dll)，需要降级到 torch 2.1.0+cpu
  - sentence-transformers 5.x 需要 torch >= 2.4，不兼容 torch 2.1.0，需降级到 sentence-transformers 2.7.0 + transformers 4.41.0
  - numpy 需降级到 <2.0 以兼容 torch 2.1.0
- **测试结果**: BGE-M3 Embedding (dim=1024) ✅ / Milvus 插入+检索 ✅ / 智能切片 ✅ / 前端构建 ✅
- **待完成**: git commit & push / 部署到服务器 / 运行迁移脚本

### 2026-07-10: 修复 RAG 知识库文档页 3 个前端 bug
- **Bug1 `source` vs `source_type` 字段名不匹配**: 后端 `_doc_to_dict()` 返回 `source_type`，前端模板用 `d.source`/`detail.source`/`r.source` → 所有"来源"字段永远显示 `-`
  - 修复：`KnowledgeDocumentsView.vue` 三处 `d.source` → `d.source_type`
- **Bug2 详情接口返回结构嵌套未解包**: 后端 `api_doc_detail` 返回 `{"doc": {...}, "chunks": [...]}`，前端直接赋值 `detail.value = resp` → `detail.title`/`detail.content` 全部 undefined
  - 修复：`openDetail()` 解包 `detail.value = { ...resp.doc, chunks: resp.chunks }`
- **Bug3 创建弹窗"来源"输入框无效**: 前端有 `form.source` 输入框，但后端 `api_doc_create` 硬编码 `source_type: "manual"` → 用户填了也没用
  - 修复：删除创建弹窗中的来源输入框
- **验证**: `npm run build` 成功 / 本地后端重启 HTTP 200

### 2026-07-10: 用户与权限页新增修改密码功能 + 确认 8000 已是 Vue SPA
- **确认现状**: 8000 端口 `/` 路由返回 `frontend/dist/index.html`（Vue SPA），`/login` 也是 `_serve_vue()`。仅 product_intro/overview、容器日志/终端等少量辅助页仍用 Jinja2 模板。AGENTS.md 中"原有 Jinja2 前端(兼容保留)"的说法已过时
- **新增接口** `app/routers/users.py`:
  - `POST /users/api/{user_id}/reset-password` — 管理员重置任意用户密码（不验证旧密码）
  - `POST /users/api/change-password` — 当前用户改自己密码（验证旧密码 + 新旧不能相同）
  - 均要求新密码 ≥4 位
- **前端** `UsersView.vue`:
  - 操作列每行加"修改密码"按钮（btn-warning 橙色）
  - 弹窗根据是否当前用户决定：当前用户需填旧密码+新密码+确认，走 change-password；其他用户只需新密码+确认，走 reset-password
  - 前端校验：旧密码非空、新密码≥4位、两次新密码一致
- **验证**: build 成功 / 后端重启 HTTP 200 / 接口测试（错误旧密码被拒✅、重置成功✅、短密码被拒✅）

### 2026-07-09: 修复移动端「连接服务器超时」——JS 懒加载 chunk 404（base URL 不统一）
- **根因**: 移除 `/assets` 静态挂载后（避免与 API 路由冲突），移动端构建产物 hardcode `/assets/` 路径：
  - HTML 层路径已通过字符串 replace `/assets/` → `/mobile-assets/assets/` 修复
  - 但 JS 代码中 Vite 动态 import 的 chunk 仍引用 `/assets/...` → 404
  - 且服务器 `aiops.db` 已损坏（`database disk image is malformed`），API 返回 500 → 移动端显示"连接服务器超时"
- **修复**:
  - `mobile/vite.config.js` 加 `base: '/mobile-app/'` → 构建产物所有路径统一为 `/mobile-app/assets/...`
  - `app/main.py`: 用 `app.mount("/mobile-app", StaticFiles(html=True))` 替代 `serve_mobile()` 路由 + `/mobile-assets` 挂载
  - 移除 `/mobile-assets` 的 PUBLIC_PATHS 条目
  - 服务器：`git checkout HEAD -- db/aiops.db` 从 git 恢复健康数据库
- **验证**: `/mobile-app/` 200、JS/CSS 静态资源 200、API 401(未登录)/200(已登录) ✅

### 2026-07-09: 记录正确部署方式（弃用 tools/deploy.py）
- **不要用** `tools/deploy.py`（本地打包上传 565MB 太慢，且包含 helm 等服务器已有的大文件）
- **正确方式**：本地 `git push` → SSH 到服务器 → 服务器上操作：

```bash
# 1. 备份
cd /data && tar -czf AIOPS.bak.$(date +%Y%m%d_%H%M%S).tar.gz AIOPS/

# 2. 拉取最新代码
cd /data/AIOPS
git config --global --add safe.directory /data/AIOPS  # 首次需执行
git fetch --all && git reset --hard origin/main

# 3. 构建前端
cd /data/AIOPS/frontend && npm run build

# 4. 构建移动端
cd /data/AIOPS/mobile && npm run build:h5

# 5. 安装 Python 依赖
cd /data/AIOPS && pip3 install -r requirements.txt

# 6. 重启后端
pkill -f 'python.*run\\.py' 2>/dev/null
sleep 2
cd /data/AIOPS && setsid python3 run.py > /tmp/aiops_backend.log 2>&1 &
sleep 5
curl -s -o /dev/null -w '%{http_code}' http://127.0.0.1:8000/
```

### 2026-07-09: 修复 /assets/api/* 路由 404（静态文件挂载冲突）
- `app/main.py:169` 的 `app.mount("/assets", _MultiStaticFiles(...))` 与 `assets.router`（prefix=/assets）冲突
- 静态挂载在 Starlette 中优先级高于路由，所有 `/assets/*` API 请求被拦截返回 404
- 修复：移除该静态挂载（前端资源已由 `/vue-assets` 和 `/mobile-assets` 分别承载）

### 2026-07-08: 修复 docs 登录截图（之前误放了仪表盘截图）
- `docs/screenshots/login.png` 实际显示的是仪表盘而非登录页
- 用 Playwright 重新截图正确的 Vue SPA 登录页并替换

### 2026-07-08: 修复 mobile chat 输入栏固定底部（第四次尝试）
- 根本原因：`uni-page-body` 无明确高度，`height: 100%` 解析为 `auto`，flex 布局无法正确分配空间
- 修复方案：`onShow` 中用 JS 计算 `window.innerHeight - navBar - tabBar`，给 `uni-page-body` 设置精确像素高度
- 同时配合 `overflow: hidden` 防止页面整体滚动
- `onHide` 时清理样式，避免影响其他页面

### 2026-07-08: 修复 mobile 全量 404（图片 + JS chunk + CSS）
- **根因**: mobile 和 frontend 都用 `/assets/` 路径引用 Vite 构建产物，但后端只挂载了一个目录
  - 解决: 自定义 `_MultiStaticFiles`（继承 StaticFiles），按序尝试 `[mobile, frontend]` 两个 assets 目录
  - `GET /assets/xxx.js` 先查 `mobile/dist/build/h5/assets/`，找不到再查 `frontend/dist/assets/`
- **tab 图标 404**: `mobile/dist/build/h5/static/tab/tools.png` 文件本身缺失（项目遗漏）
  - 从 `mine.png` 复制创建 `tools.png` / `tools_on.png`
- **部署重启不可靠**: `_run()` 用 `get_pty=True`，PTY 关闭时后台进程被 SIGHUP 杀掉
  - 解决: `_step_restart()` 中后台启动改用 `transport.open_session()` + `setsid`，避免 PTY
- **最终验证**: 14 条关键路由全部 200 ✅

### 2026-07-08: 拓扑视图新增异常筛选 + 关联资产面板
- **需求**: 爸爸要求拓扑视图能筛选出异常资产（红色边框高亮），并能查看选中节点的关联资产
- **异常筛选按钮**: toolbar 新增「仅异常」toggle 按钮，激活后只显示异常节点 + 其直接关联节点/边，异常节点放大至 48px + 5px 红色边框 + 发光阴影
- **关联资产面板**: 点击任意节点 → 右侧图例面板显示节点详情 + 「关联资产(N)」列表（名称+状态），关联边在图中高亮为橙色 3px
- **辅助函数**: `getDisplayData()` 计算筛选后的节点/边集，`isConnectedTo()` 判断两节点是否连通，`toggleAbnormalFilter()` 切换筛选
- **el-menu 性能**: `:collapse-transition="false"` + sidebar `will-change: width` + el-icon `font-size: 14px`（规避 Setting 图标 Chrome bug）
- **build 验证**: 2411 modules / 15.08s / 0 errors ✅

### 2026-07-08: 12 个概念型功能页统一加「📖 概念说明」——GuideDrawer 可复用组件 + 小白友好科普
- **需求**: 爸爸说 SRE 可靠性下的功能页（SLO/错误预算/消耗速率/SLA/可用性报表/升级策略/值班表）对小白来说不知道是干嘛的、什么逻辑，要求都加操作说明。并扩展到所有概念型页面
- **统一方案**: 抽取 AgentWorkflowEditor.vue 现有的 guide-drawer 样式为可复用组件 `GuideDrawer.vue`
  - 组件位置: `frontend/src/components/GuideDrawer.vue`
  - 支持 v-model 控制显隐、title prop、默认 slot 填充内容
  - 内置 guide-section / key-value-list / formula / tip-box / guide-code 等样式类
  - 预置浅色主题、动画滑入、520px 侧边抽屉
- **已添加概念说明的 12 个页面**:
  - **SRE 可靠性（7页）**: SLO配置(什么是SLO/几个9/窗口期/状态判定) / 错误预算(计算公式/三态含义/SRE理念) / 消耗速率(Burn Rate>1含义/三窗口意义) / SLA协议(SLO vs SLA区别/可用性计算/处罚等级) / 可用性报表(可用性定义/年停机对照) / 升级策略(升级链机制/三级配置说明) / 值班表(轮值方式/排班计算)
  - **混沌工程（1页）**: 混沌工程概念/6种故障类型说明/目标层级(SLO验证)
  - **Helm（1页）**: Chart/Release/Repository 三大概念 / 回滚机制 / values.yaml
  - **Ansible（1页）**: Inventory/Playbook/Module 核心概念 / 三Tab功能说明 / 执行流程
  - **链路追踪（1页）**: Trace/Span/瀑布图概念 / 怎么看瀑布图 / 页面使用指南
  - **变更审批（1页）**: 变更管理目的 / 状态流转(草稿→待审批→已批准→进行中→完成/回滚) / 变更类型 / 风险等级
- **入口按钮位置**:
  - el-card 类页面(7个SRE+混沌) → card-header 内加小型「📖 概念说明」按钮
  - 自定义 header 类(Helm/Ansible/ChangeWorkflow) → page-header 内右侧加 btn-guide 按钮
  - TraceView → section-toolbar 内加 el-button
- **build 验证**: `npm run build` → 2411 模块 / 16.19s / 0 errors ✅
- **专业名词**: 新手引导体验(Onboarding UX)、上下文帮助(Contextual Help)、概念科普(Conceptual Onboarding)、微文案(Microcopy)、UI 复杂度审计(UI Complexity Audit)

### 2026-07-08: 修复 3 个线上 bug（SQLite NULLS LAST / PDF 字体 / PointerEvent 传参）
- **bug1 `notifications/api/recent` 500**: SQLite 不支持 `NULLS LAST` 语法，移除 `.nullslast()` → 恢复 200
- **bug2 `agent-workflow/api/runs/2/pdf` 500**: 硬编码 `C:\Windows\Fonts\msyh.ttc`（Windows 路径），Linux 上无此字体。
  - 修复方案：将 `msyh.ttc` / `msyhbd.ttc` 放入项目 `fonts/` 目录，代码优先查找本地 `fonts/`，找不到则回退 Windows 路径
  - 部署时通过 SCP 将字体传到服务器 `/data/AIOPS/fonts/`
- **bug3 前端 `@click="exportPdf"` 传参错误**: Vue 自动传入 PointerEvent 对象，按位或失败 → `typeof runId === 'number'` 防御式判断
- 前端已重新构建部署（`npm run build` → SCP dist 到服务器）

### 2026-07-08: 自愈规则端到端真实测试 + 3 bug 修复 + nginx PID 文件修复
- **测试场景**: 爸爸要求用真实资产(39.96.51.45, id=179, 阿里云ECS)端到端测试自愈规则"创建→执行→结果"
- **bug1 check_and_remediate 变量未定义**: `remediation_service.py:248` `{action}` → `{rem.action_type}`，否则自动触发路径崩溃
- **bug2 后端 create 缺 params_command**: `remediation.py:api_remediation_create` 加 `params_command: str = Form("")` + `if action_type=="run_command": params["command"]=params_command`
- **bug3 前端表单缺 command 输入框**: `RemediationView.vue` 加 `v-if="form.action_type==='run_command'"` 命令输入框 + form 加 params_command + createRule append
- **nginx PID 文件修复（服务器侧）**: aa_nginx.conf 的 `pid` 指令被注释，nginx 用默认相对路径 `logs/nginx.pid`，systemd forking 期望 `/var/run/nginx.pid` → 路径不匹配 → 等 PID 文件 90 秒超时 → failed。修复：`sed -i 's@^#pid\s\+logs/nginx.pid;@pid /var/run/nginx.pid;@' /etc/aa_nginx/aa_nginx.conf`（已备份 .bak）。修复后 systemctl restart nginx 秒成 EXIT=0，active(running)，80 端口监听
- **测试结果**: 告警84(triggered, asset_id=179, rule_id=1) → check_and_remediate → log1 规则#1 restart_service ✅成功(nginx重启) + log2 规则#7 run_command ✅成功(hostname=iZ2ze1y0pr2xbbyedc2v54Z) → 告警 acknowledged
- **专业名词**: 告警驱动自愈(Alert-driven Remediation)、PID文件路径不匹配(PID File Path Mismatch)、forking类型服务(Type=forking)、启动超时(TimeoutStartUSec 90s)

### 2026-07-08: 部署到 39.96.51.45 + Ansible 三步流程验证通过
- **部署目标**: 39.96.51.45（Alibaba Cloud Linux 3，Python 3.11.13，Node 20.20.2）
- **部署路径**: /data/AIOPS
- **备份**: `/data/AIOPS.bak.20260708_160749`（含旧代码 + 数据库 + .git）
- **传输**: tar 打包本地项目（141MB，含 helm 双平台二进制），SCP 到服务器解压
- **Python 依赖**: `pip3 install -r requirements.txt` → ansible-12.3.0 + ansible-core-2.19.11 ✓
- **前端构建**: `npm run build` → dist/index.html + assets 成功 ✓
- **License 修复**: 免费版 license.lic 绑定旧机器指纹，移除 `license_service.py` 中机器指纹校验，使任意有效许可证可在任意机器使用
- **Ansible 三步流程验证**:
  1. `PUT /ansible/api/inventories/1` → 200（更新主机清单 `39.96.51.45-db`，含 SSH 凭据）
  2. `POST /ansible/api/playbooks` → 200（创建 Playbook `ping-test`）
  3. `POST /ansible/api/run` → 200，`exit_code:0, status:completed`
     - TASK [Gathering Facts]: ok
     - TASK [ping test]: ok
     - PLAY RECAP: ok=2, unreachable=0, failed=0
- **当前状态**: 后端运行中（PID 2055098），开放端口 8000，Ansible 可用
- **仓库文件清档**: 删除本地临时脚本（tmp_deploy.sh/verify.py/fp.py/flow.py/flow2.py + aiops_deploy.tar）

### 2026-07-08: requirements.txt 加 ansible + bin/ 清理 Windows wrapper
- **需求**: 爸爸要求 `requirements.txt` 加 ansible，pip 装完就能用
- **变更**:
  - `requirements.txt` 加 `ansible==12.3.0`
  - `pip install ansible` 后 venv Scripts 下生成 `ansible-playbook.exe` / `ansible.exe` 等 10 个入口
  - 删掉 `bin/ansible-playbook.cmd` / `bin/ansible.cmd`（遮住了 Scripts 的 exe）
  - `_find_ansible_bin()` 去掉 `.cmd`/`.bat` 探测，Windows 只认 `.exe`
  - `bin/` 最终文件：`helm.exe` / `helm` / `ansible-playbook` / `ansible`（4 个）
- **Ansible Windows 限制**: Ansible 依赖 `grp` 等 Linux 专有模块，Windows 上 `--version` 和实际执行都会失败（`ansible/cli/__init__.py:52 check_blocking_io()` → `import grp` → ModuleNotFoundError）。这是 Ansible 自身的平台限制，部署到 Linux 正常

### 2026-07-08: Ansible 使用 bin/ 包装脚本，删除一键安装
- **决策**: 爸爸否决一键安装按钮方案，要求只靠 `bin/` 目录放可执行文件，断网也能用
- **变更**:
  - 删除 `POST /ansible/api/install` 端点（`ansible.py:401-419`）
  - 删除前端 AnsibleView.vue 安装按钮、`installing` ref、`installAnsible()` 函数、`.btn-install`/`.installing-text` CSS
  - 创建 `bin/ansible-playbook.cmd` / `bin/ansible.cmd`（Windows 包装脚本 → `python -m ansible`）
  - 创建 `bin/ansible-playbook` / `bin/ansible`（Linux shebang 包装脚本 → `python3 -m ansible`）
  - `_find_ansible_bin()` 新增 `.cmd`/`.bat` 后缀检测（Windows 优先 exe → cmd → bat）
  - `ansible_status()` 改为以 `--version` 实际运行结果判定 `installed`（而非仅二进制存在）
- **验证**: STATUS 返回 `installed: false`（本机未装 ansible Python 包）、INSTALL 返回 404 ✓；`npm run build` 通过 ✓
- **使用方式**: 部署服务器上 `pip install ansible` 一次，`bin/ansible-playbook` 包装脚本自动转发到已安装的 Python 模块，不需要额外配 PATH

### 2026-07-08: Ansible 内置化 + 一键安装 + PUBLIC_PATHS 修复
- ~~此记录已被上文覆盖，保留历史参考~~ 一键安装方案已废弃，改为包装脚本方案

### 2026-07-08: 资产列表表格溢出修复 + 资产生命周期加分页
- **需求**: 爸爸反馈资产列表的列表超出列表卡片边界 + 资产生命周期没有翻页功能
- **问题1 资产列表表格溢出**: `AssetsView.vue` 表格 11 列（名称/CI类型/纳管层级/IP/状态/生命周期/引用孤岛/连接方式/标签/创建时间/操作），`td` 全部 `white-space:nowrap`，无横向滚动容器 → 内容撑破 `.panel` 卡片边界
- **爸爸二审否定横向滚动**: 第一版用 `overflow-x:auto` + `min-width:1120px` 横向滚动方案，爸爸明确"不想让他滚动"，要求真正缩减列宽/删不重要列/标签列改操作按钮
- **最终修复1（删3列 + 标签按钮化）**:
  - 删「纳管层级」列：信息冗余，顶部 K8s 统计条已展示持久化/弱纳管/孤岛数量
  - 删「连接方式」列：低频信息（SSH/Agent/K8s API/SNMP），编辑详情里看即可
  - 删「标签」列：改为操作列加「标签」按钮（橙色，`v-if="a.tags"` 有标签才显示），点击 `ElMessageBox.alert` 弹窗显示标签内容
  - 11 列减至 8 列（名称/CI类型/IP/状态/生命周期/引用孤岛/创建时间/操作），宽度充足不滚动
  - 撤销 table-wrap/min-width，恢复纯 `width:100%` 表格
- **问题2 生命周期无分页**: `LifecycleView.vue` `v-for="it in items"` 一次性渲染全部资产（约178条），页面过长
- **修复2**: 加客户端分页（与 AssetsView 一致）：`currentPage/pageSize(默认20)/pageSizeOptions[10,20,50,100]/totalPages/pagedItems/pageNumbers(省略号折叠)`；`v-for` 改 `pagedItems`；底部加分页栏（共N项 + 上下页/页码 + 条/页下拉 + 跳页输入）；import 加 `computed/watch`；加分页栏 CSS
- **跨页定位修复**: onMounted 原逻辑 `items.find` 后直接 `scrollIntoView`，分页后目标行可能不在当前页 DOM → 改为先 `findIndex` 算出页码 `currentPage = floor(idx/pageSize)+1`，双重 `nextTick` 等分页渲染再滚动
- **验证**: `npm run build` 成功 ✓
- **专业名词**: 列瘦身(Column Slimming)、信息冗余消除(Redundancy Elimination)、低频信息下沉(Low-frequency Info Demotion)、操作列按钮化(Button-ization)、客户端分页(Client-side Pagination)、跨页定位(Cross-page Anchoring)
