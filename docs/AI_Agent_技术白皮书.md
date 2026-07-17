# AI 智能运维助手技术白皮书

> 本文档面向客户技术团队，阐述 AI 智能运维助手（简称 Agent）的能力边界、核心概念、技术架构与 SOP。

---

## 一、产品定位

AI 智能运维助手是 AIOps 平台的核心交互入口，通过自然语言对话完成：

- **查询**：资产、告警、指标、日志、K8s 资源
- **分析**：告警根因、调用链、异常检测
- **操作**：安装部署、重启服务、清理磁盘、确认/解决告警
- **执行**：运维自动化剧本（SOP WorkFlow）

---

## 二、核心概念

### 2.1 工具（Tool）

Agent 可调用的原子能力单元，分为两类：

| 类型 | 说明 | 示例 |
|------|------|------|
| **只读查询** | 直接调用，无需确认 | `query_assets`、`query_alerts`、`query_metrics` |
| **运维操作** | 通过"提议-确认"闭环执行 | `restart_service`、`install_package`、`run_script` |

### 2.2 提议-确认闭环（Propose-Confirm Loop）

高危运维操作必须用户显式确认，防止 AI 误操作：

```
用户: "帮我重启 Nginx"
Agent:  [提议动作]  重启 Nginx 服务 (高危)
       ┌─────────────────────────────┐
       │  用户点击「确认」按钮        │
       └─────────────────────────────┘
              ↓
         系统执行 → 结果反馈
```

### 2.3 异步任务（Background Job）

安装部署等长耗时任务（>30s）采用异步执行，用户可实时查看进度：

```
用户: "在这台服务器安装 Elasticsearch"
Agent:  [提议安装] → 用户确认 → 任务已提交
       ┌─────────────────────────────┐
       │  Agent 轮询任务状态            │
       │  "安装进行中，已完成 60%..."  │
       └─────────────────────────────┘
              ↓
         安装完成 → 最终结果汇报
```

### 2.4 补偿式回滚（Saga Pattern / Compensating Transaction）

多步骤安装任务中，任意步骤失败时自动逆向回滚已完成的步骤：

```
步骤1: 检测 OS            ✓
步骤2: 安装依赖包          ✓
步骤3: 下载 ES 二进制包     ✗ 网络超时
       ↓
自动回滚: 卸载已安装的依赖包 → 清理残留文件
```

### 2.5 SOP 工作流（Workflow）

预定义的多步骤运维剧本，支持 DAG 编排，确认一次自动推进全流程：

```
提议工作流: "在 K8s 集群扩容 Deployment"
  节点1: 检查当前 Pod 数        (自动执行)
  节点2: 修改 replicas 数量      (需确认)
  节点3: 验证扩容结果          (自动执行)
```

---

## 三、工具清单

### 3.1 只读查询工具

| 工具名 | 功能 |
|--------|------|
| `query_assets` | 查询资产列表（服务器、网络设备、数据库等） |
| `query_alerts` | 查询告警列表（支持状态/级别筛选） |
| `get_alert_detail` | 查询单个告警详情 |
| `query_metrics` | 查询指标时序数据 |
| `query_incidents` | 查询故障单 |
| `analyze_incident_rca` | 故障单根因分析 |
| `query_k8s_events` | 查询 K8s 事件 |
| `list_k8s_pods` | 列出 K8s Pod |
| `query_runbook` | 检索标准操作流程 |
| `query_knowledge_rag` | 语义搜索知识库 |

### 3.2 运维操作工具（需确认）

| 工具名 | 风险等级 | 功能说明 |
|--------|----------|----------|
| `restart_service` | 高危 | 远程重启服务 |
| `clean_disk` | 高危 | 清理指定路径磁盘空间 |
| `run_script` | 极危 | 在远程主机执行脚本 |
| `run_command` | 极危 | 远程执行任意命令（危险命令黑名单拦截） |
| `install_package` | 极危 | 异步安装软件（Elasticsearch/Nginx/MySQL 等） |
| `acknowledge_alert` | 低危 | 确认告警 |
| `resolve_alert` | 低危 | 解决告警 |
| `resolve_incident` | 低危 | 关闭故障单 |
| `silence_alert` | 中危 | 静默告警（计划维护） |
| `create_alert_rule` | 中危 | 新建告警规则 |
| `update_alert_rule` | 中危 | 更新告警规则 |
| `delete_alert_rule` | 高危 | 删除告警规则 |
| `create_asset` | 中危 | 添加资产 |
| `update_asset` | 中危 | 更新资产配置 |
| `delete_asset` | 高危 | 删除资产 |
| `probe_assets` | 低危 | 批量探测资产健康状态 |

---

## 四、异步安装详细流程

### 4.1 安装 Elasticsearch 示例

