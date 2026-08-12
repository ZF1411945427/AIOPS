# AIOps 全库字段规范契约（Single Source of Truth）

> **所有数据库表、前后端代码的字段命名必须以本文件为准。**
> 新增/修改任何字段，必须先改本文件，再同步前后端代码。
> 最后更新: 2026-07-19

---

## 第一章：全局命名规则（适用于所有表）

### 1.1 时间字段

所有 `DateTime` 类型字段必须统一后缀：

| 正确 | 错误 |
|------|------|
| `xxx_at` | `xxx_time`, `xxx_date`, `last_xxx`, `until`, `first_seen`, `last_seen` |

**例外：** `timestamp` 保留（标准约定）。

### 1.2 布尔字段

所有 `Boolean` 类型字段必须加前缀：

| 语义 | 正确 | 错误 |
|------|------|------|
| 判断性质 | `is_xxx` | `xxx` （如 `success` → `is_success`） |
| 拥有性质 | `has_xxx` | `xxx` （如 `hallucination_flag` → `has_hallucination`） |
| 开关性质 | `enabled` | `active`, `visible` |

### 1.3 描述/备注字段

统一用 `description`，禁止别名：

| 正确 | 错误 |
|------|------|
| `description` | `notes`, `note`, `comment`, `remarks`, `remark`, `memo`, `detail` |

### 1.4 JSON/配置字段

必须带业务前缀，禁止泛型名：

| 正确 | 错误 |
|------|------|
| `channel_config` | `config` |
| `remediation_params` | `params` |
| `report_data` | `data` |

### 1.5 外键字段

格式：`{referenced_table}_id`

| 正确 | 错误 |
|------|------|
| `user_id` | `changed_by`, `executed_by` |

### 1.6 状态字段

统一用 `status`，禁止别名。

### 1.7 字段长度

同名字段跨表必须统一长度：

| 字段名 | 统一长度 |
|--------|---------|
| `name` | String(128) |
| `title` | String(256) |
| `status` | String(32) |
| `severity` | String(32) |
| `metric_name` | String(64) |
| `category` | String(32) |
| `ci_type` | String(32) |
| `risk_level` | String(16) |
| `source` | String(32) |
| `description` | Text（长文本）或 String(512)（短文本） |
| `reason` | String(256) |
| `tags` | String(256) |

---

## 第二章：各表字段规范

### `chaos_experiments` — 混沌实验

| 字段名 | 当前 | 修正 | 说明 |
|--------|------|------|------|
| name | String(128) | — | ✅ |
| description | Text | — | ✅ |
| target_type | String(32) | — | |
| target_layer | String(32) | — | |
| target_selector | Text | — | |
| fault_type | String(64) | — | |
| fault_params | Text | — | |
| steady_state | Text | — | |
| status | String(32) | — | ✅ |
| result | String(32) | — | |
| started_at | DateTime | — | ✅ |
| finished_at | DateTime | — | ✅ |
| created_at | DateTime | — | ✅ |

### `chaos_runs` — 混沌运行记录

| 字段名 | 当前 | 修正 | 说明 |
|--------|------|------|------|
| experiment_id | FK | — | ✅ |
| `steady_state_passed` | Boolean | ✅ | |
| `auto_recovered` | Boolean | `is_auto_recovered` | ❌ 缺 is_ |
| alerts_triggered | Integer | — | |
| error_budget_impact | Float | — | |
| duration_seconds | Integer | — | |
| steady_state_before | Text | — | |
| steady_state_after | Text | — | |
| **`notes`** | Text | **`description`** | ❌ 描述字段 |
| started_at | DateTime | — | ✅ |
| created_at | DateTime | — | ✅ |

### `assets` — 资产主表

| 字段名 | 当前 | 修正 | 说明 |
|--------|------|------|------|
| name | String(128) | — | ✅ |
| **`type`** | String(64) | **删除** | ❌ 废弃，ci_type 已覆盖 |
| ci_type | String(32) | — | ✅ 契约已有 |
| parent_id | FK | — | ✅ |
| ip | String(64) | — | |
| **`os`** | String(16) | **`linux`/`windows`/`other`** | ✅ 新增：server/virtual_machine/cloud_host 操作系统枚举 |
| status | String(32) | — | ✅ |
| tags | String(256) | — | |
| ci_attributes | Text | — | ✅ 契约已有 |
| k8s_cluster | String(128) | — | |
| connection_type | String(32) | — | ✅ 契约已有 |
| connection_config | Text | — | ✅ 契约已有 |
| created_at | DateTime | — | ✅ |
| **`last_checked`** | DateTime | **`last_checked_at`** | ❌ 缺 _at |
| latency_ms | Integer | — | |
| health_status | String(16) | — | |

### `alert_silences` — 告警静默

| 字段名 | 当前 | 修正 | 说明 |
|--------|------|------|------|
| rule_id | FK | — | ✅ |
| **`until`** | DateTime | **`expires_at`** | ❌ 非 _at |
| reason | String(256) | — | |
| created_at | DateTime | — | ✅ |

### `alerts` — 告警

✅ 所有字段符合规范。

| 字段名 | 当前 | 说明 |
|--------|------|------|
| rule_id | FK | ✅ |
| asset_id | FK | ✅ |
| metric_name | String(64) | ✅ |
| actual_value | Float | ✅ |
| threshold | Float | ✅ |
| severity | String(32) | ✅ |
| status | String(32) | ✅ |
| message | Text | ✅ |
| created_at | DateTime | ✅ |
| resolved_at | DateTime | ✅ |

### `notification_channels` — 通知渠道

| 字段名 | 当前 | 修正 | 说明 |
|--------|------|------|------|
| name | String(64) | — | |
| type | String(32) | — | |
| **`config`** | Text | **`channel_config`** | ❌ JSON 泛名 |
| enabled | Boolean | — | ✅ |
| created_at | DateTime | — | ✅ |

### `notification_logs` — 通知日志

| 字段名 | 当前 | 修正 | 说明 |
|--------|------|------|------|
| alert_id | FK | — | ✅ |
| channel_id | FK | — | ✅ |
| channel_type | String(32) | — | |
| recipient | String(256) | — | |
| title | String(256) | — | |
| **`content`** | Text | **`notification_content`** | ❌ JSON 泛名 |
| **`success`** | Boolean | **`is_success`** | ❌ 缺 is_ |
| error_message | Text | — | |
| created_at | DateTime | — | ✅ |

### `remediation_logs` — 自愈日志

| 字段名 | 当前 | 修正 | 说明 |
|--------|------|------|------|
| remediation_id | FK | — | ✅ |
| alert_id | FK | — | ✅ |
| action_type | String(32) | — | |
| target | String(128) | — | |
| **`success`** | Boolean | **`is_success`** | ❌ 缺 is_ |
| output | Text | — | |
| created_at | DateTime | — | ✅ |

### `remediation_effects` — 自愈效果

| 字段名 | 当前 | 修正 | 说明 |
|--------|------|------|------|
| remediation_id | FK | — | ✅ |
| alert_id | FK | — | ✅ |
| executed_at | DateTime | — | ✅ |
| check_at | DateTime | — | ✅ |
| alert_status_at_execute | String(32) | — | |
| alert_status_at_check | String(32) | — | |
| **`asset_recovered`** | Boolean | **`is_asset_recovered`** | ❌ 缺 is_ |
| **`alert_resolved`** | Boolean | **`is_alert_resolved`** | ❌ 缺 is_ |
| recovery_time_seconds | Integer | — | |
| **`notes`** | Text | **`description`** | ❌ 描述字段 |
| created_at | DateTime | — | ✅ |

### `auto_remediations` — 自动响应规则

| 字段名 | 当前 | 修正 | 说明 |
|--------|------|------|------|
| name | String(128) | — | ✅ |
| rule_id | FK | — | ✅ |
| action_type | String(32) | — | |
| **`params`** | Text | **`remediation_params`** | ❌ JSON 泛名 |
| enabled | Boolean | — | ✅ |
| created_at | DateTime | — | ✅ |

### `reports` — 报告

| 字段名 | 当前 | 修正 | 说明 |
|--------|------|------|------|
| title | String(256) | — | ✅ |
| type | String(32) | — | |
| **`period_start`** | DateTime | **`period_started_at`** | ❌ 缺 _at |
| **`period_end`** | DateTime | **`period_ended_at`** | ❌ 缺 _at |
| summary | Text | — | |
| **`data`** | Text | **`report_data`** | ❌ JSON 泛名 |
| created_at | DateTime | — | ✅ |

### `dashboard_card_configs` — 仪表盘卡片

| 字段名 | 当前 | 修正 | 说明 |
|--------|------|------|------|
| user_id | FK | — | ✅ |
| card_type | String(64) | — | |
| title | String(128) | — | |
| **`config`** | Text | **`card_config`** | ❌ JSON 泛名 |
| position | Integer | — | |
| **`visible`** | Boolean | **`is_visible`** | ❌ 缺 is_ |

### `prediction_models` — 预测模型

| 字段名 | 当前 | 修正 | 说明 |
|--------|------|------|------|
| name | String(128) | — | ✅ |
| metric_name | String(64) | — | ✅ |
| asset_id | Integer | — | |
| model_type | String(32) | — | |
| **`params`** | Text | **`model_params`** | ❌ JSON 泛名 |
| enabled | Boolean | — | ✅ |
| created_at | DateTime | — | ✅ |

### `data_sources` — 数据源

