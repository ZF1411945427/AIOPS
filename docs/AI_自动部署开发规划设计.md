# AI 自动部署(LLM-driven Deployment Automation)开发规划设计

> 版本: v0.1
> 日期: 2026-08-11
> 状态: 规划设计稿,待评审
> 定位: AIOps 平台从「被动运维」到「主动变更管理」的跃迁,变更管理(Change Management)与部署编排(Deployment Orchestration)闭环。

---

## 一、背景与目标

### 1.1 业务背景

当前 AIOps 平台已打通 **监控 → 分析 → 修复 → 验证** 的运维闭环,但只能"修"(对存量故障做自愈),不能"建"(面向变更做部署)。部署/变更仍是人工:

- 运维拿一份部署手册,逐条手工在目标机执行,参数写死,换环境就要改。
- 多环境(测试/预发/生产)环境差异大,参数映射、依赖检查、失败排查全靠人肉。

本功能目标:上传**代码包引用** + **部署手册** + **现有环境信息**(资产),AI 基于真实环境生成结构化部署计划并逐步执行,实现 **AI 驱动的变更编排**。

### 1.2 核心价值

1. **补齐 AIOps 闭环**:监控看得到,修得了,还能主动低成本地完成应用的部署/扩容/升级/回滚。
2. **AI 擅长而不是传统 CI/CD 擅长的点**:自动适配环境差异、故障自动回滚、沉淀部署知识复用。传统 Jenkins/CICD 只能"按写死的流水线跑",无法理解手册语义、无法感知目标环境差异。
3. **复用现有能力**:不再从零造轮子,底层执行、资产连接、AI 规划全部复用已有模块。

### 1.3 差异化定位(避免做成"又一个 Jenkins")

| 维度 | 传统 CI/CD / Ansible | 本功能 |
|------|----------------------|--------|
| 输入 | 写死的 pipeline / playbook | 自然语言部署手册 + 结构化 SOP |
| 环境感知 | 人工在 playbook 里写死 IP/端口 | AI 用资产 + probe 探测结果自动映射 |
| 参数替换 | 模板变量手动/少量 | AI 识别 `${ENV_xxx}` 占位符自动代换 |
| 故障处理 | 流水线中止 | AI 自动校验 + 智能回滚 + 诊断 |
| 知识沉淀 | 无 | 执行成功沉淀 RAG,下次复用 |

**核心卖点 = 环境感知(Environment-Aware Adaptation) + 智能止损(Intelligent Rollback)**,而不是基础设施执行能力。

---

## 二、现状盘点(可复用资产)

| 环节 | 现有组件 | 说明 |
|------|---------|------|
| 资产/环境信息 | `assets.connection_config` | SSH/HTTP/K8s 等连接配置 |
| SSH 安全执行 | `ssh_helper.connect_ssh` | TOFU 指纹自举 + known_hosts 白名单统一入口 |
| 命令执行 | `workflow_service` + MCP 工具 `execute_run_command` | 模板/自定义节点执行 |
| 环境探测 | Pre-Run `context.probe` | df/du/free/uptime 等只读探测,失败不阻塞 |
| AI 规划 | `agent_chat` + `propose_action` | AI 提议动作 → 待确认 → 人工 confirm |
| 部署手册检索 | RAG(`kb_documents.asset_id` + `query_knowledge_rag`) | 已支持部署文档按资产归属存储与检索 |
| 部署 SOP | `sop_templates.py` 91 个模板 | `seed_workflow_templates` 播种 |
| 回滚参考 | `blue_green_deploys` / `change_tasks` | 变更/回滚模型参考 |

**结论**:本质是"复用 workflow_service + ssh_helper + agent 闭环,新增三个能力:代码包引用 / 部署文档解析 / 环境映射"。

---

## 三、功能架构设计

### 3.1 总体流程

