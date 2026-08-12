# AIOps 借鉴 Pixiu 集成改造设计 v1

> 日期: 2026-08-12
> 状态: 设计稿,待评审
> 定位: 借鉴 Pixiu 开源项目的工程化优势,分阶段集成到 AIOps 项目的 AI 自动部署功能

---

## 一、Pixiu 项目逆向分析总结

### 1.1 Pixiu 是什么

Pixiu 是一个 Go 编写的云原生容器平台,核心能力是**通过页面"点点点"部署 K8S 集群**。其技术栈为 Go + Gin + GORM + MySQL + Docker SDK + kubez-ansible(Ansible 驱动)。

### 1.2 Pixiu 的 5 大核心优势(代码层确认)

| 编号 | 优势 | 关键代码位置 | 设计要点 |
|------|------|-------------|---------|
| ① | **离线部署 K8S** | `deploy/offline/README.md` | `builder serve` 同时起私有 Registry + Apt/Yum 源,自动加载离线包到本地仓库,隔离公网部署 |
| ② | **Deploy Agent 模式** | `pkg/deployagent/agent.go`, `pkg/deployagent/runner.go`, `cmd/deploy-agent/main.go` | 边缘节点主动出站:心跳(5s) + Claim 任务 + 拉取 Plan + 本地渲染 + Docker 执行 + 回传结果 |
| ③ | **Job 队列 + 状态机** | `pkg/controller/plan/agent_job.go`, `pkg/controller/plan/worker.go` | `workqueue.RateLimitingInterface` 限速队列 + `jobs` 表持久化 + 轮询(2s) + 超时控制(60min) |
| ④ | **部署驱动容器化** | `pkg/deployagent/runner.go`, `pkg/util/container/container.go` | 部署逻辑封装在 Docker 镜像(kubez-ansible)中,目标机只需 Docker,无需额外依赖 |
| ⑤ | **反向隧道** | `pkg/tunnel/manager.go`, `pkg/clusteragent/agent.go` | 基于 `rancher/remotedialer`,Cluster-Agent 从边缘发起 WebSocket 连接,控制面反向访问 apiserver |

### 1.3 Pixiu 的辅助设计亮点

- **Handler 职责链模式**: `pkg/controller/plan/worker.go` 定义 `Handler` 接口,8 个 Handler 串行执行,可插拔
- **模板渲染引擎**: `template/globals.go`/`hosts.go`/`multinode.go`,Go `text/template` 渲染配置文件
- **双认证(密码+密钥)**: `types.PlanNodeAuth` 统一抽象,序列化到 JSON,支持 `PasswordAuth` / `KeyAuth`
- **路由元数据持久化**: 路由注册时自动写入 `apis` 表,支持 API 级权限控制
- **定时任务管理器**: `cron/v3` 驱动集群同步(30s)/告警评估/审计清理

### 1.4 Pixiu 的不足(我们已领先)

| 维度 | Pixiu | AIOps 项目 |
|------|-------|-----------|
| 部署智能度 | 模板化执行(Ansible Playbook) | AI 驱动(环境感知/失败诊断/DAG 编排/自主决策) |
| 实时终端 | 无(仅任务日志) | WebSocket 实时 xterm.js 终端 |
| 报告系统 | 无 | AI 生成交付级报告(MD/HTML/PDF) |
| 部署目标 | 仅 K8S 集群 | 任意应用(通过 AI 解析手册) |
| 失败处理 | 简单状态机(失败即终止) | AI 诊断 + 修复建议 + 自主决策(fix/retry/skip/rollback) |

---

## 二、AIOps 项目现状

> ⚠️ 重要更正(2026-08-12): 设计初稿阶段 B"Agent 模式"经核对,我们的系统**已有完整的 Agent 下发与监控能力**,且比 Pixiu 的 deploy-agent 更先进。阶段 B 从"新建 Agent 系统"改为"部署执行引擎复用现有 agent 通道"。

### 2.0 现有 Agent 下发与监控(已存在,设计阶段 B 的前提)