| 字段名 | 当前 | 修正 | 说明 |
|--------|------|------|------|
| name | String(128) | — | ✅ |
| type | String(32) | — | |
| endpoint | String(512) | — | |
| auth_type | String(32) | — | |
| auth_config | Text | — | ✅ 有前缀 |
| scrape_interval | Integer | — | |
| mapping_config | Text | — | |
| enabled | Boolean | — | ✅ |
| last_status | String(32) | — | |
| last_error | Text | — | |
| **`last_scrape`** | DateTime | **`last_scraped_at`** | ❌ 缺 _at |
| created_at | DateTime | — | ✅ |

> **type 枚举**(由后端 `DS_TYPES` 驱动,前端下拉自动同步):`prometheus` / `custom_api` / `log_file` / `ssh` / `kubernetes` / `docker` / `elasticsearch` / `loki` / `jaeger` / `otel`
>
> **loki**: endpoint 填 Loki HTTP 地址(如 `http://10.0.9.12:3100`),auth_config 支持 `username`/`password`(Basic)与 `org_id`(X-Scope-OrgID 多租户)。日志查询走 `log_query_service.LokiAdapter`(LogQL `/loki/api/v1/query_range`),`logs.py` 的 `/logs/api/sources` 与 `/logs/api/search` 已按 type 分发;日志中心与 MCP `query_log_sources` 均自动包含 loki。
>
> **kubernetes** auth_config 字段(证书巡检走 SSH,务必保留以下 ssh_ 前缀字段):
>
> | 字段名 | 类型 | 说明 |
> |--------|------|------|
> | `k8s_auth` | String | 认证方式(token / kubeconfig 等),复用现有字段 |
> | `k8s_api_server` | String | K8s API Server 地址(如 `https://192.168.100.129:6443`) |
> | `k8s_token` | String | 敏感;后端返回 `***` + `has_k8s_token`,前端编辑置空、空值=不更新 |
> | `kubeconfig` | String | 敏感;后端返回 `***` + `has_kubeconfig` |
> | `verify_ssl` | Boolean | 是否校验 SSL |
> | `k8s_distro` | String | **K8s 发行版类型**(2026-08-12 新增):自动检测/手动指定,枚举值: `auto`(自动检测) / `kubeadm` / `k3s` / `rke` / `openshift` / `binary`(自定义路径) / `cloud`(云托管,走 API) |
> | `cert_paths` | Text | **自定义证书路径列表**(2026-08-12 新增):JSON 数组,如 `["/etc/kubernetes/pki/*.crt"]`;binary 模式必填,其他模式可选追加 |
> | `renew_command` | String | **自定义续期命令**(2026-08-12 新增):binary 模式可选,空则提示手动续期 |
> | `ssh_host` | String | master 节点 SSH 地址(证书巡检扫描 `/etc/kubernetes/pki` 用) |
> | `ssh_user` | String | SSH 用户名(默认 root) |
> | `ssh_password` | String | 敏感;后端返回 `***` + `has_ssh_password`,前端编辑置空、空值=不更新 |
> | `ssh_port` | Integer | SSH 端口(默认 22) |
>
> 消费方:`app/services/k8s_cert_service.py`(多发行版适配器,2026-08-12 重构)、`app/routers/k8s_cert.py`(`/k8s/cert/api/clusters` / `/k8s/cert/api/inspect` / `/k8s/cert/api/renew`)、`connection_service._test_kubernetes`、`datasource_service._scrape_kubernetes`。新增/修改字段必须先改本契约,再同步前后端与数据库。

### `change_requests` — 变更请求

| 字段名 | 当前 | 修正 | 说明 |
|--------|------|------|------|
| title | String(256) | — | ✅ |
| description | Text | — | ✅ |
| ci_type | String(64) | — | |
| asset_id | Integer | — | |
| change_type | String(32) | — | |
| priority | String(32) | — | |
| status | String(32) | — | ✅ |
| risk_level | String(32) | — | |
| **`planned_start`** | DateTime | **`planned_started_at`** | ❌ 缺 _at |
| **`planned_end`** | DateTime | **`planned_ended_at`** | ❌ 缺 _at |
| requester_id | FK | — | ✅ |
| reviewer_id | FK | — | ✅ |
| review_comment | Text | — | |
| created_at | DateTime | — | ✅ |
| updated_at | DateTime | — | ✅ |

### `spans` — 链路追踪

| 字段名 | 当前 | 修正 | 说明 |
|--------|------|------|------|
| trace_id | String(64) | — | |
| span_id | String(64) | — | |
| parent_span_id | String(64) | — | |
| service_name | String(128) | — | |
| operation_name | String(256) | — | |
| **`start_time`** | DateTime | **`started_at`** | ❌ _time 后缀 |
| **`end_time`** | DateTime | **`ended_at`** | ❌ _time 后缀 |
| duration_ms | Float | — | |
| status | String(32) | — | ✅ |
| tags | Text | — | |
| created_at | DateTime | — | ✅ |

### OTLP/HTTP 链路接入契约（SDK ↔ 平台）

> 涉及 OTel Agent / SDK 接入、`trace_ingest` 路由、接入指引页（`TraceAgentGuide.vue`）开发时**必须**遵守，否则 Agent 接入会失败或数据丢失。

| 项 | 契约值 | 说明 |
|----|--------|------|
| 标准采集端点 | `POST /v1/traces` | OTel SDK exporter 请求 URL = `OTEL_EXPORTER_OTLP_ENDPOINT` + `/v1/traces`。SDK/Agent 配 **base 地址**（如 `http://<AIOps-IP>:8000`），不要带 `/v1/traces` 后缀 |
| 协议 | `http/protobuf` | **禁用 `http/json`**：OTel Java Agent ≥ 2.x 已移除 json 协议；仅 protobuf/grpc 被现代 SDK 支持 |
| Content-Type 分发 | `application/json` → OTLP JSON；其余 → OTLP protobuf | 端点按请求头分发，兼容手动 JSON 推送与 SDK protobuf 上报 |
| 关闭信号 | `OTEL_METRICS_EXPORTER=none`、`OTEL_LOGS_EXPORTER=none` | 平台只收 traces；不关会造成 metrics/logs 协议解析失败 |
| 手动 SDK endpoint | 必须带完整路径 `http://<AIOps-IP>:8000/v1/traces` | `OTLPSpanExporter(endpoint=...)` 等手动构造不追加 `/v1/traces`，需自行补齐 |
| 旧端点（保留） | `POST /api/v1/traces/otlp` | 兼容旧 Collector/JSON 推送；接入指引已不再推荐 |
| License 白名单 | `license_service.py:_LICENSE_PUBLIC_PREFIXES` 含 `/v1/traces` | 非 `/api/` 前缀路径必须加白名单，否则被 License 中间件拦截 |
| 应用服务名 | `OTEL_SERVICE_NAME`（Java: `-Dotel.service.name`） | 入库为 `spans.service_name`，前端拓扑/服务列表依赖它 |
| DB/Cache 子 Span | 由上游服务 Agent 自动拦截生成 | MySQL/Redis/Kafka 等中间件无需单独装 Agent |

### `netflow_records` — 网络流量

| 字段名 | 当前 | 修正 | 说明 |
|--------|------|------|------|
| src_ip | String(64) | — | |
| dst_ip | String(64) | — | |
| src_port | Integer | — | |
| dst_port | Integer | — | |
| protocol | String(16) | — | |
| bytes_sent | Integer | — | |
| bytes_rcvd | Integer | — | |
| **`start_time`** | DateTime | **`started_at`** | ❌ _time 后缀 |
| **`end_time`** | DateTime | **`ended_at`** | ❌ _time 后缀 |
| created_at | DateTime | — | ✅ |

### `asset_lifecycles` — 资产生命周期

| 字段名 | 当前 | 修正 | 说明 |
|--------|------|------|------|
| asset_id | FK | — | ✅ |
| status | String(32) | — | ✅ |
| previous_status | String(32) | — | |
| **`changed_by`** | FK | **`user_id`** | ❌ 外键不匹配 users.id |
| **`comment`** | Text | **`description`** | ❌ 描述字段 |
| created_at | DateTime | — | ✅ |

### `change_tasks` — 变更任务

| 字段名 | 当前 | 修正 | 说明 |
|--------|------|------|------|
| change_id | FK | — | ✅ |
| step_order | Integer | — | |
| description | String(512) | — | ✅ |
| command | String(1024) | — | |
| status | String(32) | — | ✅ |
| result | Text | — | |
| **`executed_by`** | FK | **`user_id`** | ❌ 外键不匹配 users.id |
| executed_at | DateTime | — | ✅ |
| created_at | DateTime | — | ✅ |

### `error_budgets` — 错误预算

| 字段名 | 当前 | 修正 | 说明 |
|--------|------|------|------|
| slo_id | FK | — | ✅ |
| service_name | String(100) | — | |
| **`period_start`** | DateTime | **`period_started_at`** | ❌ 缺 _at |
| **`period_end`** | DateTime | **`period_ended_at`** | ❌ 缺 _at |
| budget_total | Float | — | |
| budget_consumed | Float | — | |
| budget_remaining | Float | — | |
| burn_rate | Float | — | |
| status | String(20) | — | |
| created_at | DateTime | — | ✅ |

### `sla_records` — SLA 记录

