---
name: kafka-smart-ops
description: Kafka 智能运维专家：消费延迟/Lag 分析、Topic 分区巡检、Broker 健康检查、消费组诊断，输出根因与优化建议
version: 1.0.0
author: aiops
license: MIT
category: component
risk_level: read_only
keywords: ["Kafka", "消费延迟", "Lag", "Topic", "Broker"]
tools_required: ["kafka_monitor", "query_metrics", "query_alerts"]
---
# Kafka 智能运维技能

## 目标
对 Kafka 集群进行健康巡检与故障诊断，定位消费延迟(Lag)、Topic 分区失衡、Broker 异常并给出优化建议。

## 前置
- 目标 Kafka 资产需已登记，并在 `connection_config` 配置 `kafka_bootstrap_servers`(逗号分隔)。

## 执行步骤
1. **集群概览**: 用 `kafka_monitor` action=`cluster` 读取集群 ID / Broker 列表 / Controller。
2. **Topic 巡检**: 用 `kafka_monitor` action=`topics` 列出所有 Topic 与数量，识别异常 Topic。
3. **消费组与延迟(Lag)**: 用 `kafka_monitor` action=`groups` 列出消费组；对高频/关键消费组用 action=`lag`(需 topic+group) 检查各分区 `end_offset - position` 的 Lag。
4. **分区分布**: 对疑似失衡的 Topic 用 action=`partitions` 检查分区 leader 分布，判断是否分区不均衡导致单 Broker 热点。
5. **关联分析**: 用 `query_metrics`/`query_alerts` 检查 Broker 主机 CPU/磁盘/网络与告警，判断是否资源瓶颈或磁盘满写失败。

## 输出格式
```markdown
### Kafka 集群概览
- Broker 数 / Controller / 状态
### Topic 与分区
- Topic 总数 / 分区失衡风险
### 消费延迟(Lag)
- 关键消费组各分区 Lag / 评估
### 根因与建议
- 2-3 条建议（分区扩容/消费者扩容/参数调优/磁盘清理）
```

## 禁止
- 不执行 Topic 创建/删除/改配置等写操作（本技能只读）。
- 不编造 Lag/分区数据，必须来自 `kafka_monitor` 返回原文。