| 文件 | 职责 | 与 Pixiu deploy-agent 对比 |
|------|------|---------------------------|
| `app/services/agent_deploy_service.py` | 一键 SSH 下发 edge_agent 到目标资产(装 python3 + 推送脚本 + systemd) | 优于 Pixiu(需手动下载二进制) |
| `app/services/edge_tunnel_service.py` | 云端侧反向隧道(注册/心跳/在线池/命令下发/审计) | 优于 Pixiu(WebSocket 实时 vs HTTP 轮询) |
| `app/routers/agent_deploy.py` | Agent 下发/清单/命令/审计/统一路由 API | 部分对齐 Pixiu agent API |
| `edge_agent/edge_agent.py` | 主机侧守护进程(WS 拨出/心跳/指标/PTY/命令执行) | 优于 Pixiu(还支持 WebSSH + 指标采集) |

**现有统一命令路由(关键复用点)**:
```python
# app/routers/agent_deploy.py
def route_exec(asset_id, command, ...) -> dict:
    """有在线 agent 走隧道,否则 SSH 回退。"""
    if asset.edge_agent_id and is_agent_online(asset.edge_agent_id):
        return await execute_command_via_tunnel(...)   # channel=tunnel
    return _ssh_fallback(...)                           # channel=ssh
```

**结论**: Agent 基础设施已具备,无需重复建设。阶段 B 只需做一件事——让 AI 部署执行引擎(现在硬编码走 SSH)接入 `route_exec`,优先走 agent 隧道。

### 2.1 已实现能力

- **AI 解析手册**: `ai_parse_manual()` → 结构化 SOP JSON
- **环境探查**: `probe_environment()` → SSH 探查 OS/端口/镜像/容器/目录
- **AI 环境映射**: `ai_auto_env_mapping()` → env_mapping + 服务拓扑 + 自适应建议
- **失败诊断**: `_ai_step_failure()` → AI 根因诊断 + 修复命令
- **DAG 编排**: `_ai_build_execution_dag()` → 并行组/串行组
- **自主决策**: `_ai_autonomous_decision()` → fix/retry/skip/rollback
- **健康门控**: `_ai_health_gate()` → 每步后检查 Docker/磁盘/端口
- **实时终端**: WebSocket + xterm.js
- **报告下载**: MD/HTML/PDF

### 2.2 缺失能力(待集成)

| 缺失项 | 当前状态 | 痛点 |
|--------|---------|------|
| 离线部署 | 全无 | 客户生产环境大多隔离公网,无法拉取镜像/包 |
| Agent 通道接入部署执行 | 部署硬编码 SSH 直连 | 已部署 edge_agent 的资产仍走 SSH,未利用隧道 |
| 部署任务持久化队列 | 无(直接调用) | 崩溃后任务丢失,无超时重试队列 |
| 容器化执行引擎 | 裸 SSH 执行 | 目标机需预装各种依赖,版本管理困难 |
| 反向隧道 | **已有**(edge_tunnel_service) | 已解决,无需新建 |

---

## 三、集成方案总览

### 3.1 技术挑战

Pixiu 是 Go 项目,我们是 Python 项目,所以**不能搬代码,只能借鉴设计**。具体差异:

| 维度 | Pixiu(Go) | AIOps(Python) | 集成方式 |
|------|----------|---------------|---------|
| 语言 | Go 1.25 | Python 3.10+ | 设计模型移植 |
| 框架 | Gin + GORM | FastAPI + SQLAlchemy | 对应模块实现 |
| 数据库 | MySQL | SQLite(SQLite-WAL) | 模型兼容 |
| 部署 | Docker 容器 | SSH 直连 | 新增容器执行路径 |
| 前端 | Vue SPA(独立仓库) | Vue SPA(内嵌) | 复用现有前端框架 |

### 3.2 四阶段集成路线

```
阶段 A: 离线部署能力     ← 最高价值,最独立
  ├─ OfflineRepoBundle 模型 + 离线仓库管理
  ├─ 私有 Registry 管理(内嵌/外挂)
  ├─ 离线包自动加载 + 镜像导入
  └─ AI 部署对接离线源

阶段 B: 部署执行接入 Agent 通道  ← 轻量改造(复用现有 edge_agent)
  ├─ 部署执行引擎 route_exec 化(隧道优先,SSH 回退)
  ├─ deploy_jobs 表(作业持久化)
  └─ 部署计划可选执行模式(local/agent/auto [默认])

阶段 C: 任务队列工程化    ← 提升可靠性
  ├─ deploy_jobs 状态机 + 后台 worker
  ├─ 超时/重试/持久化
  └─ 崩溃恢复

阶段 D: 容器化执行引擎    ← 可选,最重
  ├─ Runner 镜像管理
  ├─ Docker 容器执行路径
  └─ SSH 拉镜像 + docker run 替代裸命令
```