| 字段名 | 当前 | 修正 | 说明 |
|--------|------|------|------|
| service_name | String(100) | — | |
| sla_target | Float | — | |
| **`period_start`** | DateTime | **`period_started_at`** | ❌ 缺 _at |
| **`period_end`** | DateTime | **`period_ended_at`** | ❌ 缺 _at |
| uptime_seconds | Integer | — | |
| downtime_seconds | Integer | — | |
| achieved_sla | Float | — | |
| penalty | String(50) | — | |
| status | String(20) | — | |
| created_at | DateTime | — | ✅ |

### `availability_reports` — 可用性报告

| 字段名 | 当前 | 修正 | 说明 |
|--------|------|------|------|
| service_name | String(100) | — | |
| **`report_date`** | DateTime | **`reported_at`** | ❌ _date 后缀 |
| total_uptime | Integer | — | |
| total_downtime | Integer | — | |
| availability_pct | Float | — | |
| incident_count | Integer | — | |
| total_duration | Integer | — | |
| created_at | DateTime | — | ✅ |

### `ci_attributes` — CI 属性

| 字段名 | 当前 | 修正 | 说明 |
|--------|------|------|------|
| ci_model_id | FK | — | ✅ |
| name | String(64) | — | |
| display_name | String(128) | — | |
| field_type | String(32) | — | |
| **`required`** | Boolean | **`is_required`** | ❌ 缺 is_ |
| default_value | String(256) | — | |
| **`options`** | Text | **`attr_options`** | ❌ JSON 泛名 |
| order | Integer | — | |
| created_at | DateTime | — | ✅ |

### `cluster_anomaly_events` — 集群异常事件

| 字段名 | 当前 | 修正 | 说明 |
|--------|------|------|------|
| anomaly_type | String(64) | — | |
| cluster | String(128) | — | |
| message | Text | — | |
| severity | String(32) | — | ✅ |
| count | Integer | — | |
| **`first_seen`** | DateTime | **`first_seen_at`** | ❌ 缺 _at |
| **`last_seen`** | DateTime | **`last_seen_at`** | ❌ 缺 _at |
| **`resolved`** | Boolean | **`is_resolved`** | ❌ 缺 is_ |
| created_at | DateTime | — | ✅ |

### `api_tokens` — API Token

| 字段名 | 当前 | 修正 | 说明 |
|--------|------|------|------|
| name | String(128) | — | |
| token | String(64) | — | |
| permissions | String(256) | — | |
| **`last_used`** | DateTime | **`last_used_at`** | ❌ 缺 _at |
| enabled | Boolean | — | ✅ |
| created_at | DateTime | — | ✅ |

### `k8s_events` — K8s 事件

| 字段名 | 当前 | 修正 | 说明 |
|--------|------|------|------|
| cluster | String(128) | — | |
| namespace | String(128) | — | |
| name | String(256) | — | |
| kind | String(64) | — | |
| reason | String(128) | — | |
| message | Text | — | |
| source | String(128) | — | |
| **`first_seen`** | DateTime | **`first_seen_at`** | ❌ 缺 _at |
| **`last_seen`** | DateTime | **`last_seen_at`** | ❌ 缺 _at |
| count | Integer | — | |
| severity | String(32) | — | ✅ |
| created_at | DateTime | — | ✅ |

### `discovery_schedules` — 发现调度

✅ 全部可用。

### `discovery_jobs` — 发现任务

| 字段名 | 当前 | 修正 | 说明 |
|--------|------|------|------|
| name | String(128) | — | |
| job_type | String(32) | — | |
| target | String(256) | — | |
| **`config`** | Text | **`job_config`** | ❌ JSON 泛名 |
| status | String(32) | — | ✅ |
| result_summary | Text | — | |
| created_at | DateTime | — | ✅ |
| finished_at | DateTime | — | ✅ |

### `report_schedules` — 报告调度

| 字段名 | 当前 | 修正 | 说明 |
|--------|------|------|------|
| name | String(128) | — | |
| report_type | String(32) | — | |
| cron_expr | String(128) | — | |
| channel | String(32) | — | |
| channel_config | Text | — | ✅ 有前缀 |
| enabled | Boolean | — | ✅ |
| **`last_run`** | DateTime | **`last_run_at`** | ❌ 缺 _at |
| created_at | DateTime | — | ✅ |

### `ext_cmdb_configs` — 外部 CMDB

| 字段名 | 当前 | 修正 | 说明 |
|--------|------|------|------|
| name | String(128) | — | |
| cmdb_type | String(32) | — | |
| api_url | String(512) | — | |
| auth_config | Text | — | ✅ 有前缀 |
| sync_interval | Integer | — | |
| **`last_sync`** | DateTime | **`last_synced_at`** | ❌ 缺 _at |
| enabled | Boolean | — | ✅ |
| created_at | DateTime | — | ✅ |

### `ext_event_sources` — 外部事件源

| 字段名 | 当前 | 修正 | 说明 |
|--------|------|------|------|
| name | String(128) | — | |
| source_type | String(32) | — | |
| api_url | String(512) | — | |
| auth_config | Text | — | ✅ 有前缀 |
| sync_interval | Integer | — | |
| **`last_sync`** | DateTime | **`last_synced_at`** | ❌ 缺 _at |
| enabled | Boolean | — | ✅ |
| created_at | DateTime | — | ✅ |

### `system_configs` — 系统配置

| 字段名 | 当前 | 修正 | 说明 |
|--------|------|------|------|
| key | String(128) | — | |
| **`value`** | Text | **`config_value`** | ❌ JSON 泛名 |
| description | String(256) | — | ✅ |
| updated_at | DateTime | — | ✅ |

### `incident_approvals` — 审批记录

| 字段名 | 当前 | 修正 | 说明 |
|--------|------|------|------|
| incident_id | FK | — | ✅ |
| approver_id | FK | — | ✅ |
| action | String(32) | — | |
| **`comment`** | Text | **`description`** | ❌ 描述字段 |
| created_at | DateTime | — | ✅ |

### `blue_green_switch_records` — 蓝绿切换记录

| 字段名 | 当前 | 修正 | 说明 |
|--------|------|------|------|
| deploy_id | FK | — | ✅ |
| from_label | String(64) | — | |
| to_label | String(64) | — | |
| operator | String(64) | — | |
| **`note`** | String(256) | **`description`** | ❌ 描述字段 |
| created_at | DateTime | — | ✅ |

### `remediation_effect_records` — 效果追踪记录

| 字段名 | 当前 | 修正 | 说明 |
|--------|------|------|------|
| (已有字段) | | | |
| **`notes`** | Text | **`description`** | ❌ 描述字段 |

### `agent_evaluations` — Agent 评估

| 字段名 | 当前 | 修正 | 说明 |
|--------|------|------|------|
| **`success`** | Boolean | **`is_success`** | ❌ 缺 is_ |
| **`hallucination_flag`** | Boolean | **`has_hallucination`** | ❌ 缺 has_ |

### `ab_test_records` — A/B 测试记录

| 字段名 | 当前 | 修正 | 说明 |
|--------|------|------|------|
| **`success`** | Boolean | **`is_success`** | ❌ 缺 is_ |

### `oncall_schedules` — 值班表

| 字段名 | 当前 | 修正 | 说明 |
|--------|------|------|------|
| **`current_period_start`** | DateTime | **`current_period_started_at`** | ❌ 缺 _at |
| **`current_period_end`** | DateTime | **`current_period_ended_at`** | ❌ 缺 _at |
| **`auto_rotate`** | Boolean | **`is_auto_rotate`** | ❌ 缺 is_ |

---

## 第三章：跨表同语义字段长度统一

| 字段名 | 统一长度 | 涉及表 |
|--------|---------|--------|
| name | String(128) | chaos_experiments, chaos_scenarios, assets, tags, alert_rules, notification_channels, auto_remediations, data_sources, api_tokens, anomaly_configs, notification_templates, remediation_workflows, log_anomaly_rules, prediction_models, alert_webhooks, metric_records(改为128), ci_models, ci_attributes, report_schedules, saved_filters, discovery_jobs, ext_cmdb_configs, trace_anomaly_configs, kafka_pipelines, ext_event_sources, netflow_collectors, service_mesh_configs, blue_green_deploys, escalation_policies(改为128), ab_test_configs, discovery_schedules, mcp_servers, agent_configs |
| title | String(256) | notification_logs, incidents, knowledge_base, reports, runbooks, dashboard_card_configs(改为256), change_requests, knowledge_drafts |
| status | String(32) | chaos_experiments, assets, alerts, incidents, change_requests, change_tasks, asset_lifecycles, spans, discovery_jobs, blue_green_deploys, asset_metric_recommendations(改为32), asset_baseline_checks(改为32), knowledge_drafts(改为32), ab_test_configs(改为32), discovery_results(改为32) |
| severity | String(32) | alert_rules, alerts, incidents, knowledge_base, k8s_events, runbooks, notification_templates, log_anomaly_rules, cluster_anomaly_events, security_baseline_templates(改为32), knowledge_drafts |
| metric_name | String(64) | alert_rules, alerts, alert_suppressions, anomaly_configs, alert_silence_schedules, hotspot_analyses, prediction_models, metric_templates(改为64), asset_metric_recommendations(改为64), anomaly_benchmarks |
| category | String(32) | chaos_scenarios, runbooks(改为32), metric_templates, asset_metric_recommendations, security_baseline_templates, workflow_templates |
| source | String(32) | log_anomaly_rules, feature_store_items(改为32), asset_metric_recommendations, k8s_events(改为32) |
| service_name | String(128) | slo_configs(改为128), sla_records(改为128), availability_reports(改为128), spans, trace_anomaly_configs |
| reason | String(256) | alert_silences, alert_suppressions(改为256), alert_escalations, k8s_events(改为256), alert_silence_schedules |
| tags | String(256) | assets, knowledge_base, runbooks, kb_documents, kb_chunks |
| cron_expr | String(128) | alert_silence_schedules(改为128), report_schedules |

