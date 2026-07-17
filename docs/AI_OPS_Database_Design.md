# AIOps 数据库设计文档

## 1. 总览

- **总计表数：** 108 张表
- **数据库：** SQLite（本地开发），生产环境可迁移至 PostgreSQL（pgvector 支持向量检索）
- **ORM：** SQLAlchemy（声明式基类 Base）
- **命名规范：** 见 CONTRACT.md（全库字段规范契约）
- **模型定义文件：** app/models.py（~1872 行，108 个模型类）

---

## 2. 表结构详表（按模块分组）

### 2.1 资产与配置管理

| # | 表名 | 列名 | 类型 | 约束 | 说明 |
|---|------|------|------|------|------|
| 1 | **assets** | id | Integer | PK, Index | 主键 |
|   | | name | String(128) | NOT NULL | 资产名称 |
|   | | ci_type | String(32) | default=server | CI 类型 |
|   | | parent_id | Integer | FK->assets.id, nullable | 父资产 ID |
|   | | ip | String(64) | default= | IP 地址 |
|   | | status | String(32) | default=offline | 资产状态 |
|   | | tags | String(256) | default= | 标签 |
|   | | ci_attributes | Text | default={} | CI 属性 JSON |
|   | | k8s_cluster | String(128) | default= | 所属 K8s 集群 |
|   | | connection_type | String(32) | default=ssh | 连接类型 |
|   | | connection_config | Text | default={} | 连接配置 JSON |
|   | | created_at | DateTime | default=now() | 创建时间 |
|   | | last_checked_at | DateTime | nullable | 最后检查时间 |
|   | | latency_ms | Integer | nullable | 延迟毫秒数 |
|   | | health_status | String(16) | default=green | 健康状态 |
| 2 | **asset_relations** | id | Integer | PK, Index | 主键 |
|   | | parent_id | Integer | FK->assets.id, NOT NULL | 父资产 ID |
|   | | child_id | Integer | FK->assets.id, NOT NULL | 子资产 ID |
|   | | relation_type | String(32) | default=depends_on | 关系类型 |
| 3 | **asset_lifecycles** | id | Integer | PK, Index | 主键 |
|   | | asset_id | Integer | FK->assets.id, NOT NULL | 资产 ID |
|   | | status | String(32) | default=provisioning | 状态 |
|   | | previous_status | String(32) | default= | 前状态 |
|   | | user_id | Integer | FK->users.id, nullable | 操作人 |
|   | | description | Text | default= | 描述 |
|   | | created_at | DateTime | default=now() | 创建时间 |
| 4 | **asset_change_logs** | id | Integer | PK, Index | 主键 |
|   | | asset_id | Integer | FK->assets.id, nullable | 资产 ID |
|   | | asset_name | String(256) | default= | 资产名称快照 |
|   | | field | String(64) | default= | 变更字段 |
|   | | old_value | Text | default= | 旧值 |
|   | | new_value | Text | default= | 新值 |
|   | | operator | String(64) | default=system | 操作人 |
|   | | created_at | DateTime | default=now() | 创建时间 |
| 5 | **ci_models** | id | Integer | PK, Index | 主键 |
|   | | name | String(64) | UNIQUE, NOT NULL | 模型名称 |
|   | | display_name | String(128) | default= | 显示名 |
|   | | description | Text | default= | 描述 |
|   | | parent_type | String(64) | nullable | 父类型 |
|   | | icon | String(32) | default= | 图标 |
|   | | created_at | DateTime | default=now() | 创建时间 |
| 6 | **ci_attributes** | id | Integer | PK, Index | 主键 |
|   | | ci_model_id | Integer | FK->ci_models.id, NOT NULL | CI 模型 ID |
|   | | name | String(64) | NOT NULL | 属性名 |
|   | | display_name | String(128) | default= | 显示名 |
|   | | field_type | String(32) | default=string | 字段类型 |
|   | | is_required | Boolean | default=False | 是否必填 |
|   | | default_value | String(256) | default= | 默认值 |
|   | | attr_options | Text | default= | 选项 JSON |
|   | | order | Integer | default=0 | 排序号 |
|   | | created_at | DateTime | default=now() | 创建时间 |
| 7 | **tag_categories** | id | Integer | PK, Index | 主键 |
|   | | name | String(64) | UNIQUE, NOT NULL | 分类标识 |
|   | | label | String(64) | NOT NULL | 显示标签 |
|   | | color | String(16) | default=#6366f1 | 颜色 |
|   | | icon | String(32) | default=tag | 图标 |
|   | | sort_order | Integer | default=0 | 排序号 |
| 8 | **tags** | id | Integer | PK, Index | 主键 |
|   | | name | String(128) | NOT NULL | 标签名 |
|   | | category_id | Integer | FK->tag_categories.id, nullable | 分类 |
|   | | color | String(16) | default=#6366f1 | 颜色 |
|   | | description | String(256) | default= | 描述 |
|   | | created_at | DateTime | default=now() | 创建时间 |
| 9 | **data_sources** | id | Integer | PK, Index | 主键 |
|   | | name | String(128) | NOT NULL | 数据源名 |
|   | | type | String(32) | NOT NULL | 数据源类型 |
|   | | endpoint | String(512) | default= | 端点 |
|   | | auth_type | String(32) | default=none | 认证类型 |
|   | | auth_config | Text | default= | 认证配置 |
|   | | scrape_interval | Integer | default=30 | 采集间隔(秒) |
|   | | mapping_config | Text | default={} | 映射配置 |
|   | | enabled | Boolean | default=True | 是否启用 |
|   | | last_status | String(32) | default=unknown | 最后一次状态 |
|   | | last_error | Text | default= | 最后一次错误 |
|   | | last_scraped_at | DateTime | nullable | 最后采集时间 |
|   | | created_at | DateTime | default=now() | 创建时间 |
| 10 | **discovery_schedules** | id | Integer | PK, Index | 主键 |
|   | | name | String(128) | NOT NULL | 调度名 |
|   | | protocol | String(16) | default=ssh | 协议 |
|   | | target_range | String(256) | default= | 目标范围 |
|   | | port | Integer | default=22 | 端口 |
|   | | credential_id | Integer | nullable | 凭据 ID |
|   | | schedule_cron | String(64) | default=0 2 * * * | cron 表达式 |
|   | | enabled | Boolean | default=True | 是否启用 |
|   | | created_at | DateTime | default=now() | 创建时间 |
| 11 | **discovery_jobs** | id | Integer | PK, Index | 主键 |
|   | | name | String(128) | - | 任务名 |
|   | | job_type | String(32) | default=ssh | 任务类型 |
|   | | target | String(256) | - | 目标 |
|   | | job_config | Text | default={} | 任务配置 |
|   | | status | String(32) | default=pending | 状态 |
|   | | result_summary | Text | default= | 结果摘要 |
|   | | created_at | DateTime | default=now() | 创建时间 |
|   | | finished_at | DateTime | nullable | 完成时间 |
| 12 | **discovery_results** | id | Integer | PK, Index | 主键 |
|   | | schedule_id | Integer | FK->discovery_schedules.id, nullable, Index | 调度 ID |
|   | | ip | String(64) | NOT NULL | IP |
|   | | hostname | String(128) | default= | 主机名 |
|   | | port | Integer | default=0 | 端口 |
|   | | status | String(16) | default=discovered | 状态 |
|   | | asset_id | Integer | FK->assets.id, nullable, Index | 关联资产 |
|   | | os_type | String(32) | default= | 操作系统 |
|   | | services | Text | default= | 服务列表 |
|   | | raw_output | Text | default= | 原始输出 |
|   | | discovered_at | DateTime | default=now() | 发现时间 |
| 13 | **ext_cmdb_configs** | id | Integer | PK, Index | 主键 |
|   | | name | String(128) | - | 配置名 |
|   | | cmdb_type | String(32) | default=generic | CMDB 类型 |
|   | | api_url | String(512) | - | API URL |
|   | | auth_config | Text | default={} | 认证配置 |
|   | | sync_interval | Integer | default=60 | 同步间隔(分) |
|   | | last_synced_at | DateTime | nullable | 最后同步时间 |
|   | | enabled | Boolean | default=False | 是否启用 |
|   | | created_at | DateTime | default=now() | 创建时间 |
| 14 | **metric_records** | id | Integer | PK, Index | 主键 |
|   | | asset_id | Integer | FK->assets.id, nullable | 资产 ID |
|   | | name | String(64) | NOT NULL | 指标名 |
|   | | value | Float | NOT NULL | 值 |
|   | | unit | String(32) | default=% | 单位 |
|   | | labels | Text | default={} | 标签 JSON |
|   | | timestamp | DateTime | default=now() | 时间戳 |
| 15 | **metric_templates** | id | Integer | PK, Index | 主键 |
|   | | ci_type | String(32) | NOT NULL, Index | CI 类型 |
|   | | metric_key | String(64) | NOT NULL | 指标键 |
|   | | metric_name | String(128) | NOT NULL | 指标名 |
|   | | category | String(32) | default=performance | 分类 |
|   | | unit | String(32) | default= | 单位 |
|   | | description | String(256) | default= | 描述 |
|   | | collect_method | String(32) | default=ssh | 采集方法 |
|   | | collect_command | String(512) | default= | 采集命令 |
|   | | default_threshold_warn | Float | nullable | 默认警告阈值 |
|   | | default_threshold_critical | Float | nullable | 默认严重阈值 |
|   | | sort_order | Integer | default=0 | 排序号 |
|   | | enabled | Boolean | default=True | 是否启用 |
|   | | created_at | DateTime | default=now() | 创建时间 |
| 16 | **asset_metric_recommendations** | id | Integer | PK, Index | 主键 |
|   | | asset_id | Integer | FK->assets.id, NOT NULL, Index | 资产 ID |
|   | | metric_key | String(64) | NOT NULL | 指标键 |
|   | | metric_name | String(128) | default= | 指标名 |
|   | | category | String(32) | default= | 分类 |
|   | | unit | String(32) | default= | 单位 |
|   | | source | String(16) | default=template | 来源 |
|   | | status | String(16) | default=recommended | 状态 |
|   | | reason | Text | default= | 原因 |
|   | | created_at | DateTime | default=now() | 创建时间 |
| 17 | **feature_store_items** | id | Integer | PK, Index | 主键 |
|   | | feature_name | String(128) | Index | 特征名 |
|   | | entity_type | String(64) | default=asset | 实体类型 |
|   | | entity_id | Integer | default=0 | 实体 ID |
|   | | feature_value | Float | default=0.0 | 特征值 |
|   | | feature_json | Text | default={} | 特征 JSON |
|   | | source | String(64) | default=manual | 来源 |
|   | | created_at | DateTime | default=now() | 创建时间 |