---

## 四、阶段 A: 离线部署能力(详细设计)

### 4.1 设计目标

参照 Pixiu 的 `builder serve` 方案,让 AIOps 平台在离线(air-gapped)环境中也能部署 K8S 集群和业务应用:用户上传离线包 → 平台自动加载镜像到私有 Registry + 生成 Apt/Yum 源 → 部署命令自动指向私有源。

### 4.2 数据模型

新增 `offline_repo_bundles` 表:

```python
class OfflineRepoBundle(Base):
    """离线仓库包 - 对标 Pixiu builder 的离线包管理"""
    __tablename__ = "offline_repo_bundles"

    id = Column(Integer, primary_key=True, index=True)
    name = Column(String(128), nullable=False, comment="离线包名称,如 pixiu-packages-ubuntu-24.04")
    description = Column(Text, default="")
    version = Column(String(64), default="", comment="K8S 版本,如 v1.31.6")
    os_type = Column(String(32), default="", comment="系统类型: ubuntu/centos/debian")
    os_version = Column(String(32), default="", comment="系统版本: 24.04/7/11")
    bundle_type = Column(String(32), nullable=False, comment="包类型: images/packages/server")
    file_path = Column(String(512), default="", comment="离线包文件路径(服务器存储路径)")
    file_size = Column(Integer, default=0, comment="文件大小(字节)")
    md5 = Column(String(64), default="", comment="文件 MD5 校验")
    status = Column(String(32), default="pending", comment="pending/loading/loaded/failed")
    loaded_images = Column(Integer, default=0, comment="已加载镜像数")
    total_images = Column(Integer, default=0, comment="总镜像数")
    loaded_packages = Column(Integer, default=0, comment="已加载系统包数")
    loaded_at = Column(DateTime, nullable=True, comment="加载完成时间")
    created_at = Column(DateTime, default=lambda: datetime.now())
    updated_at = Column(DateTime, default=lambda: datetime.now(), onupdate=lambda: datetime.now())
```

新增 `offline_registries` 表:

```python
class OfflineRegistry(Base):
    """私有镜像仓库配置 - 对标 Pixiu builder 的 Registry"""
    __tablename__ = "offline_registries"

    id = Column(Integer, primary_key=True, index=True)
    name = Column(String(128), nullable=False, comment="仓库名称")
    registry_url = Column(String(256), nullable=False, comment="仓库地址,如 10.0.0.1:5000")
    is_internal = Column(Boolean, default=False, comment="是否内嵌(平台自管理)")
    storage_path = Column(String(512), default="", comment="内嵌仓库存储路径")
    is_secure = Column(Boolean, default=False, comment="是否 HTTPS")
    username = Column(String(64), default="", comment="仓库用户名")
    password = Column(String(128), default="", comment="仓库密码")
    has_password = Column(Boolean, default=False, comment="是否已设置密码")
    is_default = Column(Boolean, default=False, comment="是否默认仓库")
    status = Column(String(32), default="active", comment="active/inactive/error")
    created_at = Column(DateTime, default=lambda: datetime.now())
    updated_at = Column(DateTime, default=lambda: datetime.now(), onupdate=lambda: datetime.now())
```

新增 `offline_package_sources` 表:

```python
class OfflinePackageSource(Base):
    """离线系统包源 - 对标 Pixiu builder 的 Apt/Yum 源"""
    __tablename__ = "offline_package_sources"

    id = Column(Integer, primary_key=True, index=True)
    bundle_id = Column(Integer, ForeignKey("offline_repo_bundles.id"), nullable=True)
    os_type = Column(String(32), nullable=False, comment="系统类型")
    os_version = Column(String(32), default="", comment="系统版本")
    source_url = Column(String(256), nullable=False, comment="源地址,如 http://10.0.0.1:8080/deb")
    source_type = Column(String(16), nullable=False, comment="deb/rpm")
    package_count = Column(Integer, default=0, comment="软件包数量")
    is_active = Column(Boolean, default=True, comment="是否启用")
    created_at = Column(DateTime, default=lambda: datetime.now())
```

