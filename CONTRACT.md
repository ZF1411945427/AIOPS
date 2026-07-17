# AIOps 全库字段规范契约（Single Source of Truth）

> **所有数据库表、前后端代码的字段命名必须以本文件为准。**
> 新增/修改任何字段，必须先改本文件，再同步前后端代码。
> 最后更新: 2026-07-15

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