```
用户: "在 192.168.1.10 上安装 Elasticsearch 8.19.0，最小配置"

Step 1 → 提议安装
  propose_action(
    action_type="install_package",
    payload={
      package_name: "elasticsearch",
      asset_id: 123,
      version: "8.19.0",
      options: { start_service: true }
    }
  )

Step 2 → 用户确认 → 创建 BackgroundJob

Step 3 → 后台线程分步执行
  [5%]   检测操作系统
  [15%]  安装系统依赖（Java/curl/wget）
  [30%]  下载 Elasticsearch 二进制包 (~1GB)
  [50%]  解压安装到 /opt/elasticsearch
  [60%]  写入配置文件（单节点 + 内存锁定）
  [70%]  注册 systemd 服务
  [80%]  启动 Elasticsearch
  [92%]  等待 10s 启动
  [95%]  验证 HTTP 9200 端口
  [100%] 安装完成

Step 4 → AI 轮询 get_task_status，每轮汇报进度
  "正在下载 Elasticsearch，预计还需 2-3 分钟..."

Step 5 → 安装完成，汇报最终结果
  "✅ Elasticsearch 8.19.0 安装完成
   访问地址: http://192.168.1.10:9200
   集群名: my-es-cluster
   内存: 512m JVM heap"
```

### 4.2 失败回滚示例

```
用户: "在服务器安装 Elasticsearch"

Step 3 → 后台线程执行
  [5%]   检测操作系统 (Ubuntu)
  [15%]  安装依赖包 (openjdk-17)
  [30%]  下载 ES 包
  [60%]  解压安装
  [75%]  写入配置文件
  [80%]  启动 ES
  [95%]  验证 HTTP 端点  ✗ 连接超时

       ↓ 检测到失败
自动回滚:
  [回滚] 停止 elasticsearch 服务
  [回滚] 删除 /opt/elasticsearch 目录
  [回滚] 删除下载的 tar.gz 包
  [回滚] 卸载 openjdk-17 相关包

Step 4 → AI 汇报
  "❌ Elasticsearch 安装失败（ES 启动验证超时）。
   系统已自动回滚所有变更。
   原因: 目标主机内存较小（512MB），建议先升级配置后重试。"
```

---

## 五、技术架构

### 5.1 组件交互图

```
┌──────────────┐      ┌─────────────────┐      ┌──────────────────┐
│   前端 Vue    │ ──▶ │  FastAPI 后端    │ ──▶ │   LLM (GPT-4o)   │
│  AI 助手页   │      │  Agent Service  │      │  (工具调用)       │
└──────────────┘      └────────┬─────────┘      └──────────────────┘
                               │
                    ┌──────────┴──────────┐
                    │                     │
              ┌─────▼─────┐      ┌──────▼──────┐
              │ MCP Tools │      │ Background  │
              │ (工具层)  │      │ Task Runner │
              └─────┬─────┘      │ (线程池)    │
                    │            └──────┬──────┘
         ┌──────────┼──────────┐        │
         │          │          │        │
  ┌──────▼──┐ ┌────▼───┐ ┌───▼────┐   │ SSH
  │ Remed.   │ │Assets  │ │Alert   │   │
  │ Service  │ │Service │ │Service │   ▼
  └──────────┘ └────────┘ └────────┘  ┌──────────────────┐
                                       │  Remote Host     │
                                       │  (SSH Execute)  │
                                       └──────────────────┘
```

### 5.2 关键设计

#### 安全分层

- **工具注册层**：所有 `execute_*` 工具标记 `expose_to_llm=False`，LLM 无法直调
- **提议层**：`propose_action` 是唯一入口，校验 action_type 白名单
- **确认层**：PendingAction 等用户 UI 确认后才执行
- **审计层**：ToolInvocation 记录每次调用的请求/响应/延迟

#### LLM 超时治理

| 方案 | 说明 |
|------|------|
| **短任务（<30s）** | `execute_*` 同步执行，LLM 等待返回 |
| **长任务（>30s）** | BackgroundJob 异步执行，LLM 轮询 `get_task_status` |
| **危险命令** | 黑名单拦截（`rm -rf /`、`mkfs`、`dd` 等） |

#### 状态追踪

```
PendingAction.status: pending → confirmed → executing → executed / failed
BackgroundJob.status: pending → running → success / failed
  ↕ 自动关联
get_task_status(job_id) → 实时进度 + 最终结果
```

---

## 六、FAQ

**Q: AI 会不会误操作服务器？**

A: 不会。所有写操作（重启、删除、安装）都需要用户在 UI 点击确认，没有自动执行的通道。危险命令（`rm -rf /`、`dd`、`shutdown`）在命令层被黑名单拦截。

**Q: 安装过程中网络断了怎么办？**

A: 任务记录保存在数据库，重启后自动继续。安装失败时会自动执行回滚，保持服务器干净。

**Q: 支持哪些软件的安装？**

A: 目前支持：Elasticsearch（ES）、Nginx、MySQL，以及通用的 apt/yum 包管理器安装。

**Q: 如何查看 AI 执行过的所有操作？**

A: 在「AI 审计」页面可以查看完整的工具调用记录，包含每个操作的发起时间、执行结果、耗时。
