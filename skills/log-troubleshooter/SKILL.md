---
name: log-troubleshooter
description: 日志异常排查专家：检索指定时间窗/关键词的日志，归纳异常模式并给出根因假设与下一步排查建议
version: 1.0.0
author: aiops
license: MIT
category: diagnosis
risk_level: read_only
keywords: ["日志", "log", "troubleshoot", "排查", "异常"]
tools_required: ["query_logs", "query_alerts", "query_metrics"]
---
# 日志异常排查技能

## 目标
定位某主机/服务在给定时间窗内日志中的异常模式，形成根因假设并给出可执行的排查建议。

## 输入约定
调用方应提供：时间窗（hours 或 start/end）、目标主机或服务（asset/host）、关键词（可选）。

## 执行步骤
1. 先用 `query_logs` 检索目标时间窗内该主机/服务的关键词命中日志（默认最近 1-3 小时，取前 50 条）。
2. 若命中日志量异常偏多，再用 `query_alerts` 查询同一资产在同期是否产生告警（severity=critical/warning）。
3. 若疑似资源型异常，再用 `query_metrics` 检查 CPU/内存/磁盘指标是否在同期异常（对比基线）。
4. 汇总分析：
   - 归类日志级别分布（error/warn/info），列出 TOP 错误日志原文（最多 3 条，原样引用）。
   - 判断是否与告警、指标异常同源（时间对齐）。
   - 给出 2-3 条根因假设（按可能性排序，说明依据）。
   - 给出下一步验证动作（如查看某配置、扩容、重启某组件），并注明风险。

## 输出格式
```markdown
### 异常定位
- 时间窗 / 对象 / 命中量
### 关键日志(TOP3)
### 关联告警与指标
### 根因假设
1. …
### 建议动作
- …
```

## 禁止
- 不编造日志内容，所有日志必须来自 query_logs 返回原文。
- 不执行任何写操作（本技能只读）。