### 4.3 API 设计

```
Offline 仓库管理:
  POST   /offline/api/bundles/upload         上传离线包
  GET    /offline/api/bundles                 列表(分页+过滤)
  GET    /offline/api/bundles/{id}            详情
  POST   /offline/api/bundles/{id}/load       加载离线包(自动导入镜像/包)
  DELETE /offline/api/bundles/{id}            删除
  GET    /offline/api/bundles/{id}/images     查看已加载镜像列表
  GET    /offline/api/bundles/{id}/packages   查看已加载包列表

Registry 管理:
  POST   /offline/api/registries             创建
  PUT    /offline/api/registries/{id}         更新
  DELETE /offline/api/registries/{id}         删除
  GET    /offline/api/registries              列表
  GET    /offline/api/registries/{id}         详情
  POST   /offline/api/registries/{id}/test    测试连接
  GET    /offline/api/registries/{id}/images  查看仓库镜像

包源管理:
  POST   /offline/api/sources                 创建
  DELETE /offline/api/sources/{id}            删除
  GET    /offline/api/sources                 列表

健康检查:
  GET    /offline/api/health                  离线仓库整体健康状态
```

### 4.4 前端页面

- **离线仓库管理页**(`OfflineRepoView.vue`):
  - 上传离线包(拖拽 + 文件选择)
  - 离线包列表(名称/版本/类型/状态/进度/加载时间)
  - 加载按钮 + 进度条(实时显示镜像导入进度)
  - 镜像列表弹窗(名称/标签/大小/状态)
- **Registry 管理页**(`OfflineRegistryView.vue`):
  - 添加/编辑/删除 Registry
  - 测试连接
  - 镜像浏览
- **部署计划对接**: 部署计划编辑页增加"离线模式"开关,启用后自动配置私有 Registry 和包源

### 4.5 后端服务

新增 `app/services/offline_repo_service.py`:

```python
def upload_bundle(db, file, name, bundle_type, os_type, os_version, version) -> dict
    """上传离线包,保存到存储目录,返回 bundle 记录"""

def load_bundle(db, bundle_id: int) -> dict
    """加载离线包:
    1. 解压 tar.gz
    2. 扫描镜像列表(images/)
    3. 逐个 docker load + docker tag + docker push 到 Registry
    4. 扫描 deb/rpm 包(packages/)
    5. 生成 Apt/Yum 源 metadata
    6. 更新 bundle 状态为 loaded
    """

def get_registry_images(db, registry_id: int) -> list
    """通过 Registry API 列出仓库镜像"""

def get_health_status(db) -> dict
    """检查所有 Registry 和包源可用性"""

def get_repo_config_for_plan(db, plan_id: int) -> dict
    """获取部署计划所需的离线配置(镜像仓库地址/包源地址)"""
```

### 4.6 离线部署流程

```
用户上传离线包(.tar.gz)
  │
  ▼
平台保存到 storage/offline/ 目录
  │
  ▼
用户点击"加载"
  │
  ▼
load_bundle():
  ├─ 解压: 读取 images/ 和 packages/ 目录
  ├─ 镜像: docker load → docker tag → docker push 到 Registry
  ├─ 包: 生成 Packages.gz(deb) 或 repodata(rpm)
  └─ 启动 HTTP 文件服务提供包源
  │
  ▼
创建部署计划时:
  ├─ 镜像仓库: 自动填入私有 Registry 地址
  ├─ 包源: 自动填入包源 URL
  └─ 目标机配置 insecure-registries 指向私有 Registry
  │
  ▼
执行部署:
  ├─ docker pull 从私有 Registry 拉取
  └─ apt/yum install 从私有源安装
```

### 4.7 依赖

- Python `docker` SDK(已有,用于环境探查)
- Python `aiohttp` / `requests`(已有)
- 宿主机需安装 Docker(已有,VictoriaMetrics 跑在 Docker 中)
- 可选: `createrepo`(rpm) / `dpkg-dev`(deb) 用于生成包源 metadata