### 2.2 监控与告警

| # | 表名 | 列名 | 类型 | 约束 | 说明 |
|---|------|------|------|------|------|
| 18 | **alert_rules** | id | Integer | PK, Index | 主键 |
|   | | name | String(128) | NOT NULL | 规则名 |
|   | | metric_name | String(64) | NOT NULL | 指标名 |
|   | | condition | String(8) | NOT NULL | 条件(>/<) |
|   | | threshold | Float | NOT NULL | 阈值 |
|   | | severity | String(32) | default=warning | 严重级别 |
|   | | enabled | Boolean | default=True | 是否启用 |
|   | | created_at | DateTime | default=now() | 创建时间 |
| 19 | **alerts** | id | Integer | PK, Index | 主键 |
|   | | rule_id | Integer | FK->alert_rules.id, nullable | 规则 ID |
|   | | asset_id | Integer | FK->assets.id, nullable | 资产 ID |
|   | | metric_name | String(64) | NOT NULL | 指标名 |
|   | | actual_value | Float | NOT NULL | 实际值 |
|   | | threshold | Float | NOT NULL | 阈值 |
|   | | severity | String(32) | NOT NULL | 严重级别 |
|   | | status | String(32) | default=triggered | 告警状态 |
|   | | message | Text | default= | 告警消息 |
|   | | created_at | DateTime | default=now() | 触发时间 |
|   | | resolved_at | DateTime | nullable | 解决时间 |
| 20 | **alert_silences** | id | Integer | PK, Index | 主键 |
|   | | rule_id | Integer | FK->alert_rules.id, NOT NULL | 规则 ID |
|   | | expires_at | DateTime | NOT NULL | 过期时间 |
|   | | reason | String(256) | default= | 原因 |
|   | | created_at | DateTime | default=now() | 创建时间 |
| 21 | **alert_silence_schedules** | id | Integer | PK, Index | 主键 |
|   | | rule_id | Integer | FK->alert_rules.id, nullable | 规则 ID |
|   | | metric_name | String(64) | default= | 指标名 |
|   | | asset_id | Integer | nullable | 资产 ID |
|   | | cron_expr | String(64) | default=0 2 * * 0 | cron 表达式 |
|   | | duration_minutes | Integer | default=120 | 静默时长(分) |
|   | | reason | String(256) | default= | 原因 |
|   | | enabled | Boolean | default=True | 是否启用 |
|   | | created_at | DateTime | default=now() | 创建时间 |
| 22 | **alert_suppressions** | id | Integer | PK, Index | 主键 |
|   | | rule_id | Integer | FK->alert_rules.id, nullable | 规则 ID |
|   | | rule_name | String(128) | default= | 规则名快照 |
|   | | metric_name | String(64) | default= | 指标名 |
|   | | asset_id | Integer | nullable | 资产 ID |
|   | | suppressed_count | Integer | default=1 | 抑制次数 |
|   | | reason | String(64) | default=dedup | 原因 |
|   | | created_at | DateTime | default=now() | 创建时间 |
| 23 | **alert_escalations** | id | Integer | PK, Index | 主键 |
|   | | alert_id | Integer | FK->alerts.id, NOT NULL | 告警 ID |
|   | | from_severity | String(32) | NOT NULL | 原始级别 |
|   | | to_severity | String(32) | NOT NULL | 升级后级别 |
|   | | reason | String(256) | default= | 原因 |
|   | | created_at | DateTime | default=now() | 创建时间 |
| 24 | **alert_webhooks** | id | Integer | PK, Index | 主键 |
|   | | name | String(128) | NOT NULL | Webhook 名 |
|   | | url | String(512) | NOT NULL | URL |
|   | | secret | String(128) | default= | 密钥 |
|   | | retry_count | Integer | default=3 | 重试次数 |
|   | | timeout | Integer | default=10 | 超时(秒) |
|   | | enabled | Boolean | default=True | 是否启用 |
|   | | created_at | DateTime | default=now() | 创建时间 |
| 25 | **notification_channels** | id | Integer | PK, Index | 主键 |
|   | | name | String(64) | NOT NULL | 渠道名 |
|   | | type | String(32) | NOT NULL | 渠道类型 |
|   | | channel_config | Text | default= | 渠道配置 |
|   | | enabled | Boolean | default=True | 是否启用 |
|   | | created_at | DateTime | default=now() | 创建时间 |
| 26 | **notification_logs** | id | Integer | PK, Index | 主键 |
|   | | alert_id | Integer | FK->alerts.id, nullable | 告警 ID |
|   | | channel_id | Integer | FK->notification_channels.id, nullable | 渠道 ID |
|   | | channel_type | String(32) | NOT NULL | 渠道类型 |
|   | | recipient | String(256) | default= | 接收人 |
|   | | title | String(256) | default= | 标题 |
|   | | notification_content | Text | default= | 通知内容 |
|   | | is_success | Boolean | default=False | 是否成功 |
|   | | error_message | Text | default= | 错误信息 |
|   | | created_at | DateTime | default=now() | 创建时间 |
| 27 | **notification_templates** | id | Integer | PK, Index | 主键 |
|   | | name | String(128) | NOT NULL | 模板名 |
|   | | channel_type | String(32) | default= | 渠道类型 |
|   | | title_template | Text | default= | 标题模板 |
|   | | body_template | Text | default= | 正文模板 |
|   | | severity | String(32) | default=warning | 严重级别 |
|   | | enabled | Boolean | default=True | 是否启用 |
|   | | created_at | DateTime | default=now() | 创建时间 |
| 28 | **anomaly_configs** | id | Integer | PK, Index | 主键 |
|   | | name | String(128) | NOT NULL | 配置名 |
|   | | metric_name | String(64) | NOT NULL | 指标名 |
|   | | asset_id | Integer | nullable | 资产 ID |
|   | | algorithm | String(32) | default=sigma | 算法 |
|   | | sensitivity | Float | default=3.0 | 敏感度 |
|   | | window_size | Integer | default=20 | 窗口大小 |
|   | | period | Integer | default=12 | 周期 |
|   | | enabled | Boolean | default=True | 是否启用 |
|   | | created_at | DateTime | default=now() | 创建时间 |
| 29 | **log_anomaly_rules** | id | Integer | PK, Index | 主键 |
|   | | name | String(128) | NOT NULL | 规则名 |
|   | | source | String(32) | default=k8s | 日志源 |
|   | | keyword | String(256) | default= | 关键字 |
|   | | regex_pattern | String(512) | default= | 正则表达式 |
|   | | log_level | String(32) | default= | 日志级别 |
|   | | threshold | Integer | default=10 | 阈值 |
|   | | window_minutes | Integer | default=5 | 时间窗口(分) |
|   | | severity | String(32) | default=warning | 严重级别 |
|   | | enabled | Boolean | default=True | 是否启用 |
|   | | created_at | DateTime | default=now() | 创建时间 |
| 30 | **hotspot_analyses** | id | Integer | PK, Index | 主键 |
|   | | metric_name | String(64) | NOT NULL | 指标名 |
|   | | dimension | String(64) | default= | 维度 |
|   | | dimension_value | String(128) | default= | 维度值 |
|   | | contribution | Float | default=0.0 | 贡献度 |
|   | | baseline | Float | default=0.0 | 基线值 |
|   | | current | Float | default=0.0 | 当前值 |
|   | | change_pct | Float | default=0.0 | 变化百分比 |
|   | | created_at | DateTime | default=now() | 创建时间 |
| 31 | **anomaly_benchmarks** | id | Integer | PK, Index | 主键 |
|   | | asset_id | Integer | FK->assets.id, nullable, Index | 资产 ID |
|   | | metric_name | String(64) | NOT NULL | 指标名 |
|   | | algorithm | String(32) | default= | 算法 |
|   | | window_minutes | Integer | default=60 | 窗口(分) |
|   | | precision | Float | default=0.0 | 精确率 |
|   | | recall | Float | default=0.0 | 召回率 |
|   | | f1_score | Float | default=0.0 | F1 分数 |
|   | | threshold | Float | default=0.0 | 最佳阈值 |
|   | | labeled_at | DateTime | nullable | 标注时间 |
|   | | created_at | DateTime | default=now() | 创建时间 |

### 2.3 混沌工程

| # | 表名 | 列名 | 类型 | 约束 | 说明 |
|---|------|------|------|------|------|
| 32 | **chaos_experiments** | id | Integer | PK, Index | 主键 |
|   | | name | String(128) | NOT NULL | 实验名 |
|   | | description | Text | default= | 描述 |
|   | | target_type | String(32) | default=pod | 目标类型 |
|   | | target_layer | String(32) | default=host | 目标层次 |
|   | | target_selector | Text | default={} | 目标选择器 |
|   | | fault_type | String(64) | NOT NULL | 故障类型 |
|   | | fault_params | Text | default={} | 故障参数 |
|   | | steady_state | Text | default={} | 稳态定义 |
|   | | status | String(32) | default=pending | 实验状态 |
|   | | result | String(32) | default= | 实验结果 |
|   | | started_at | DateTime | nullable | 开始时间 |
|   | | finished_at | DateTime | nullable | 结束时间 |
|   | | created_at | DateTime | default=now() | 创建时间 |
| 33 | **chaos_runs** | id | Integer | PK, Index | 主键 |
|   | | experiment_id | Integer | FK->chaos_experiments.id, NOT NULL | 实验 ID |
|   | | is_steady_state_passed | Boolean | default=False | 稳态是否通过 |
|   | | is_auto_recovered | Boolean | default=False | 是否自动恢复 |
|   | | alerts_triggered | Integer | default=0 | 触发告警数 |
|   | | error_budget_impact | Float | default=0.0 | 错误预算影响 |
|   | | duration_seconds | Integer | default=0 | 持续秒数 |
|   | | steady_state_before | Text | default={} | 实验前稳态 |
|   | | steady_state_after | Text | default={} | 实验后稳态 |
|   | | description | Text | default= | 描述 |
|   | | started_at | DateTime | default=now() | 开始时间 |
| 34 | **chaos_scenarios** | id | Integer | PK, Index | 主键 |
|   | | name | String(128) | NOT NULL | 场景名 |
|   | | description | Text | default= | 描述 |
|   | | category | String(32) | default=pod | 分类 |
|   | | target_layer | String(32) | default=host | 目标层次 |
|   | | fault_type | String(64) | NOT NULL | 故障类型 |
|   | | fault_params | Text | default={} | 故障参数 |
|   | | risk_level | String(16) | default=low | 风险等级 |
|   | | recommended_slo | String(128) | default= | 推荐 SLO |
|   | | is_builtin | Boolean | default=False | 是否内置 |
|   | | created_at | DateTime | default=now() | 创建时间 |

