# AIOps 项目记忆

> 每次会话开始时读取本文件了解项目背景和之前的决策。
> 按照时间倒序排列。完整历史见 `MEMORY.md.bak.20260712`。

---

## 关键信息（始终保留）
- **项目路径**: `E:\AIOPS\project05`
- **启动后端**: `E:\Program Files\Python\Python313\python.exe run.py`（端口 8000）
- **启动前端**: `npm run dev --prefix frontend`（端口 3000，proxy → 8000）
- **启动移动端**: `npm run dev:h5 --prefix mobile`（端口 5173）
- **构建前端**: `npm run build --prefix frontend`
- **登录密码**: admin / 1234
- **Embedding**: BGE-small-zh-v1.5（512维）；RAG V2 用 BGE-M3（1024维）
- **向量库**: Milvus Lite（`db/milvus/kb_v2.db`）
- **数据库**: SQLite（`db/aiops.db` + `db/aiops_real.db`）
- **部署服务器**: 39.96.51.45（/data/AIOPS），git push → SSH 拉取 → 构建 → 重启

---

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
