---
name: elasticsearch-smart-ops
description: Elasticsearch 智能运维专家：集群健康巡检、索引分片均衡、GC/JVM 分析、慢查询诊断
version: 1.0.0
author: aiops
license: MIT
category: component
risk_level: read_only
keywords: ["Elasticsearch", "ES", "集群", "分片", "索引", "JVM"]
tools_required: ["query_metrics", "query_logs", "query_alerts"]
---
# Elasticsearch 智能运维技能

## 目标
对 Elasticsearch 集群进行健康巡检与故障诊断，定位集群红/黄状态、分片失衡、JVM/GC 压力、慢查询问题。

## 执行步骤
1. **集群健康**: 检查集群健康状态(green/yellow/red)，red 表示有主分片未分配, yellow 表示有副本未分配，需重点处理。
2. **分片均衡分析**: 结合索引分片数与节点数, 判断是否分片过度(单节点分片过多)、分片分布不均导致单节点压力。
3. **JVM/GC 分析**: 检查节点 JVM heap 使用率, 若持续 >85% 提示 heap 压力；分析 GC 频繁停顿(慢查询/卡顿诱因)。
4. **慢查询诊断**: 结合 `query_logs` 检索 ES 慢日志(slowlog)与 `query_metrics` 中的查询延迟, 定位慢查询索引与语句。
5. **磁盘水位**: 检查节点磁盘使用率, 判断是否触发 low/watermark 导致分片无法分配。
6. **关联分析**: 用 `query_alerts` 查 ES 集群告警。

## 输出格式
```markdown
### ES 集群健康
- 状态 / 节点数 / 分片数
### 分片与节点
- 失衡风险 / 磁盘水位
### JVM/GC
- heap 使用率 / GC 评估
### 慢查询
### 根因与建议
- 2-3 条建议（分片规划/索引生命周期/扩容/heap 调优）
```

## 禁止
- 不执行索引关闭/删除/force merge 等写操作（本技能只读诊断）。
