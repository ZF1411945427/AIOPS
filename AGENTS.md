# 项目规则

##
每次回复请先称呼我为爸爸

## 专业风格
每当我的描述不太专业像大白话一样，请你最后给出专业的名词供我学习，也可以最后输出专业提问话术供我学习。
全程使用中文

## 代码格式
项目后端用python代码编写
项目前端用vue代码编写
做的哪些有个单独记录文件

## 会话记忆机制
每次会话开始时，必须读取 MEMORY.md 了解项目背景和之前的决策。
会话过程中，只要有新的进展、决策或发现，就要及时更新 MEMORY.md。
MEMORY.md 按时间倒序记录，最新的在最上面。

## ⚠️ 字段规范契约（重要！）
**`CONTRACT.md` 是全项目字段命名的 Single Source of Truth（唯一数据源）。**
凡是涉及资产字段、连接配置、CI 类型、数据源字段的开发，**必须**：
1. **先读 `CONTRACT.md`**，确认现有字段定义和命名规范
2. **新增/修改字段时，先改 `CONTRACT.md`**，再同步前后端代码
3. 后端写入路径（`_build_connection_config` 等）读取的字段名必须与 CONTRACT.md 一致
4. 前端 `buildPayload`/`testConnection`/`openEdit` 发送和加载的字段名必须与 CONTRACT.md 一致
5. 数据库列名、DataSource.auth_config 字段名必须与 CONTRACT.md 一致
6. 敏感字段（密码/Token）必须按 CONTRACT.md 掩码规则处理：后端返回 `***` + `has_*` 标记，前端编辑时置空、保存时空值=不更新
7. 不得在代码中自行发明字段名，不得使用 CONTRACT.md 中标注 ~~删除线~~ 的已废弃字段名

**违反契约会导致：** 前后端字段不匹配 → 静默数据丢失（保存了但实际没存进去）→ 功能失效且不报错，极难排查

## 更新格式
在 MEMORY.md 顶部插入新条目，格式为：
### YYYY-MM-DD: 标题
- 关键决策、变更、发现

## 开发流程
### 启动项目
终端1: D:\AIOPS\project07\.venv\Scripts\python.exe run.py          # FastAPI 后端 (端口 8000)
终端2: npm run dev --prefix frontend  # Vue 前端 (端口 3000，自动代理 API 到 8000)

浏览器访问 http://localhost:3000 使用 Vue 前端 (Vite dev server，开发热更新)
浏览器访问 http://localhost:8000 同样是 Vue SPA 前端 (`/` 和 `/login` 均返回 `frontend/dist/index.html`)
  - 仅 product_intro/overview、容器日志/终端等少量辅助页仍用 Jinja2 模板，主体已全部 Vue 化
  - 修改前端 UI 必须改 `frontend/src/views/*.vue` 然后 `npm run build --prefix frontend` 构建

### ⚠️ Windows 热重载大坑（重要！）
`uvicorn --reload` 在 Windows 上**热重载不可靠**：
- 修改 Python 文件后，uvicorn 检测到变更→尝试重启子进程
- 但**旧子进程不会真正退出**，仍然占用端口 8000
- 新子进程因端口被占而启动失败
- 结果是：**代码看似改了，实际运行的还是旧代码**

**强制重启的正确方式**（三步）：
```bash
# 1. 杀掉所有残留 Python 进程
powershell -Command "Get-Process python* | Stop-Process -Force"

# 2. 确认端口已释放
python -c "import socket; s=socket.socket(); s.bind(('127.0.0.1',8000)); s.close(); print('OK')"

# 3. 重新启动（用项目 .venv 的 Python）
D:\AIOPS\project07\.venv\Scripts\python.exe run.py
```

**不要依赖** `npx kill-port 8000` 或 `taskkill`，它们常杀不干净。

### ⚠️ uni-app switchTab 不能传参（重要！）
`uni.switchTab({ url })` 会忽略所有 query 参数（`?tab=xxx` 无效）。
**跨 tab 页传参必须用 `getApp().globalData`。**
示例：
```js
// 发
const app = getApp(); app.globalData.alertTab = 'triggered'
uni.switchTab({ url: '/pages/alert/list' })
// 收（在目标页 onLoad 里读）
const app = typeof getApp === 'function' ? getApp() : null
const tab = app && app.globalData && app.globalData.alertTab
if (tab) { activeTab.value = tab; app.globalData.alertTab = null }
```

