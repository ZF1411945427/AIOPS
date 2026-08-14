# 本系统 vs ongrid-main 能力评分对比

> 评估时间：2026-08-14
> 对比对象：`D:\AIOPS\project08`（本系统，Python/FastAPI/Vue） vs `D:\AIOPS\ongrid-main`（Go/DDD/React）
> 评分口径：沿用赶超计划的加权维度（共 10 分制）。每项附证据，避免高估低估。
> 本系统已含全部"赶超Ongrid改造"（F 系列 + G1 + P1-5 + P2-5 + P3-2 + D2/D3 + 拓扑服务调用），见《Ongrid改造新增功能页与操作总览.md》。

---

## 一、on-grid-main 模块概览（能力边界）

`ongrid-main` 为 Go 单体（`cmd/ongrid` 主程序 + `cmd/ongrid-edge` 边缘代理），DDD 分层（`internal/{iam,manager,edgeagent}`），主要 biz 模块：

| 层 | 模块 | 说明 |
|----|------|------|
| iam | org / membership / user | 组织、成员、用户（多租户 RBAC 基础） |
| manager/biz/aiops | agent、chatruntime、graph、investigator、tools(110)、decorators、alertdraft | Agent 内核 / 对话运行时 / 调查 / 110 工具 / 装饰器链 |
| alert | alert、investigator、alertconfig | 告警规则(kind 8 类)/调查 |
| edge | edge(18) + edgeagent/* | 边缘代理：collector/plugins/k8s(23)/cmdpolicy/host_files/webshell/restart_service/skill |
| flow | flow(15) | 工作流(3 触发/并行 fan-out/error port) |
| knowledge/marketplace/mcp/secret/skill/topology/report/setting | | 知识库(RAG)/技能市场/MCP/秘钥/拓扑/报表/设置 |
| device / metric / monitor / promwrite / imbridge(IM) / k8s / grafana / approval / audit | | 网络设备/指标/Prom写回/IM 桥接/审批/审计 |

> 注：ongrid 的 iam(org/tenant) + approval + audit 等是其强项；本系统用 role_menus + 资源级 RBAC + 审计日志覆盖。

---

## 二、逐维度评分（10 分制，附双方证据）

> 口径：基于真实代码/工程资产盘点（非印象分）。本系统列含 2026-08-14 "除安全鉴权外全面赶超" 会话已完成工作（详见第四章）。

| 权重 | 维度 | Ongrid | 本系统(当前) | 说明 |
|------|------|:---:|:---:|------|
| 15% | **Agent/AI 能力** | **8.5** | **9.0** | 本系统领先。ongrid: coordinator+persona+token 流式(仍 feature flag 门控)+6 装饰器+110 工具+toolreplay hoisting。本系统: SSE token 真流式落地 + hoisting(稳定id/去重/参数兜底)+装饰器(metric/tenant_bind)+ToolBag 延迟加载(AIOPS_TOOLBAG=1, payload -26%)。 |
| 10% | **工作流自动化** | **8.0** | **8.5** | 本系统领先。ongrid: 3 触发+fan-out+OR-join+execute-once+error port。本系统: 告警/cron 触发+并行 fan-out+OR-join+error port+画布 trigger 配置+运行态观察+仪表盘。 |
| 15% | **架构工程化** | **9.5** | **8.0** | ongrid 仍领先。ongrid: DDD 三有界上下文+**go-arch-lint 三 BC 强制**+依赖注入。本系统: H4 bootstrap 收敛+H1 契约+H2 models 21 域拆分(无循环 import)+**本次新增依赖边界检查 `tools/arch_check.py`(AST 方向约束+循环检测, CI job), 修复 services→routers 反向依赖**；仍为单体、无强制 BC、main.py ~1205 行。 |
| 10% | **安全鉴权** | **9.0** | **7.0** | ongrid 领先(用户明确"安全鉴权除外"不赶超)。ongrid: iam 组织级 RBAC+审计。本系统: 菜单 RBAC+资源级 RolePermission+审计, 多租户/Casbin 未深度接入。 |
| 10% | **生态(技能/MCP/secret/RAG)** | **8.0** | **8.5** | 本系统领先: F1/F2 技能市场+ F3 secret⚟+ 外部 MCP + git 知识库 + BGE/BM25 混合检索 + 双 rerank > ongrid 纯向量。 |
| 10% | **监控/告警/RCA** | **8.5** | **9.0** | 本系统领先: 8 类规则(metric_raw/anomaly/forecast/burn_rate/trace_latency/trace_error_rate/log_match/log_volume)+C1-C3 自动调查闭环+**本次新增检测算法单测(sigma/ewma/mad/DTW/RCA/告警评估)**。 |
| 10% | **功能广度** | **8.0** | **9.5** | 本系统独有部署引擎/AI 部署/K8s/混沌/巡检/SLO/值班/移动端/自愈/变更/拓扑多 Tab。 |
| 5% | **可部署性** | **9.0** | **8.5** | ongrid 仍领先。ongrid: docker-compose+helm+**发布/升级/卸载脚本+多架构发布流程实战**。本系统: Dockerfile+compose(monitoring/postgres profile)+install/upgrade/uninstall+Helm chart(lint 0 fail)+AIOPS_DB_URL Postgres 生产模式+**本次新增 Makefile(build-multi 多架构/建带 Postgres 版)**；缺 Helm 真集群实战与镜像多架构已发布。 |
| 5% | **代码质量** | **9.0** | **7.0** | ongrid 仍领先。ongrid: **318 测试文件**+e2e+vitest+golangci 12 linter+覆盖率门禁。本系统: **本次从 55 用例/7% 覆盖率/+0 虚设门禁 → 140 pytest(覆盖率 24.06%>真实门禁 20%)+13 vitest+8 项 e2e 冒烟+ruff(1 linter)**；测试数/覆盖率仍有差距。 |
| 5% | **可观测性** | **9.0** | **8.5** | ongrid 仍领先。ongrid: Prom+Loki+Tempo+**预置 Grafana provisioning**。本系统: D2 /metrics+D3 trace_id 全链路+结构化日志+**本次新增 Grafana provisioning(3 datasource)+预置 AIOps 面板+ Loki/Tempo docker-compose+OTLP gRPC 端口可配置(AIOPS_OTLP_GRPC_PORT)**；缺真实 tracing 后端深度接入(自研入库). |
| 5% | **产品覆盖(SRE/部署/移动端)** | 7.0 | **9.5** | 本系统独有部署引擎+移动端+SRE 套件。 |

> 单项维度（非加权）参考：Agent 内核 9.5 vs 7.0 ↓已升 9.0；代码质量 9.0 vs 6.5；RAG 7.0 vs 8.5；监控本系统已由纯阈值升至 8 类规则与 ongrid 对齐。

---

## 三、加权总分

| 维度 | 权重 | 本系统 | 本系统×权重 | Ongrid | Ongrid×权重 |
|------|:---:|:---:|:---:|:---:|:---:|
| Agent/AI 能力 | 15% | 9.0 | 1.350 | 8.5 | 1.275 |
| 工作流自动化 | 10% | 8.5 | 0.850 | 8.0 | 0.800 |
| 架构工程化 | 15% | 8.0 | 1.200 | 9.5 | 1.425 |
| 安全鉴权 | 10% | 7.0 | 0.700 | 9.0 | 0.900 |
| 生态 | 10% | 8.5 | 0.850 | 8.0 | 0.800 |
| 监控/告警/RCA | 10% | 9.0 | 0.900 | 8.5 | 0.850 |
| 功能广度 | 10% | 9.5 | 0.950 | 8.0 | 0.800 |
| 可部署性 | 5% | 8.5 | 0.425 | 9.0 | 0.450 |
| 代码质量 | 5% | 7.0 | 0.350 | 9.0 | 0.450 |
| 可观测性 | 5% | 8.5 | 0.425 | 9.0 | 0.450 |
| 产品覆盖 | 5% | 9.5 | 0.475 | 7.0 | 0.350 |
| **合计** | **100%** | **—** | **8.48** | **—** | **8.55** |

**加权总分：本系统 ≈ 8.48 ｜ ongrid-main ≈ 8.55**（含安全，差 0.07）

> **剔除安全鉴权后**（其余权重归一）：本系统 ≈ **8.64** vs ongrid ≈ **8.50**（差 **+0.14，小幅领先 ongrid**）。
> 说明：本文件此前一度记录为"8.75 vs 8.73 / 剔安全反超 0.42"属**过度乐观**（未核实 ongrid 318 单测、go-arch-lint 强制、Loki/Tempo/预置 Grafana 等真实资产）。2026-08-14 重评（代码证据版）校准为：含安全本 8.28 vs ongrid 8.50；本会话完成"除安全外全面赶超"第一轮后，代码质量 5.5→7.0、架构 7.5→8.0、可部署 8.0→8.5、可观测 8.0→8.5，收敛为上述 8.48 vs 8.55 / 剔安全 8.64 vs 8.50。

---

## 四、结论速览

| 维度 | 谁领先 | 差距 |
|------|:---:|------|
| Agent / 工作流 | **本系统领先** | 0.5 |
| 监控 / 生态 / 功能 / 产品 | **本系统领先** | 0.1~1.5 |
| 架构 / 可部署 / 代码质量 / 可观测 | **ongrid 领先** | 0.1~2.0 |
| 安全鉴权 | ongrid 领先(不赶超) | 2.0 |

**一句话**：本系统胜在**功能全栈+生态+产品纵深**（功能 9.5/产品 9.5），Agent/工作流/监控小幅领先；ongrid 在**工程纵深四项**（架构 9.5、代码质量 9.0(+)318 测试、可观测 9.0、可部署 9.0）仍领先。含安全口径 8.48 vs 8.55（差 0.07）；**剔除安全**（用户明确不赶超项）**8.64 vs 8.50，本系统小幅反超（+0.14）**。

## 五、2026-08-14 本轮赶超（除安全外）已完成工作

1. **代码质量（5.5→7.0）**：新增 5 个后端测试文件（核心算法 26 / secret_vault 17 / tenant 11 / SLO 7 / RCA 11），覆盖率真实门禁 `--cov-fail-under=0→20%`（实测 7%→24%）；新增 TestClient 集成测试 13 项（覆盖 main.py 路由层）；前端接入 vitest（request/websocket 13 项，854ms）；新增真实进程 e2e 冒烟（8 端点 8/8）；新增 `requirements-ci.txt` 纯净依赖验证。
2. **架构工程化（7.5→8.0）**：新增 `tools/arch_check.py`（AST 依赖方向约束 + 循环检测，对齐 go-arch-lint），修 `services/mcp_tools` 反向依赖 routers；CI 加 `backend-arch` job。
3. **可观测性（8.0→8.5）**：Grafana provisioning（Prometheus/Loki/Tempo 三 datasource + 预置 AIOps 概览面板）；docker-compose 加 loki/tempo/profile 与 data 卷；OTLP gRPC 端口可配置 `AIOPS_OTLP_GRPC_PORT`（默认 14317，避免与 Tempo 4317 冲突）。
4. **可部署性（8.0→8.5）**：新增 `Makefile`（build-multi 多架构 `docker buildx --platform linux/amd64,arm64`、test/lint/arch-check/compose 编排）。

> 仍领先 ongrid 的工程侧工作（下一轮可选）：① 代码质量再上探（e2e 入 CI、更多服务单测、覆盖率 24%→40%+）；② 架构拆主路径（main.py ~1205 行 / deploy_service 199KB 收敛）；③ 接入 Tempo 作为真实 tracing 后端 + Loki 日志采集；④ Helm 真集群部署验证。