### 2.4 告警协同与事件管理

| # | 表名 | 列名 | 类型 | 约束 | 说明 |
|---|------|------|------|------|------|
| 35 | **incidents** | id | Integer | PK, Index | 主键 |
|   | | title | String(256) | NOT NULL | 事件标题 |
|   | | severity | String(32) | default=warning | 严重级别 |
|   | | status | String(32) | default=open | 状态 |
|   | | asset_id | Integer | FK->assets.id, nullable | 关联资产 |
|   | | alert_count | Integer | default=0 | 关联告警数 |
|   | | impact | String(32) | default=high | 影响范围 |
|   | | description | Text | default= | 描述 |
|   | | approver_id | Integer | FK->users.id, nullable | 审批人 |
|   | | review_comment | Text | default= | 审批意见 |
|   | | created_at | DateTime | default=now() | 创建时间 |
|   | | resolved_at | DateTime | nullable | 解决时间 |
| 36 | **incident_alerts** | id | Integer | PK, Index | 主键 |
|   | | incident_id | Integer | FK->incidents.id, NOT NULL | 事件 ID |
|   | | alert_id | Integer | FK->alerts.id, NOT NULL | 告警 ID |
| 37 | **incident_approvals** | id | Integer | PK, Index | 主键 |
|   | | incident_id | Integer | FK->incidents.id, NOT NULL | 事件 ID |
|   | | approver_id | Integer | FK->users.id, nullable | 审批人 |
|   | | action | String(32) | NOT NULL | 动作(submit/approve/reject) |
|   | | description | Text | default= | 描述 |
|   | | created_at | DateTime | default=now() | 创建时间 |
| 38 | **alert_kb_links** | id | Integer | PK, Index | 主键 |
|   | | alert_id | Integer | FK->alerts.id, NOT NULL | 告警 ID |
|   | | kb_id | Integer | FK->knowledge_base.id, NOT NULL | 知识库 ID |
| 39 | **alert_event_links** | id | Integer | PK, Index | 主键 |
|   | | alert_id | Integer | FK->alerts.id, NOT NULL | 告警 ID |
|   | | event_id | Integer | FK->k8s_events.id, NOT NULL | 事件 ID |
|   | | relation | String(32) | default=triggered_by | 关系类型 |
|   | | created_at | DateTime | default=now() | 创建时间 |
| 40 | **alert_session_links** | id | Integer | PK, Index | 主键 |
|   | | alert_id | Integer | FK->alerts.id, NOT NULL | 告警 ID |
|   | | session_id | Integer | FK->chat_sessions.id, NOT NULL | 会话 ID |
|   | | context_summary | Text | default= | 上下文摘要 |
|   | | created_at | DateTime | default=now() | 创建时间 |
| 41 | **asset_session_links** | id | Integer | PK, Index | 主键 |
|   | | asset_id | Integer | FK->assets.id, NOT NULL | 资产 ID |
|   | | session_id | Integer | FK->chat_sessions.id, NOT NULL | 会话 ID |
|   | | context_summary | Text | default= | 上下文摘要 |
|   | | created_at | DateTime | default=now() | 创建时间 |

### 2.5 SRE 与 OnCall

| # | 表名 | 列名 | 类型 | 约束 | 说明 |
|---|------|------|------|------|------|
| 42 | **slo_configs** | id | Integer | PK | 主键 |
|   | | service_name | String(100) | NOT NULL | 服务名 |
|   | | slo_target | Float | NOT NULL | 目标可用性 |
|   | | window_days | Integer | default=30 | 窗口天数 |
|   | | total_requests | Integer | default=0 | 总请求数 |
|   | | error_requests | Integer | default=0 | 错误请求数 |
|   | | status | String(20) | default=healthy | 状态 |
|   | | created_by | String(50) | - | 创建人 |
|   | | created_at | DateTime | default=now() | 创建时间 |
|   | | updated_at | DateTime | default=now(), onupdate | 更新时间 |
| 43 | **error_budgets** | id | Integer | PK | 主键 |
|   | | slo_id | Integer | FK->slo_configs.id | 关联 SLO |
|   | | service_name | String(100) | NOT NULL | 服务名 |
|   | | period_started_at | DateTime | - | 周期开始 |
|   | | period_ended_at | DateTime | - | 周期结束 |
|   | | budget_total | Float | default=100 | 总预算% |
|   | | budget_consumed | Float | default=0 | 已消耗% |
|   | | budget_remaining | Float | default=100 | 剩余% |
|   | | burn_rate | Float | default=0 | 消耗速率 |
|   | | status | String(20) | default=healthy | 状态 |
|   | | created_at | DateTime | default=now() | 创建时间 |
| 44 | **sla_records** | id | Integer | PK | 主键 |
|   | | service_name | String(100) | NOT NULL | 服务名 |
|   | | sla_target | Float | NOT NULL | SLA 目标 |
|   | | period_started_at | DateTime | - | 周期开始 |
|   | | period_ended_at | DateTime | - | 周期结束 |
|   | | uptime_seconds | Integer | default=0 | 运行时长(秒) |
|   | | downtime_seconds | Integer | default=0 | 停机时长(秒) |
|   | | achieved_sla | Float | default=0.0 | 实际 SLA |
|   | | penalty | String(50) | default=none | 处罚 |
|   | | status | String(20) | default=active | 状态 |
|   | | created_at | DateTime | default=now() | 创建时间 |
| 45 | **availability_reports** | id | Integer | PK | 主键 |
|   | | service_name | String(100) | NOT NULL | 服务名 |
|   | | reported_at | DateTime | - | 报告日期 |
|   | | total_uptime | Integer | default=0 | 总运行时间(秒) |
|   | | total_downtime | Integer | default=0 | 总停机时间(秒) |
|   | | availability_pct | Float | default=100.0 | 可用性百分比 |
|   | | incident_count | Integer | default=0 | 故障次数 |
|   | | total_duration | Integer | default=0 | 总时长(秒) |
|   | | created_at | DateTime | default=now() | 创建时间 |
| 46 | **oncall_schedules** | id | Integer | PK | 主键 |
|   | | team_name | String(50) | NOT NULL | 团队名 |
|   | | rotation_type | String(20) | default=weekly | 轮转类型 |
|   | | members | Text | - | 成员列表 JSON |
|   | | schedule | Text | - | 轮值表 JSON |
|   | | current_oncall | String(50) | - | 当前值班人 |
|   | | current_period_started_at | DateTime | - | 当前周期开始 |
|   | | current_period_ended_at | DateTime | - | 当前周期结束 |
|   | | is_auto_rotate | Boolean | default=True | 是否自动轮转 |
|   | | holidays | Text | default=[] | 节假日 JSON |
|   | | created_by | String(50) | - | 创建人 |
|   | | created_at | DateTime | default=now() | 创建时间 |
|   | | updated_at | DateTime | default=now(), onupdate | 更新时间 |
| 47 | **escalation_policies** | id | Integer | PK | 主键 |
|   | | name | String(100) | NOT NULL | 策略名 |
|   | | levels | Text | - | 升级级别 JSON |
|   | | wait_minutes | Text | - | 每级等待时间 JSON |
|   | | notify_channels | Text | - | 通知渠道 JSON |
|   | | is_active | Boolean | default=True | 是否启用 |
|   | | created_by | String(50) | - | 创建人 |
|   | | created_at | DateTime | default=now() | 创建时间 |
|   | | updated_at | DateTime | default=now(), onupdate | 更新时间 |
| 48 | **system_posture_records** | id | Integer | PK, Index | 主键 |
|   | | day | String(16) | NOT NULL, Index | 日期 |
|   | | system_key | String(64) | NOT NULL | 系统键 |
|   | | system_name | String(128) | default= | 系统名 |
|   | | environment | String(32) | default=prod | 环境 |
|   | | domain | String(64) | default= | 领域 |
|   | | status | String(16) | default=unknown | 状态 |
|   | | sla_value | Float | nullable | SLA 值 |
|   | | health_score | Integer | nullable | 健康分 |
|   | | alerts_count | Integer | default=0 | 告警数 |
|   | | incidents_count | Integer | default=0 | 事件数 |
|   | | created_at | DateTime | default=now() | 创建时间 |

### 2.6 AI 智能体

