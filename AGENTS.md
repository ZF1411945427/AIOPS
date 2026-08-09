# 项目规则

## 基本约定
- 每次回复请先称呼我为爸爸
- 全程使用中文;若我的描述像大白话,最后给出专业名词或专业提问话术供我学习
- 后端用 Python,前端用 Vue;做的内容有单独记录文件

## 会话记忆机制
- 每次会话开始时,必须读取 `MEMORY.md` 了解项目背景和之前的决策
- 会话过程中,有新的进展/决策/发现,及时更新 `MEMORY.md`(时间倒序,最新在最上面)
- 新条目格式:`### YYYY-MM-DD: 标题` + 关键决策/变更/发现

## ⚠️ 字段规范契约(重要!)
**`CONTRACT.md` 是全项目字段命名的 Single Source of Truth(唯一数据源)。**
涉及资产字段、连接配置、CI 类型、数据源字段的开发,**必须**:
1. **先读 `CONTRACT.md`** 确认现有字段定义和命名规范
2. **新增/修改字段时,先改 `CONTRACT.md`** 再同步前后端代码
3. 后端写入路径(`_build_connection_config` 等)、前端 `buildPayload`/`testConnection`/`openEdit`、数据库列名、`DataSource.auth_config` 字段名必须与 CONTRACT.md 一致
4. 敏感字段(密码/Token):后端返回 `***` + `has_*` 标记,前端编辑时置空、保存时空值=不更新
5. 不得自行发明字段名,不得使用 CONTRACT.md 中标注 ~~删除线~~ 的已废弃字段名

**违反契约会导致:** 前后端字段不匹配 → 静默数据丢失(保存了但实际没存进去)→ 功能失效且不报错,极难排查

## ⚠️ 路径规范契约(重要!)
**所有文件路径必须基于 `__file__`(Python)或 `%~dp0`(.bat)动态计算,禁止硬编码绝对路径(如 `D:\AIOPS\project08\xxx`)。**

| 场景 | 规范写法 |
|------|---------|
| Python 追加 `sys.path` / `os.chdir` | `os.path.dirname(os.path.abspath(__file__))` |
| Python 引用项目内资源(static/logs/models/fonts) | `Path(__file__).resolve().parent.parent / "logs"` |
| 日志目录默认值 | `os.environ.get("AIOPS_LOG_DIR", str(PROJECT_ROOT / "logs"))` |
| `.bat` 的 `cd` / 引用项目内目录 | `cd /d %~dp0` / `cd /d %~dp0frontend` |
| 测试脚本截图目录 | `os.path.join(os.path.dirname(__file__), "screenshots", "e2e_xxx")` |
| 部署脚本项目根目录 | `os.path.dirname(os.path.abspath(__file__))` |
| e2e 测试引用项目数据库 | `os.path.dirname(os.path.dirname(os.path.dirname(__file__))) / "db"` |

## ⚠️ 日志文件位置规范(重要!)

**所有 `.log` 日志文件必须统一放在项目根目录的 `logs/` 文件夹下,禁止散落在根目录或子目录(如 `frontend/`、`mobile/`)。**

| 日志来源 | 规范位置 |
|---------|---------|
| 后端日志(结构化日志,按天轮转) | `logs/aiops_{YYYY-MM-DD}.log`(由 `app/logger.py` 自动生成) |
| 后端启动重定向(手动重定向) | `logs/backend.log` |
| 前端 dev server 输出 | `logs/frontend_dev.log` |
| 移动端 dev/build 输出 | `logs/mobile_dev.log` |
| 临时排查日志 | `logs/_xxx.log`(用完即删) |

**规范写法:**
- Python 引用日志目录:`os.environ.get("AIOPS_LOG_DIR", str(Path(__file__).resolve().parent.parent / "logs"))`(见 `app/logger.py:36`)
- 手动重定向启动后端:`python run.py > logs/backend.log 2>&1`
- 前端日志:`npm run dev --prefix frontend > logs/frontend_dev.log 2>&1`
- 移动端日志:`npm run dev:h5 --prefix mobile > logs/mobile_dev.log 2>&1`

**禁止:** 在项目根目录生成 `*.log`(如 `_run_stdout.log`、`_err.log`、`mobile_dev.log`、`frontend.log`);把日志写到 `frontend/`、`mobile/` 等子目录。

**违反会导致:** 日志分散难排查,且 `*.log` 已被 `.gitignore` 忽略但散落文件易被误提交或遗漏清理。