---

## 第四章：废弃字段清单

| 表 | 废弃字段 | 替代 | 原因 |
|----|---------|------|------|
| assets | `type` | `ci_type` | 两者语义重复，ci_type 更精确 |
| — | `cluster` (ci_type 枚举值) | `kubernetes_cluster` | 契约已标注废弃 |

---

## 第五章：敏感字段掩码规则（沿用）

| 字段 | 掩码标记 |
|------|---------|
| ssh_password | has_ssh_password |
| ssh_private_key | has_ssh_private_key |
| k8s_token | has_k8s_token |
| kubeconfig | has_kubeconfig |
| db_password | has_db_password |
| http_credential | has_http_credential |

**前端编辑规则：** 加载后密码字段置空，保存时空值不更新，用 `has_*` 标记显示「已设置」。

---

## 第六章：字段命名总则

1. **snake_case** — 全小写下划线，前后端一致
2. **不缩写** — `password` 不写 `passwd`，`credential` 不写 `cred`，`description` 不写 `desc`
3. **前缀即类型** — `is_` 布尔、`has_` 拥有、`ssh_` SSH 字段、`k8s_` K8s 字段
4. **后缀即语义** — `_at` 时间、`_id` 外键、`_type` 类型、`_config` JSON 配置
5. **一义一名** — 同一种含义全库用一个字段名（禁止 `name/title/label` 混用）
6. **本文件唯一权威** — 代码中不得自行发明字段名，新增字段必须先改本契约

---

## 第七章：评估 / A/B 测试 / 知识草稿三模块完整字段定义

> 2026-07-19 新增。这三个模块为本次强力测试与修复的核心，统一在此定义以避免前后端字段漂移。

### `agent_ground_truths` — Agent 评估 GroundTruth 测试集

| 字段名 | 类型 | 默认 | 说明 |
|--------|------|------|------|
| id | Integer PK | - | 主键 |
| name | String(128) | NOT NULL | 用例名 |
| category | String(32) | "qa" | qa / tool_call / rag / reasoning |
| question | Text | NOT NULL | 测试问题 |
| expected_answer | Text | "" | 预期答案 |
| expected_tools | Text | "[]" | JSON array of expected tool names |
| tags | String(256) | "" | 标签 |
| difficulty | String(16) | "medium" | easy / medium / hard |
| is_active | Boolean | True | 启用标志（软删除用） |
| created_at | DateTime | now() | - |
| updated_at | DateTime | now()/onupdate | - |

**API 约定**：
- 列表 `GET /agent/api/ground-truth/tests` 默认只返回 `is_active=True`，`?include_inactive=true` 显示全部
- 删除 `DELETE /agent/api/ground-truth/tests/{id}` 默认软删（is_active=False），`?hard=true` 物理删除

### `agent_ground_truth_runs` — GroundTruth 测试执行记录

| 字段名 | 类型 | 默认 | 说明 |
|--------|------|------|------|
| id | Integer PK | - | - |
| test_id | Integer FK(agent_ground_truths.id) | NOT NULL | - |
| session_id | Integer | nullable | 保留字段，当前不写入 |
| provider_id | Integer | nullable | 实际使用的 AI Provider |
| model_name | String(64) | "" | provider.default_model |
| actual_answer | Text | "" | LLM 最终回答 |
| actual_tools | Text | "[]" | JSON array，元素为 `{"name":"x","is_success":true,"latency_ms":120}` |
| answer_score | Float | 0.0 | 答案相似度 0~1（字符 2-gram Jaccard + SequenceMatcher 综合） |
| tool_score | Float | 0.0 | 工具匹配度 0~1（成功执行的工具才算命中） |
| total_score | Float | 0.0 | 综合分 = answer_score * 0.6 + tool_score * 0.4 |
| latency_ms | Integer | 0 | - |
| error | String(512) | "" | LLM 调用错误（无错误则空） |
| created_at | DateTime | now() | - |

### `ab_test_configs` — A/B 测试配置

| 字段名 | 类型 | 默认 | 说明 |
|--------|------|------|------|
| id | Integer PK | - | - |
| name | String(128) | NOT NULL | 实验名 |
| provider_a_id | Integer FK(ai_providers.id) | nullable | A 组 provider |
| provider_b_id | Integer FK(ai_providers.id) | nullable | B 组 provider |
| model_a | String(64) | "" | A 组模型名（创建/启动时由 provider.default_model 自动填充） |
| model_b | String(64) | "" | B 组模型名（创建/启动时由 provider.default_model 自动填充） |
| split_ratio | String(8) | "50/50" | 分流比，格式 "N/M" |
| metric | String(32) | "latency" | latency / accuracy / success |
| status | String(16) | "active" | active / stopped（同一时刻全局仅 1 个 active） |
| created_at | DateTime | now() | - |
| updated_at | DateTime | now()/onupdate | - |

**API 约定**：
- 创建时校验 A≠B、provider 存在
- 启动（status=active）时自动停止其他 active 实验
- 删除 `DELETE /agent/api/ab-test/configs/{id}` 级联删除 ab_test_records

### `ab_test_records` — A/B 测试结果记录

| 字段名 | 类型 | 默认 | 说明 |
|--------|------|------|------|
| id | Integer PK | - | - |
| test_id | Integer FK(ab_test_configs.id) | nullable | - |
| session_id | Integer | nullable | - |
| group | String(8) | "a" | a / b（由 md5(test_id:session_id) % 100 < ratio_a 决定） |
| provider_id | Integer | nullable | - |
| model_name | String(64) | "" | - |
| latency_ms | Integer | 0 | - |
| token_count | Integer | 0 | LLM usage.total_tokens，无则记 0 |
| is_success | Boolean | True | 由 agent_service 真实判定（content 非空且无 error） |
| user_feedback | String(16) | "" | 保留字段，当前未采集 |
| created_at | DateTime | now() | - |

### `knowledge_drafts` — AI 知识草稿

| 字段名 | 类型 | 默认 | 说明 |
|--------|------|------|------|
| id | Integer PK | - | - |
| alert_id | Integer FK(alerts.id) | nullable | 关联告警（告警来源时有值；故障单来源时取首个 alert_id） |
| title | String(256) | NOT NULL | 标题 |
| symptom | Text | "" | 故障表现 |
| root_cause | Text | "" | 根因 |
| solution | Text | "" | 解决方案 |
| tags | String(256) | "" | 英文逗号分隔 |
| severity | String(32) | "warning" | critical / high / warning / info |
| asset_type | String(32) | "" | - |
| source_data | Text | "" | JSON，含 alert_id / incident_id / 原始信息 |
| source_type | String(32) | "auto" | auto / sop / manual |
| sop_steps | Text | "[]" | JSON array of {step, action, command, expectation} |
| status | String(16) | "pending" | pending / approved / rejected |
| reject_reason | Text | "" | 拒绝原因（前端 body 传，后端 Body 接收） |
| created_at | DateTime | now() | - |
| updated_at | DateTime | now()/onupdate | - |

**API 约定**：
- `POST /knowledge/api/auto-gen/drafts/{id}/reject` body: `{"reason":"xxx"}`
- `GET /knowledge/api/auto-gen/drafts/stats` 返回 `{pending, approved, rejected, total}`（后端 GROUP BY）
- `DELETE /knowledge/api/auto-gen/drafts/{id}` 仅允许删除非 approved 状态
- **审批通过后同步 RAG（2026-08-08 修复）**：除写入 `knowledge_base` + 建立 `alert_kb_links` 外，必须同步创建 `kb_documents` 条目（`kb_id` 关联本知识、`source_type="auto"`、`content` = `title + 症状 + 根因 + 解决方案 + 标签` 拼接文本）并调用 `rag_service.index_document` 完成切片/向量索引，确保 AI 助手 `query_knowledge_rag`（走 `rag_service.vector_search`，只查 `kb_chunks`）能检索到新入库知识。索引失败则整体回滚。
- 若审批接口未同步 RAG，将导致：knowledge_base 有数据但 RAG 检索不到（静默缺口）

### `knowledge_base` — 知识库（审批通过后入库）

| 字段名 | 类型 | 默认 | 说明 |
|--------|------|------|------|
| id | Integer PK | - | - |
| title | String(256) | NOT NULL | - |
| symptom | Text | "" | - |
| root_cause | Text | "" | - |
| solution | Text | "" | - |
| tags | String(256) | "" | - |
| severity | String(32) | "warning" | - |
| asset_type | String(32) | "" | - |
| source_type | String(32) | "manual" | manual / auto（自动沉淀；approve_draft 同步 RAG 时用 auto） |
| sop_steps | Text | "[]" | - |
| version_number | Integer | 1 | - |
| change_log | Text | "" | - |
| created_at | DateTime | now() | - |
| updated_at | DateTime | now()/onupdate | - |

### `alert_kb_links` — 告警与知识库关联

| 字段名 | 类型 | 默认 | 说明 |
|--------|------|------|------|
| id | Integer PK | - | - |
| alert_id | Integer FK(alerts.id) | NOT NULL | - |
| kb_id | Integer FK(knowledge_base.id) | NOT NULL | - |

### `kb_documents` — RAG 文档（knowledge_base 的检索索引载体）