| # | 表名 | 列名 | 类型 | 约束 | 说明 |
|---|------|------|------|------|------|
| 49 | **ai_providers** | id | Integer | PK, Index | 主键 |
|   | | name | String(128) | UNIQUE, NOT NULL | 提供商名 |
|   | | provider_type | String(32) | default=openai_compatible | 提供商类型 |
|   | | base_url | String(255) | default= | 基础 URL |
|   | | api_key_encrypted | Text | default= | 加密 API Key |
|   | | default_model | String(128) | default= | 默认模型 |
|   | | temperature | Float | default=0.2 | 温度参数 |
|   | | max_tokens | Integer | default=10000 | 最大 Token 数 |
|   | | timeout_seconds | Integer | default=30 | 超时(秒) |
|   | | is_enabled | Boolean | default=True | 是否启用 |
|   | | created_at | DateTime | default=now() | 创建时间 |
|   | | updated_at | DateTime | default=now(), onupdate | 更新时间 |
| 50 | **agent_configs** | id | Integer | PK, Index | 主键 |
|   | | name | String(64) | UNIQUE, default=default | Agent 名 |
|   | | default_provider_id | Integer | FK->ai_providers.id, nullable | 默认提供商 |
|   | | system_prompt | Text | default= | 系统提示词 |
|   | | welcome_message | String(255) | default= | 欢迎语 |
|   | | suggested_questions | Text | default=[] | 建议问题 JSON |
|   | | is_enabled | Boolean | default=True | 是否启用 |
|   | | allow_action_execution | Boolean | default=True | 允许执行动作 |
|   | | require_confirmation | Boolean | default=True | 需要确认 |
|   | | max_history_messages | Integer | default=12 | 最大历史消息数 |
|   | | created_at | DateTime | default=now() | 创建时间 |
|   | | updated_at | DateTime | default=now(), onupdate | 更新时间 |
| 51 | **chat_sessions** | id | Integer | PK, Index | 主键 |
|   | | user_id | Integer | FK->users.id, NOT NULL | 用户 ID |
|   | | title | String(128) | default=新会话 | 标题 |
|   | | status | String(16) | default=active | 状态 |
|   | | context | Text | default={} | 上下文 JSON |
|   | | last_message_at | DateTime | default=now() | 最后消息时间 |
|   | | created_at | DateTime | default=now() | 创建时间 |
|   | | updated_at | DateTime | default=now(), onupdate | 更新时间 |
| 52 | **chat_messages** | id | Integer | PK, Index | 主键 |
|   | | session_id | Integer | FK->chat_sessions.id, NOT NULL | 会话 ID |
|   | | role | String(16) | NOT NULL | 角色(user/assistant/system) |
|   | | message_type | String(16) | default=text | 消息类型 |
|   | | message_content | Text | default= | 消息内容 |
|   | | citations | Text | default=[] | 引用 JSON |
|   | | tool_calls | Text | default=[] | 工具调用 JSON |
|   | | metadata_json | Text(metadata) | default={} | 元数据 JSON |
|   | | created_at | DateTime | default=now() | 创建时间 |
| 53 | **mcp_servers** | id | Integer | PK, Index | 主键 |
|   | | name | String(128) | UNIQUE, NOT NULL | MCP 服务名 |
|   | | server_type | String(16) | default=platform_builtin | 服务类型 |
|   | | endpoint | String(255) | default= | 端点 |
|   | | description | String(255) | default= | 描述 |
|   | | auth_config | Text | default={} | 认证配置 |
|   | | tool_whitelist | Text | default=[] | 工具白名单 |
|   | | is_builtin | Boolean | default=False | 是否内置 |
|   | | is_enabled | Boolean | default=True | 是否启用 |
|   | | created_at | DateTime | default=now() | 创建时间 |
|   | | updated_at | DateTime | default=now(), onupdate | 更新时间 |
| 54 | **pending_actions** | id | Integer | PK, Index | 主键 |
|   | | session_id | Integer | FK->chat_sessions.id, nullable | 会话 ID |
|   | | message_id | Integer | FK->chat_messages.id, nullable | 消息 ID |
|   | | run_id | Integer | nullable | 运行 ID |
|   | | node_run_id | Integer | nullable | 节点运行 ID |
|   | | action_type | String(64) | NOT NULL | 动作类型 |
|   | | title | String(128) | default= | 标题 |
|   | | risk_level | String(16) | default=low | 风险等级 |
|   | | reason | String(500) | nullable | 原因 |
|   | | status | String(16) | default=pending | 状态 |
|   | | action_payload | Text | default={} | 动作负载 |
|   | | result_payload | Text | default={} | 结果负载 |
|   | | confirmed_by | String(64) | default= | 确认人 |
|   | | confirmed_at | DateTime | nullable | 确认时间 |
|   | | created_at | DateTime | default=now() | 创建时间 |
|   | | updated_at | DateTime | default=now(), onupdate | 更新时间 |
| 55 | **tool_invocations** | id | Integer | PK, Index | 主键 |
|   | | session_id | Integer | FK->chat_sessions.id, NOT NULL | 会话 ID |
|   | | message_id | Integer | FK->chat_messages.id, nullable | 消息 ID |
|   | | tool_name | String(64) | NOT NULL | 工具名 |
|   | | status | String(16) | default=pending | 状态 |
|   | | latency_ms | Integer | default=0 | 延迟(毫秒) |
|   | | request_payload | Text | default={} | 请求负载 |
|   | | response_summary | Text | default={} | 响应摘要 |
|   | | created_at | DateTime | default=now() | 创建时间 |
| 56 | **background_jobs** | id | Integer | PK, Index | 主键 |
|   | | job_id | String(64) | UNIQUE, NOT NULL, Index | 任务 UUID |
|   | | action_type | String(64) | NOT NULL | 动作类型 |
|   | | title | String(128) | default= | 标题 |
|   | | status | String(16) | default=pending | 状态 |
|   | | progress | Integer | default=0 | 进度(0-100) |
|   | | progress_message | String(256) | default= | 步骤描述 |
|   | | result_payload | Text | default={} | 结果 JSON |
|   | | error_message | String(512) | default= | 错误信息 |
|   | | asset_id | Integer | FK->assets.id, nullable | 资产 ID |
|   | | session_id | Integer | FK->chat_sessions.id, nullable | 会话 ID |
|   | | pending_action_id | Integer | FK->pending_actions.id, nullable | 待确认动作 ID |
|   | | created_at | DateTime | default=now() | 创建时间 |
|   | | started_at | DateTime | nullable | 开始时间 |
|   | | finished_at | DateTime | nullable | 结束时间 |
| 57 | **agent_evaluations** | id | Integer | PK, Index | 主键 |
|   | | session_id | Integer | nullable, Index | 会话 ID |
|   | | provider_id | Integer | nullable, Index | 提供商 ID |
|   | | model_name | String(64) | default= | 模型名 |
|   | | task_type | String(32) | default=chat | 任务类型 |
|   | | prompt_tokens | Integer | default=0 | 提示 Token 数 |
|   | | completion_tokens | Integer | default=0 | 生成 Token 数 |
|   | | total_tokens | Integer | default=0 | 总 Token 数 |
|   | | latency_ms | Integer | default=0 | 延迟(毫秒) |
|   | | round_count | Integer | default=0 | 轮次数 |
|   | | tool_call_count | Integer | default=0 | 工具调用次数 |
|   | | is_success | Boolean | default=True | 是否成功 |
|   | | has_hallucination | Boolean | default=False | 是否存在幻觉 |
|   | | completion_rate | Float | default=1.0 | 完成率 |
|   | | feedback | String(16) | default= | 反馈 |
|   | | created_at | DateTime | default=now(), Index | 创建时间 |

### 2.7 自愈与自动化

| # | 表名 | 列名 | 类型 | 约束 | 说明 |
|---|------|------|------|------|------|
| 58 | **auto_remediations** | id | Integer | PK, Index | 主键 |
|   | | name | String(128) | NOT NULL | 规则名 |
|   | | rule_id | Integer | FK->alert_rules.id, nullable | 告警规则 ID |
|   | | action_type | String(32) | NOT NULL | 动作类型 |
|   | | remediation_params | Text | default= | 自愈参数 |
|   | | enabled | Boolean | default=True | 是否启用 |
|   | | created_at | DateTime | default=now() | 创建时间 |
| 59 | **remediation_logs** | id | Integer | PK, Index | 主键 |
|   | | remediation_id | Integer | FK->auto_remediations.id, nullable | 自愈规则 ID |
|   | | alert_id | Integer | FK->alerts.id, nullable | 告警 ID |
|   | | action_type | String(32) | NOT NULL | 动作类型 |
|   | | target | String(128) | default= | 目标 |
|   | | is_success | Boolean | default=False | 是否成功 |
|   | | output | Text | default= | 输出 |
|   | | created_at | DateTime | default=now() | 创建时间 |
| 60 | **remediation_effects** | id | Integer | PK, Index | 主键 |
|   | | remediation_id | Integer | FK->auto_remediations.id, nullable | 自愈规则 ID |
|   | | alert_id | Integer | FK->alerts.id, nullable | 告警 ID |
|   | | executed_at | DateTime | NOT NULL | 执行时间 |
|   | | check_at | DateTime | NOT NULL | 检查时间 |
|   | | alert_status_at_execute | String(32) | default=triggered | 执行时告警状态 |
|   | | alert_status_at_check | String(32) | default=unknown | 检查时告警状态 |
|   | | is_asset_recovered | Boolean | default=False | 资产是否恢复 |
|   | | is_alert_resolved | Boolean | default=False | 告警是否解决 |
|   | | recovery_time_seconds | Integer | default=0 | 恢复时间(秒) |
|   | | description | Text | default= | 描述 |
|   | | created_at | DateTime | default=now() | 创建时间 |
| 61 | **remediation_workflows** | id | Integer | PK, Index | 主键 |
|   | | name | String(128) | NOT NULL | 工作流名 |
|   | | rule_id | Integer | FK->alert_rules.id, nullable | 告警规则 ID |
|   | | steps | Text | default=[] | 步骤 JSON |
|   | | enabled | Boolean | default=True | 是否启用 |
|   | | created_at | DateTime | default=now() | 创建时间 |
| 62 | **remediation_effect_records** | id | Integer | PK, Index | 主键 |
|   | | remediation_id | Integer | FK->auto_remediations.id, nullable, Index | 自愈规则 ID |
|   | | log_id | Integer | FK->remediation_logs.id, nullable, Index | 自愈日志 ID |
|   | | alert_id | Integer | FK->alerts.id, nullable, Index | 告警 ID |
|   | | asset_id | Integer | FK->assets.id, nullable, Index | 资产 ID |
|   | | status_before | String(32) | default= | 处理前状态 |
|   | | status_after | String(32) | default= | 处理后状态 |
|   | | effect | String(16) | default= | 效果 |
|   | | checked_at | DateTime | nullable | 检查时间 |
|   | | description | Text | default= | 描述 |
|   | | created_at | DateTime | default=now() | 创建时间 |
| 63 | **ansible_inventories** | id | Integer | PK, Index | 主键 |
|   | | name | String(128) | UNIQUE, NOT NULL | 清单名 |
|   | | description | String(256) | default= | 描述 |
|   | | content | Text | default= | YAML 内容 |
|   | | created_at | DateTime | default=now() | 创建时间 |
|   | | updated_at | DateTime | default=now(), onupdate | 更新时间 |
| 64 | **ansible_playbooks** | id | Integer | PK, Index | 主键 |
|   | | name | String(128) | UNIQUE, NOT NULL | Playbook 名 |
|   | | description | String(256) | default= | 描述 |
|   | | content | Text | default= | YAML 内容 |
|   | | created_at | DateTime | default=now() | 创建时间 |
|   | | updated_at | DateTime | default=now(), onupdate | 更新时间 |
| 65 | **ansible_runs** | id | Integer | PK, Index | 主键 |
|   | | inventory_id | Integer | nullable | 清单 ID |
|   | | playbook_id | Integer | nullable | Playbook ID |
|   | | inventory_name | String(128) | default= | 清单名快照 |
|   | | playbook_name | String(128) | default= | Playbook 名快照 |
|   | | extra_vars | Text | default= | 额外变量 |
|   | | output | Text | default= | 输出 |
|   | | error | Text | default= | 错误 |
|   | | exit_code | Integer | default=0 | 退出码 |
|   | | status | String(32) | default=pending | 状态 |
|   | | created_at | DateTime | default=now() | 创建时间 |
|   | | finished_at | DateTime | nullable | 完成时间 |
| 66 | **script_tasks** | id | Integer | PK, Index | 主键 |
|   | | target_name | String(128) | - | 目标名 |
|   | | script_content | Text | - | 脚本内容 |
|   | | output | Text | default= | 输出 |
|   | | error | Text | default= | 错误 |
|   | | exit_code | Integer | default=0 | 退出码 |
|   | | created_at | DateTime | default=now() | 创建时间 |

