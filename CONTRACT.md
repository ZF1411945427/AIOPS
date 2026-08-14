# AIOps 全库字段规范契约（Single Source of Truth）

> **所有数据库表、前后端代码的字段命名必须以本文件为准。**
> 新增/修改任何字段，必须先改本文件，再同步前后端代码。
> 最后更新: 2026-08-13

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
| 
equire_second_approval | Boolean | false | 高危操作是否需要二级审批 |
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
| 
isk_level | String(16) | "medium" | 动作风险等级 |
| mode | String(8) | "live" | 执行模式：dry_run / live |
| payload | Text | "{}" | 动作参数（JSON） |
| decision | String(16) | "allowed" | 决策：allowed / rejected / dry_run |
| 
eject_reason | String(255) | "" | 拒绝原因 |
| pproved_by | Integer | 0 | 审批人 ID |
| created_at | DateTime | now | |

### 9.4 约定

- 所有 JSON 字段用 Text 列存 JSON 字符串，后端提供 get_xxx() 解析方法
- 风险等级枚举：
ead_only < dvisory < medium < high < critical（只升不降）
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
| http_proxy | String(256) | "" | 在线部署代理 URL（如 `http://192.168.100.2:7897`），留空=不走代理 |
| https_proxy | String(256) | "" | HTTPS 代理 URL（留空=用 http_proxy） |
| no_proxy | String(512) | "127.0.0.1,localhost,.local" | 不走代理的地址列表 |
| nodes_json | Text | "[]" | 节点定义 JSON（见 13.3 节点对象结构） |
| status | String(32) | "draft" | draft/planned/running/succeeded/failed/rolled_back |
| current_step | Integer | 0 | 当前执行步骤序号（编排阶段） |
| logs_json | Text | "[]" | 执行日志事件列表（{ts,type,node,step,message}） |
| kubeconfig | Text | "" | **敏感：产出 kubeconfig 内容（后端列表不返回，详情按需返回）** |
| join_token | Text | "" | **敏感：worker 加入 token（临时，仅执行期写入）** |
| report_json | Text | "{}" | 部署报告（node 状态矩阵 + 关键信息） |
| untaint_master | Boolean | False | 部署后是否去除 master 节点污点（允许 Pod 调度到 master） |
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

---

## 第十四章：MCP 工具注册表装饰器元数据（2026-08-13 新增）

> `app/services/tool_registry.py` + `app/services/mcp_registry.MCPToolDef` 为工具注册提供横切装饰器链
> （对齐 Ongrid `tools/decorators`：audit / ratelimit / review_gate / timeout）。
> 装饰器只写函数属性 `_tool_*`，`@register_mcp_tool` 读取并落入 `MCPToolDef`；`call_mcp_tool` 统一强制执行。

### 14.1 MCPToolDef 元数据字段（内存态，非 DB 列）

| 字段名 | 类型 | 默认 | 说明 |
|--------|------|------|------|
| `timeout_seconds` | int \| None | None(=30s 默认) | 工具级超时；`call_mcp_tool` 用独立线程+独立 session 执行并在超时后返回 `timeout:true` 错误，防 Agent 卡死 |
| `ratelimit_per_minute` | int \| None | None(=不限) | 滑动窗口限流（进程内，按工具名隔离），超限返回 error |
| `audit_enabled` | bool | False | 每次调用写一条 `AuditLog`（method='TOOL'，action='tool_execute'，path='tool://<name>'） |
| `review_gate` | bool | False | 写操作审查门（write gate）：内部写工具本身 `expose_to_llm=False`，此标记供 reviewer 子代理二签 |

### 14.2 装饰器用法（与 @register_mcp_tool 等价，可在其下叠加）

```python
@register_mcp_tool(name="xxx", ...)          # 方式A：直接传参数
@tool_timeout(10)                            # 方式B：叠装饰器（在 @register_mcp_tool 之下）
@tool_ratelimit(120)
@tool_audit()
def xxx(db=None, user_id=None, **kwargs): ...
```

已应用示例（当前实际值）：`query_metrics`(10s,120/min)、`query_knowledge_rag`(45s,60/min)、
`propose_action`(10s,audit,review_gate)。

### 14.3 工具执行超时行为契约

- `call_mcp_tool(name, args, db, user_id, allow_internal, timeout_override)`
- 超时路径在**独立线程 + 独立 DB session** 内执行 handler（SQLAlchemy Session 非线程安全，禁止跨线程共享调用方 session）
- 超时返回 `{"status":"error","message":"...执行超时...", "timeout":true, "tool_name":name}`
- Agent 循环把 timeout error 当普通工具结果回灌 LLM，由 LLM 决定重试/放弃

---

## 第十五章：智能体工作流告警自动触发契约（2026-08-13 新增）

### 15.1 `agent_workflows` 触发字段