---

## 五、阶段 B: 部署执行接入 Agent 通道(详细设计)

> ⚠️ 设计更正: 原"Agent 模式"方案假设我们没有 Agent,需新建 deploy_agents + agent_client。经核对,系统已有完整的 edge_agent 下发/监控/隧道能力(`agent_deploy_service.py` + `edge_tunnel_service.py` + `edge_agent.py`)。阶段 B 改为**轻量接入**。

### 5.1 设计目标

复用现有 edge_agent 反向隧道,让 AI 部署执行引擎不再硬编码走 SSH,而是**隧道优先、SSH 回退**。资产上已部署 edge_agent 时,部署命令走 WebSocket 隧道(实时、单向网络友好);未部署时自动回退 SSH(兼容现状)。

### 5.2 现状与改造点

**现状**: `deploy_service.py` 的 `_ssh_connect()` 直接建 SSH 连接执行命令,完全没走 agent 隧道。

**改造**: 现有 `route_exec`/`route_exec_async`(agent_deploy.py)已经实现了"隧道优先,SSH 回退"的统一路由,但**是按单条命令粒度**(每次调用一个命令,等待结果返回)。部署执行是"多步骤、逐步执行、实时流输出",需要把 `route_exec` 的能力接入部署执行引擎。

**方案 A(轻量,推荐)**: 在 `deploy_service.py` 增加 `_exec_command_on_asset()` 统一执行函数:
```python
def _exec_command_on_asset(db, asset, command, timeout=30, cwd="") -> dict:
    """部署执行统一入口: 有在线 agent 走隧道,否则 SSH 回退。"""
    if asset.edge_agent_id and is_agent_online(asset.edge_agent_id):
        result = _run_async(execute_command_via_tunnel(
            db, asset.edge_agent_id, command, 0, "deploy", "", timeout))
        result["channel"] = "tunnel"
        return result
    client, host = _ssh_connect(asset)
    # ... 现有 SSH 执行逻辑 ...
    return {"channel": "ssh", ...}
```
然后把现有执行路径(`_ai_stream_execute` 中所有 `client.exec_command`)替换为 `_exec_command_on_asset`。

**方案 B(完整,后置)**: 部署计划增加 `exec_mode` 字段,显式选择执行通道:
- `local`: 控制面 SSH 直连(现状)
- `agent`: 仅允许隧道执行(资产必须在线 agent)
- `auto`(默认): 隧道优先,SSH 回退

### 5.3 数据模型

**无需新增 `deploy_agents` 表**(已有 `EdgeSession` 管理 agent 在线状态)。

`deploy_jobs` 表(部署作业持久化,对标 Pixiu `jobs` 表,供阶段 C 任务队列使用):

```python
class DeployJob(Base):
    """部署作业 - 对标 Pixiu jobs 表,持久化部署执行记录"""
    __tablename__ = "deploy_jobs"

    id = Column(Integer, primary_key=True, index=True)
    plan_id = Column(Integer, ForeignKey("deploy_plans.id"), nullable=False, comment="关联部署计划")
    agent_id = Column(String(64), default="", comment="执行 agent(edge_agent_id),空=SSH")
    channel = Column(String(16), default="ssh", comment="执行通道: ssh/tunnel")
    task_name = Column(String(128), default="", comment="任务名称")
    step_order = Column(Integer, default=0, comment="关联步骤序号")
    command = Column(Text, default="", comment="执行命令")
    status = Column(String(32), default="pending", comment="pending/running/success/failed/timeout")
    message = Column(Text, default="", comment="状态消息")
    logs = Column(Text, default="", comment="执行日志(累积)")
    result = Column(Text, default="", comment="执行结果(JSON)")
    timeout_seconds = Column(Integer, default=600, comment="超时时间(秒)")
    started_at = Column(DateTime, nullable=True, comment="开始时间")
    finished_at = Column(DateTime, nullable=True, comment="完成时间")
    created_at = Column(DateTime, default=lambda: datetime.now())
    updated_at = Column(DateTime, default=lambda: datetime.now(), onupdate=lambda: datetime.now())
```