### 2.8 工作流与 SOP

| # | 表名 | 列名 | 类型 | 约束 | 说明 |
|---|------|------|------|------|------|
| 67 | **workflow_templates** | id | Integer | PK, Index | 主键 |
|   | | name | String(128) | NOT NULL | 模板名 |
|   | | description | Text | default= | 描述 |
|   | | category | String(64) | default=generic | 分类 |
|   | | trigger_type | String(32) | default=manual | 触发类型 |
|   | | trigger_condition | Text | default= | 触发条件 |
|   | | nodes | Text | default=[] | DAG 节点 JSON |
|   | | edges | Text | default=[] | DAG 边 JSON |
|   | | risk_level | String(32) | default=medium | 风险等级 |
|   | | enabled | Boolean | default=True | 是否启用 |
|   | | created_at | DateTime | default=now() | 创建时间 |
|   | | updated_at | DateTime | default=now(), onupdate | 更新时间 |
| 68 | **workflow_runs** | id | Integer | PK, Index | 主键 |
|   | | template_id | Integer | FK->workflow_templates.id, nullable | 模板 ID |
|   | | session_id | Integer | FK->chat_sessions.id, nullable | 会话 ID |
|   | | title | String(256) | NOT NULL | 标题 |
|   | | status | String(32) | default=pending | 状态 |
|   | | context | Text | default={} | 上下文 JSON |
|   | | trigger_source | String(32) | default=ai | 触发来源 |
|   | | started_at | DateTime | nullable | 开始时间 |
|   | | completed_at | DateTime | nullable | 完成时间 |
|   | | created_at | DateTime | default=now() | 创建时间 |
|   | | updated_at | DateTime | default=now(), onupdate | 更新时间 |
| 69 | **workflow_node_runs** | id | Integer | PK, Index | 主键 |
|   | | run_id | Integer | FK->workflow_runs.id, NOT NULL, Index | 运行 ID |
|   | | node_id | String(64) | NOT NULL | 节点 ID |
|   | | node_name | String(128) | default= | 节点名 |
|   | | action_type | String(64) | NOT NULL | 动作类型 |
|   | | payload | Text | default={} | 负载 JSON |
|   | | status | String(32) | default=pending | 状态 |
|   | | result | Text | default= | 结果 |
|   | | requires_confirm | Boolean | default=False | 是否需要确认 |
|   | | pending_action_id | Integer | nullable | 待确认动作 ID |
|   | | retry_count | Integer | default=0 | 重试次数 |
|   | | started_at | DateTime | nullable | 开始时间 |
|   | | completed_at | DateTime | nullable | 完成时间 |
|   | | created_at | DateTime | default=now() | 创建时间 |
| 70 | **agent_workflows** | id | Integer | PK, Index | 主键 |
|   | | name | String(128) | NOT NULL | 工作流名 |
|   | | description | Text | default= | 描述 |
|   | | category | String(64) | default=generic | 分类 |
|   | | nodes | Text | default=[] | DAG 节点 JSON |
|   | | edges | Text | default=[] | DAG 边 JSON |
|   | | inputs_schema | Text | default=[] | 输入 Schema |
|   | | outputs_schema | Text | default=[] | 输出 Schema |
|   | | enabled | Boolean | default=True | 是否启用 |
|   | | published | Boolean | default=False | 是否发布 |
|   | | trigger_type | String(32) | default=manual | 触发类型 |
|   | | trigger_condition | Text | default={} | 触发条件 |
|   | | created_by | Integer | nullable | 创建人 |
|   | | created_at | DateTime | default=now() | 创建时间 |
|   | | updated_at | DateTime | default=now(), onupdate | 更新时间 |
| 71 | **agent_workflow_runs** | id | Integer | PK, Index | 主键 |
|   | | workflow_id | Integer | FK->agent_workflows.id, nullable | 工作流 ID |
|   | | workflow_snapshot | Text | default={} | 快照 JSON |
|   | | session_id | Integer | FK->chat_sessions.id, nullable | 会话 ID |
|   | | status | String(32) | default=pending | 状态 |
|   | | inputs | Text | default={} | 输入 JSON |
|   | | runtime_context | Text | default={} | 运行时上下文 |
|   | | outputs | Text | default={} | 输出 JSON |
|   | | trigger_source | String(32) | default=api | 触发来源 |
|   | | error | Text | default= | 错误信息 |
|   | | started_at | DateTime | nullable | 开始时间 |
|   | | completed_at | DateTime | nullable | 完成时间 |
|   | | created_at | DateTime | default=now() | 创建时间 |
|   | | updated_at | DateTime | default=now(), onupdate | 更新时间 |
|   | | triggered_by | String(64) | default= | 触发人 |
| 72 | **agent_workflow_node_runs** | id | Integer | PK, Index | 主键 |
|   | | run_id | Integer | FK->agent_workflow_runs.id, NOT NULL, Index | 运行 ID |
|   | | node_id | String(64) | NOT NULL | 节点 ID |
|   | | node_type | String(32) | NOT NULL | 节点类型 |
|   | | node_name | String(128) | default= | 节点名 |
|   | | run_config | Text | default={} | 运行配置 |
|   | | status | String(32) | default=pending | 状态 |
|   | | output | Text | default={} | 输出 JSON |
|   | | error | Text | default= | 错误 |
|   | | requires_confirm | Boolean | default=False | 需要确认 |
|   | | pending_action_id | Integer | nullable | 待确认动作 ID |
|   | | started_at | DateTime | nullable | 开始时间 |
|   | | completed_at | DateTime | nullable | 完成时间 |
|   | | created_at | DateTime | default=now() | 创建时间 |
| 73 | **workflow_audit_logs** | id | Integer | PK, Index | 主键 |
|   | | run_id | Integer | nullable, Index | 运行 ID |
|   | | node_run_id | Integer | nullable | 节点运行 ID |
|   | | workflow_id | Integer | nullable | 工作流 ID |
|   | | action | String(32) | NOT NULL | 动作 |
|   | | operator | String(64) | default= | 操作人 |
|   | | tool_name | String(64) | default= | 工具名 |
|   | | execution_mode | String(16) | default= | 执行模式 |
|   | | risk_level | String(16) | default= | 风险等级 |
|   | | detail | Text | default={} | 详情 JSON |
|   | | created_at | DateTime | default=now() | 创建时间 |

### 2.9 用户与权限

| # | 表名 | 列名 | 类型 | 约束 | 说明 |
|---|------|------|------|------|------|
| 74 | **users** | id | Integer | PK, Index | 主键 |
|   | | username | String(64) | UNIQUE, NOT NULL, Index | 用户名 |
|   | | password_hash | String(256) | NOT NULL | 密码哈希 |
|   | | role | String(32) | default=admin | 角色 |
|   | | created_at | DateTime | default=now() | 创建时间 |
| 75 | **api_tokens** | id | Integer | PK, Index | 主键 |
|   | | name | String(128) | NOT NULL | Token 名 |
|   | | token | String(64) | UNIQUE, NOT NULL, Index | Token 值 |
|   | | permissions | String(256) | default=read | 权限 |
|   | | last_used_at | DateTime | nullable | 最后使用时间 |
|   | | enabled | Boolean | default=True | 是否启用 |
|   | | created_at | DateTime | default=now() | 创建时间 |
| 76 | **saved_filters** | id | Integer | PK, Index | 主键 |
|   | | name | String(128) | NOT NULL | 过滤器名 |
|   | | page | String(64) | default=alerts | 页面 |
|   | | filters | Text | default={} | 过滤器 JSON |
|   | | user_id | Integer | FK->users.id, nullable | 用户 ID |
|   | | created_at | DateTime | default=now() | 创建时间 |

### 2.10 日志与追踪