```
上传/引用
┌─────────────── ①  输入物  ───────────────┐
│ · 代码包 artifact（不落本地,仅存服务器路径引用）│
│ · 部署手册 doc（markdown，环境信息为示例）   │
│ · 目标环境信息（可选,从 assets 拉取）       │
└───────────────┬───────────────────────────┘
                ▼
┌─────────────── ②  AI 解析 → 结构化部署计划 ─┐
│ · 手册 → SOP JSON（步骤/命令/校验/回滚）    │
│ · ${ENV_xxx} 占位符 → 环境映射             │
└───────────────┬───────────────────────────┘
                ▼
┌─────────────── ③  环境预检（probe）         ┐
│ · 磁盘/端口/依赖/连通性 预飞行检查          │
└───────────────┬───────────────────────────┘
                ▼
┌─────────────── ④  逐步执行（人工确认）      ┐
│ · 每步调用 MCP / ssh 落目标机              │
│ · 每步自动校验 + 快照                      │
└───────────────┬───────────────────────────┘
                ▼
┌─────────────── ⑤  校验 → 成功/回滚         ┐
│ · 成功:沉淀 RAG 知识                        │
│ · 失败:自动回滚 + 诊断报告                   │
└────────────────────────────────────────────┘
```

### 3.2 模块划分

| 模块 | 职责 | 新增/复用 |
|------|------|-----------|
| `deploy_plans` 管理 | 部署计划 CRUD + 状态机 | 新增 |
| 部署文档解析 | 手册 → 结构化 SOP JSON | 新增 |
| 环境健康预检 | 复用 workflow probe + assets 扩充 | 复用+增强 |
| AI 规划执行引擎 | 复用 workflow_service / agent 闭环 | 复用为主 |
| 代码包引用 | `artifact_path` 引用,不落本地 | 新增 |
| 回滚与校验 | 执行快照 + 失败回滚 | 新增 |
| 知识沉淀 | 复用工单/知识审批链路写 RAG | 复用 |

### 3.3 数据模型（初稿,待进 CONTRACT.md）

#### `deploy_plans` — 部署计划

| 字段 | 类型 | 说明 |
|------|------|------|
| id | Integer PK | 主键 |
| name | String(128) | 计划名 |
| description | Text | 描述 |
| artifact_path | String(512) | **代码包引用路径(资产服务器),平台不落本地** |
| doc_path | String(512) | 部署手册存储/引用路径 |
| asset_id | Integer FK(assets.id) | 目标环境资产 |
| status | String(32) | draft / planned / running / succeeded / failed / rolled_back |
| created_by | Integer FK(users.id) | 创建人 |
| created_at | DateTime | - |
| updated_at | DateTime | - |

#### `deploy_steps` — 部署步骤（SOP 解析 / 执行结果）

| 字段 | 类型 | 说明 |
|------|------|------|
| id | Integer PK | - |
| plan_id | Integer FK(deploy_plans.id) | - |
| step_order | Integer | 步骤序号 |
| description | String(512) | 步骤说明 |
| command | String(1024) | 待执行命令(已做环境代换) |
| verify_command | String(1024) | 校验命令 |
| rollback_command | String(1024) | 回滚命令 |
| status | String(32) | pending / running / succeeded / failed / skipped / rolled_back |
| output | Text | 执行输出 |
| started_at | DateTime | - |
| finished_at | DateTime | - |

> 字段命名遵守 CONTRACT.md 规范:时间 `_at`、外键 `_id`、JSON 带前缀、布尔 `is_`。上表为规划稿,**正式落库前先写进 CONTRACT.md 再同步前后端**。

---

## 四、AI 解析与规划核心逻辑

### 4.1 部署手册 → 结构化 SOP

> **核心难点**:部署手册格式千变万化,AI 解析易漏步、乱序。**必须约束 AI 输出结构化 SOP JSON,而不是自由文本。**

```
AI 输出 schema（严格约束）:
{
  "plan_name": "...",
  "preflight": [只读命令列表, 用于环境预检],
  "steps": [
    {
      "order": 1,
      "description": "步骤说明",
      "command": "shell 命令, 支持 ${ENV_xxx} 占位符",
      "verify": "可选, 执行后校验命令",
      "rollback": "可选, 失败回滚命令",
      "risk": "low|medium|high"
    }
  ]
}
```

### 4.2 环境参数映射（防幻觉关键）

- **手册为"示例环境"**,IP/端口/目录是例子。AI 必须用真实环境替换。
- 强约束:手册中环境敏感值标 `${ENV_xxx}` 占位符,声明式代入:
  - `target_ip` ← 资产 `assets.ip`
  - `app_dir` / `log_dir` ← probe 探测结果
  - `service_name` ← 用户输入 context
