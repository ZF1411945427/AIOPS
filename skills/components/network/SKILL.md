---
name: network-smart-ops
description: 网络设备智能运维专家：交换机/路由器状态巡检、接口流量与错误、LLDP 邻居、链路故障诊断
version: 1.0.0
author: aiops
license: MIT
category: component
risk_level: read_only
keywords: ["网络", "交换机", "路由器", "LLDP", "接口", "链路"]
tools_required: ["net_device_query", "query_metrics", "query_alerts"]
---
# 网络设备智能运维技能

## 目标
对交换机/路由器等网络设备进行健康巡检与故障诊断，定位接口异常、链路故障、邻居消失问题。

## 前置
- 网络设备资产需已登记，支持 SSH 登录，或在 `connection_config` 配置了连接信息。

## 执行步骤
1. **设备状态**: 用 `net_device_query` 执行 `show version`/`display version` 读取设备型号、运行时长、版本、CPU/内存使用。
2. **接口巡检**: 执行 `show interfaces summary`(或 `show interfaces status`) 统计 up/down 接口, 找出 down 或错误包高的接口。
3. **错误包分析**: 对重点接口执行 `show interfaces <port>` 查看 input/output errors、CRC、discards, 判断是物理故障/光衰/协商问题。
4. **邻居巡检**: 执行 `show lldp neighbors`(或 `show cdp neighbors`) 核对邻居关系, 定位链路中断或邻居消失。
5. **协议状态**: 若为路由设备, 执行 `show bgp summary`/`show ospf neighbor` 检查路由协议与邻居状态。
6. **关联分析**: 用 `query_alerts` 查链路/接口告警确认。

## 输出格式
```markdown
### 设备概览
- 型号/运行时长/版本/负载
### 接口状态
- up/down 统计 / 异常接口
### 邻居与链路
- LLDP 邻居 / 断裂链路
### 根因与建议
- 2-3 条建议（更换光模块/检查协商/链路切换/端口开启）
```

## 禁止
- 不执行配置类命令(shutdown/no shutdown 等)写操作（本技能仅 show/display/get/ping 只读）。