| 字段名 | 当前 | 类型 | 说明 |
|--------|------|------|------|
| `trigger_type` | 已有 | String(32) | `manual` / `alert_auto`（告警自动触发）/ `chat` / `scheduled` |
| `trigger_condition` | 已有 | Text(JSON) | 告警匹配条件，形如 `{"severity":"critical"}` 或 `{"metric_name":"cpu_usage"}`；空 `{}` = 匹配所有；支持 key：`severity`/`status`/`metric_name`/`rule_id`/`asset_id` |

### 15.2 触发行为

- `main.py background_loop` 周期调用 `agent_workflow_service.check_alert_triggers(db, lookback_minutes=10)`：
  - 查询 `trigger_type='alert_auto'` 且 `enabled=true` 的工作流
  - 匹配最近 10 分钟新告警（`Alert.created_at >= cutoff`，最多扫 200 条）
  - **防重复**：同一告警对同一工作流只触发一次（按 `AgentWorkflowRun.inputs.alert_id` 历史去重）
  - 触发时 `inputs={"alert_id": <id>, "alert": {id,rule_id,asset_id,metric_name,actual_value,severity,status,message,created_at}}`
    `trigger_source="alert"`、`triggered_by="system"`
- 触发后仍走 `start_workflow_run` 异步执行（后台线程独立 session），工作流节点照常 fan-out

### 15.3 并行 fan-out 与恢复

- 并发上限：`SystemConfig.key='workflow_max_concurrency'`（默认 4，范围 1~32）
- `_advance_run` 每轮取所有依赖已满足的 pending 节点，`ThreadPoolExecutor` 并发执行（每节点独立 session）
- 任一节点 `awaiting_confirm` → run 置 `awaiting_confirm` 暂停；确认后 `_advance_run` 续推
- 重启恢复：启动时 `agent_workflow_service.resume_unfinished_runs(db)` 扫描 `running`/`awaiting_confirm` 的 run 续跑
- ⚠️ 节点构造固定用 `AgentWorkflowNodeRun.run_config`（模型列名，勿用 `config`，历史 bug）

### 15.4 cron 定时触发（B3，2026-08-13 扩展）

| 字段名 | 约定 |
|--------|------|
| `trigger_type` | `cron`（定时调度） |
| `trigger_condition` | `{"cron": "<5字段cron表达式>"}`，如 `{"cron": "0 8 * * *"}`；支持 `cron_expr` 别名 |
| 触发源 | `AgentWorkflowRun.trigger_source="cron"`、`triggered_by="system"` |

- `main.py background_loop` 周期调用 `workflow_cron_scheduler.check_cron_triggers(db)`：
  - 遍历 `trigger_type='cron'` 且 `enabled=true` 的工作流
  - croniter 判定当前分钟命中；防重复：该工作流最后一次 cron run 的 `started_at >= 当前分钟` 则跳过
  - 非法表达式（<5 字段/空）跳过并 warning 日志
- `inputs` 取自 `trigger_condition.inputs`（可选），供节点模板引用
- API：`GET /agent-workflow/api/cron/next-runs`（未来计划）、`POST /agent-workflow/api/cron/preview`（body `{"cron":...}` 返回 5 次）

### 15.5 notify / agent 节点（B5，2026-08-13 扩展）

节点类型 `type` 新增 `notify`、`agent`（`NODE_EXECUTORS` 注册）。

**notify 节点 `node_data`:**

| 字段名 | 必填 | 说明 |
|--------|------|------|
| `channel` | ✅ | `NotificationChannel.name`（须 enabled） |
| `recipient` | | chat_id/群会话ID；缺省取 channel_config.chat_id |
| `title` / `content` | content 必填 | 支持 `{{ }}` Jinja 模板 |
| `fallback_channel` | | 主渠道失败时的备用渠道名 |

- 发送走 `im_chatops_service.reply_to_im(channel, chat_id, text)`（feishu/dingtalk/wecom webhook）
- 失败返回 `status=failed` + `error`（不中断进程）

**agent 节点 `node_data`:**

| 字段名 | 必填 | 说明 |
|--------|------|------|
| `sub_agent_name` | | 子代理名；空=自动路由（`route_sub_agent`） |
| `prompt` | ✅ | 任务文本，支持模板 |
| `max_tokens` | | 覆盖 Provider 配置 |

- 调用 `call_llm(provider, [system(子代理prompt), user(prompt)])`，输出 `{reply, sub_agent, system_prompt}`

## 第十六章：LLM Reviewer 写操作审查门契约（2026-08-13 新增）

### 16.1 判定规则

- 入口：`app/services/reviewer_agent.py` `should_review(tool_name)`，命中任一即审查：
  - 工具元数据 `review_gate=True`
  - 工具 `risk_level` 为 `high` / `critical`