| 字段名 | 类型 | 默认 | 说明 |
|--------|------|------|------|
| id | Integer PK | - | - |
| kb_id | Integer FK(knowledge_base.id) | nullable | 关联知识库条目（auto 沉淀时有值；上传文档为 NULL） |
| title | String(256) | NOT NULL | 文档标题 |
| source_type | String(32) | "manual" | manual / upload / alert_case / incident_case / **auto**（approve_draft 同步 RAG） |
| file_path | String(512) | "" | 上传文件原始存储路径 |
| file_ext | String(16) | "" | 文件扩展名 md/txt/pdf/docx |
| content | Text | "" | 全文内容（auto 沉淀时 = 标题+症状+根因+解决方案+标签 拼接） |
| chunk_count | Integer | 0 | 切片数量 |
| status | String(32) | "pending" | pending / indexed / failed |
| tags | String(256) | "" | - |
| asset_type | String(32) | "" | - |
| asset_id | Integer FK(assets.id) | nullable | 关联具体资产 |
| severity | String(32) | "warning" | - |
| index_engine | String(16) | "v1" | v1 / v2 / both（索引归属引擎；v1=TF-IDF 存 kb_chunks，v2=Milvus） |
| created_by | Integer FK(users.id) | nullable | - |
| created_at | DateTime | now() | - |
| updated_at | DateTime | now()/onupdate | - |

### `kb_chunks` — RAG 切片（向量检索实际命中单元）

| 字段名 | 类型 | 默认 | 说明 |
|--------|------|------|------|
| id | Integer PK | - | - |
| document_id | Integer FK(kb_documents.id) | NOT NULL | - |
| chunk_index | Integer | NOT NULL | 切片序号 |
| content | Text | NOT NULL | 切片文本 |
| embedding | Text | "" | 向量 JSON 字符串（TF-IDF 稀疏向量） |
| embedding_mode | String(32) | "tfidf" | tfidf / provider |
| token_count | Integer | 0 | - |
| tags | String(256) | "" | - |
| asset_type | String(32) | "" | - |
| severity | String(32) | "warning" | - |
| created_at | DateTime | now() | - |

> **RAG 检索链路约定**：AI 助手 `query_knowledge_rag` 只查 `kb_chunks`（经 `kb_documents` 关联标题）。因此所有需要被 RAG 检索到的知识（含 auto 审批沉淀）**必须**同步创建 `kb_documents` 并执行 `index_document`。
> **asset_id 过滤（2026-08-08 补强）**：`query_knowledge_rag` 新增 `asset_id` 参数 → `rag_service.vector_search` 经 `kb_chunks.document_id JOIN kb_documents.id` 过滤 `kb_documents.asset_id`，实现"查某资产时只检索该资产关联的部署文档/知识"。`kb_chunks` 表**不新增** asset_id 列，资产归属一律走 `kb_documents.asset_id`（部署文档上传时在 `knowledge_documents.py` 写入）。

### `runbooks` — 标准操作流程(Runbook) API 契约（2026-08-08 补充）

> 表格字段见 models.py `Runbook`。本节约定 **API 层**行为，前端 `RunbooksView.vue` 与后端 `app/routers/runbooks.py` 必须一致。

| 约定项 | 规则 |
|--------|------|
| `content` 别名 | 前端表单字段为 `content`，后端模型无此列。create/update 收到 `content` 时**写入 `symptom`**；`_rb_to_dict` 返回 `content`(= `symptom`)，保证前端内容字段保存与回显一致（2026-08-08 修复，此前静默丢弃） |
| `tags` 归一化 | 契约类型 String(256)（JSON 字符串）。create/update 必须经 `_norm_tags()` 归一化：list/tuple → `json.dumps` 字符串，字符串原样保留（2026-08-08 修复，此前传数组直接 500） |
| `query_runbook` 检索 | MCP 工具（`mcp_tools.py:749`）按 `search`(title/symptom/diagnosis/steps/tags 模糊)、`category`、`asset_type` 过滤，AI 助手在"问怎么操作/处理步骤"时优先调用 |
| 告警联动推荐 | `smart_recommend.py:_score_runbook`：metric 命中 tag +5、标题含 metric +3、asset_type 匹配 +3、症状文本重叠 +4、severity 对齐 +1 |

---

## 第八章：中间件子类型与数据库子类型枚举（2026-07-19 新增）

> **本节为 `mw_subtype` 与 `db_type` 字段的唯一权威枚举清单。**
> 前后端下拉选项、连接测试、健康检查路径、巡检模板覆盖范围均以本节为准。
> 新增/修改子类型必须先改本节，再同步前后端代码。

### 8.1 `mw_subtype` — 中间件子类型枚举（ci_type="middleware" 时使用）

> 当 `ci_type="middleware"` 时，`mw_subtype` 用于细分具体中间件产品。
> `mw_port` 字段对应下方"默认端口"，`mw_admin_url` 为可选管理地址。
> 连接测试：`connection_type="http"` 时按 `mw_subtype` 路由到对应健康检查路径。

#### 8.1.1 Web 服务器 / 应用服务器

| mw_subtype | 标签 | 默认端口 | 健康检查路径 |
|-----------|------|---------|------------|
| nginx | Nginx | 80 | `/` |
| apache | Apache HTTP | 80 | `/` |
| tomcat | Tomcat | 8080 | `/` |
| jetty | Jetty | 8080 | `/` |
| weblogic | WebLogic | 7001 | `/console` |
| websphere | WebSphere | 9043 | `/ibm/console` |
| wildfly | WildFly/JBoss | 8080 | `/` |

#### 8.1.2 消息队列

| mw_subtype | 标签 | 默认端口 | 健康检查方式 |
|-----------|------|---------|------------|
| kafka | Kafka | 9092 | TCP 端口连通 |
| rabbitmq | RabbitMQ | 15672 | `/api/overview` |
| rocketmq | RocketMQ | 9876 | TCP 端口连通 |
| activemq | ActiveMQ | 8161 | `/api/jolokia/` |
| pulsar | Apache Pulsar | 8080 | `/admin/v2/brokers/healthcheck` |

#### 8.1.3 注册中心 / 配置中心

| mw_subtype | 标签 | 默认端口 | 健康检查路径 |
|-----------|------|---------|------------|
| nacos | Nacos | 8848 | `/nacos/v1/ns/operator/metrics` |
| zookeeper | ZooKeeper | 2181 | TCP + ruok 命令 |
| apollo | Apollo | 8080 | `/health` |
| consul | Consul | 8500 | `/v1/status/leader` |
| eureka | Eureka | 8761 | `/eureka/apps` |
| etcd | Etcd | 2379 | `/health` |

#### 8.1.4 流量控制 / API 网关

| mw_subtype | 标签 | 默认端口 | 健康检查路径 |
|-----------|------|---------|------------|
| sentinel | Sentinel | 8080 | `/health` |
| apisix | APISIX | 9180 | `/apisix/status` |
| kong | Kong | 8001 | `/status` |
| spring_cloud_gateway | Spring Cloud Gateway | 8080 | `/actuator/health` |
| haproxy | HAProxy | 80 | `/stats` |

#### 8.1.5 分布式事务

| mw_subtype | 标签 | 默认端口 | 健康检查路径 |
|-----------|------|---------|------------|
| seata | Seata | 8091 | `/health` |

#### 8.1.6 缓存
| mw_subtype | 标签 | 默认端口 | 健康检查方式 |
|-----------|------|---------|------------|
| memcached | Memcached | 11211 | TCP 端口连通 |
| redis | Redis | 6379 | TCP 端口连通 |

#### 8.1.7 对象存储 / 其他

| mw_subtype | 标签 | 默认端口 | 健康检查路径 |
|-----------|------|---------|------------|
| minio | MinIO | 9000 | `/minio/health/live` |

**约定：**
- `mw_subtype` 取值必须在上表枚举内；未列出的中间件统一用 `middleware`（空 subtype），按 HTTP 通用健康检查。
- 前端 `AssetsView.vue` 中间件下拉选项必须与本表一致。
- 后端 `connection_service.py::_test_middleware` 按本表的"健康检查路径/方式"实施。

### 8.2 `db_type` — 数据库子类型枚举（ci_type="database" 时使用）

> 当 `ci_type="database"` 时，`db_type` 用于细分具体数据库产品。
> 连接测试：`connection_type="database"` 时按 `db_type` 路由到对应驱动。

| db_type | 标签 | 默认端口 | 驱动 / 测试方式 |
|---------|------|---------|---------------|
| mysql | MySQL | 3306 | pymysql |
| postgresql | PostgreSQL | 5432 | psycopg2 |
| oracle | Oracle | 1521 | cx_Oracle / oracledb（SID or Service Name） |
| sqlserver | SQL Server | 1433 | pyodbc / pymssql |
| mongodb | MongoDB | 27017 | pymongo |
| redis | Redis | 6379 | redis-py |
| elasticsearch | Elasticsearch | 9200 | HTTP `/_cluster/health` |
| tidb | TiDB | 4000 | pymysql（MySQL 协议兼容） |
| clickhouse | ClickHouse | 8123 | HTTP `/?query=SELECT+1` |
| dameng | 达梦 DM | 5236 | dmPython（可选）/ TCP 端口连通 |
| oceanbase | OceanBase | 2883 | pymysql（MySQL 协议兼容） |
| mariadb | MariaDB | 3306 | pymysql |
| sqlite | SQLite | — | 本地文件，连接测试跳过端口检测 |

