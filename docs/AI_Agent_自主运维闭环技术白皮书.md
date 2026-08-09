# AI Agent 自主运维闭环 — 技术白皮书

## 一、整体架构

### 三层架构图

```
┌──────────────────────────────────────────────────────────────┐
│  Layer 3: AI Agent 决策层（大脑）                             │
│                                                              │
│  ┌──────────────────────────────────────────────────────┐    │
│  │  agent_service.py（对话推理引擎）                       │    │
│  │  ReAct 循环 + 30+ MCP 工具 + 幻觉检测 + 链式推进       │    │
│  │  process_chat_message() → call_llm() → tool_call()     │    │
│  └──────────────────────────────────────────────────────┘    │
│                                                              │
│  ┌──────────────────────────────────────────────────────┐    │
│  │  agent_autonomous.py（自主巡检闭环，新增）              │    │
│  │  Perceive → Analyze → Act → Verify                    │    │
│  │  每 5 分钟自动运行，由 main.py background_loop 触发     │    │
│  └──────────────────────────────────────────────────────┘    │
│                                                              │
│  MCP 工具清单（按场景分组）：                                 │
│  ┌──────────┬──────────────┬──────────────────────────────┐  │
│  │ 场景     │ 工具           │ 说明                        │  │
│  ├──────────┼──────────────┼──────────────────────────────┤  │
│  │ 告警     │ query_alerts  │ 查告警列表/详情              │  │
│  │          │ acknowledge   │ 确认/解决/静默告警           │  │
│  │          │ create_rule   │ 创建/更新/删除告警规则       │  │
│  ├──────────┼──────────────┼──────────────────────────────┤  │
│  │ 资产     │ query_assets  │ 查资产列表                   │  │
│  │          │ create_asset  │ 创建/更新/删除资产           │  │
│  ├──────────┼──────────────┼──────────────────────────────┤  │
│  │ 指标     │ query_metrics │ PromQL + 字段模式查指标      │  │
│  ├──────────┼──────────────┼──────────────────────────────┤  │
│  │ 执行     │ run_command   │ 远程执行命令（隧道优先）      │  │
│  │          │ restart       │ 重启服务                     │  │
│  │          │ clean_disk    │ 清理磁盘                     │  │
│  │          │ install_pkg   │ 安装软件包（异步）            │  │
│  ├──────────┼──────────────┼──────────────────────────────┤  │
│  │ 知识     │ query_kb     │ 知识库 + RAG 语义检索         │  │
│  │          │ query_runbook│ 标准操作流程                  │  │
│  ├──────────┼──────────────┼──────────────────────────────┤  │
│  │ 分析     │ analyze_rca  │ 根因分析                      │  │
│  │          │ correlation  │ 多维关联分析                  │  │
│  └──────────┴──────────────┴──────────────────────────────┘  │
├──────────────────────────────────────────────────────────────┤
│  Layer 2: 统一执行层（双臂）                                  │
│                                                              │
│  route_exec(asset_id, command)                               │
│  ┌─────────────────────┐      ┌─────────────────────┐        │
│  │ Edge Agent 隧道     │      │ SSH 回退             │        │
│  │ 持久 WebSocket 连接  │      │ paramiko 临时连接    │        │
│  │ 零监听端口 / 过防火墙  │      │ 需 22 端口暴露       │        │
│  │ 毫秒级 / 双向实时    │      │ 每次新建连接          │        │
│  └─────────────────────┘      └─────────────────────┘        │
│  对上层完全透明，调用方只需指定 asset_id + command             │
│                                                              │
│  沙盒管控：执行前过 sandbox.evaluate() 策略评估                │
│  包括：资产白名单 / 工具白名单 / 命令黑名单 / 风险等级         │
├──────────────────────────────────────────────────────────────┤
│  Layer 1: 节点执行层（手脚）                                  │
│                                                              │
│  edge_agent.py（部署在目标节点上的轻量守护进程）               │
│  ┌──────────────┐  ┌──────────────┐  ┌──────────────────┐   │
│  │ 指标采集      │  │ 命令执行      │  │ 自动重连          │   │
│  │ CPU/内存/磁盘 │  │ subprocess    │  │ 指数退避 1~60s   │   │
│  │ 每 60s 上报   │  │ 支持 PTY 终端 │  │ 断线自动恢复      │   │
│  └──────────────┘  └──────────────┘  └──────────────────┘   │
│  零监听端口，所有通信通过已建立的 WebSocket 反向隧道            │
└──────────────────────────────────────────────────────────────┘
```

### 关键设计原则

| 原则 | 说明 |
|------|------|
| 决策在云端，执行在边缘 | AI 大脑跑在云端（LLM），edge agent 只做采集+执行 |
| 统一执行路由 | 所有工具的最终执行必经 route_exec()，不分通道 |
| 沙盒安全管控 | 每个执行动作过策略评估，高危操作需用户确认 |
| 自主闭环 | 感知→分析→执行→验证，无需人工介入 |
| 可观测性 | 每轮闭环记录到 AutonomousCycle 表，前端可视 |