- 审查时机：`confirm_pending_action`（agent_service）与 `confirm_workflow_node`（agent_workflow_service）在**用户确认后、执行前**调用 `review_action`
- 审查器输出 JSON：`{"verdict": "approve"|"reject", "confidence": 0-100, "reason": "中文理由", "suggestions": [...]}`
- `verdict=reject` → 阻断执行：PendingAction `status=failed`、工作流节点 `failed` 后 `_advance_run` 续推
- 无 LLM / 异常 → **fail-open 放行**（保可用），但 `error` 字段标记原因

### 16.2 `pending_actions` 新增字段

| 字段名 | 类型 | 说明 |
|--------|------|------|
| `review_result` | Text | LLM reviewer 二签结果 JSON（verdict/confidence/reason/suggestions）；空串=未审查 |

- 迁移：`app/main.py _MIGRATIONS['pending_actions']` 含 `review_result TEXT DEFAULT ''`，启动自动补列

### 16.3 工具元数据（A2 装饰器契约补充）

- `MCPToolDef` 增加 `review_gate` 字段；`propose_action` 已标记 `review_gate=True`
- 高危/写操作建议显式 `review_gate=True`（否则按 risk_level 自动命中）

## 第十七章：自动调查闭环契约（C1-C3，2026-08-13 新增）

### 17.1 触发策略（C1 worker）

- 入口：`app/services/auto_investigator.py` `auto_investigate_new_incidents`，注册于 `background_loop`（服务名 `auto_investigate`）
- 触发条件（全部满足才 spawn worker）：
  - `incidents.status = 'open'`
  - `incidents.severity in ('critical', 'high')`
  - `incidents.created_at` 在回溯窗口内（默认 30 分钟）
  - `incidents.ai_rca_at` 为空（防重复标记，spawn 前置位）
  - 无 `completed` 状态的 `investigation_reports`
- 手动触发：`POST /incidents/api/{incident_id}/investigate` → 异步 `run_investigation_async(incident_id, db=db)`，worker 沿用当前库模式

### 17.2 `investigation_reports` 表字段

| 字段名 | 类型 | 说明 |
|--------|------|------|
| `id` | Integer PK | 报告 ID |
| `incident_id` | FK→incidents | 关联故障单 |
| `alert_id` | FK→alerts | 可空，预留单告警调查 |
| `investigation_type` | String(32) | 默认 `root_cause` |
| `title` | String(256) | 报告标题（取 incident.title） |
| `status` | String(16) | `running` / `completed` / `failed`（三态） |
| `report_data` | Text(JSON) | 结构化报告：`summary` / `root_cause` / `root_causes` / `evidence` / `timeline` / `recommendations` / `risks` / `action_needed` |
| `report_md` | Text | 渲染后的 Markdown（IM/会话回写用） |
| `evidence_summary` | Text | 证据摘要（前 5 条 evidence_texts JSON） |
| `error_message` | Text | failed 时的错误原因 |
| `created_at` / `completed_at` | DateTime | 创建/完成时间 |

- 表由 `Base.metadata.create_all` 自动建（`InvestigationReport` 定义于 `app/models.py`），无需迁移条目

### 17.3 结构化报告 JSON 字段（C2 LLM 二次抽取）

- 来源：`rca_service.analyze_incident` 的 6 部分 Investigation Package（facts/timeline/candidate_causes/evidence/exclusions/next_steps）整理成 `evidence_package` 后交给二次 LLM
- LLM 输出严格 JSON：`summary`(String)、`root_cause`(Dict)、`root_causes`(List[Dict]：rank/asset/confidence/reason)、`evidence`(List[String])、`timeline`(String)、`recommendations`(List[Dict]：action/priority)、`risks`(List)、`action_needed`(Bool)
- 无 Provider / LLM 解析失败 → `_fallback_report` 降级（基于算法包，`_fallback` 字段标记原因），**不产生空壳报告**

### 17.4 回写通道（C3）

- 聊天会话：复用标题 `[自动调查] {incident.title}` 的 ChatSession（不存在则创建，归属 admin），写入 `message_type=analysis` 的 assistant 消息，正文为 `**自动调查报告（故障 #{id}）**\n\n{report_md}`
- IM 渠道：仅 `notification_channels.bidirectional=True AND enabled=True` 的渠道，取 `channel_config.chat_id`，调用 `im_chatops_service.reply_to_im(channel, chat_id, report_md[:3900])`；无 chat_id 跳过、发送失败仅记日志不影响主流程

### 17.5 对外 API

| 方法 | 路径 | 说明 |
|------|------|------|
| GET | `/incidents/api/reports/investigation?incident_id=&limit=` | 报告列表 |
| GET | `/incidents/api/reports/investigation/{report_id}` | 报告详情（含完整 report_data/report_md） |
| POST | `/incidents/api/{incident_id}/investigate` | 手动触发异步调查 |

---