- 映射来源优先级:用户 context > 资产字段 > probe 探测 > 手册示例(兜底并在计划中打标「示例值,请确认」)。
- 计划生成后**展示环境映射对照表**,人工确认后才能执行,杜绝 AI 直接用示例 IP 部署。

### 4.3 执行引擎

- 复用 `workflow_service` 的节点执行与失败传播逻辑(含 confirm 待确认机制)。
- 每一步:执行 → `verify` 校验 → 通过才进下一步。
- 任何一步失败:执行该步及已跳过依赖的 `rollback`,计划置 `rolled_back`/`failed`。

---

## 五、安全与可靠性设计

### 5.1 变更管理(Top 风险:变更会直接影响业务,信任门槛远高于告警分析)

- **人工确认**：高风险步骤(重启服务/删数据/改配置)必须二次确认,复用 confirm 闭环。
- **预飞行检查(Preflight)**：执行前 probe 磁盘剩余、端口占用、依赖版本、连通性,不满足直接拒绝。
- **审计日志**：所有执行/回滚/确认全量落库,可追溯。
- **沙盒联动**：可对接现有 sandbox 策略引擎做工具/命令/资产黑名单。

### 5.2 代码包安全(不落本地)

- 平台**只存 `artifact_path` 引用**,不存储上传文件本体。
- 目标机通过 SSH 从资产服务器拉取,校验 checksum(计划中可含 `sha256`)。
- 拉取/解压/放置均在目标机完成,平台进程不接触二进制。

### 5.3 回滚与幂等

- 每步记录"执行前快照"(文件备份/服务原状态/端口占),失败可按 `rollback_command` 恢复。
- 部署命令尽量幂等(先探测再做),重复执行不破坏环境。

### 5.4 契约合规

- 所有新增字段先进 `CONTRACT.md`,前后端、DB 列名、MCP 工具字段与之一致。
- 敏感字段(如资产服务器账号密码)遵循掩码规则:`***` + `has_*`,编辑置空、空值不更新。
- 路径一律基于 `__file__`/`%~dp0` 动态计算,禁止硬编码。

---

## 六、落地路径（MVP → 增强）

### 阶段一：MVP（先验证"AI 能懂手册并安全执行"）

1. 新增 `deploy_plans` / `deploy_steps` 表 + 基础 CRUD API。
2. 上传/引用部署手册 + `artifact_path`。
3. AI 解析手册 → 结构化 SOP JSON(步骤/命令/校验/回滚)。
4. 环境映射对照表展示 + 人工确认。
5. 复用 workflow 执行引擎逐步执行,每步 `verify`,失败触发 `rollback`。
6. 选择一个**回滚友好、影响可控**的场景(如微服务滚动更新/静态文件发布)做 Demo/金丝雀(Golden Path)验证。

### 阶段二：增强

- 部署知识沉淀到 RAG,下次同类部署直接复用计划模板。
- 代码包从资产服务器拉取 + checksum 校验。
- 对接 sandbox 沙盒策略、审计、审批流。
- 支持 K8s 部署(SOP 生成 `kubectl apply`/Helm)、数据库变更(带备份)。

---

## 七、风险与取舍

| 风险 | 等级 | 缓解 |
|------|------|------|
| AI 解析手册幻觉(漏步/乱序/错误参数) | 高 | 强约束输出 SOP JSON + 环境映射对照人工确认 + 高优逐步执行 |
| 变更影响生产业务 | 高 | 优先低风险场景、二次确认、preflight、自动回滚 |
| 环境映射错误(用示例 IP 部署) | 中 | 占位符声明式映射 + 映射表展示 + 默认拒绝示例值 |
| 代码包拉取安全 | 中 | 不落本地 + checksum 校验 + SSH 白名单 |
| 契约违规导致静默数据丢失 | 中 | 先改 CONTRACT.md 再同步前后端 |
| 信任门槛/TTM | 中 | 金丝雀场景先行,成功案例沉淀,再扩展 |

---

## 八、交付里程碑建议

- **M1**:建表 + CRUD + 手册上传 + AI 解析 SOP(MVP 骨架)。
- **M2**:执行引擎接入 + 环境映射 + 逐步执行/校验/回滚(Golden Path 闭环)。
- **M3**:知识沉淀 + 代码包拉取校验 + 沙盒/审计/审批(生产化)。

> 立项评审通过后,第一步先更新 `CONTRACT.md`(新增 deploy_plans/deploy_steps 字段契约),再动前后端。