---

## 二、自主巡检闭环详解

### 闭环流程

```
每 5 分钟触发（或手动触发）
         │
         ▼
┌─────────────────────────────────────────────────────┐
│  Phase 1: 感知 (Perceive)                            │
│  遍历所有资产，查询最新指标和告警                     │
│  CPU > 90% → critical                               │
│  CPU > 80% → warning                                │
│  内存 > 90% → critical                              │
│  磁盘 > 92% → critical                              │
│  活跃告警 → 按 severity 分级                        │
│  结果存入 AutonomousCycle.issues_found              │
└──────────────────────┬──────────────────────────────┘
                       ▼
┌─────────────────────────────────────────────────────┐
│  Phase 2: 分析 (Analyze)                             │
│  规则引擎分析异常并生成修复计划                      │
│  ┌──────────────────────────────────────────────┐   │
│  │ CPU critical → ps aux 排查 top 进程           │   │
│  │ 内存 critical → free -m + ps 排查内存占用     │   │
│  │ 磁盘 critical → df -h + du 排查空间占用       │   │
│  │ 告警 critical → 检查告警详情                   │   │
│  └──────────────────────────────────────────────┘   │
│  结果存入 AutonomousCycle.llm_analysis + plan       │
└──────────────────────┬──────────────────────────────┘
                       ▼
┌─────────────────────────────────────────────────────┐
│  Phase 3: 执行 (Act)                                 │
│  遍历修复计划，通过 route_exec 下发                  │
│  route_exec(asset_id, command)                      │
│  有在线 agent → 隧道执行                            │
│  无在线 agent → SSH 回退                            │
│  结果存入 AutonomousCycle.actions_taken              │
└──────────────────────┬──────────────────────────────┘
                       ▼
┌─────────────────────────────────────────────────────┐
│  Phase 4: 验证 (Verify)                              │
│  记录执行结果（成功/失败）                           │
│  更新 AutonomousCycle 状态                          │
│  等待下一轮循环再感知，形成持续改进                  │
└─────────────────────────────────────────────────────┘
```

### 数据模型

```sql
-- 自主巡检闭环记录表
CREATE TABLE autonomous_cycles (
    id          INTEGER PRIMARY KEY AUTOINCREMENT,
    cycle_id    TEXT    UNIQUE,           -- 闭环 UUID
    status      TEXT,                     -- running / success / failed / partial
    phase       TEXT,                     -- perceive / analyze / act / verify / done
    summary     TEXT,                     -- 一句话摘要
    detail      TEXT,                     -- 详细描述
    issues_found TEXT,                    -- JSON: 发现的问题列表
    actions_taken TEXT,                   -- JSON: 执行的动作列表
    llm_analysis TEXT,                    -- LLM 分析输出
    error_message TEXT,                   -- 异常信息
    asset_count INTEGER DEFAULT 0,        -- 检查资产数
    issue_count INTEGER DEFAULT 0,        -- 发现问题数
    action_count INTEGER DEFAULT 0,       -- 执行动作数
    success_count INTEGER DEFAULT 0,      -- 成功动作数
    duration_ms INTEGER DEFAULT 0,        -- 总耗时
    created_at  DATETIME DEFAULT CURRENT_TIMESTAMP,
    finished_at DATETIME
);
```

---

## 三、场景验证

### 场景 1：CPU 高负载 → 自动排查

**触发条件**：资产 vm-132-master2 CPU 使用率 95.5%（超过 critical 阈值 90%）

**闭环记录**：

| 阶段 | 操作 | 结果 |
|------|------|------|
| 感知 | 查询 18 个资产的最新指标 | 发现 1 个问题：asset#2 CPU=95.5% critical |
| 分析 | 规则引擎匹配 CPU critical 规则 | 生成诊断命令：`ps aux --sort=-%cpu \| head -10` |
| 执行 | `route_exec(2, "ps aux --sort=-%cpu \| head -10")` | 通道=SSH，exit=-1（SSH 不通，预期行为） |
| 验证 | 记录执行失败 | 状态=partial（1 动作 0 成功） |

**结论**：闭环逻辑完整走通。SSH 执行失败是因为 vm-132-master2 未部署 edge agent 且 SSH 凭据不可达。部署 edge agent 后通道会自动切换为隧道。

### 场景 2：正常状态 → 无需操作

**触发条件**：其他 17 个资产指标均在正常范围

**闭环记录**：未发现问题，状态=success，0 动作

### 覆盖场景矩阵

| 场景 | 指标 | 阈值 | 触发动作 | 预期 |
|------|------|------|---------|------|
| CPU 高 | cpu_usage > 90% | critical | `ps aux --sort=-%cpu` | 诊断 |
| CPU 告警 | cpu_usage > 80% | warning | 仅记录不操作 | 告警 |
| 内存高 | memory_usage > 90% | critical | `free -m && ps aux --sort=-%mem` | 诊断 |
| 磁盘高 | disk_usage > 92% | critical | `df -h && du -sh /*` | 诊断 |
| 活跃告警 | alert severity=critical | — | 检查告警详情 | 诊断 |