## 第十八章：凭据保险库（Secrets Vault）契约

> 2026-08-13 新增（F3）。集中加密存储连接凭据，数据源/连接配置只存 `{{secret:name}}` 引用，运行时才解密注入。

### 18.1 表 `secret_vaults`（`SecretVault` 模型，create_all 自动建）

| 列名 | 类型 | 说明 |
|------|------|------|
| id | Integer PK | 自增 |
| name | String(128) unique | 引用名（`{{secret:<name>}}` 中的 name），不允许含 `{`/`}`/空白 |
| description | String(256) | 用途说明 |
| value_type | String(32) | `password`/`token`/`api_key`/`private_key`/`custom` |
| scope | String(64) | `global`/`data_source`/`asset`（默认 `global`，仅作分组语义，不做硬约束） |
| secret_value_encrypted | Text | **Fernet 加密密文**（`VAULT_ENCRYPT_SEED` 派生 key），绝不存明文 |
| created_by | Integer nullable | 创建人 user_id |
| created_at / updated_at | DateTime | 时间戳 |

### 18.2 加密与掩码规范

- 加密复用 AIProvider 的 Fernet 方案：`base64.urlsafe_b64encode(sha256(VAULT_ENCRYPT_SEED).digest())`，新增 `app/config.py` 的 `VAULT_ENCRYPT_SEED`（环境变量 `AIOPS_VAULT_SEED`）
- 列表/详情接口**一律返回掩码值**：`value_masked = "***"` + `has_value` 布尔标记；解密只在服务内部（引用注入、`/resolve` 测试接口）
- 创建/更新接口 `secret_value` 为空 ⇒ 不更新密文（沿用 第五章 空值=不更新 规则）

### 18.3 引用注入规范（DataSource `auth_config` 集成）

- 格式：`{{secret:<name>}}`，可出现在 `auth_config` JSON 的任意字段值（含 ssh_password/k8s_token/db_password 等敏感字段），也支持嵌套进字符串（如 URL 内）
- 解析时机：**使用点**（`datasource_service.test_source` / `scrape_source` 各分支解析 `auth_config` 之后），由 `secret_vault.resolve_secret_refs(cfg, db)` 递归替换
- 未找到引用名 ⇒ 保留原占位符不动，调用方照常使用（fail-open，避免连接报错信息泄露）
- `_SENSITIVE_AUTH_KEYS` 掩码规则不变：`auth_config` 中存的是 `{{secret:name}}` 引用而非真实值，前端显示 `***` 天然成立；保存时合并逻辑（空值=不更新）对引用字符串同样适用

### 18.4 对外 API

| 方法 | 路径 | 说明 |
|------|------|------|
| GET | `/api/vault/secrets` | 凭据列表（掩码 + has_value） |
| POST | `/api/vault/secrets` | 创建（name/description/value_type/scope/secret_value） |
| PUT | `/api/vault/secrets/{id}` | 更新（secret_value 空 = 不更新） |
| DELETE | `/api/vault/secrets/{id}` | 删除 |
| GET | `/api/vault/secrets/{id}` | 详情（掩码） |
| POST | `/api/vault/secrets/resolve` | 测试引用解析：传入任意 dict/str，返回替换后的结果 |
| GET | `/api/vault/references` | 扫描 `data_sources.auth_config` 中所有 `{{secret:name}}` 引用（含失效引用标记） |

---

## 第十九章：技能体系（SKILL.md + 注册表 + 市场）契约

> 2026-08-13 新增（F1/F2）。技能 = 可执行的 SKILL.md 指令集（frontmatter 元数据 + Markdown 指令正文），加载进注册表后可被 Agent 通过 MCP 工具调用；市场做 zip 打包私服分发。

### 19.1 SKILL.md 规范

- 存放目录：内置技能 `skills/<name>/SKILL.md`（随仓库分发）；导入/市场技能入库（`skills` 表），不落盘
- frontmatter（YAML，`---` 包裹，必须字段 `name`）：`name`、`description`、`version`、`author`、`license`、`category`、`risk_level`(`read_only`/`interactive`/`danger`)、`keywords`(JSON list)、`tools_required`(JSON list，声明依赖的 MCP 工具名)
- 正文 = Markdown 操作指令，供 LLM 阅读后按步骤执行（配合 `tools_required` 调工具）
- 解析失败 / 缺 `name` ⇒ 跳过该技能并记日志，不影响其他技能加载

### 19.2 表 `skills`（`Skill` 模型，create_all 自动建）

