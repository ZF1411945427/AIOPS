# AIOps 项目记忆

> 每次会话开始时读取本文件了解项目背景和之前的决策。
> 按照时间倒序排列。

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