### ⚠️ uni-app H5 publicPath 覆盖 vite base 导致资源 404（重要！）
**`manifest.json` 的 `h5.publicPath` 优先级高于 `vite.config.js` 的 `base`，缺失会覆盖！**
- 现象：访问 `/mobile-app/` 页面 HTML 200，但 `/assets/*.js`、`/assets/*.css` 全部 404 → 白屏
- 根因：`mobile/src/manifest.json` 的 `h5` 节点缺 `publicPath`，uni-app 默认 `/`，**覆盖** `vite.config.js` 的 `base: '/mobile-app/'` → build 产物资源路径为 `/assets/`
- 404 链路：HTML 引用 `/assets/xxx.js` → 5173 proxy `/assets` → 后端 8000 的 `/assets/` 是 API 路由（`app/routers/assets.py`，`prefix="/assets"`，无静态文件）→ 404
- **修复**（`mobile/src/manifest.json` h5 节点必须同时配）：
  ```json
  "h5": {
      "router": { "mode": "hash", "base": "/mobile-app/" },
      "publicPath": "/mobile-app/",
      "title": "AIOps 移动运维",
      "template": "index.html"
  }
  ```
- 改完必须重新 `npm run build:h5 --prefix mobile`，新产物 `dist/build/h5/index.html` 资源路径变为 `/mobile-app/assets/*`
- **教训**：uni-app 的 H5 资源前缀由 `manifest.json` 决定，`vite.config.js` 的 base 会被覆盖；同一 `/assets` 路径既是静态资源又是 API，需通过前缀隔离

### ⚠️ 后端启动方式（重要！）
在 opencode 的 bash 工具中直接运行 `python run.py` 会**随 bash 会话超时而终止进程**。
必须在新窗口中启动（PowerShell 环境用 `Start-Process`，cmd 环境用 `start`）：

```powershell
# PowerShell（opencode bash 工具实际是 PowerShell）
Start-Process -FilePath 'D:\AIOPS\project07\.venv\Scripts\python.exe' -ArgumentList 'run.py' -WorkingDirectory 'D:\AIOPS\project07' -WindowStyle Normal
```
```bash
# cmd 环境
start "AIOps Backend" D:\AIOPS\project07\.venv\Scripts\python.exe run.py
```

### ⚠️ uni-app H5 页面组件缓存大坑（重要！）
**uni-app 的 Vite 插件对 `src/pages/` 下的页面组件（如 `oncall/my.vue`）有深层编译缓存**
- 修改 `.vue` 页面文件（模板/脚本/样式）后，即使重启 dev server，改动**可能不生效**
- `curl` 验证 Vite 返回的是新文件，但浏览器 DOM 仍渲染旧版本（CSS 背景色、调试条全不显示）
- **`src/main.js` 的改动总是生效**（因为它是入口模块，Vite 每次都重新加载）
- 用 `document.addEventListener('click', ...)` 捕获阶段监听可以全局拦截组件内事件

**遇到页面组件改动不生效时：**
1. 先把补丁逻辑写在 `main.js` 里验证（入口文件改动一定生效）
2. 确认逻辑正确后，再排查页面组件缓存问题（可能需 `npm run build:h5` 全量构建）
3. 绕过方案：通过全局事件拦截 + 直接调 API 来实现功能，不依赖页面组件内的代码

### ⚠️ @tap 事件的 DOM 拦截
- uni-app 的 `@tap` 事件在 H5 中同时触发 `touchstart` 和 `click` 事件
- `<view>` 渲染为 `<uni-view>` 自定义元素
- 全局拦截应用 `document.addEventListener('click', handler, true)`（捕获阶段）
- 通过文本内容匹配（如 `el.textContent.trim() === '拨号'`）比类名匹配更可靠
**登录页由 Vue SPA 渲染，不是 Jinja2 模板！**
- 路由 `GET /login` → `auth.py:_serve_vue()` → `frontend/dist/index.html`
- **真正的登录页组件**: `frontend/src/views/LoginView.vue`
- ~~`app/templates/login.html` 是旧 Jinja2 模板，**已废弃不用**（死代码 dead code）~~ **已删除**
- 修改登录页 UI 必须改 `LoginView.vue`，然后 `npm run build --prefix frontend` 构建

### 构建 Vue 前端
```bash
cd frontend && npm run build
```

### Vue 项目结构
```
frontend/
├── index.html              # 入口 HTML
├── vite.config.js          # Vite 配置 (代理 /api, /agent, /ai 到 FastAPI)
├── package.json
├── src/
│   ├── main.js             # Vue 入口
│   ├── App.vue             # 根组件
│   ├── assets/main.css     # 设计系统 (从 sxdevops 移植)
│   ├── layout/
│   │   └── AppLayout.vue   # 主布局 (侧边栏 + 顶栏 + 内容区)
│   ├── router/index.js     # Vue Router
│   ├── stores/
│   │   └── app.js          # Pinia store (侧边栏折叠状态)
│   ├── api/
│   │   └── request.js      # Axios 封装
│   └── views/
│       └── ChatView.vue    # AI 智能助手聊天页 (第一个 Vue 页面)
```