### 5.4 API 设计

```
部署执行通道:
  GET    /deploy/api/exec/channel           查询资产执行通道(asset_id → tunnel/ssh)
  POST   /deploy/api/exec/preview           预览某条命令会走哪个通道

Job 管理(部署作业):
  GET    /deploy/api/jobs                    列表(按 plan_id/status 过滤)
  GET    /deploy/api/jobs/{id}               详情
  GET    /deploy/api/jobs/{id}/logs          获取日志
  POST   /deploy/api/jobs/{id}/retry         重试
  POST   /deploy/api/jobs/{id}/cancel        取消

部署计划:
  PUT    /deploy/api/plans/{id}              增加 exec_mode 字段(local/agent/auto)
```

**Agent 管理沿用现有** `/agent/*` API(`/agent/agents` 列表、`/agent/deploy` 下发、`/agent/exec` 执行),不重复建设。

### 5.5 前端改动

- **DeployView.vue**: 部署计划编辑增加"执行模式"下拉(本地 SSH / Agent 隧道 / 自动)。部署执行终端标题区显示当前通道徽标(🔧 SSH / 📡 Tunnel)。
- **AgentManageView.vue**(已有): 无需大改,只补充展示"最近部署作业"Tab(可选)。

### 5.6 集成点

```
现有: deploy_service._ssh_connect() → client.exec_command(cmd)   [硬编码 SSH]
改造: deploy_service._exec_command_on_asset()
        ├─ asset 有在线 agent → execute_command_via_tunnel()      [channel=tunnel]
        └─ 否则 → _ssh_connect() → exec_command                    [channel=ssh, 兼容现状]
```

**收益**: 已下发 edge_agent 的资产自动走隧道(实时、单向网络友好),未下发资产继续走 SSH,无需用户感知切换。

---

## 六、阶段 C: 任务队列工程化(详细设计)

### 6.1 设计目标

参照 Pixiu 的 `workqueue` + `jobs` 表设计,为部署任务提供可靠的队列、持久化、超时、重试、崩溃恢复能力。

### 6.2 设计要点

- **队列**: 进程内 `queue.Queue`(对标 Pixiu `workqueue`)
- **持久化**: `deploy_jobs` 表(复用阶段 B 的表)
- **Worker**: 后台线程池(对标 Pixiu `worker` 协程)
- **状态机**: `pending → running → success/failed/timeout`
- **超时**: 每个 Job 独立 `timeout_seconds`
- **重试**: 失败后自动重试(最多 3 次)
- **崩溃恢复**: 启动时扫描 `running` 状态的 Job,重置为 `pending`

### 6.3 与现有 AI 执行引擎的集成

```python
# 现有 stream_execute 的改造
def stream_execute(db, plan_id, user_id=0, decision_queue=None):
    """改造后的执行入口"""
    plan = db.query(DeployPlan).filter(DeployPlan.id == plan_id).first()
    if plan.exec_mode == "local":
        # 现有 SSH 直连路径(不变)
        yield from _ai_stream_execute(db, plan_id, user_id, decision_queue)
    else:
        # Agent 路径: 创建 Job 序列
        yield from _agent_execute(db, plan_id, user_id)
```

### 6.4 后台 Worker

新增 `app/services/job_worker.py`:

```python
import threading, queue, time
from sqlalchemy.orm import Session

class JobWorker:
    """后台作业 Worker - 对标 Pixiu worker 协程"""
    def __init__(self, db_factory, num_workers=2):
        self._queue = queue.Queue()
        self._workers = []
        self._num_workers = num_workers

    def start(self):
        for i in range(self._num_workers):
            t = threading.Thread(target=self._worker_loop, daemon=True)
            t.start()
            self._workers.append(t)

    def _worker_loop(self):
        while True:
            plan_id = self._queue.get()
            if plan_id is None:
                break
            try:
                # 执行部署(复用现有逻辑)
                for event in stream_execute(self._db_session(), plan_id):
                    pass
            except Exception as e:
                logger.error(f"worker: plan {plan_id} failed: {e}")
            finally:
                self._queue.task_done()
```

---

## 七、阶段 D: 容器化执行引擎(简要设计)

