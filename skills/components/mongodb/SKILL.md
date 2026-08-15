---
name: mongodb-smart-ops
description: MongoDB 智能运维专家：副本集健康、慢操作、集合大小、服务器状态诊断（通过 mongo_diagnose 工具），输出根因与建议
version: 1.0.0
author: aiops
license: MIT
category: component
risk_level: read_only
keywords: ["MongoDB", "副本集", "慢操作", "文档库"]
tools_required: ["mongo_diagnose", "query_metrics", "query_alerts"]
---
# MongoDB 智能运维技能

## 目标
对 MongoDB 进行健康巡检与故障诊断，定位副本集异常、慢操作、存储问题。

## 执行步骤
1. **服务器状态**: 用 `mongo_diagnose` action=server 获取 uptime/连接数。
2. **副本集健康**: action=replica 检查各成员 stateStr 与 health(是否有节点 PRIMARY 下移/SECONDARY 落后)。
3. **慢操作**: action=slow 提取按执行秒数排序的慢查询 currentOp。
4. **存储**: action=stats 看各库 sizeOnDisk。
5. **关联分析**: 用 `query_alerts` 查 Mongo 告警。

## 输出格式
```markdown
### Mongo 状态
### 副本集成员
### 慢操作 TOP
### 根因与建议
```

## 禁止
- 不执行任何写操作（本技能只读）。
