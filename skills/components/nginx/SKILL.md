---
name: nginx-smart-ops
description: Nginx 智能运维专家：连接数分析、502/504 故障诊断、Upstream 健康检查、配置优化建议
version: 1.0.0
author: aiops
license: MIT
category: component
risk_level: read_only
keywords: ["Nginx", "502", "504", "连接数", "Upstream"]
tools_required: ["query_metrics", "query_logs", "query_alerts"]
---
# Nginx 智能运维技能

## 目标
对 Nginx 进行健康巡检与故障诊断，定位连接压力、502/504 网关错误、Upstream 异常并给出优化建议。

## 执行步骤
1. **访问/错误日志**: 用 `query_logs` 检索目标时间窗内 Nginx 访问与错误日志，统计 5xx/4xx 分布，提取 TOP 错误原文。
2. **502/504 定位**: 若命中大量 502(网关不可达, upstream 宕机/拒连) 或 504(网关超时, upstream 响应慢), 结合日志中的 upstream 地址判断后端服务。
3. **连接数分析**: 用 `query_metrics` 检查该资产 `nginx.connections`/`accepts`/`handled`/`TCP connections`，判断 `worker_connections` 是否被耗尽。
4. **Upstream 健康**: 若配置了 upstream, 结合后端服务指标与告警, 判断是后端宕机、负载过高还是配置超时过短。
5. **关联分析**: 用 `query_alerts` 查同期告警, 用 `query_metrics` 看 CPU/内存/带宽。

## 输出格式
```markdown
### Nginx 状态总览
- 错误码分布 / 连接数 / QPS
### 502/504 定位
- 诱因(后端宕机/超时/连接耗尽)
### 根因与建议
- 2-3 条建议（调 worker_connections/proxy 超时/后端扩容/健康检查）
```

## 禁止
- 不修改 Nginx 配置或重启服务（本技能只读诊断）。