| 列名 | 类型 | 说明 |
|------|------|------|
| id | Integer PK | 自增 |
| name | String(128) unique | 技能名（frontmatter.name），`use_skill` 的入参名 |
| description | String(512) | frontmatter.description |
| version / author / license | String | 版本 / 作者 / 许可 |
| category | String(64) | 分类（diagnosis/remediation/inspection/…） |
| risk_level | String(32) | `read_only` / `interactive` / `danger` |
| keywords | Text | JSON list |
| tools_required | Text | JSON list（依赖 MCP 工具名） |
| content | Text | SKILL.md 全文（frontmatter + 正文） |
| source | String(32) | `builtin`(skills/ 目录) / `upload`(JSON 安装) / `marketplace`(zip 导入) / `remote`(远程 GitHub 仓库安装) |
| file_path | String(512) | builtin 相对路径，其余为空 |
| enabled | Boolean | 默认 True；false 时不出现在 Agent 工具清单 |
| usage_count | Integer | 被 `use_skill` 调用次数（审计计数） |
| created_by / created_at / updated_at | | 创建人 / 时间戳 |

### 19.3 表 `skill_executions`（`SkillExecution` 模型，create_all 自动建）

| 列名 | 类型 | 说明 |
|------|------|------|
| id | Integer PK | 自增 |
| skill_id | Integer | 关联 skills.id |
| skill_name | String(128) | 冗余技能名 |
| tool | String(64) | 触发来源：`use_skill`(Agent) / `manual`(页面按钮) |
| status | String(16) | `success` / `failed` |
| input_summary | Text | 入参摘要（截断 500） |
| output_summary | Text | 输出摘要（截断 2000） |
| duration_ms | Integer | 执行耗时 |
| executed_by | Integer nullable | 用户 id（manual 时有值） |
| created_at | DateTime | 执行时间 |

### 19.4 注册表 / Agent 集成

- `app/services/skill_registry.py`：`scan_builtin_skills(db)` 启动时扫描 `skills/**/SKILL.md` 增量入库（已有 name 不覆盖）；`list_skills`/`get_skill`/`create_skill`/`update_skill`/`delete_skill`/`record_execution`/`list_executions`/`export_package`(zip)/`import_package`(zip)
- 内置技能「卸载」= 置 `enabled=False`（删除后重启会被 scan 重新加入）；导入/市场技能删除直接删行
- MCP 工具（注册于 `skill_mcp_tools.py`，随 mcp_tools 导入生效）：
  - `list_skills`(read_only)：列出所有 enabled 技能（name/description/category）
  - `use_skill`(read_only)：入参 `name`+`input`，返回 SKILL.md 指令正文供 LLM 执行；每次调用记录 `skill_executions` 审计 + `skills.usage_count+1`；技能不存在/已禁用返回错误
- 市场 `app/routers/marketplace.py` + `marketplace/packages/*.zip` 私服目录：publish(库→zip)/install(zip→库)/list/delete；zip 内为单个 `SKILL.md`（frontmatter 即 manifest）

### 19.5 对外 API

| 方法 | 路径 | 说明 |
|------|------|------|
| GET | `/api/skills` | 技能列表（?keyword=） |
| GET | `/api/skills/{id}` | 详情（含 content） |
| POST | `/api/skills` | 创建/安装（JSON 含 content） |
| PUT | `/api/skills/{id}` | 更新（enabled/description/…） |
| DELETE | `/api/skills/{id}` | 卸载（内置=禁用） |
| POST | `/api/skills/{id}/run` | 手动执行（写审计记录） |
| GET | `/api/skills/executions` | 执行审计列表 |
| GET | `/api/skills/{id}/export` | 导出技能包 zip |
| POST | `/api/skills/import` | 上传 zip 导入安装 |
| GET | `/api/marketplace/packages` | 市场包列表 |
| POST | `/api/marketplace/publish` | 发布技能到市场（{skill_id}） |
| POST | `/api/marketplace/install` | 从市场安装（{package}） |
| DELETE | `/api/marketplace/packages/{package}` | 删除市场包 |
| GET | `/api/marketplace/remote/presets` | 预设社区技能仓库（skills.sh 生态） |
| GET | `/api/marketplace/remote/repos/{owner}/{repo}/skills?branch=` | 列出远程仓库 skills/ 技能 |
| GET | `/api/marketplace/remote/repos/{owner}/{repo}/skills/{skill}` | 预览单个远程技能（元数据+正文） |
| POST | `/api/marketplace/remote/install` | 从远程仓库安装（{owner,repo,skill,branch?}），source=remote |
| GET | `/api/marketplace/remote/token` | 查询 GitHub Token 是否配置（返回值=***+has_value+source，不等明文） |
| POST | `/api/marketplace/remote/token` | 设置 GitHub Token（{token}；空=不修改；{clear:true}=清除） |

远程源 GitHub Token **系统层可配置**：存于 `SystemConfig` key=`github_api_token`（`system_configs`表），运行时由 `skill_remote.resolve_github_token` 解析（优先级：入参 > 系统配置 > 环境变量 `GITHUB_TOKEN`）。该 key 属于 `config_service.SENSITIVE_KEYS`，**通用配置列表 `get_all_configs` 完全跳过、不回显**（避免设置页全量回写 `***` 覆盖真实值）；仅技能市场页专用 token API（GET 查询/POST 设置/clear 清除）可读写。