### 7.1 设计目标

参照 Pixiu 的 `docker run` 执行方式,将部署执行引擎从"SSH 裸命令"升级为"目标机 SSH 拉取 Runner 镜像 + Docker 容器执行"。

### 7.2 设计要点

- **Runner 镜像**: 封装常用部署工具(Ansible/Docker Compose/Kubectl)的 Docker 镜像
- **执行流程**: SSH 连接目标机 → `docker pull runner:latest` → `docker run --rm -v /configs:/configs runner deploy`
- **配置挂载**: 通过 `-v` 将渲染后的配置挂载到容器内
- **网络**: `--net=host` 让容器直接使用宿主机网络

### 7.3 数据模型

```python
class Runner(Base):
    """部署执行引擎 - 对标 Pixiu runner 模型"""
    __tablename__ = "deploy_runners"

    id = Column(Integer, primary_key=True, index=True)
    name = Column(String(128), nullable=False, unique=True)
    engine_image = Column(String(512), nullable=False, comment="引擎镜像,如 kubez-ansible:v2.0.2")
    os_supported = Column(Text, default="[]", comment="支持的操作系统列表(JSON)")
    description = Column(Text, default="")
    status = Column(String(32), default="installed", comment="installed/not_installed/error")
    created_at = Column(DateTime, default=lambda: datetime.now())
```

### 7.4 集成点

容器化执行引擎作为现有 SSH 执行路径的**替代方案**,不改变上层 AI 解析/DAG 编排/决策逻辑,只替换底层执行方式:

```
现有: SSH → exec_command("docker compose up -d")
改造: SSH → docker pull runner → docker run runner deploy
```

---

## 八、CONTRACT.md 扩展

### 8.1 新增第十二章: 离线部署

| 表名 | 字段 | 类型 | 说明 |
|------|------|------|------|
| `offline_repo_bundles` | `name` | String(128) | 离线包名称 |
| | `description` | Text | 描述 |
| | `version` | String(64) | K8S 版本 |
| | `os_type` | String(32) | 系统类型 |
| | `os_version` | String(32) | 系统版本 |
| | `bundle_type` | String(32) | images/packages/server |
| | `file_path` | String(512) | 文件存储路径 |
| | `file_size` | Integer | 文件大小 |
| | `md5` | String(64) | 文件校验 |
| | `status` | String(32) | pending/loading/loaded/failed |
| | `loaded_images` | Integer | 已加载镜像数 |
| | `total_images` | Integer | 总镜像数 |
| | `loaded_packages` | Integer | 已加载包数 |
| `offline_registries` | `name` | String(128) | 仓库名称 |
| | `registry_url` | String(256) | 仓库地址 |
| | `is_internal` | Boolean | 是否内嵌 |
| | `storage_path` | String(512) | 存储路径 |
| | `is_secure` | Boolean | 是否 HTTPS |
| | `username` | String(64) | 用户名 |
| | `password` | String(128) | 密码(敏感) |
| | `has_password` | Boolean | 是否已设置 |
| `offline_package_sources` | `os_type` | String(32) | 系统类型 |
| | `source_url` | String(256) | 源地址 |
| | `source_type` | String(16) | deb/rpm |

### 8.2 新增第十三章: 部署执行通道与作业

| 表名 | 字段 | 类型 | 说明 |
|------|------|------|------|
| `deploy_jobs` | `plan_id` | Integer | 关联计划 |
| | `agent_id` | String(64) | 执行 agent(edge_agent_id),空=SSH |
| | `channel` | String(16) | 执行通道: ssh/tunnel |
| | `task_name` | String(128) | 任务名称 |
| | `step_order` | Integer | 关联步骤序号 |
| | `command` | Text | 执行命令 |
| | `status` | String(32) | pending/running/success/failed/timeout |
| | `logs` | Text | 执行日志 |
| | `result` | Text | 执行结果(JSON) |
| | `timeout_seconds` | Integer | 超时时间 |

> 说明: Agent 本身(`EdgeSession`/`EdgeCommandLog`)已有 CONTRACT 定义,阶段 B 不新增 Agent 表。

### 8.3 DeployPlan 模型扩展