**约定：**
- `db_type` 取值必须在上表枚举内。
- 前端 `AssetsView.vue` 数据库下拉选项必须与本表一致。
- 后端 `connection_service.py::_test_database` 必须按本表覆盖所有 `db_type`：
  - 已支持：mysql / postgresql / redis
  - 本次新增支持：oracle / sqlserver / mongodb / elasticsearch / tidb / clickhouse / dameng / oceanbase / mariadb / sqlite
- 未安装驱动的类型：返回明确的"缺少驱动: xxx，请执行 pip install xxx"提示，不得静默失败。

### 8.3 字段命名约束（沿用）

- `mw_subtype` 字段类型 String(32)，默认值 `nginx`（向后兼容）
- `mw_port` 字段类型 Integer，默认值 80
- `mw_admin_url` 字段类型 String(512)，可选
- `db_type` 字段类型 String(32)，默认值 `mysql`
- `db_port` 字段类型 Integer，默认值 3306
- `db_user` / `db_password` / `db_name` 字段沿用 CONTRACT.md 第五章敏感字段掩码规则


---

## 第九章：AI 运维沙盒（AIOps Sandbox）字段契约

> 本模块为独立功能，暂不侵入现有 Agent/Edge 执行链。用于控制 AI Agent 下发到节点后的作用范围。
> 三张表：**sandbox_configs**（全局配置）、**sandbox_policies**（细粒度策略）、**sandbox_execution_logs**（沙盒执行日志）。

### 9.1 sandbox_configs（全局沙盒配置，单行）

| 字段 | 类型 | 默认 | 说明 |
|------|------|------|------|
| id | Integer PK | - | |
| 
ame | String(64) | "default" | 配置名 |
| is_enabled | Boolean | false | 沙盒总开关（默认关闭，不影响现有功能） |
| dry_run_mode | Boolean | false | 干运行模式：记录"将执行"但不真正执行 |
| max_actions_per_session | Integer | 10 | 单会话最大执行次数 |
| max_actions_per_day | Integer | 50 | 单日最大执行次数 |
| max_risk_level | String(16) | "critical" | 允许的最大风险等级（read_only/advisory/medium/high/critical，默认不限制） |
| execution_window_start | String(5) | "" | 写操作允许开始时间 "HH:MM"，空=不限制 |
| execution_window_end | String(5) | "" | 写操作允许结束时间 "HH:MM"，空=不限制 |
| created_at | DateTime | now | |
| updated_at | DateTime | now/onupdate | |

### 9.2 sandbox_policies（细粒度沙箱策略）

| 字段 | 类型 | 默认 | 说明 |
|------|------|------|------|
| id | Integer PK | - | |
| 
ame | String(64) | - | 策略名 |
| description | Text | "" | 描述 |
| scope_type | String(16) | "global" | 作用范围类型：global / role / user / session |
| scope_id | Integer | 0 | 作用范围 ID（role_id/user_id/session_id） |
| llowed_asset_ids | Text | "[]" | 允许操作的资产白名单（JSON 数组） |
| locked_asset_ids | Text | "[]" | 禁止操作的资产黑名单（JSON 数组） |
| llowed_tools | Text | "[]" | 允许调用的工具白名单（JSON 数组，空=继承全部） |
| locked_tools | Text | "[]" | 禁止调用的工具黑名单（JSON 数组） |
| llowed_commands | Text | "[]" | 允许的命令前缀白名单（JSON 数组，如 ["systemctl restart","df"]） |
| locked_commands | Text | "[]" | 禁止的命令黑名单（JSON 数组，支持正则） |
| max_risk_level | String(16) | "critical" | 本策略允许的最大风险等级 |
| max_actions_per_day | Integer | 0 | 本策略单日最大执行次数（0=继承全局） |
| equire_second_approval | Boolean | false | 高危操作是否需要二级审批 |
| is_enabled | Boolean | true | 策略是否启用 |
| created_at | DateTime | now | |
| updated_at | DateTime | now/onupdate | |

### 9.3 sandbox_execution_logs（沙盒执行日志）

| 字段 | 类型 | 默认 | 说明 |
|------|------|------|------|
| id | Integer PK | - | |
| session_id | Integer | 0 | 关联会话 ID |
| ction_type | String(32) | "" | 动作类型（restart/clean/scale/script/run_command） |
| 	ool_name | String(64) | "" | 调用的 MCP 工具名 |
| sset_id | Integer | 0 | 目标资产 ID |
| isk_level | String(16) | "medium" | 动作风险等级 |
| mode | String(8) | "live" | 执行模式：dry_run / live |
| payload | Text | "{}" | 动作参数（JSON） |
| decision | String(16) | "allowed" | 决策：allowed / rejected / dry_run |
| eject_reason | String(255) | "" | 拒绝原因 |
| pproved_by | Integer | 0 | 审批人 ID |
| created_at | DateTime | now | |

### 9.4 约定

- 所有 JSON 字段用 Text 列存 JSON 字符串，后端提供 get_xxx() 解析方法
- 风险等级枚举：ead_only < dvisory < medium < high < critical（只升不降）
- 决策顺序：先查黑名单（blocked）→ 再查白名单（allowed）→ 再查风险等级 → 再查执行配额
- 黑名单优先级高于白名单

---

## 第十章：工作流运行时 context 注入规范（Pre-Run Probe）

> 适用：`WorkflowTemplate` / `WorkflowRun`（workflow_service）、`sop_templates.py` 节点命令。
> 新增/修改任何 `context.*` 字段必须先改本节，再同步模板与代码。

### 10.1 节点命令参数化三来源（优先级从高到低）

| 优先级 | 来源 | 说明 |
|--------|------|------|
| 1 | `context.<用户/LLM字段>` | 创建 run 时由调用方传入，如 `service_name`、`namespace`、`asset_id` |
| 2 | `context.probe.<探测字段>` | 引擎 Pre-Run 自动探测注入（见 10.2），无则回退 default |
| 3 | `{{ xxx | default(写死值) }}` | 兜底默认值，保证无探测/无参数时行为不变（向后兼容） |

### 10.2 探测字段命名（`context.probe.*`）

引擎在 `start_workflow_run` 创建 run 后、执行只读节点前，对 `context.asset_id` 目标资产自动跑一组只读命令，结果解析注入 `context.probe`。**探测失败/资产离线不阻塞工作流**，模板靠 `default` 兜底。

| 字段 | 类型 | 说明 | 示例 |
|------|------|------|------|
| `probe.timestamp` | String | 探测时间 ISO 格式 | "2026-08-11T15:04:05" |
| `probe.raw` | Object | 原始命令输出（诊断用，不参与模板渲染）；探测不到某段则缺省 | `{"df_text": "...", "mem_text": "...", "load_text": "..."}` |
| `probe.raw.df_text` | String | `df -h` 原始输出（不含 tmpfs） | 多行文本 |
| `probe.raw.mem_text` | String | `free -m` 原始输出 | 多行文本 |
| `probe.raw.load_text` | String | `uptime` 原始输出 | 一行文本 |
| `probe.fullest_mount` | String | 使用率最高的挂载点路径 | "/" |
| `probe.disk_usage_pct` | String | 最满挂载点使用率（数字字符串） | "92" |
| `probe.top_dirs` | String | 最满挂载点下 TOP 大目录（空格分隔，可直接嵌入 `du -sh <目录...>`） | "/tmp /var/log" |
| `probe.log_dirs` | String | 存在的日志目录（空格分隔，可直接嵌入 `find <目录...>`） | "/var/log /var/log/nginx" |
| `probe.nginx_log_dir` / `probe.app_log_dir` / `probe.redis_log_dir` / `probe.mysql_log_dir` / `probe.auth_log_dir` / `probe.haproxy_log_dir` | String | 探测到存在的具体日志目录；探测不到则字段不存在，用模板 default 兜底 | "/var/log/nginx" |

### 10.3 模板命令规范

1. **路径/目录必须优先引用 probe**，格式统一：`{{ context.probe.xxx | default('原写死值') }}`
2. 探测字段为空格分隔目录列表时，命令可直接内嵌：`du -sh {{ context.probe.top_dirs | default('/tmp /var/log /home /opt') }}`
3. **禁止**新增模板写死绝对路径（如 `find /var/log -name ...`），除非该路径探测不可得（如具体配置文件）。
4. 探测命令集合（`_PROBE_SCRIPT`，见 workflow_service.py）必须全部为只读命令（df/du/ls/find/awk/sort/free/uptime），禁止写操作。
5. 上游节点输出可被下游引用：`{{ upstream.<node_id>.data.xxx }}`（`_advance_run` 自动收集已完成节点 result 注入渲染）。
- 本模块独立，不修改 gent_service.py / 
emediation_service.py / edge_tunnel_service.py 现有执行链

---

## 第十一章：AI 自动部署（Deploy）字段契约

> 适用：`deploy_plans` / `deploy_steps` 两张表，`app/services/deploy_service.py`，`app/routers/deploy.py`。
> 前端 `DeployView.vue` 消费。
> 新增/修改字段必须先改本节，再同步前后端代码。

### 11.1 deploy_plans — 部署计划