| # | 表名 | 列名 | 类型 | 约束 | 说明 |
|---|------|------|------|------|------|
| 77 | **spans** | id | Integer | PK, Index | 主键 |
|   | | trace_id | String(64) | Index | 追踪 ID |
|   | | span_id | String(64) | - | Span ID |
|   | | parent_span_id | String(64) | default= | 父 Span ID |
|   | | service_name | String(128) | - | 服务名 |
|   | | operation_name | String(256) | - | 操作名 |
|   | | started_at | DateTime | - | 开始时间 |
|   | | ended_at | DateTime | - | 结束时间 |
|   | | duration_ms | Float | default=0 | 耗时(毫秒) |
|   | | status | String(32) | default=OK | 状态 |
|   | | tags | Text | default={} | 标签 JSON |
|   | | created_at | DateTime | default=now() | 创建时间 |
| 78 | **trace_anomaly_configs** | id | Integer | PK, Index | 主键 |
|   | | name | String(128) | - | 配置名 |
|   | | service_name | String(128) | default= | 服务名 |
|   | | latency_threshold_ms | Float | default=1000 | 延迟阈值(毫秒) |
|   | | error_rate_threshold | Float | default=0.05 | 错误率阈值 |
|   | | enabled | Boolean | default=True | 是否启用 |
|   | | created_at | DateTime | default=now() | 创建时间 |
| 79 | **k8s_events** | id | Integer | PK, Index | 主键 |
|   | | cluster | String(128) | default= | 集群 |
|   | | namespace | String(128) | default= | 命名空间 |
|   | | name | String(256) | default= | 资源名 |
|   | | kind | String(64) | default= | 资源类型 |
|   | | reason | String(128) | default= | 原因 |
|   | | message | Text | default= | 消息 |
|   | | source | String(128) | default= | 来源 |
|   | | first_seen_at | DateTime | nullable | 首次出现时间 |
|   | | last_seen_at | DateTime | nullable | 最后出现时间 |
|   | | count | Integer | default=1 | 出现次数 |
|   | | severity | String(32) | default=info | 严重级别 |
|   | | created_at | DateTime | default=now() | 创建时间 |
| 80 | **cluster_anomaly_events** | id | Integer | PK, Index | 主键 |
|   | | anomaly_type | String(64) | - | 异常类型 |
|   | | cluster | String(128) | default=default | 集群 |
|   | | message | Text | default= | 消息 |
|   | | severity | String(32) | default=warning | 严重级别 |
|   | | count | Integer | default=1 | 次数 |
|   | | first_seen_at | DateTime | - | 首次发现时间 |
|   | | last_seen_at | DateTime | - | 最后发现时间 |
|   | | is_resolved | Boolean | default=False | 是否已解决 |
|   | | created_at | DateTime | default=now() | 创建时间 |
| 81 | **netflow_records** | id | Integer | PK, Index | 主键 |
|   | | src_ip | String(64) | - | 源 IP |
|   | | dst_ip | String(64) | - | 目标 IP |
|   | | src_port | Integer | default=0 | 源端口 |
|   | | dst_port | Integer | default=0 | 目标端口 |
|   | | protocol | String(16) | default=TCP | 协议 |
|   | | bytes_sent | Integer | default=0 | 发送字节 |
|   | | bytes_rcvd | Integer | default=0 | 接收字节 |
|   | | started_at | DateTime | - | 开始时间 |
|   | | ended_at | DateTime | - | 结束时间 |
|   | | created_at | DateTime | default=now() | 创建时间 |
| 82 | **netflow_collectors** | id | Integer | PK, Index | 主键 |
|   | | name | String(128) | - | 采集器名 |
|   | | collector_type | String(32) | default=sflow | 采集器类型 |
|   | | listen_host | String(64) | default=0.0.0.0 | 监听地址 |
|   | | listen_port | Integer | default=6343 | 监听端口 |
|   | | enabled | Boolean | default=False | 是否启用 |
|   | | created_at | DateTime | default=now() | 创建时间 |
| 83 | **kafka_pipelines** | id | Integer | PK, Index | 主键 |
|   | | name | String(128) | - | 管道名 |
|   | | brokers | String(512) | - | Broker 地址 |
|   | | topic | String(128) | - | 主题 |
|   | | group_id | String(128) | default=aiops | 消费者组 |
|   | | pipeline_type | String(32) | default=log | 管道类型 |
|   | | transform | String(32) | default=raw | 转换方式 |
|   | | enabled | Boolean | default=False | 是否启用 |
|   | | created_at | DateTime | default=now() | 创建时间 |

### 2.11 知识管理

| # | 表名 | 列名 | 类型 | 约束 | 说明 |
|---|------|------|------|------|------|
| 84 | **knowledge_base** | id | Integer | PK, Index | 主键 |
|   | | title | String(256) | NOT NULL | 标题 |
|   | | symptom | Text | default= | 症状 |
|   | | root_cause | Text | default= | 根因 |
|   | | solution | Text | default= | 解决方案 |
|   | | tags | String(256) | default= | 标签 |
|   | | severity | String(32) | default=warning | 严重级别 |
|   | | asset_type | String(32) | default= | 资产类型 |
|   | | source_type | String(32) | default=manual | 来源类型 |
|   | | sop_steps | Text | default=[] | SOP 步骤 JSON |
|   | | created_at | DateTime | default=now() | 创建时间 |
|   | | updated_at | DateTime | default=now(), onupdate | 更新时间 |
| 85 | **kb_documents** | id | Integer | PK, Index | 主键 |
|   | | kb_id | Integer | FK->knowledge_base.id, nullable | 知识库 ID |
|   | | title | String(256) | NOT NULL | 标题 |
|   | | source_type | String(32) | default=manual | 来源类型 |
|   | | file_path | String(512) | default= | 文件路径 |
|   | | file_ext | String(16) | default= | 扩展名 |
|   | | content | Text | default= | 全文内容 |
|   | | chunk_count | Integer | default=0 | 切片数 |
|   | | status | String(32) | default=pending | 状态 |
|   | | tags | String(256) | default= | 标签 |
|   | | asset_type | String(32) | default= | 资产类型 |
|   | | severity | String(32) | default=warning | 严重级别 |
|   | | index_engine | String(16) | default=v1 | 索引引擎 |
|   | | created_by | Integer | FK->users.id, nullable | 上传人 |
|   | | created_at | DateTime | default=now() | 创建时间 |
|   | | updated_at | DateTime | default=now(), onupdate | 更新时间 |
| 86 | **kb_chunks** | id | Integer | PK, Index | 主键 |
|   | | document_id | Integer | FK->kb_documents.id, NOT NULL, Index | 文档 ID |
|   | | chunk_index | Integer | NOT NULL | 切片序号 |
|   | | content | Text | NOT NULL | 切片文本 |
|   | | embedding | Text | default= | 向量 JSON |
|   | | embedding_mode | String(32) | default=tfidf | 向量模式 |
|   | | token_count | Integer | default=0 | Token 数 |
|   | | tags | String(256) | default= | 标签 |
|   | | asset_type | String(32) | default= | 资产类型 |
|   | | severity | String(32) | default=warning | 严重级别 |
|   | | created_at | DateTime | default=now() | 创建时间 |
| 87 | **knowledge_drafts** | id | Integer | PK, Index | 主键 |
|   | | alert_id | Integer | FK->alerts.id, nullable, Index | 告警 ID |
|   | | title | String(256) | NOT NULL | 标题 |
|   | | symptom | Text | default= | 症状 |
|   | | root_cause | Text | default= | 根因 |
|   | | solution | Text | default= | 解决方案 |
|   | | tags | String(256) | default= | 标签 |
|   | | severity | String(32) | default=warning | 严重级别 |
|   | | asset_type | String(32) | default= | 资产类型 |
|   | | source_data | Text | default= | 源数据 |
|   | | source_type | String(32) | default=auto | 来源类型 |
|   | | sop_steps | Text | default=[] | SOP 步骤 JSON |
|   | | status | String(16) | default=pending | 审核状态 |
|   | | reject_reason | Text | default= | 驳回原因 |
|   | | created_at | DateTime | default=now() | 创建时间 |
|   | | updated_at | DateTime | default=now(), onupdate | 更新时间 |
| 88 | **runbooks** | id | Integer | PK, Index | 主键 |
|   | | title | String(256) | NOT NULL | 标题 |
|   | | category | String(64) | default=general | 分类 |
|   | | symptom | Text | default= | 症状 |
|   | | diagnosis | Text | default= | 诊断 |
|   | | steps | Text | default= | 步骤 |
|   | | tags | String(256) | default= | 标签 |
|   | | severity | String(32) | default=warning | 严重级别 |
|   | | asset_type | String(32) | default= | 资产类型 |
|   | | created_at | DateTime | default=now() | 创建时间 |
|   | | updated_at | DateTime | default=now(), onupdate | 更新时间 |

### 2.12 变更管理

| # | 表名 | 列名 | 类型 | 约束 | 说明 |
|---|------|------|------|------|------|
| 89 | **change_requests** | id | Integer | PK, Index | 主键 |
|   | | title | String(256) | NOT NULL | 标题 |
|   | | description | Text | default= | 描述 |
|   | | ci_type | String(64) | default= | CI 类型 |
|   | | asset_id | Integer | nullable | 资产 ID |
|   | | change_type | String(32) | default=normal | 变更类型 |
|   | | priority | String(32) | default=medium | 优先级 |
|   | | status | String(32) | default=draft | 状态 |
|   | | risk_level | String(32) | default=low | 风险等级 |
|   | | planned_started_at | DateTime | nullable | 计划开始时间 |
|   | | planned_ended_at | DateTime | nullable | 计划结束时间 |
|   | | requester_id | Integer | FK->users.id, nullable | 请求人 |
|   | | reviewer_id | Integer | FK->users.id, nullable | 审批人 |
|   | | review_comment | Text | default= | 审批意见 |
|   | | created_at | DateTime | default=now() | 创建时间 |
|   | | updated_at | DateTime | default=now(), onupdate | 更新时间 |
| 90 | **change_tasks** | id | Integer | PK, Index | 主键 |
|   | | change_id | Integer | FK->change_requests.id, NOT NULL | 变更 ID |
|   | | step_order | Integer | default=0 | 步骤序号 |
|   | | description | String(512) | default= | 描述 |
|   | | command | String(1024) | default= | 命令 |
|   | | status | String(32) | default=pending | 状态 |
|   | | result | Text | default= | 结果 |
|   | | user_id | Integer | FK->users.id, nullable | 执行人 |
|   | | executed_at | DateTime | nullable | 执行时间 |
|   | | created_at | DateTime | default=now() | 创建时间 |

