---
name: linux-server-ops
description: Linux 服务器智能运维专家：CPU/内存/磁盘/负载分析、进程异常诊断、内核参数检查，输出根因与优化建议
version: 1.0.0
author: aiops
license: MIT
category: component
risk_level: read_only
keywords: ["Linux", "服务器", "CPU", "内存", "磁盘", "进程", "巡检"]
tools_required: ["query_metrics", "query_logs", "query_alerts"]
---
# Linux 服务器智能运维技能

## 目标
对 Linux 服务器进行健康巡检与故障诊断，定位 CPU/内存/磁盘/负载异常、进程问题并给出优化建议。

## 执行步骤
1. **资源总览**: 用 `query_metrics` 读取 CPU 使用率、内存使用率、磁盘 IO/空间、Load Average，判断整体健康度。
2. **负载与瓶颈**: 若 Load Average 持续高于核数，用 CPU 指标区分 us/sy/wa；若 iowait 高则疑似磁盘瓶颈，若 sy 高则疑似系统调用/进程风暴。
3. **内存分析**: 检查内存使用率与 swap 使用, 判断是否内存不足导致 swap 抖动或 OOM 风险。
4. **磁盘水位**: 检查各挂载点空间与 inode，识别磁盘满风险(通常 >85% 告警)。
5. **进程异常定位**: 结合 `query_logs` 检索 `java`/`oom-killer`/`out of memory`/关键服务日志, 定位高耗进程或 OOM 事件。
6. **内核/配置检查**(可选): 检查 `sysctl` 关键参数(fs.file-max/net.core.somaxconn/tcp 相关)是否被调优或存在漂移。
7. **关联分析**: 用 `query_alerts` 查服务器资源告警。

## 输出格式
```markdown
### 服务器健康总览
- CPU/内存/磁盘/Load
### 瓶颈定位
- 负载构成 / swap / 磁盘
### 进程与事件
- 高耗进程 / OOM
### 根因与建议
- 2-3 条优化建议（扩容/清理/调内核参数/重启服务）
```

## 禁止
- 不执行 kill/rm/重启等写操作（本技能只读诊断）。
- 不编造资源/进程数据，必须来自工具返回原文。
