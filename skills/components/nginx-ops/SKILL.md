---
name: nginx-ops-diagnose
description: Nginx 智能运维诊断：连接数、5xx、配置语法检查（通过 nginx_diagnose 工具），输出根因与优化建议
version: 1.0.0
author: aiops
license: MIT
category: component
risk_level: read_only
keywords: ["Nginx", "连接数", "5xx", "配置"]
tools_required: ["nginx_diagnose", "query_metrics", "query_logs", "query_alerts"]
---
# Nginx 智能运维诊断技能

## 目标
对 Nginx 进行健康巡检与故障诊断，定位连接压力、5xx 错误、配置异常。

## 执行步骤
1. **连接分析**: 用 `nginx_diagnose` action=conn 获取 TCP 连接数/ESTAB 状态，判断连接是否被打满。
2. **5xx 统计**: action=logs 统计 access.log 中 4xx/5xx 数量。
3. **配置检查**: action=config 执行 nginx -t 语法校验。
4. **关联分析**: 用 `query_logs` 检索错误日志、`query_metrics` 看资源、`query_alerts` 查告警。

## 输出格式
```markdown
### Nginx 状态
### 连接与错误
### 配置检查
### 根因与建议
```

## 禁止
- 不修改配置或重启服务（本技能只读）。
