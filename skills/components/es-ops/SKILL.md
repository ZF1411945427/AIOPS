---
name: es-smart-ops
description: Elasticsearch 智能运维诊断：集群健康、分片分布、JVM 堆（通过 es_diagnose 工具），输出根因与建议
version: 1.0.0
author: aiops
license: MIT
category: component
risk_level: read_only
keywords: ["Elasticsearch", "ES", "集群", "分片", "JVM"]
tools_required: ["es_diagnose", "query_metrics", "query_logs", "query_alerts"]
---
# Elasticsearch 智能运维诊断技能

## 目标
对 ES 集群进行健康巡检与故障诊断，定位红/黄状态、分片失衡、JVM 堆压力。

## 执行步骤
1. **集群健康**: 用 `es_diagnose` action=health 获取 status/nodes/unassigned。
2. **分片分析**: action=shards 获取 relocating/initializing 数。
3. **JVM**: action=jvm 获取 heap_used_percent。
4. **关联分析**: 用 `query_logs` 检索慢日志、`query_alerts` 查告警。

## 输出格式
```markdown
### ES 集群健康
### 分片状态
### JVM 堆
### 根因与建议
```

## 禁止
- 不执行索引删除/关闭等写操作（本技能只读）。