| 现有字段 | 新增 | 说明 |
|---------|------|------|
| `exec_mode` | String(16), default="auto" | local/agent/auto(隧道优先,SSH 回退) |

---

## 九、风险与缓解

| 风险 | 级别 | 缓解措施 |
|------|------|---------|
| 离线包加载依赖宿主机 Docker 和系统工具(createrepo/dpkg-dev) | 中 | 加载操作在后台异步执行,失败时标记状态并返回错误信息 |
| Registry 内嵌实现复杂(Docker Registry v2 API) | 高 | 初期只支持"外挂 Registry",内嵌作为 v2 可选 |
| 部署执行接入隧道可能影响现有 SSH 执行稳定性 | 中 | 隧道优先仅在有在线 agent 时生效,失败自动回退 SSH,兼容现状 |
| 容器化执行引擎改造量大,可能影响现有功能 | 高 | 阶段 D 作为可选,不强制,先保证 A/B/C 稳定 |

---

## 十、实施路径

### 10.1 阶段依赖关系

```
阶段 A(离线部署) ── 独立,可先做
阶段 B(部署接入 Agent 通道) ── 独立,与 A 无依赖
阶段 C(任务队列) ── 复用 B 的 deploy_jobs 表,可与 B 合并
阶段 D(容器化执行) ── 依赖 A 的 Registry,可后置
```

### 10.2 推荐顺序

```
第 1 轮: 阶段 A(离线部署) + 阶段 B(部署接入 Agent 通道) → 两个独立,可并行
第 2 轮: 阶段 C(任务队列) → 与 B 合并实施
第 3 轮: 阶段 D(容器化执行) → 可选,按需
```

### 10.3 每轮工作量估算

| 阶段 | 后端(新文件) | 后端(改文件) | 前端(新页面) | 前端(改文件) | 估算工时 |
|------|------------|------------|------------|------------|---------|
| A | `offline_repo_service.py` + `offline_repo.py`(router) | `models.py` + `main.py` + CONTRACT.md | `OfflineRepoView.vue` + `OfflineRegistryView.vue` | `AppLayout.vue` + `menu_config.json` | 4-6 天 |
| B | 无(复用 edge_tunnel_service) | `deploy_service.py` + `deploy.py`(router) + `models.py` + CONTRACT.md | 无新页面 | `DeployView.vue`(执行模式下拉+通道徽标) | 1-2 天 |
| C | `job_worker.py` | `deploy_service.py` + `deploy.py`(router) | 无新页面 | 已有 | 2-3 天 |
| D | `runner_service.py` + 容器化执行路径 | `deploy_service.py` | 无新页面 | 已有 | 3-5 天 |

---

## 十一、附录: Pixiu 关键代码参考

| Pixiu 文件 | 行数 | 核心逻辑 | 参考价值 |
|-----------|------|---------|---------|
| `cmd/deploy-agent/main.go` | 100 | Agent 主循环:心跳 + Claim + RunJob | 参考: 与我们 edge_agent 对比,确认无需重建 |
| `pkg/deployagent/agent.go` | 150 | Agent 通信封装 + RunJob 分发 | 参考: 与我们 edge_tunnel_service 对比,确认无需重建 |
| `pkg/deployagent/runner.go` | 116 | Docker pull + run 执行引擎 | 阶段 D 的容器化执行 |
| `pkg/deployagent/util.go` | 138 | 配置渲染 + SFTP 获取 kubeconfig | 阶段 D 的渲染逻辑 |
| `pkg/controller/plan/agent_job.go` | 128 | Job 创建 + 轮询 + 超时控制 | 阶段 C 的 Job 状态机 |
| `pkg/controller/plan/worker.go` | 362 | Worker 编排 + Handler 链 | 阶段 C 的 Worker 设计 |
| `pkg/planrender/render.go` | 220 | 模板渲染引擎 | 参考(现有项目已用 Jinja2) |
| `pkg/tunnel/manager.go` | 139 | 反向隧道(remotedialer) | 参考: 与我们 edge_tunnel 隧道对比 |
| `deploy/offline/README.md` | 145 | 离线部署完整操作流程 | 阶段 A 的产品设计 |
| `template/globals.go` | 118 | globals.yml 模板 | 参考(模板语法) |