---

## 四、操作指南

### 4.1 查看自主巡检结果

**方式一：Web 界面**
```
浏览器 → AI Agent 管控 → Agent 自主巡检
```
页面显示：
- 顶部统计：巡检次数 / 发现问题 / 执行动作 / 成功动作
- 巡检历史表格：每轮的状态、摘要、问题数、动作数、耗时
- 点击"详情"查看完整的问题列表和执行动作
- 点击"立即巡检"手动触发一轮

**方式二：API**
```bash
# 查看历史（最近 50 条）
curl http://localhost:8000/agent/autonomous/history?limit=50

# 手动触发一轮
curl -X POST http://localhost:8000/agent/autonomous/trigger
```

### 4.2 部署 Edge Agent 到目标节点

```
浏览器 → AI Agent 管控 → Agent 下发与监控
  → 选择可部署资产
  → 确认云端地址（默认 http://11.0.1.1:8000，即宿主机 VMware 网关）
  → 点击"下发 Agent"
  → 查看部署进度
  → 部署成功后，Agent 自动注册上线
```

部署后效果：
- 该资产显示在线
- 命令执行通道自动切换为隧道（WebSocket）
- 指标采集每 60s 上报
- 心跳每 30s 保活

### 4.3 命令执行

**方式一：Web 界面**
```
浏览器 → AI Agent 管控 → Agent 下发与监控
  → 切到"命令执行"Tab
  → 选择资产 + 输入命令 → 执行
```

**方式二：API**
```bash
# 通过统一路由执行（隧道优先，SSH 回退）
curl -X POST http://localhost:8000/agent/exec \
  -H "Content-Type: application/json" \
  -d '{"asset_id": 1, "command": "hostname && uptime", "timeout": 10}'
```

### 4.4 沙盒策略配置

```
浏览器 → AI Agent 管控 → 沙盒管理
  → 配置策略：资产白名单 / 工具白名单 / 命令黑名单 / 风险等级
  → 开启后，所有执行命令过沙盒评估
```

### 4.5 AI 智能体对话

```
浏览器 → AI 运营者 → AI 智能助手
```
或已有菜单入口（如已配置）：
```
浏览器 → AI Agent 管控 → Agent 智能体对话
```

对话示例：
- "帮我查一下 vm-131-master1 的 CPU 使用率"
- "列出所有告警"
- "重启 nginx 服务"（会提议→确认→执行）

---

## 五、菜单结构

### 左侧菜单层次

```
AI Agent 管控（原 AI 运维沙盒）
├─ Agent 管理
│   ├─ Agent 下发与监控    ← 部署/管理 edge agent，执行命令
│   └─ Agent 自主巡检      ← 查看自主巡检闭环历史，手动触发
└─ 沙盒策略
    └─ 沙盒管理            ← 安全策略配置
```

---

## 六、配置文件

### 阈值配置（`agent_autonomous.py`）

```python
CPU_WARN_THRESHOLD = 80.0    # CPU 告警阈值
CPU_CRIT_THRESHOLD = 90.0    # CPU 严重阈值
MEM_WARN_THRESHOLD = 80.0    # 内存告警阈值
MEM_CRIT_THRESHOLD = 90.0    # 内存严重阈值
DISK_WARN_THRESHOLD = 85.0   # 磁盘告警阈值
DISK_CRIT_THRESHOLD = 92.0   # 磁盘严重阈值
```

### 巡检周期（`main.py`）

```python
_AUTONOMOUS_INTERVAL = 300  # 秒，默认 5 分钟
```

---

## 七、新增文件清单

| 文件 | 说明 |
|------|------|
| `app/services/agent_autonomous.py` | 自主巡检闭环服务（感知→分析→执行→验证） |
| `app/routers/agent_autonomous.py` | 自主巡检 API（历史查询 + 手动触发） |
| `frontend/src/views/AgentAutonomousView.vue` | 自主巡检前端看板 |
| `app/models.py` | 新增 `AutonomousCycle` 模型 |
| `app/main.py` | 注册路由 + 注册到 background_loop（每 5 分钟） |

### 增强文件

| 文件 | 改动 |
|------|------|
| `app/menu_config.json` | AI Agent 管控 新增"Agent 自主巡检"菜单项 |
| `frontend/AppLayout.vue` | 注册 AgentAutonomousView 组件 |
| `app/routers/agent_deploy.py` | 新增 `route_exec_async()`（修复 event loop 嵌套） |
| `app/services/edge_tunnel_service.py` | 新增 `save_latest_metrics()` / `get_latest_metrics()` |
| `edge_agent/edge_agent.py` | 新增 `collect_metrics()`（每 60s 上报指标） |
| `app/services/agent_deploy_service.py` | 一键下发 agent（SSH 推送→安装→注册） |