| 字段 | 类型 | 默认 | 说明 |
|------|------|------|------|
| id | Integer PK | - | 主键 |
| name | String(128) | NOT NULL | 计划名称 |
| description | Text | "" | 描述 |
| artifact_path | String(512) | "" | **代码包引用路径（资产服务器路径），平台不落本地**。支持三种来源：①资产服务器已有路径（如 `/opt/app`，平台不下载）②HTTP 下载地址（`http(s)://`，平台 curl 自动下载到资产）③Git 仓库地址（`github.com`/`gitee.com` 等，平台识别并自动 clone/下载 zip 到资产） |
| artifact_download_path | String(512) | "" | **源码自动下载目标路径（资产服务器侧）**：识别到 HTTP/Git 地址时，源码下载到该目录（如 `/data/aiops-deploy/<计划名>`）。为空时后端默认 `auto`（由后端按计划名生成 `/data/aiops-deploy/<name>`） |
| artifact_auto_download | Boolean | True | **是否在环境探查(probe)前自动下载源码**：True=探查看自动先下载（幂等，目录已存在且有 compose 则跳过）；False=不自动下载，需手册步骤自行处理（如手动 SFTP 上传） |
| doc_raw | Text | "" | 部署手册原始内容（markdown） |
| doc_file_name | String(256) | "" | 上传的部署手册文件名（.md/.txt/.docx 等） |
| asset_ids | Text | "[]" | 目标环境资产 ID 列表（JSON 数组，支持多资产） |
| env_mapping | Text | "{}" | 环境映射对照表 JSON，如 `{"target_ip": "192.168.1.100", "app_dir": "/opt/app"}` |
| environment_probe_json | Text | "{}" | **环境探查结果 JSON**：SSH 目标机后采集的 compose 内容/端口/镜像/目录/OS |
| env_analysis_json | Text | "{}" | **AI 环境分析 JSON**：基于探查结果，AI 生成的 SOP 适配建议（自适应调整） |
| sop_json | Text | "[]" | AI 解析手册后生成的结构化 SOP JSON，schema 见 11.3 |
| status | String(32) | "draft" | draft / planned / running / succeeded / failed / rolled_back |
| preflight_json | Text | "{}" | 预飞行检查结果 JSON |
| deploy_report_json | Text | "{}" | **部署报告 JSON**：AI 生成的交付级部署报告（含 executive_summary 执行摘要、environment 环境信息、timeline 时间线、steps_table 步骤表、key_observations 关键观察、verification 验证、test_results 测试记录、issues 问题列表、risk_assessment 风险评估、recommendations 建议、overall_assessment 总体评估，以及 total_steps/succeeded_steps/failed_steps/skipped_steps/total_assets/preflight_passed/verification_passed/ai_decisions 等 KPI 指标） |
| test_results_json | Text | "{}" | **部署后验证/测试记录 JSON**：SSH 健康检查、容器状态、端口检查、HTTP 探测结果 |
| execution_history_json | Text | "[]" | **执行历史记录 JSON**：每次部署的时间戳、状态、资产统计（最多保留 50 条） |
| cleanup_history_json | Text | "[]" | **回滚清理历史记录 JSON**：每次手动回滚清理的时间戳(cleaned_at)、目标目录(app_dir)、各资产(assets[]：asset/ip/status/lines 操作日志行)（最多保留 20 条） |
| last_deployed_at | DateTime | nullable | 最近一次部署时间 |
| deploy_count | Integer | 0 | 累计部署次数 |
| dag_json | Text | "{}" | **AI 执行引擎 DAG 执行计划 JSON**：AI 分析步骤依赖后生成的 DAG，含 groups(并行组/串行组)、reasoning |
| ai_decision_log_json | Text | "[]" | **AI 自主决策日志 JSON**：每次失败时 AI 的决策记录(fix/retry/skip/rollback)，含根因、修复命令、时间戳(最多 200 条) |
| created_by | Integer FK(users.id) | nullable | 创建人 |
| created_at | DateTime | now() | - |
| updated_at | DateTime | now()/onupdate | - |

### 11.2 deploy_steps — 部署步骤（执行记录）

| 字段 | 类型 | 默认 | 说明 |
|------|------|------|------|
| id | Integer PK | - | 主键 |
| plan_id | Integer FK(deploy_plans.id) | NOT NULL | 所属计划 |
| step_order | Integer | 0 | 步骤序号 |
| description | String(512) | "" | 步骤说明 |
| command | Text | "" | 待执行命令（已做环境代换，含 `${ENV_xxx}` 占位符） |
| verify_command | Text | "" | 校验命令 |
| rollback_command | Text | "" | 回滚命令 |
| risk_level | String(16) | "medium" | low / medium / high |
| status | String(32) | "pending" | pending / running / succeeded / failed / skipped / rolled_back / fixing（修复中） |
| output | Text | "" | 执行输出 |
| diagnosis | Text | "" | **失败时 AI 诊断结果文本**：根因分析 |
| fix_command | Text | "" | **AI 建议的修复命令**（人工确认后执行） |
| retry_count | Integer | 0 | 重试次数 |
| precheck_result | Text | "" | **AI 预执行风险检查结果**：执行前 AI 分析命令风险(risk/reason/precheck) |
| started_at | DateTime | nullable | - |
| finished_at | DateTime | nullable | - |

### 11.3 SOP JSON schema（`deploy_plans.sop_json` 存储格式）

```json
{
  "plan_name": "xxx 部署",
  "preflight": [
    {"check": "disk_space", "command": "df -h /", "expect": "使用率 < 80%"},
    {"check": "port_available", "command": "ss -tlnp | grep 8080", "expect": "端口未占用"}
  ],
  "steps": [
    {
      "order": 1,
      "description": "拉取代码包",
      "command": "wget -q ${ARTIFACT_URL} -O /tmp/package.tar.gz && echo 'sha256: ${CHECKSUM}'",
      "verify": "ls -la /tmp/package.tar.gz",
      "rollback": "rm -f /tmp/package.tar.gz",
      "risk": "low"
    }
  ]
}
```

### 11.4 环境映射占位符约定

| 占位符 | 来源 | 示例 |
|--------|------|------|
| `${TARGET_IP}` | assets.ip | 192.168.1.100 |
| `${APP_DIR}` | probe/用户输入 | /opt/myapp |
| `${LOG_DIR}` | probe/用户输入 | /var/log/myapp |
| `${ARTIFACT_URL}` | deploy_plans.artifact_path | http://artifacts.local/release/v1.0.tar.gz |
| `${ARTIFACT_DOWNLOAD_PATH}` | deploy_plans.artifact_download_path | /data/aiops-deploy/myapp（git/http 源码自动下载目标路径，供手册引用） |
| `${CHECKSUM}` | 用户输入 | a1b2c3d4... |
| `${SERVICE_NAME}` | 用户输入 | myapp-backend |
| `${ENV_xxx}` | env_mapping JSON | 自定义占位符，由 AI 识别手册后提出 |

### 11.5 状态机

```
draft → planned → running → succeeded → (post-verify → report)
                    ↓               ↘
                 failed → rolled_back
```

- 执行完成后自动记录执行历史、生成部署报告、运行后验证
- 部署报告含：概述、步骤表、环境信息、验证结果、测试记录、问题与建议
- 验证涵盖：Docker 状态、容器运行、端口监听、HTTP 健康检查

- `draft`: 刚创建，尚未解析
- `planned`: AI 解析完成，生成 SOP + 环境映射，待人工确认
- `running`: 执行中
- `succeeded`: 全部步骤成功
- `failed`: 某步失败（含校验失败）
- `rolled_back`: 失败后执行回滚完成

### 11.6 AI 执行引擎（10 分能力）

> 前端 `DeployView.vue` 执行 Tab 消费，WS 事件兼容旧事件 + 新增事件。

**五大 AI 能力：**

| 能力 | 说明 | 事件 |
|------|------|------|
| ① 动态编排(DAG) | 执行前 AI 分析步骤依赖，生成并行组/串行组执行计划 | `dag_plan` |
| ② 自主决策 | 步骤失败后 AI 直接决策 fix/retry/skip/rollback，无需人工确认 | `ai_decision` |
| ③ 执行前预判 | 每步执行前 AI 分析命令风险，产出 risk/precheck/suggest_modify | `ai_precheck` |
| ④ 并行调度 | DAG parallel=true 组内步骤多线程并行执行 | `parallel_group` |
| ⑤ 自适应回滚 | AI 只回滚有状态步骤，跳过 echo/mkdir/校验等无状态步骤 | — |

**新增 WS 事件：**

| 事件类型 | 字段 | 说明 |
|---------|------|------|
| dag_plan | groups, reasoning | DAG 执行计划 |
| parallel_group | group, steps, parallel, reason | 并行组开始 |
| ai_precheck | step, risk, reason, precheck, guard_note | AI 预执行风险检查 |
| ai_decision | step, decision, reason, fix_commands | AI 自主决策（不再等用户） |

**AI 回退策略：** 任一 AI 能力不可用时静默回退为安全的确定性行为（DAG→线性、自主决策→回滚、预判→跳过、回滚→全量逆序），不影响部署可用。

---

## 第十二章：离线部署（Offline Repo）字段契约

> 适用：`offline_repo_bundles` / `offline_registries` / `offline_package_sources` 三张表，
> `app/services/offline_repo_service.py`，`app/routers/offline_repo.py`。
> 前端 `OfflineRepoView.vue` 消费。
> 新增/修改字段必须先改本节，再同步前后端代码。

### 12.1 offline_repo_bundles — 离线仓库包

