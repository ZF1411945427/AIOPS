---
name: mysql-smart-ops
description: MySQL 智能运维专家：慢 SQL 诊断、连接数/锁分析、主从复制巡检、性能指标解读，输出根因与优化建议
version: 1.0.0
author: aiops
license: MIT
category: component
risk_level: read_only
keywords: ["MySQL", "慢SQL", "数据库", "锁", "复制", "连接池"]
tools_required: ["query_mysql", "check_mysql_permissions", "query_metrics", "query_alerts"]
---
# MySQL 智能运维技能

## 目标
对 MySQL 实例进行健康巡检与故障诊断，定位慢 SQL、连接/锁、主从复制问题并给出可执行优化建议。

## 前置
- 目标 MySQL 资产需已在资产库登记，并在 `connection_config` 配置了连接信息（db_host/db_port/db_user/db_password）。
- 先调用 `check_mysql_permissions` 确认本技能可用权限范围（避免执行越权操作）。

## 执行步骤
1. **实例状态**: 用 `query_mysql` 执行 `SHOW GLOBAL STATUS` 中关键指标（Uptime、Threads_connected、Max_used_connections、Slow_queries、QPS），判断整体健康度。
2. **连接与锁分析**: 查询 `SHOW PROCESSLIST` 统计各状态（Sleep/Query/Lock）连接数，识别堆积/长时间运行的查询，结合 `performance_schema` 锁等待判断是否有锁问题。
3. **慢 SQL 诊断**: 若 `Slow_queries` 偏高，查询慢日志表（如 `mysql.slow_log` 或开启 `performance_schema.events_statements_summary_by_digest`），按耗时排序取 TOP 慢 SQL。
4. **主从复制巡检**: 执行 `SHOW REPLICA STATUS`（或 `SHOW SLAVE STATUS`），检查 `Slave_IO_Running`/`Slave_SQL_Running` 是否为 Yes、`Seconds_Behind_Master` 是否为 0，判断复制延迟。
5. **关联分析**: 用 `query_metrics` 检查该资产 CPU/内存/磁盘 IO 指标，用 `query_alerts` 查同期告警，判断慢 SQL 是否为资源瓶颈所致。

## 输出格式
```markdown
### MySQL 健康总览
- 运行时长 / 当前连接 / 最大连接 / QPS / 慢查询数
### 连接与锁
- 各状态连接数 / 锁等待异常
### TOP 慢 SQL
1. 耗时 / 语句摘要 / 影响分析
### 主从复制
- IO/SQL 线程状态 / 延迟秒数
### 根因与建议
- 2-3 条根因假设 + 可执行优化（索引优化/连接池调整/参数建议）
```

## 禁止
- 不执行任何 INSERT/UPDATE/DELETE/DDL 写操作（本技能只读）。
- 不编造 SQL 语句或性能数据，必须来自 `query_mysql` 返回的原文。
