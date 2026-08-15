---
name: k8s-smart-ops
description: Kubernetes 智能运维专家：Pod 故障诊断、Deployment/节点巡检、资源调度分析、事件关联，输出根因与处置建议
version: 1.0.0
author: aiops
license: MIT
category: component
risk_level: read_only
keywords: ["K8s", "Kubernetes", "Pod", "故障", "调度", "集群"]
tools_required: ["list_k8s_pods", "query_k8s_events", "query_metrics", "query_logs"]
---
# K8S 智能运维技能

## 目标
对 Kubernetes 集群进行健康巡检与故障诊断，定位 Pod 异常、资源调度、事件风暴问题并给出处置建议。

## 前置
- 目标集群资产需已登记并连通 K8s API(K8s 数据源或 `connection_config`)。

## 执行步骤
1. **Pod 状态巡检**: 用 `list_k8s_pods` 列出目标命名空间/集群的 Pod，按状态(Pending/CrashLoopBackOff/ImagePullBackOff/Error)筛选异常 Pod。
2. **事件关联**: 用 `query_k8s_events` 查询异常 Pod 相关的 K8s 事件(InsufficientMemory/FailedScheduling/LivenessProbe 等)，定位具体诱因。
3. **资源调度分析**: 结合 Pod Requests/Limits 与节点资源(`query_metrics` 节点 CPU/内存), 判断是否资源不足导致调度失败或驱逐。
4. **工作负载等级**: 判断是 Deployment/StatefulSet/DaemonSet 的副本异常，评估滚动更新失败或就绪探针问题。
5. **关联分析**: 用 `query_logs` 查看异常 Pod 容器日志, 用 `query_alerts` 查同期告警。

## 输出格式
```markdown
### 集群健康概览
- 异常 Pod 数 / 涉及工作负载
### 关键事件(TOP3)
### 资源分析
- 节点容量 / 请求 / 分配
### 根因与建议
- 2-3 条处置建议（补资源/调探针/回滚版本/排查镜像）
```

## 禁止
- 不执行任何 K8s 写操作(delete/apply/scale)（本技能只读诊断）。
- 不编造 Pod/事件数据，必须来自工具返回原文。