| 字段 | 类型 | 默认 | 说明 |
|------|------|------|------|
| id | Integer PK | - | 主键 |
| name | String(128) | NOT NULL | 离线包名称，如 `pixiu-packages-ubuntu-24.04` |
| description | Text | "" | 描述 |
| version | String(64) | "" | K8S/应用版本，如 `v1.31.6` |
| os_type | String(32) | "" | 系统类型：ubuntu/centos/debian |
| os_version | String(32) | "" | 系统版本：24.04/7/11 |
| bundle_type | String(32) | NOT NULL | 包类型：images/packages/server |
| file_path | String(512) | "" | **离线包文件路径（服务器存储路径，不落前端）** |
| file_size | Integer | 0 | 文件大小（字节） |
| md5 | String(64) | "" | 文件 MD5 校验 |
| status | String(32) | "pending" | pending/loading/loaded/failed |
| loaded_images | Integer | 0 | 已加载镜像数 |
| total_images | Integer | 0 | 总镜像数 |
| loaded_packages | Integer | 0 | 已加载系统包数 |
| load_message | String(512) | "" | 加载进度消息/失败原因 |
| loaded_at | DateTime | nullable | 加载完成时间 |
| created_at | DateTime | now() | - |
| updated_at | DateTime | now()/onupdate | - |

### 12.2 offline_registries — 私有镜像仓库

| 字段 | 类型 | 默认 | 说明 |
|------|------|------|------|
| id | Integer PK | - | 主键 |
| name | String(128) | NOT NULL | 仓库名称 |
| registry_url | String(256) | NOT NULL | 仓库地址，如 `10.0.0.1:5000` |
| is_internal | Boolean | False | 是否内嵌（平台自管理） |
| storage_path | String(512) | "" | 内嵌仓库存储路径 |
| is_secure | Boolean | False | 是否 HTTPS |
| username | String(64) | "" | 仓库用户名 |
| password | String(128) | "" | **敏感字段：仓库密码（后端返回 `***` + `has_password` 标记，前端编辑置空、保存空值=不更新）** |
| has_password | Boolean | False | 是否已设置密码 |
| is_default | Boolean | False | 是否默认仓库 |
| status | String(32) | "active" | active/inactive/error |
| created_at | DateTime | now() | - |
| updated_at | DateTime | now()/onupdate | - |

### 12.3 offline_package_sources — 离线系统包源（deb/rpm）

| 字段 | 类型 | 默认 | 说明 |
|------|------|------|------|
| id | Integer PK | - | 主键 |
| bundle_id | Integer FK(offline_repo_bundles.id) | nullable | 关联离线包 |
| os_type | String(32) | NOT NULL | 系统类型 |
| os_version | String(32) | "" | 系统版本 |
| source_url | String(256) | NOT NULL | 源地址，如 `http://10.0.0.1:8080/deb` |
| source_type | String(16) | NOT NULL | deb/rpm |
| package_count | Integer | 0 | 软件包数量 |
| is_active | Boolean | True | 是否启用 |
| created_at | DateTime | now() | - |

### 12.4 离线部署流程

```
用户上传离线包(.tar.gz)
  → 保存到 <PROJECT_ROOT>/storage/offline/ 目录 + 校验 MD5
  → 用户点击"加载"
      → 解压扫描 images/ 与 packages/ 目录
      → 镜像: docker load → docker tag → docker push 到默认 Registry（可选）
      → 包源: 生成 Packages.gz(deb) / repodata(rpm) 索引 + 本地 HTTP 静态服务
      → bundle.status = loaded / failed
创建部署计划时: 离线模式自动填入私有 Registry + 包源 URL（后续阶段对接 deploy_plans）
```

### 12.5 敏感字段掩码规则（沿用第五章）

- `offline_registries.password`：后端详情/列表返回 `***`，同时返回 `has_password` 布尔标记
- 前端编辑时密码输入框置空；提交时空值=不更新（保留旧密码）
- `storage_path`（内嵌仓库本地路径）属于服务器侧字段，不回传、前端不可编辑

---

## 第十三章：K8S 离线集群部署（K8S Offline Cluster Deploy）字段契约

> 适用：`k8s_cluster_plans` / `k8s_cluster_nodes` 两张表，
> `app/services/k8s_offline_deploy_service.py`，`app/routers/k8s_offline_deploy.py`。
> 前端 `K8sOfflineDeployView.vue` 消费。
> 功能定位：在离线环境下，复用「第十二章」离线仓库（私有 Registry + 包源），
> 通过 SSH 在目标主机上执行 kubeadm 编排，一键创建 K8S 集群，产出 kubeconfig 并自动接入平台 K8S 监控。
> 新增/修改字段必须先改本节，再同步前后端代码。

### 13.1 k8s_cluster_plans — K8S 集群部署计划

| 字段 | 类型 | 默认 | 说明 |
|------|------|------|------|
| id | Integer PK | - | 主键 |
| name | String(128) | NOT NULL | 集群名称（作为 k8s_cluster 标识 / DataSource 名称） |
| kubernetes_version | String(64) | "" | K8S 版本，如 `v1.31.6` |
| runtime | String(32) | "containerd" | 容器运行时：containerd/docker |
| cni | String(32) | "calico" | 网络插件：calico/cilium/flannel |
| pod_cidr | String(32) | "10.244.0.0/16" | Pod CIDR |
| service_cidr | String(32) | "10.96.0.0/12" | Service CIDR |
| image_repository | String(256) | "" | 控制面镜像仓库（默认用离线默认 Registry） |
| bundle_id | Integer FK(offline_repo_bundles.id) | nullable | 关联离线包（可空，联调/在线模式不要求） |
| registry_id | Integer FK(offline_registries.id) | nullable | 关联私有 Registry（加载镜像用） |
| nodes_json | Text | "[]" | 节点定义 JSON（见 13.3 节点对象结构） |
| status | String(32) | "draft" | draft/planned/running/succeeded/failed/rolled_back |
| current_step | Integer | 0 | 当前执行步骤序号（编排阶段） |
| logs_json | Text | "[]" | 执行日志事件列表（{ts,type,node,step,message}） |
| kubeconfig | Text | "" | **敏感：产出 kubeconfig 内容（后端列表不返回，详情按需返回）** |
| join_token | Text | "" | **敏感：worker 加入 token（临时，仅执行期写入）** |
| report_json | Text | "{}" | 部署报告（node 状态矩阵 + 关键信息） |
| created_by | Integer FK(users.id) | nullable | 创建人 |
| created_at | DateTime | now() | - |
| updated_at | DateTime | now()/onupdate | - |

### 13.2 k8s_cluster_nodes — 集群节点

| 字段 | 类型 | 默认 | 说明 |
|------|------|------|------|
| id | Integer PK | - | 主键 |
| plan_id | Integer FK(k8s_cluster_plans.id) | NOT NULL | 关联计划 |
| asset_id | Integer FK(assets.id) | nullable | 关联平台资产（可空=手填 IP+SSH 凭据） |
| host_role | String(16) | "worker" | master/worker |
| ip | String(64) | "" | 节点 IP |
| hostname | String(64) | "" | 节点主机名（空=部署时探测） |
| username | String(64) | "" | SSH 用户 |
| password | String(128) | "" | **敏感：SSH 密码（详情返回 `***` + `has_password`）** |
| has_password | Boolean | False | 是否已设置 SSH 密码 |
| ssh_port | Integer | 22 | SSH 端口 |
| status | String(32) | "pending" | pending/running/succeeded/failed |
| init_roles | Text | "" | 控制面额外角色：control-plane/etcd（多 master 用） |
| joined_at | DateTime | nullable | 加入时间 |
| created_at | DateTime | now() | - |

### 13.3 节点对象结构（nodes_json 元素 / 前端提交体）

```json
{
  "asset_id": 12,            // 可选，关联资产时自动取连接配置
  "host_role": "master",     // master/worker
  "ip": "192.168.1.10",
  "hostname": "k8s-master01",// 可选
  "username": "root",
  "password": "",            // 敏感：提交即写入，回显保持空
  "ssh_port": 22,
  "init_roles": "control-plane,etcd"   // 仅 mult-master：首 master 可空
}
```

### 13.4 部署执行流程（kubeadm 编排，7 阶段）

```
阶段0 预检:    各节点 SSH 连通/root/OS/swap/内核模块
阶段1 环境准备: 各节点 关 swap + 加载 overlay/br_netfilter + sysctl + 配 hostname/hosts
阶段2 运行时:   各节点 装 containerd + 配置 + 导入离线镜像(或配置私有 Registry insecure)
阶段3 引导:     首 master 生成 kubeadm-config.yaml + 预拉镜像
阶段4 初始化:   首 master kubeadm init（imageRepository 指私有仓库）→ 写 kubeconfig
阶段5 CNI:     首 master kubectl apply -f <cni>.yaml（从离线包或内置模板）
阶段6 加入:     首 master 生成 join token/hash → 各 worker kubeadm join（多 master 追加 control-plane join）
阶段7 验证+接入: kubectl get nodes/pods -A 全 Ready → 采集 kubeconfig → 自动创建 DataSource(type=kubernetes)
```

### 13.5 敏感字段掩码规则（沿用第五章）

- `k8s_cluster_nodes.password`：后端详情返回 `***` + `has_password`，前端编辑置空、保存空值=不更新
- `k8s_cluster_plans.kubeconfig`：列表页不返回；详情/成功后按需返回，前端下载/复制时再请求
- `join_token`：仅执行期临时写入，成功后清空

### 13.6 平台接入约定

- 部署成功自动在 `data_sources` 表创建一行 `type='kubernetes'` 记录，`name` = 集群名称，
  `auth_config['kubeconfig']` = 采集到的 kubeconfig，`enabled=true`，`endpoint` = 首 master `https://<ip>:6443`
- 该 DataSource 立即被 `k8s_monitor` / `k8s_resources` 消费（集群资源自动纳管）
