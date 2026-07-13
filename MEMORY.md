# AIOps 项目记忆

> 每次会话开始时读取本文件了解项目背景和之前的决策。
> 按照时间倒序排列。完整历史见 `MEMORY.md.bak.20260712`。

---

## 2026-07-13: 远程脚本目标主机修复（同时支持 DataSource 和 Asset）
- **问题**: 远程脚本下拉只查 `data_sources` 表（type=ssh/host/linux），但 39.96.51.45 (id=179) 在 `assets` 表（ci_type=cloud_host），导致下拉为空
- **修复**: `script_exec.py` 的 `api_script_targets` 同时查询 `DataSource`(SSH类型) + `Asset`(cloud_host 且有 connection_config)，Asset 用 `asset_{id}` 格式区分
- **修复**: `api_script_execute` 的 `target_id` 从 `int` 改为 `str`，支持 `asset_179` 前缀识别 Asset 类型
- **前端**: 无需修改，`t.id` 直接作为 value 发送即可兼容 `asset_179` 格式

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
- **登录密码**: admin / 1234
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
