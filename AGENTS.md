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

## 更新格式
在 MEMORY.md 顶部插入新条目，格式为：
### YYYY-MM-DD: 标题
- 关键决策、变更、发现

## 开发流程
### 启动项目
终端1: python run.py          # FastAPI 后端 (端口 8000)
终端2: npm run dev --prefix frontend  # Vue 前端 (端口 3000，自动代理 API 到 8000)

浏览器访问 http://localhost:3000 使用 Vue 前端
浏览器访问 http://localhost:8000 使用原有 Jinja2 前端(兼容保留)

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

# 3. 重新启动
python run.py
```

**不要依赖** `npx kill-port 8000` 或 `taskkill`，它们常杀不干净。

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
