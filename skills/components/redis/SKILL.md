---
name: redis-smart-ops
description: Redis 智能运维专家：内存分析、热 Key/大 Key 检测、命中率优化、连接数分析，输出根因与优化建议
version: 1.0.0
author: aiops
license: MIT
category: component
risk_level: read_only
keywords: ["Redis", "内存", "热Key", "命中率", "缓存"]
tools_required: ["redis_monitor", "query_metrics", "query_alerts"]
---
# Redis 智能运维技能

## 目标
对 Redis 实例进行健康巡检与故障诊断，定位内存、热 Key、命中率、连接数问题并给出优化建议。

## 前置
- 目标 Redis 资产需已登记，并在 `connection_config` 配置 `redis_host`/`redis_port`/`redis_password`。

## 执行步骤
1. **实例概览**: 用 `redis_monitor` 执行 `INFO`，读取 `redis_version`/`uptime_in_seconds`/`connected_clients`/`total_commands_processed`/`keyspace_hits`/`keyspace_misses`。
2. **内存分析**: 从 `INFO memory` 读取 `used_memory`/`used_memory_human`/`maxmemory`/`mem_fragmentation_ratio`/`used_memory_peak`，判断内存水位与碎片化。
3. **命中率优化**: 计算 `keyspace_hits/(keyspace_hits+keyspace_misses)` 命中率；若 < 90%，提示热点缺失/过期策略问题。
4. **热 Key / 大 Key 检测**: 用 `redis_monitor` 执行 `MEMORY STATS`（或 `CONFIG GET` 相关项），结合 `INFO` 中 `evicted_keys`/`expired_keys` 判断驱逐/过期是否异常。
5. **连接与慢命令**: 用 `redis_monitor` 执行 `CLIENT LIST` 分析连接来源，`SLOWLOG`(只读) 识别慢命令。
6. **关联分析**: 用 `query_metrics`/`query_alerts` 检查该资产 CPU/内存指标与告警，判断是否资源瓶颈。
7. **集群巡检**(如适用): 若为集群，用 `INFO cluster`/`CLUSTER INFO` 检查集群状态与槽位。

## 输出格式
```markdown
### Redis 健康总览
- 版本/运行时长/连接数/命令QPS
### 内存分析
- 已用/最大/碎片率/峰值
### 命中率
- 命中率百分比 / 评估
### 热 Key 与大 Key
- 风险点
### 连接与慢命令
### 根因与建议
- 2-3 条优化建议（内存淘汰策略/大Key拆分/连接池配置）
```

## 禁止
- 不执行写操作（本技能只读，仅 PING/INFO/CLIENT LIST/CONFIG GET/DBSIZE/MEMORY/只读 SLOWLOG）。
- 不编造 Redis 数据，必须来自 `redis_monitor` 返回原文。