---

## 第二十章：K8s 多集群 data plane + edge 升级协作器契约

> 2026-08-13 新增（F5）。对标 Ongrid `controller/node 双角色 + edge upgrade_job`（状态机+批次+回滚）。核心：① `k8s_clusters` 注册表把多个 K8s `DataSource(type='kubernetes')` 聚合成命名集群，各自独立 telemetry 通道；② `k8s_upgrade_jobs`+`k8s_upgrade_steps` 持久化升级协调器，批量滚动 edge 代理版本、逐批 verify、失败回滚。

### 20.1 表 `k8s_clusters`（`K8sCluster` 模型，create_all 自动建）

| 列名 | 类型 | 说明 |
|------|------|------|
| id | Integer PK | 自增 |
| name | String(128) unique | 集群名 |
| role | String(16) | `controller` / `node`（双角色） |
| datasource_id | Integer nullable | 关联 `data_sources.id`（type=kubernetes） |
| data_plane_status | String(16) | `active` / `standby` / `error`（独立遥测通道状态） |
| telemetry_channel | String(64) | 该集群独立 telemetry 通道名（默认 `<name>.telemetry`） |
| namespace_scope | String(128) | 命名空间范围（空=全集群） |
| target_version | String(32) | 升级目标 agent 版本 |
| agent_version | String(32) | 当前 agent 版本 |
| last_check_at | DateTime | 最近连通性检查 |
| created_at / updated_at | | 时间戳 |

### 20.2 表 `k8s_upgrade_jobs`（`K8sUpgradeJob`，create_all 自动建）

| 列名 | 类型 | 说明 |
|------|------|------|
| id | Integer PK | 自增 |
| name | String(128) | 升级任务名 |
| cluster_id | Integer nullable | 关联 k8s_clusters.id |
| from_version | String(32) | 当前版本 |
| to_version | String(32) | 目标版本 |
| status | String(24) | `pending`/`running`/`paused`/`completed`/`failed`/`rolled_back` |
| strategy | String(16) | `all_at_once` / `batch` |
| batch_size | Integer | 每批 agent 数（batch 策略） |
| overall_progress | Integer | 0-100 进度 |
| log_json | Text | 执行日志（JSON list） |
| created_by / created_at / updated_at | | 创建人/时间戳 |

### 20.3 表 `k8s_upgrade_steps`（`K8sUpgradeStep`，create_all 自动建）

| 列名 | 类型 | 说明 |
|------|------|------|
| id | Integer PK | 自增 |
| job_id | Integer | 关联 k8s_upgrade_jobs.id |
| step_order | Integer | 批内顺序 |
| batch_no | Integer | 批次号 |
| agent_id | String(64) | edge agent_id（edge_sessions.agent_id） |
| hostname | String(128) | 目标主机名 |
| action | String(16) | `upgrade` / `verify` / `rollback` |
| status | String(16) | `pending`/`running`/`success`/`failed`/`skipped` |
| output | Text | 执行输出 |
| duration_ms | Integer | 耗时 |
| created_at | DateTime | |

### 20.4 升级协调器语义
- 状态机：`pending → running →（逐批 running → completed）`；任一步升级失败 → 自动触发同批 `rollback` → `failed`；手动 pause 可中断。
- `verify`：升级某 agent 后对 `edge_sessions.agent_version` 断言 == `to_version`（失败视为该步失败）。
- 幂等续传：job/steps 全部落库，重启后按 status=running 的 job 可恢复（当前版本不自动续跑，提供查询+手动继续）。
- 内置角色语义：cluster.role=controller 的 agent 先升级（批次单独），再 node。

### 20.5 对外 API
| 方法 | 路径 | 说明 |
|------|------|------|
| GET | `/api/k8s-clusters` | 多集群列表（含独立遥测汇总） |
| POST | `/api/k8s-clusters` | 注册集群（name/role/datasource_id/...） |
| PUT | `/api/k8s-clusters/{id}` | 更新（role/data_plane_status/target_version/...） |
| DELETE | `/api/k8s-clusters/{id}` | 删除集群 |
| GET | `/api/k8s-clusters/{id}/telemetry` | 单集群独立 telemetry（events/资产汇总） |
| GET | `/api/upgrade-jobs` | 升级任务列表 |
| POST | `/api/upgrade-jobs` | 创建升级任务（to_version/strategy/batch_size/cluster_id/agent_id 列表） |
| GET | `/api/upgrade-jobs/{id}` | 任务详情（含 steps） |
| POST | `/api/upgrade-jobs/{id}/run` | 启动/继续执行（同步跑完批次，便于测试与查看） |
| POST | `/api/upgrade-jobs/{id}/pause` | 暂停 |
| DELETE | `/api/upgrade-jobs/{id}` | 删除任务 |