**禁止:** 在 `.py` 写 `sys.path.insert(0, 'D:/AIOPS/project08')` 或 `os.chdir('...')`;在 `.bat` 写 `cd /d D:\AIOPS\project08` 或硬编码 `python.exe` 绝对路径;在测试脚本硬编码外机路径;硬编码 `C:\Windows\Fonts\`(用项目 `fonts/` 目录)。

**违反会导致:** 项目换机器/目录后全部路径失效 → 后端拒绝启动 → 所有功能不可用,且排查极其困难。

## 开发流程
### 启动项目
- 后端:`python run.py`(FastAPI,端口 8000,需在项目根目录执行)
- 前端:`npm run dev --prefix frontend`(端口 3000,自动代理 API 到 8000)
- 构建:`npm run build --prefix frontend`(修改 `frontend/src/views/*.vue` 后必须构建)
- 浏览器访问 http://localhost:3000(Vite dev server)或 http://localhost:8000(Vue SPA,`/` 和 `/login` 返回 `frontend/dist/index.html`)
- 仅 product_intro/overview、容器日志/终端等少量辅助页仍用 Jinja2 模板,主体已全部 Vue 化

### 后端启动方式(opencode bash 工具内)
直接运行 `python run.py` 会随 bash 会话超时终止进程,必须在新窗口启动:
```powershell
Start-Process -FilePath 'python.exe' -ArgumentList 'run.py' -WorkingDirectory '<项目根目录>' -WindowStyle Normal
```

## ⚠️ 高频必踩大坑

### Windows 热重载不可靠
`uvicorn --reload` 在 Windows 上旧子进程不退出 → 端口 8000 被占 → 新代码不生效。强制重启三步:
```bash
# 1. 杀残留 Python 进程(用 Win32_Process 命令行区分项目 python vs VSCode 插件 python)
powershell -Command "Get-Process python* | Stop-Process -Force"
# 2. 确认端口释放
python -c "import socket; s=socket.socket(); s.bind(('127.0.0.1',8000)); s.close(); print('OK')"
# 3. 重新启动
python run.py
```
不要依赖 `npx kill-port 8000` 或 `taskkill`,常杀不干净。端口 LISTENING ≠ 服务可用,CLOSE_WAIT 堆积 + curl 超时是死锁信号。

### Vue SPA 路由 404 坑
FastAPI + Vue SPA 架构下,新增 Vue 页面后**必须**在 `main.py` 的 `@app.get("/")` 后加 catch-all 兜底,且必须在所有 `app.include_router()` **之后**(否则拦截 API):
```python
@app.get("/{path:path}", response_class=HTMLResponse, include_in_schema=False)
def serve_vue_spa(path: str):
    return HTMLResponse(content=_VUE_INDEX.read_text(encoding="utf-8"))
```
否则点击菜单 Network 出现 `GET /xxx 404`,页面空白。

### menu_config.json 分组与叶子 key 冲突
同一层分组的 key 不能与叶子节点 key 相同(如分组用 `correlation-analysis`,叶子用 `observability-correlation`)。否则菜单项可见但点击无响应(`AppLayout.vue` 匹配到分组层无 `type` 属性 → 提前 return)。排查:浏览器 Console 执行 `window._navigateTo('xxx')` 看 `activeView` 是否被设置。`menu.py` 启动时缓存到内存,改 menu_config.json 后必须重启后端。

### 新增 Vue 页面四步
无需改 `router/index.js`,但需改:① `AppLayout.vue` 注册组件 + `activeView` 分支 ② `menu_config.json` 加菜单项 ③ `role_menus` 补权限 ④(若 SPA 404)`main.py` 加 catch-all。菜单 key=activeView,`type=vue` 时 `handleMenuSelect` 设 `activeView.value = key`。

### 登录页由 Vue SPA 渲染
路由 `GET /login` → `auth.py:_serve_vue()` → `frontend/dist/index.html`;真正登录页组件是 `frontend/src/views/LoginView.vue`(旧 Jinja2 模板 `app/templates/login.html` 已删除)。修改登录页 UI 必须改 `LoginView.vue` 后构建。

## ⚠️ uni-app 移动端四坑(若涉及移动端开发)

1. **switchTab 不能传参**:`uni.switchTab({ url })` 忽略所有 query 参数,跨 tab 页传参必须用 `getApp().globalData`(发送方设 `app.globalData.xxx`,目标页 `onLoad` 读取后置空)
2. **H5 publicPath 覆盖 vite base**:`manifest.json` 的 `h5.publicPath` 优先级高于 `vite.config.js` 的 `base`,缺失会覆盖 → `/assets/*.js` 404 白屏。`mobile/src/manifest.json` 的 h5 节点必须同时配 `publicPath: "/mobile-app/"`,改完重新 `npm run build:h5 --prefix mobile`
3. **页面组件深层编译缓存**:`src/pages/` 下 `.vue` 改动可能不生效(浏览器 DOM 渲染旧版本),但 `src/main.js` 改动总生效。遇问题先在 `main.js` 验证逻辑,再排查组件缓存(可能需 `npm run build:h5` 全量构建);绕过方案用 `document.addEventListener('click', handler, true)` 全局事件拦截 + 直接调 API
4. **@tap 事件 DOM 拦截**:uni-app `@tap` 在 H5 同时触发 touchstart + click;`<view>` 渲染为 `<uni-view>`;全局拦截用捕获阶段 `document.addEventListener('click', handler, true)`,文本内容匹配比类名匹配可靠
