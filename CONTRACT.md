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
- 审批通过后：写入 knowledge_base，并根据 alert_id 或 source_data.incident_id（回查 IncidentAlert）建立 alert_kb_links 关联

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
| source_type | String(32) | "manual" | manual / auto |
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

#### 8.1.6 对象存储 / 其他

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