---

## 第二十一章：网络设备管理契约

> 2026-08-13 新增（F6）。对标 Ongrid 网络设备管理：SNMP 校验/邻居发现/接口轮询/主机-网络设备链路映射。SNMP 客户端为**纯 Python UDP 实现**（无外部依赖，支持 v1/v2c GET/WALK），并内置 **mock 模式**（`AIOPS_SNMP_MOCK=1` 或设备不可达时）用于开发/测试。

### 21.1 表 `network_devices`（`NetworkDevice`，create_all 自动建）

| 列名 | 类型 | 说明 |
|------|------|------|
| id | Integer PK | 自增 |
| asset_id | Integer nullable | 关联 assets.id（可选） |
| name | String(128) | 设备名 |
| ip | String(64) | 管理 IP |
| device_type | String(16) | `switch`/`router`/`firewall`/`ap`/`other` |
| vendor | String(64) | 厂商（sysObjectID 推断） |
| model | String(128) | 型号 |
| snmp_version | String(8) | `v1`/`v2c` |
| community | String(128) | read community |
| port | Integer | SNMP 端口（默认 161） |
| status | String(16) | `unreachable`/`ok`/`error` |
| last_poll_at | DateTime | 最近轮询 |
| created_by / created_at / updated_at | | |

### 21.2 表 `network_interfaces`（`NetworkInterface`，create_all 自动建）

| 列名 | 类型 | 说明 |
|------|------|------|
| id | Integer PK | 自增 |
| device_id | Integer | 关联 network_devices.id |
| if_index | Integer | ifIndex |
| name | String(64) | ifDescr |
| type | Integer | ifType |
| mac | String(32) | ifPhysAddress |
| admin_status | Integer | 1=up 2=down |
| oper_status | Integer | 1=up 2=down |
| speed | BigInt | ifSpeed |
| in_octets / out_octets | BigInt | 累计字节计数 |
| in_errors / out_errors | BigInt | 错误计数 |
| last_poll_at | DateTime | |

### 21.3 表 `network_neighbors`（`NetworkNeighbor`，create_all 自动建）

| 列名 | 类型 | 说明 |
|------|------|------|
| id | Integer PK | 自增 |
| device_id | Integer | 关联 network_devices.id |
| local_interface | String(64) | 本端接口 |
| neighbor_device | String(128) | 邻居设备名/IP |
| neighbor_port | String(64) | 邻居端口 |
| proto | String(8) | `lldp`/`cdp` |
| last_seen_at | DateTime | |

### 21.4 语义
- `validate_snmp`：完整连通校验（sysDescr/uptime），落 `status`。
- `poll_interfaces`：IF-MIB 轮询接口表，UDP+速率推算（前后两次 octets 差/时长），写 `network_interfaces`。
- `discover_neighbors`：LLDP-MIB（.1.0.8802.1.1.2）或 CDP（.1.3.6.1.4.1.9.9.23）邻居发现，写 `network_neighbors`。
- `map_host_links`：用 switch 邻居 + 主机 MAC（asset mac / 邻居表）反查主机→交换机端口映射。
- mock 模式：SNMP 不可达且 `AIOPS_SNMP_MOCK=1` 时生成确定性假数据，保证流程端到端可测。

### 21.5 对外 API
| 方法 | 路径 | 说明 |
|------|------|------|
| GET | `/api/network/devices` | 设备列表 |
| POST | `/api/network/devices` | 添加设备（name/ip/device_type/snmp_*） |
| GET | `/api/network/devices/{id}` | 设备详情（含接口/邻居） |
| PUT | `/api/network/devices/{id}` | 更新 |
| DELETE | `/api/network/devices/{id}` | 删除 |
| POST | `/api/network/devices/{id}/validate` | SNMP 连通校验 |
| POST | `/api/network/devices/{id}/discover` | 邻居发现 |
| POST | `/api/network/devices/{id}/poll` | 接口轮询 |
| POST | `/api/network/devices/map-links` | 主机-交换机端口映射（body: host_ip） |

---

## 第二十二章：类型化告警规则、外部 MCP、代码知识库、RCA 算法、可观测性 契约

> 2026-08-14 新增（G1 / P1-5 / P2-3 / P2-5 / P3-2 / D2 / D3 / G2 相关）。

### 22.1 告警规则类型化（G1）

- `alert_rules` 表新增两列（`_MIGRATIONS` 幂等 ALTER）：
  - `kind VARCHAR(24) DEFAULT 'metric_raw'`：`metric_raw` / `anomaly` / `forecast` / `burn_rate`
  - `config_json TEXT DEFAULT '{}'`：各 kind 参数（anomaly → z_score；forecast → horizon_points；burn_rate → window_hours/error_budget）