### 2.13 蓝绿部署与 Service Mesh

| # | 表名 | 列名 | 类型 | 约束 | 说明 |
|---|------|------|------|------|------|
| 91 | **blue_green_deploys** | id | Integer | PK, Index | 主键 |
|   | | name | String(128) | - | 部署名 |
|   | | namespace | String(64) | default=default | 命名空间 |
|   | | cluster | String(128) | default= | 集群 |
|   | | active_label | String(64) | default=blue | 当前活跃标签 |
|   | | standby_label | String(64) | default=green | 备用标签 |
|   | | active_replicas | Integer | default=3 | 活跃副本数 |
|   | | standby_replicas | Integer | default=3 | 备用副本数 |
|   | | status | String(32) | default=active | 状态 |
|   | | last_switched_at | DateTime | nullable | 最后切换时间 |
|   | | created_at | DateTime | default=now() | 创建时间 |
| 92 | **blue_green_switch_records** | id | Integer | PK, Index | 主键 |
|   | | deploy_id | Integer | FK->blue_green_deploys.id, NOT NULL | 部署 ID |
|   | | from_label | String(64) | default= | 来源标签 |
|   | | to_label | String(64) | default= | 目标标签 |
|   | | operator | String(64) | default=system | 操作人 |
|   | | description | String(256) | default= | 描述 |
|   | | created_at | DateTime | default=now() | 创建时间 |
| 93 | **service_mesh_configs** | id | Integer | PK, Index | 主键 |
|   | | name | String(128) | - | 配置名 |
|   | | mesh_type | String(32) | default=istio | 网格类型 |
|   | | api_url | String(512) | default= | API URL |
|   | | auth_config | Text | default={} | 认证配置 |
|   | | enabled | Boolean | default=False | 是否启用 |
|   | | created_at | DateTime | default=now() | 创建时间 |

### 2.14 智能巡检与安全基线

| # | 表名 | 列名 | 类型 | 约束 | 说明 |
|---|------|------|------|------|------|
| 94 | **inspection_templates** | id | Integer | PK, Index | 主键 |
|   | | name | String(128) | NOT NULL | 模板名 |
|   | | description | Text | default= | 描述 |
|   | | target_ci_types | Text | default=[] | 目标 CI 类型 |
|   | | check_items | Text | default=[] | 检查项 JSON |
|   | | enabled | Boolean | default=True | 是否启用 |
|   | | created_at | DateTime | default=now() | 创建时间 |
|   | | updated_at | DateTime | default=now(), onupdate | 更新时间 |
| 95 | **inspection_tasks** | id | Integer | PK, Index | 主键 |
|   | | name | String(128) | NOT NULL | 任务名 |
|   | | template_id | Integer | FK->inspection_templates.id, NOT NULL | 模板 ID |
|   | | scope_type | String(32) | default=manual | 范围类型 |
|   | | scope_filter | Text | default={} | 范围过滤 JSON |
|   | | asset_ids | Text | default=[] | 资产 ID 列表 |
|   | | schedule_cron | String(64) | nullable | 调度 cron |
|   | | schedule_enabled | Boolean | default=False | 调度是否启用 |
|   | | ai_analysis | Boolean | default=True | 是否 AI 分析 |
|   | | status | String(32) | default=idle | 状态 |
|   | | last_run_at | DateTime | nullable | 最后运行时间 |
|   | | created_at | DateTime | default=now() | 创建时间 |
| 96 | **inspection_records** | id | Integer | PK, Index | 主键 |
|   | | task_id | Integer | FK->inspection_tasks.id, NOT NULL | 任务 ID |
|   | | triggered_by_alert_id | Integer | FK->alerts.id, nullable | 触发告警 ID |
|   | | status | String(32) | default=running | 状态 |
|   | | total_assets | Integer | default=0 | 总资产数 |
|   | | checked_assets | Integer | default=0 | 已检查数 |
|   | | normal_count | Integer | default=0 | 正常数 |
|   | | warning_count | Integer | default=0 | 警告数 |
|   | | critical_count | Integer | default=0 | 严重数 |
|   | | overall_score | Float | default=0.0 | 总体评分 |
|   | | ai_report | Text | default= | AI 报告 |
|   | | ai_risk_summary | Text | default= | AI 风险摘要 |
|   | | ai_recommendations | Text | default=[] | AI 建议 JSON |
|   | | item_results | Text | default=[] | 检查项结果 |
|   | | started_at | DateTime | default=now() | 开始时间 |
|   | | finished_at | DateTime | nullable | 完成时间 |
|   | | duration_seconds | Float | default=0.0 | 耗时(秒) |
| 97 | **security_baseline_templates** | id | Integer | PK, Index | 主键 |
|   | | ci_type | String(32) | NOT NULL, Index | CI 类型 |
|   | | check_key | String(64) | NOT NULL | 检查键 |
|   | | check_name | String(128) | NOT NULL | 检查名 |
|   | | category | String(32) | default=access | 分类 |
|   | | severity | String(16) | default=medium | 严重级别 |
|   | | description | String(512) | default= | 描述 |
|   | | check_method | String(16) | default=ssh | 检查方法 |
|   | | check_command | String(512) | default= | 检查命令 |
|   | | expect_match | String(256) | default= | 期望匹配 |
|   | | remediation | Text | default= | 修复方案 |
|   | | sort_order | Integer | default=0 | 排序号 |
|   | | enabled | Boolean | default=True | 是否启用 |
|   | | created_at | DateTime | default=now() | 创建时间 |
| 98 | **asset_baseline_checks** | id | Integer | PK, Index | 主键 |
|   | | asset_id | Integer | FK->assets.id, NOT NULL, Index | 资产 ID |
|   | | template_id | Integer | FK->security_baseline_templates.id, NOT NULL | 模板 ID |
|   | | status | String(16) | default=pending | 状态 |
|   | | actual_value | String(512) | default= | 实际值 |
|   | | reason | Text | default= | 原因 |
|   | | checked_at | DateTime | nullable | 检查时间 |
|   | | created_at | DateTime | default=now() | 创建时间 |

### 2.15 报表与仪表盘

| # | 表名 | 列名 | 类型 | 约束 | 说明 |
|---|------|------|------|------|------|
| 99 | **reports** | id | Integer | PK, Index | 主键 |
|   | | title | String(256) | NOT NULL | 标题 |
|   | | type | String(32) | NOT NULL | 报告类型 |
|   | | period_started_at | DateTime | nullable | 统计开始时间 |
|   | | period_ended_at | DateTime | nullable | 统计结束时间 |
|   | | summary | Text | default= | 摘要 |
|   | | report_data | Text | default= | 报告数据 |
|   | | created_at | DateTime | default=now() | 创建时间 |
| 100 | **report_schedules** | id | Integer | PK, Index | 主键 |
|   | | name | String(128) | NOT NULL | 调度名 |
|   | | report_type | String(32) | default=daily | 报告类型 |
|   | | cron_expr | String(128) | default=0 8 * * * | cron 表达式 |
|   | | channel | String(32) | default=email | 推送渠道 |
|   | | channel_config | Text | default={} | 渠道配置 |
|   | | enabled | Boolean | default=True | 是否启用 |
|   | | last_run_at | DateTime | nullable | 最后运行时间 |
|   | | created_at | DateTime | default=now() | 创建时间 |
| 101 | **dashboard_card_configs** | id | Integer | PK, Index | 主键 |
|   | | user_id | Integer | FK->users.id, nullable | 用户 ID |
|   | | card_type | String(64) | NOT NULL | 卡片类型 |
|   | | title | String(128) | default= | 标题 |
|   | | card_config | Text | default={} | 卡片配置 |
|   | | position | Integer | default=0 | 位置排序 |
|   | | is_visible | Boolean | default=True | 是否可见 |

### 2.16 移动端与推送

| # | 表名 | 列名 | 类型 | 约束 | 说明 |
|---|------|------|------|------|------|
| 102 | **mobile_devices** | id | Integer | PK, Index | 主键 |
|   | | user_id | Integer | FK->users.id, NOT NULL | 用户 ID |
|   | | device_id | String(128) | NOT NULL | 设备 ID |
|   | | platform | String(16) | NOT NULL | 平台 |
|   | | push_token | String(256) | - | 推送 Token |
|   | | biometric_token | String(512) | - | 生物识别 Token |
|   | | app_version | String(32) | - | App 版本 |
|   | | last_active_at | DateTime | - | 最后活跃时间 |
|   | | created_at | DateTime | default=now() | 创建时间 |
|   | UniqueConstraint | (user_id, device_id) | - | 唯一约束 |
| 103 | **push_records** | id | Integer | PK, Index | 主键 |
|   | | device_id | Integer | FK->mobile_devices.id, NOT NULL | 设备 ID |
|   | | title | String(128) | NOT NULL | 标题 |
|   | | body | Text | - | 正文 |
|   | | payload | Text | - | 负载 |
|   | | type | String(32) | - | 推送类型 |
|   | | ref_id | Integer | - | 关联 ID |
|   | | status | String(16) | default=pending | 状态 |
|   | | provider_msg_id | String(128) | - | 提供商消息 ID |
|   | | error | Text | - | 错误信息 |
|   | | created_at | DateTime | default=now() | 创建时间 |
|   | | sent_at | DateTime | - | 发送时间 |

### 2.17 A/B 测试与实验

