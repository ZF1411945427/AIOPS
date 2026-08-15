---
name: postgresql-smart-ops
description: PostgreSQL 智能运维专家：慢查询、连接池、复制延迟、表膨胀诊断（通过 pg_diagnose 工具），输出根因与优化建议
version: 1.0.0
author: aiops
license: MIT
category: component
risk_level: read_only
keywords: ["PostgreSQL", "慢查询", "复制", "连接池", "表膨胀"]
tools_required: ["pg_diagnose", "query_metrics", "query_alerts"]
---
# PostgreSQL 智能运维技能

## 目标
对 PostgreSQL 实例进行健康巡检与故障诊断，定位慢查询、连接耗尽、复制延迟、表膨胀问题。

## 执行步骤
1. **实例概览**: 用 `pg_diagnose` action=all 获取活动/空闲连接、复制状态。
2. **慢查询诊断**: 从 `pg_diagnose` 的 top_slow 提取耗时 TOP SQL，结合 `query_metrics` 看 CPU/IO。
3. **复制延迟**: 检查 `pg_diagnose` 的 replication lag，确认主从是否同步。
4. **连接池**: activity 中 idle 占比过高提示连接泄漏，total 接近 max_connections 提示耗尽风险。
5. **关联分析**: 用 `query_alerts` 查 PG 相关告警。

## 输出格式
```markdown
### PG 健康概述
### 慢查询 TOP
### 复制状态
### 连接分析
### 根因与建议
```

## 禁止
- 不执行任何写 SQL（本技能只读）。