- 评估分发：`alert_service.check_rules` 对每条 rule 调 `_eval_rule_by_kind(rule, latest, db)`，返回 `(triggered, actual_value, message)`。
  - `metric_raw`：原静态阈值逻辑（condition+threshold）
  - `anomaly`：基线 mean±z·std，触发=当前值超基线（`z_score` 默认取自 threshold）
  - `forecast`：线性外推未来 `horizon_points` 点，投影值穿越阈值即触发
  - `burn_rate`：错误预算消耗速率 burn_rate = 消耗/(预算秒数)，触发=burn_rate 超 threshold 倍
- 规则 CRUD 增加 `kind`/`config_json` 透传与校验；列表返回 `kind`+`config`+`kinds`。
- 前端：AlertRulesView 表加「类型」列 + 表单 kind 下拉（四种）。

### 22.2 外部 MCP 服务器（P1-5）

- 表：`mcp_servers`（既有，空壳补齐）。新增 `app/services/mcp_external.py`：
  - `_rpc_call`：HTTP JSON-RPC（MCP `tools/list` / `tools/call`），支持 `auth_config.api_key`（Bearer），零外部依赖
  - `fetch_external_manifest(server)`：拉外部工具清单，工具名以 `<sever>:<tool>` 前缀隔离
  - `reload_external_tools(db)`：清空并重载所有启用外部工具到 `mcp_registry`（启动 + `/api/mcp/reload` 及 CRUD 后调用）
- `mcp_registry` 增加外部工具钩子：`_EXTERNAL_TOOLS`/`_EXTERNAL_TARGET`，`get_mcp_manifest()` 合并、`call_mcp_tool()` 未命中内置时回退外部。
- API：`/api/mcp`（CRUD + `/tools` + `/{id}/test` + `/reload`）。安全：外部工具默认 `risk_level=read_only` 只读视角，`api_key` 存 `auth_config` 掩码返回。

### 22.3 代码/git 知识库（P2-5）

- 表 `git_repos`：name(url 唯一)/url/branch/local_path/status(pending|cloning|ready|error)/file_count/last_sync_at/error_msg。
- 目录：`<PROJECT_ROOT>/repo_cache/<name>`（git clone --depth 1）。
- `git_knowledge_service.sync_repo`：clone/pull + 遍历可索引扩展名(.py/.js/.go/.md/... 跳过 .git/node_modules/dist)写入 `kb_documents`（`source_type="git"`，`file_path="__git__/<name>/<rel>"`），增量更新/删除失效文件。
- `search_code(query, repo, limit)`：对 ready 仓库内容 grep，返回 `{repo, path, line, snippet}`。
- API `/api/git-knowledge/*`：repos CRUD + `/sync` + `/search`。MCP 工具 `search_code`（read_only, category=knowledge）供 Agent 使用。

### 22.4 RCA 算法实装（P3-2，log_rca / idice）

- `app/services/rca_algos_service.py`：
  - `run_log_rca(db, asset_id, hours, keyword)`：基于指标 z 分异常 + 资产关系（`asset_relations.parent_id/child_id/relation_type`）产出异常指标/相关资产/根因假设/建议
  - `run_idice(db, asset_id, target_metric, hours)`：目标指标 vs 各候选指标皮尔逊相关 + 共同偏离 → 归因排序
- 路由：`GET /log-rca/analyze/{asset_id}`、`GET /idice/attribute/{asset_id}`（原纯 stub 已实装，status 返回 version=real）。

### 22.5 命令策略沙箱（P2-3）接线

- `evaluate_request(action_type, tool_name, asset_id, command, risk_level, session_id, user_id, role_id, db)` 已在 sandbox_service（全局开关关闭=放行，不改变现有行为）。
- 接线点：`script_exec.py` 执行前 + `mcp_tools.py` 的 `execute_run_command` / `execute_run_script`（沙盒异常不阻断，回归安全）。

### 22.6 可观测性（D2 / D3）

- `/healthz`、`/readyz` 已存在；新增 `GET /metrics`（Prometheus text/plain exposition，公开）：`aiops_healthz`、`aiops_mcp_tool_count`、`aiops_alert_rule_count`、`aiops_skill_count`、`aiops_network_device_count`、`aiops_app_up`、`aiops_db_alive`。
- 日志 trace_id：`logger.py` 格式含 `{extra[trace_id]}` + `AIOPS_LOG_JSON=1` 输出 JSON 行；`TraceIdMiddleware`（最外层）每个请求生成/透传 `x-request-id` 并 `logger.contextualize(trace_id=...)`，实现全链路串联。
- embedding（G2）：`embedding_service.py` 默认 `bge-m3` 本地 BGE-small-zh-v1.5（`models/bge-small-zh-v1.5`）离线可用，已满足对 ONNX 的目标（部署如需 ONNX 可另导出）。