| # | 表名 | 列名 | 类型 | 约束 | 说明 |
|---|------|------|------|------|------|
| 104 | **ab_test_configs** | id | Integer | PK, Index | 主键 |
|   | | name | String(128) | NOT NULL | 实验名 |
|   | | provider_a_id | Integer | FK->ai_providers.id, nullable | 提供商 A |
|   | | provider_b_id | Integer | FK->ai_providers.id, nullable | 提供商 B |
|   | | model_a | String(64) | default= | 模型 A |
|   | | model_b | String(64) | default= | 模型 B |
|   | | split_ratio | String(8) | default=50/50 | 分流比例 |
|   | | metric | String(32) | default=latency | 评估指标 |
|   | | status | String(16) | default=active | 状态 |
|   | | created_at | DateTime | default=now() | 创建时间 |
|   | | updated_at | DateTime | default=now(), onupdate | 更新时间 |
| 105 | **ab_test_records** | id | Integer | PK, Index | 主键 |
|   | | test_id | Integer | FK->ab_test_configs.id, nullable, Index | 实验 ID |
|   | | session_id | Integer | nullable, Index | 会话 ID |
|   | | group | String(8) | default=a | 分组 |
|   | | provider_id | Integer | nullable, Index | 提供商 ID |
|   | | model_name | String(64) | default= | 模型名 |
|   | | latency_ms | Integer | default=0 | 延迟(毫秒) |
|   | | token_count | Integer | default=0 | Token 数 |
|   | | is_success | Boolean | default=True | 是否成功 |
|   | | user_feedback | String(16) | default= | 用户反馈 |
|   | | created_at | DateTime | default=now(), Index | 创建时间 |

### 2.18 系统配置与外部集成

| # | 表名 | 列名 | 类型 | 约束 | 说明 |
|---|------|------|------|------|------|
| 106 | **system_configs** | id | Integer | PK, Index | 主键 |
|   | | key | String(128) | UNIQUE, NOT NULL, Index | 配置键 |
|   | | config_value | Text | default= | 配置值 |
|   | | description | String(256) | default= | 描述 |
|   | | updated_at | DateTime | default=now(), onupdate | 更新时间 |
| 107 | **ext_event_sources** | id | Integer | PK, Index | 主键 |
|   | | name | String(128) | - | 事件源名 |
|   | | source_type | String(32) | default=zabbix | 事件源类型 |
|   | | api_url | String(512) | - | API URL |
|   | | auth_config | Text | default={} | 认证配置 |
|   | | sync_interval | Integer | default=60 | 同步间隔(分) |
|   | | last_synced_at | DateTime | nullable | 最后同步时间 |
|   | | enabled | Boolean | default=False | 是否启用 |
|   | | created_at | DateTime | default=now() | 创建时间 |
| 108 | **prediction_models** | id | Integer | PK, Index | 主键 |
|   | | name | String(128) | NOT NULL | 模型名 |
|   | | metric_name | String(64) | NOT NULL | 指标名 |
|   | | asset_id | Integer | nullable | 资产 ID |
|   | | model_type | String(32) | default=linear | 模型类型 |
|   | | model_params | Text | default={} | 模型参数 |
|   | | enabled | Boolean | default=True | 是否启用 |
|   | | created_at | DateTime | default=now() | 创建时间 |

---

## 3. 表关联关系图（文本描述）

### 3.1 核心外键关系链

```
assets (self-ref)
  parent_id FK-> assets.id

asset_relations
  parent_id FK-> assets.id
  child_id  FK-> assets.id

asset_lifecycles
  asset_id  FK-> assets.id
  user_id   FK-> users.id

asset_change_logs
  asset_id  FK-> assets.id

ci_attributes
  ci_model_id FK-> ci_models.id

tags
  category_id FK-> tag_categories.id

chaos_runs
  experiment_id FK-> chaos_experiments.id

alerts
  rule_id  FK-> alert_rules.id
  asset_id FK-> assets.id

alert_silences / alert_silence_schedules / alert_suppressions
  rule_id  FK-> alert_rules.id

alert_escalations
  alert_id FK-> alerts.id

notification_logs
  alert_id   FK-> alerts.id
  channel_id FK-> notification_channels.id

incidents
  asset_id    FK-> assets.id
  approver_id FK-> users.id

incident_alerts
  incident_id FK-> incidents.id
  alert_id    FK-> alerts.id

incident_approvals
  incident_id FK-> incidents.id
  approver_id FK-> users.id

alert_kb_links
  alert_id FK-> alerts.id
  kb_id    FK-> knowledge_base.id

alert_event_links
  alert_id FK-> alerts.id
  event_id FK-> k8s_events.id

alert_session_links
  alert_id   FK-> alerts.id
  session_id FK-> chat_sessions.id

asset_session_links
  asset_id   FK-> assets.id
  session_id FK-> chat_sessions.id

auto_remediations
  rule_id FK-> alert_rules.id

remediation_logs
  remediation_id FK-> auto_remediations.id
  alert_id        FK-> alerts.id

remediation_effects / remediation_effect_records
  remediation_id FK-> auto_remediations.id
  alert_id        FK-> alerts.id
  asset_id        FK-> assets.id

remediation_workflows
  rule_id FK-> alert_rules.id

remediation_effect_records
  log_id FK-> remediation_logs.id

change_requests
  requester_id FK-> users.id
  reviewer_id  FK-> users.id

change_tasks
  change_id FK-> change_requests.id
  user_id   FK-> users.id

saved_filters
  user_id FK-> users.id

chat_sessions
  user_id FK-> users.id

chat_messages
  session_id FK-> chat_sessions.id

tool_invocations
  session_id FK-> chat_sessions.id
  message_id FK-> chat_messages.id

pending_actions
  session_id FK-> chat_sessions.id
  message_id FK-> chat_messages.id

background_jobs
  asset_id          FK-> assets.id
  session_id        FK-> chat_sessions.id
  pending_action_id FK-> pending_actions.id

agent_configs
  default_provider_id FK-> ai_providers.id

ab_test_configs
  provider_a_id FK-> ai_providers.id
  provider_b_id FK-> ai_providers.id

error_budgets
  slo_id FK-> slo_configs.id

kb_documents
  kb_id      FK-> knowledge_base.id
  created_by FK-> users.id

kb_chunks
  document_id FK-> kb_documents.id

knowledge_drafts
  alert_id FK-> alerts.id

workflow_runs
  template_id FK-> workflow_templates.id
  session_id  FK-> chat_sessions.id

workflow_node_runs
  run_id FK-> workflow_runs.id

agent_workflow_runs
  workflow_id FK-> agent_workflows.id
  session_id  FK-> chat_sessions.id

agent_workflow_node_runs
  run_id FK-> agent_workflow_runs.id

metric_records / metric_recommendations / anomaly_benchmarks / baseline_checks
  asset_id FK-> assets.id

inspection_tasks
  template_id FK-> inspection_templates.id

inspection_records
  task_id               FK-> inspection_tasks.id
  triggered_by_alert_id FK-> alerts.id

discovery_results
  schedule_id FK-> discovery_schedules.id
  asset_id    FK-> assets.id

blue_green_switch_records
  deploy_id FK-> blue_green_deploys.id

mobile_devices
  user_id FK-> users.id

push_records
  device_id FK-> mobile_devices.id

dashboard_card_configs
  user_id FK-> users.id
```

### 3.2 多对多关联表

| 关联表 | 左表 | 右表 | 语义 |
|--------|------|------|------|
| incident_alerts | incidents | alerts | 事件关联告警 |
| alert_kb_links | alerts | knowledge_base | 告警关联知识 |
| alert_event_links | alerts | k8s_events | 告警关联 K8s 事件 |
| alert_session_links | alerts | chat_sessions | 告警关联 AI 会话 |
| asset_session_links | assets | chat_sessions | 资产关联 AI 会话 |
| asset_relations | assets | assets | 资产间关系(自引用) |

### 3.3 主要数据流向

```
数据源(ext_event_sources / data_sources / kafka_pipelines)
  |
  v
metric_records / k8s_events / netflow_records / spans
  |
  v
alert_rules -> alerts -> alert_escalations
  |                    |
  v                    v
alert_silences      incident_alerts -> incidents
  |                    |
  v                    v
notification_logs    incident_approvals
  |
  v
auto_remediations -> remediation_logs -> remediation_effects
  |
  v
knowledge_drafts -> knowledge_base
  |
  v
kb_documents -> kb_chunks (vector search)
```

---

## 4. 字段命名规范

摘自 CONTRACT.md（全库字段规范契约），适用所有 108 张表。

### 4.1 全局命名规则

| 规则 | 说明 | 正确示例 | 错误示例 |
|------|------|----------|----------|
| 时间后缀 | DateTime 字段统一后缀 _at | created_at | create_time, create_date |
| 布尔前缀-判断 | 加 is_ 前缀 | is_success | success |
| 布尔前缀-拥有 | 加 has_ 前缀 | has_hallucination | hallucination_flag |
| 布尔前缀-开关 | 使用 enabled | enabled | active, visible |
| 描述统一 | 统一用 description | description | notes, comment, remark |
| JSON 前缀 | 带业务前缀 | channel_config | config |
| 外键格式 | {table}_id | user_id | changed_by, executed_by |
| 状态字段 | 统一用 status | status | state, condition |
| 命名风格 | snake_case | service_name | serviceName, ServiceName |
| 禁止缩写 | 全拼不缩写 | description | desc |

### 4.2 跨表同语义字段长度统一

| 字段名 | 统一长度 |
|--------|---------|
| name | String(128) |
| title | String(256) |
| status | String(32) |
| severity | String(32) |
| metric_name | String(64) |
| category | String(32) |
| source | String(32) |
| service_name | String(128) |
| reason | String(256) |
| tags | String(256) |
| cron_expr | String(128) |
| description | Text 或 String(512) |
| ci_type | String(32) |
| risk_level | String(16) |

### 4.3 敏感字段掩码规则

| 字段 | 掩码标记 |
|------|---------|
| ssh_password | has_ssh_password |
| ssh_private_key | has_ssh_private_key |
| k8s_token | has_k8s_token |
| kubeconfig | has_kubeconfig |
| db_password | has_db_password |
| http_credential | has_http_credential |

### 4.4 废弃字段清单

| 表 | 废弃字段 | 替代 | 原因 |
|----|---------|------|------|
| assets | type | ci_type | 语义重复，ci_type 更精确 |

---

## 5. 文档说明

- **数据来源：** app/models.py（1872 行，108 个 SQLAlchemy 模型类）
- **规范来源：** CONTRACT.md（619 行字段规范契约）
- **生成日期：** 2026-07-15
- **未采纳的契约修正：** 本表结构文档反映的是 models.py 中的*当前实际字段*，CONTRACT.md 中标注了部分字段名不规范但尚未统一修正（如 chaos_runs.notes、notification_channels.config 等），如需对齐可参考 CONTRACT.md 第二章的修正列。

