# Kubernetes 生产环境运维故障排查手册

> 文档版本：v2.3 | 更新日期：2026-07-07 | 适用范围：AIOps 平台纳管的 K8s 生产集群
> 维护人：SRE 团队 | 关键词：Kubernetes、Pod、Deployment、故障排查、根因分析、CMDB、告警

---

## 1. 文档概述

本手册沉淀了 AIOps 平台在生产环境 Kubernetes 集群运维过程中积累的故障排查经验，覆盖 Pod 异常、工作负载故障、网络问题、存储故障、节点异常五大类常见场景。每个场景包含故障现象、根因分析方法、处置步骤和预防措施，可作为 SRE 值班人员的快速参考 Runbook。

本手册遵循 AIOps 平台的三层纳管模型：持久化 CI（Cluster/Node/Namespace/Deployment/Service/Ingress/PV/PVC）、弱纳管 CI（ConfigMap/Secret，只存引用关系不入内容）、实时视图（Pod/ReplicaSet，不入库聚合到工作负载）。排查时优先从工作负载层入手，结合 Pod 实时视图定位具体实例。

---

## 2. Pod 异常状态排查

### 2.1 Pod 处于 Pending 状态

**故障现象**：`kubectl get pods` 显示 Pod 长期处于 Pending 状态，未调度到任何节点。

**常见根因**：
- 资源不足：集群节点 CPU/内存资源无法满足 Pod 的 requests 声明
- 节点污点（Taint）未容忍：Pod 没有配置相应的 tolerations
- 节点选择器（NodeSelector）或节点亲和性（NodeAffinity）不匹配
- PodDisruptionBudget 限制：驱逐导致无法调度
- 持久卷声明（PVC）未绑定：等待 PV 满足

**排查步骤**：
1. 执行 `kubectl describe pod <pod-name> -n <namespace>` 查看 Events 部分
2. 关注 FailedScheduling 事件，确认具体原因
3. 若是资源不足：`kubectl top nodes` 查看节点资源使用率，考虑扩容节点或降低 Pod requests
4. 若是污点问题：`kubectl get nodes -o custom-columns=NAME:.metadata.name,TAINTS:.spec.taints` 检查节点污点
5. 若是 PVC 未绑定：`kubectl get pvc -n <namespace>` 检查 PVC 状态，确认 StorageClass 和 PV 可用性

**AIOps 平台定位**：在工作负载详情页查看 pod_summary 概要（total/running/pending/failed/restarts），pending 数大于 0 时触发告警，可在拓扑图中点击工作负载节点查看异常详情。

**处置示例**：
```bash
# 查看调度失败原因
kubectl describe pod api-server-7d8f-abcde -n production | grep -A 10 Events

# 节点资源概览
kubectl top nodes --sort-by=memory

# 修改 Deployment 的 resources.requests 降低资源需求
kubectl set resources deployment api-server -n production \
  --requests=cpu=200m,memory=256Mi --limits=cpu=500m,memory=512Mi
```

**预防措施**：在 CMDB 中维护节点容量元数据（cpu/memory/capacity），AIOps 平台基于拓扑关系预测资源瓶颈，提前触发容量告警。

### 2.2 Pod 处于 CrashLoopBackOff 状态

**故障现象**：Pod 反复启动后崩溃，状态在 CrashLoopBackOff 和 Running 之间循环，restarts 计数持续增长。

**常见根因**：
- 应用启动失败：配置错误、依赖服务不可达、数据库连接超时
- 健康检查失败：livenessProbe 配置过于敏感，应用未就绪即被重启
- 镜像问题：镜像 tag 错误、镜像损坏、entrypoint 命令错误
- 资源限制过严：memory limit 过低导致 OOMKilled
- 权限问题：ServiceAccount 权限不足、RBAC 配置错误

**排查步骤**：
1. 执行 `kubectl logs <pod-name> -n <namespace> --previous` 查看上一次崩溃的日志
2. 执行 `kubectl describe pod <pod-name> -n <namespace>` 查看 Last State 和 Exit Code
3. Exit Code 137 表示 OOMKilled，需检查内存 limit
4. Exit Code 1 通常为应用异常，需分析日志堆栈
5. 若是健康检查问题：调整 livenessProbe 的 initialDelaySeconds 和 failureThreshold

**AIOps 平台定位**：通过 Pod 实时视图查看 restarts 计数，restarts > 5 触发严重告警。结合日志中心检索崩溃前的错误日志，关联同一工作负载的其他 Pod 是否同时异常（判断是否为应用版本问题）。

**处置示例**：
```bash
# 查看崩溃容器上次日志
kubectl logs payment-svc-6f7g-xyz -n production --previous --tail=100

# 检查 OOM
kubectl describe pod payment-svc-6f7g-xyz -n production | grep -E "Last State|Exit Code|Reason"

# 临时关闭 livenessProbe 排查（修改 Deployment）
kubectl patch deployment payment-svc -n production --type=json \
  -p='[{"op":"remove","path":"/spec/template/spec/containers/0/livenessProbe"}]'
```

**预防措施**：应用启动阶段增加 readinessProbe，livenessProbe 的 initialDelaySeconds 设置为应用典型启动时间的 2 倍以上。生产环境建议配置 preStop hook 优雅退出。

### 2.3 Pod 处于 ImagePullBackOff 状态

**故障现象**：Pod 无法拉取镜像，状态为 ImagePullBackOff 或 ErrImagePull。

**常见根因**：
- 镜像仓库认证失败：imagePullSecrets 未配置或凭证过期
- 镜像不存在：tag 拼写错误、镜像未推送、仓库被清理
- 网络问题：节点无法访问镜像仓库（防火墙、DNS、网络策略）
- 镜像仓库限流：Docker Hub 等公共仓库的拉取速率限制

**排查步骤**：
1. `kubectl describe pod <pod-name> -n <namespace>` 查看 Events 中的 Failed 错误
2. 确认镜像名和 tag：`kubectl get pod <pod-name> -n <namespace> -o jsonpath='{.spec.containers[*].image}'`
3. 在节点上手动拉取测试：`docker pull <image>` 或 `crictl pull <image>`
4. 检查 imagePullSecrets：`kubectl get secret <secret-name> -n <namespace> -o yaml`
5. 检查节点到仓库的网络连通性：`telnet registry.example.com 443`

**AIOps 平台定位**：ConfigMap/Secret 采用弱纳管模式，只存引用关系不存内容。在拓扑图中可查看 Deployment 引用了哪些 imagePullSecret，快速定位凭证问题。孤岛 Secret（无任何 Pod 引用）可能是废弃凭证，需清理。

**处置示例**：
```bash
# 重新创建 imagePullSecret
kubectl create secret docker-registry regcred \
  --docker-server=registry.example.com \
  --docker-username=ops \
  --docker-password='xxx' \
  -n production

# 更新 Deployment 引用
kubectl patch deployment api-server -n production \
  -p='{"spec":{"template":{"spec":{"imagePullSecrets":[{"name":"regcred"}]}}}}'
```

---

## 3. 工作负载故障排查

### 3.1 Deployment 滚动更新卡死

**故障现象**：执行 `kubectl rollout` 后，新 Pod 无法就绪，旧 Pod 一直保留，滚动更新停滞。

**常见根因**：
- readinessProbe 失败：新版本应用启动慢或健康检查接口异常
- 资源不足：新 Pod Pending，无法调度
- 策略配置不当：maxSurge 和 maxUnavailable 设置导致无法创建新 Pod
- 应用启动依赖：依赖的配置中心、数据库未就绪

**排查步骤**：
1. `kubectl rollout status deployment/<name> -n <namespace>` 查看滚动状态
2. `kubectl get rs -n <namespace>` 查看新旧 ReplicaSet 副本数
3. 检查新 Pod 事件和日志
4. 确认 readinessProbe 配置：`kubectl get deploy <name> -n <namespace> -o jsonpath='{.spec.template.spec.containers[*].readinessProbe}'`

**AIOps 平台定位**：Deployment 详情页显示 available/replicas 比值，available < replicas 持续超过 5 分钟触发告警。结合发布引擎的金丝雀发布功能，可逐步提升新版本副本数，降低滚动更新风险。

**处置示例**：
```bash
# 查看滚动状态
kubectl rollout status deployment order-service -n production

# 回滚到上一版本
kubectl rollout undo deployment order-service -n production

# 回滚到指定版本
kubectl rollout undo deployment order-service -n production --to-revision=3

# 暂停滚动更新（排查问题）
kubectl rollout pause deployment order-service -n production

# 恢复滚动更新
kubectl rollout resume deployment order-service -n production
```

**预防措施**：生产环境滚动更新配置 maxSurge=1, maxUnavailable=0，保证始终有可用副本。配置 progressDeadlineSeconds（默认 600s），超时自动标记为失败。

### 3.2 StatefulSet 脑裂问题

**故障现象**：StatefulSet 管理的有状态应用（如 MySQL、Redis、Kafka）出现多个 master 节点，数据不一致。

**常见根因**：
- 网络分区导致 Pod 无法通信，各自选举为 master
- node 不可达后 Pod 重新调度，但旧 Pod 未完全退出（双重调度）
- 持久卷数据损坏导致状态不一致

**排查步骤**：
1. `kubectl get pods -n <namespace> -l app=<app-name> -o wide` 查看所有 Pod 调度节点
2. 检查 Pod 反亲和性配置，确保分散调度
3. 检查 Pod 的 terminationGracePeriodSeconds，有状态应用建议设置较长（30s-300s）
4. 通过应用层工具确认主从关系（如 Redis 的 CLUSTER NODES、MySQL 的 SHOW SLAVE STATUS）

**AIOps 平台定位**：StatefulSet 在三层纳管模型中属于持久化 CI，拓扑图显示其 pod_summary。若 running=0 且 failed>0，标记为异常节点（红色边框）。结合根因分析模块沿拓扑路径传播告警分数，定位是节点故障还是应用故障。

**处置示例**：
```bash
# 强制删除卡住的 Pod（谨慎，确认旧 Pod 已无法访问）
kubectl delete pod redis-master-0 -n production --grace-period=0 --force

# 检查 PVC 绑定状态（StatefulSet 的 PVC 是静态绑定，不会随 Pod 删除）
kubectl get pvc -n production -l app=redis

# 数据修复后重建从节点
kubectl delete pod redis-slave-0 -n production  # 让 StatefulSet 重新拉起
```

**预防措施**：有状态应用必须配置 PodAntiAffinity，确保 master 和 slave 调度到不同节点。生产环境启用 PodDisruptionBudget，限制并发驱逐。

---

## 4. 网络故障排查

### 4.1 Service 无法访问

**故障现象**：通过 Service ClusterIP 或 DNS 名称无法访问后端 Pod，请求超时或连接拒绝。

**常见根因**：
- Endpoints 为空：Service 的 selector 与 Pod 标签不匹配
- Pod 未就绪：readinessProbe 失败导致 Pod 不在 Endpoints 中
- 网络策略（NetworkPolicy）限制：禁止了特定命名空间的访问
- kube-proxy 异常：节点上的 iptables/ipvs 规则未正确同步
- CoreDNS 异常：服务发现失败

**排查步骤**：
1. `kubectl get endpoints <service-name> -n <namespace>` 检查 Endpoints 是否为空
2. 若为空：对比 Service selector 和 Pod labels，`kubectl get pods -n <namespace> --show-labels`
3. `kubectl describe service <service-name> -n <namespace>` 查看配置
4. 在 Pod 内测试：`kubectl exec -it <pod> -- nslookup <service-name>` 和 `curl <service-name>:<port>`
5. 检查网络策略：`kubectl get networkpolicy -n <namespace>`
6. 检查 kube-proxy：`kubectl logs -n kube-system <kube-proxy-pod>`

**AIOps 平台定位**：Service 在拓扑图中通过 selects 边关联到 Deployment，若 Deployment 的 pod_summary 显示 running=0，则 Service 的 Endpoints 必然为空，可快速定位为工作负载问题而非网络问题。拓扑图的引用关系可追溯 Service → Deployment → ConfigMap/Secret 的完整依赖链。

**处置示例**：
```bash
# 检查 Endpoints
kubectl get endpoints api-service -n production

# 修正 selector（标签不匹配）
kubectl patch service api-service -n production \
  -p='{"spec":{"selector":{"app":"api-server","version":"v2"}}}'

# 测试服务发现
kubectl run debug --image=busybox -it --rm --restart=Never -- \
  nslookup api-service.production.svc.cluster.local

# 临时绕过 NetworkPolicy
kubectl delete networkpolicy default-deny -n production
```

### 4.2 Ingress 502/504 错误

**故障现象**：通过 Ingress 访问服务时返回 502 Bad Gateway 或 504 Gateway Timeout。

**常见根因**：
- 后端 Service 无可用 Endpoints
- Ingress Controller 与后端 Pod 通信超时
- 后端应用响应过慢，超过 Ingress 的超时配置
- TLS 证书问题：443 端口证书过期或不匹配
- Ingress 规则配置错误：path 或 host 不匹配

**排查步骤**：
1. 检查 Ingress 规则：`kubectl get ingress -n <namespace> -o yaml`
2. 确认后端 Service 和 Endpoints：`kubectl get svc,Endpoints -n <namespace>`
3. 查看 Ingress Controller 日志：`kubectl logs -n ingress-nginx <ingress-controller-pod>`
4. 测试后端直连：`kubectl exec -it <pod> -- curl -v http://<service-name>:<port>`
5. 检查 TLS 证书：`openssl s_client -connect <host>:443 -servername <host>`

**AIOps 平台定位**：Ingress 在拓扑图中通过 owns 边关联到 Namespace，可通过路径查询功能分析"Ingress → Service → Deployment → Pod"的完整调用链。证书管理可结合 SSL 证书 CI 类型，监控到期时间并提前告警。

**处置示例**：
```bash
# 调整 Ingress 超时配置
kubectl annotate ingress api-ingress -n production \
  nginx.ingress.kubernetes.io/proxy-connect-timeout="60" \
  nginx.ingress.kubernetes.io/proxy-read-timeout="300" \
  nginx.ingress.kubernetes.io/proxy-send-timeout="300"

# 更新 TLS 证书
kubectl create secret tls api-tls -n production \
  --cert=fullchain.pem --key=privkey.pem --dry-run=client -o yaml | kubectl apply -f -
```

---

## 5. 存储故障排查

### 5.1 PVC 挂载失败

**故障现象**：Pod 启动时卡在 ContainerCreating，事件显示无法挂载 PersistentVolumeClaim。

**常见根因**：
- PVC 处于 Pending 状态：无可用 PV 满足 StorageClass 和容量需求
- 存储后端故障：NFS 服务器宕机、Ceph 集群异常、云盘不可用
- 节点未安装存储插件：CSI driver 未部署或未就绪
- 文件系统错误：ext4/xfs 损坏，需 fsck 修复
- 多节点写冲突：RWO 模式的 PV 被多个节点同时挂载

**排查步骤**：
1. `kubectl get pvc -n <namespace>` 检查 PVC 状态
2. `kubectl describe pvc <pvc-name> -n <namespace>` 查看 Events
3. 若 Pending：检查 StorageClass `kubectl get storageclass` 和 PV `kubectl get pv`
4. 在节点上检查存储连通性：`showmount -e <nfs-server>` 或 `rbd info <pool>/<image>`
5. 检查 CSI 插件：`kubectl get pods -n kube-system | grep csi`

**AIOps 平台定位**：PVC 在三层纳管模型中属于持久化 CI，但采用弱引用模式记录 referenced_by（被哪些 Deployment 引用）。孤岛 PVC（无任何 Pod 引用）可能是废弃资源，需评估清理。PV 作为集群级 CI 纳管，记录 capacity 和 storage_class。

**处置示例**：
```bash
# 查看存储类和可用 PV
kubectl get storageclass
kubectl get pv --sort-by=.spec.capacity.storage

# 手动创建 PV 绑定（静态供给）
kubectl apply -f - <<EOF
apiVersion: v1
kind: PersistentVolume
metadata:
  name: pv-data-01
spec:
  capacity:
    storage: 100Gi
  accessModes: ["ReadWriteOnce"]
  persistentVolumeReclaimPolicy: Retain
  storageClassName: nfs
  nfs:
    server: 10.0.7.10
    path: /export/data-01
EOF

# 修复文件系统（在存储服务器上）
umount /export/data-01
fsck.ext4 -y /dev/sdb1
mount /export/data-01
```

### 5.2 存储容量耗尽

**故障现象**：应用写入失败，日志显示 "No space left on device" 或磁盘只读。

**常见根因**：
- 日志文件未轮转，占满存储
- 应用生成大量临时文件未清理
- 监控指标数据（Prometheus TSDB）膨胀
- 镜像层堆积，节点磁盘耗尽
- 存储后端配额用尽（如 Ceph pool 满）

**排查步骤**：
1. 在节点上检查磁盘：`df -h` 和 `du -sh /* | sort -rh | head`
2. 检查容器日志大小：`du -sh /var/log/containers/*`
3. 检查镜像占用：`crictl images` 和 `du -sh /var/lib/containerd`
4. 检查 PVC 使用率：在存储后端查看（如 Ceph 的 `ceph df`、NFS 的 `df -h`）
5. 检查应用日志轮转配置

**AIOps 平台定位**：AIOps 监控模块采集节点磁盘使用率指标，超过 85% 触发 warning，超过 95% 触发 critical。结合剩余寿命预测算法（线性回归斜率推算至阈值时间），提前预警容量瓶颈。

**处置示例**：
```bash
# 清理已退出的容器（containerd）
crictl rmi --prune

# 清理悬挂镜像
docker image prune -a --filter "until=72h"

# 配置容器日志轮转（/etc/containerd/config.toml）
[plugins."io.containerd.grpc.v1.cri".containerd]
  max_log_size = "100Mi"
  max_log_files = 5

# 扩容 PVC（需存储后端支持动态扩容）
kubectl patch pvc data-pvc -n production \
  -p='{"spec":{"resources":{"requests":{"storage":"200Gi"}}}}'
```

**预防措施**：生产环境配置日志轮转（max_log_size + max_log_files），定期清理悬挂镜像。关键数据卷配置告警阈值，AIOps 平台自动触发扩容工作流。

---

## 6. 节点异常排查

### 6.1 节点 NotReady

**故障现象**：`kubectl get nodes` 显示节点为 NotReady 状态，Pod 被驱逐。

**常见根因**：
- kubelet 异常：kubelet 进程崩溃、证书过期、与 API Server 通信失败
- 节点资源耗尽：内存不足导致 OOM，磁盘满导致 kubelet 无法写入
- 容器运行时异常：containerd/docker 服务停止
- 网络分区：节点与控制面网络中断
- 硬件故障：磁盘损坏、内存故障、网卡故障

**排查步骤**：
1. `kubectl describe node <node-name>` 查看 Conditions 部分
2. SSH 登录节点检查 kubelet：`systemctl status kubelet` 和 `journalctl -u kubelet --since "10 minutes ago"`
3. 检查容器运行时：`systemctl status containerd` 或 `systemctl status docker`
4. 检查资源：`free -h`、`df -h`、`top`
5. 检查 kubelet 证书：`openssl x509 -in /var/lib/kubelet/pki/kubelet.crt -noout -dates`

**AIOps 平台定位**：Node 在三层纳管模型中属于持久化 CI，记录 kubelet_version、os_image、cpu、memory、node_status 等属性。拓扑图中 Node 通过 owns 边关联到 Cluster，NotReady 节点标记为异常（红色边框）。根因分析模块沿拓扑路径传播，若多个 Pod 同时异常且都调度在同一 NotReady 节点，可快速定位为节点问题。

**处置示例**：
```bash
# 重启 kubelet
systemctl restart kubelet

# 重启容器运行时
systemctl restart containerd

# 驱逐节点上的 Pod（维护模式）
kubectl drain node-worker-03 --ignore-daemonsets --delete-emptydir-data

# 恢复节点
kubectl uncordon node-worker-03

# 更新 kubelet 证书（证书过期场景）
rm /var/lib/kubelet/pki/kubelet.*
systemctl restart kubelet
```

### 6.2 节点资源压力（MemoryPressure/DiskPressure）

**故障现象**：节点状态条件显示 MemoryPressure 或 DiskPressure 为 True，Pod 被驱逐。

**常见根因**：
- 内存泄漏：应用持续占用内存不释放
- 资源超卖：节点上 Pod 的 requests 总和超过节点容量
- 磁盘日志堆积：容器日志、镜像层、emptyDir 卷占满磁盘
- 系统进程占用：内核、kubelet、容器运行时自身消耗

**排查步骤**：
1. `kubectl describe node <node-name> | grep -A 5 Conditions` 查看压力状态
2. `kubectl describe node <node-name> | grep -A 10 Allocated` 查看资源分配
3. 在节点上定位内存消耗：`ps aux --sort=-%mem | head -20`
4. 定位磁盘消耗：`du -sh /var/lib/containerd /var/log/containers /var/lib/kubelet`
5. 检查驱逐阈值配置：`grep eviction /var/lib/kubelet/config.yaml`

**AIOps 平台定位**：AIOps 监控模块采集节点的 CPU/内存/磁盘指标，结合趋势预测算法提前预警。根因分析模块关联同一节点上的 Pod 告警，若多个 Pod OOM 且节点 MemoryPressure，定位为节点级问题而非单个应用问题。

**处置示例**：
```bash
# 查看节点上的资源占用 Top Pod
kubectl top pods -n production --sort-by=memory --field-selector spec.nodeName=node-worker-03

# 驱逐高内存 Pod（谨慎，确保有副本在其他节点）
kubectl delete pod memory-hog-xxx -n production

# 清理容器日志
find /var/log/containers -name "*.log" -mtime +7 -delete

# 调整驱逐阈值（软驱逐，给应用优雅退出时间）
# /var/lib/kubelet/config.yaml
evictionSoft:
  memory.available: "500Mi"
  nodefs.available: "10%"
evictionSoftGracePeriod:
  memory.available: "1m30s"
  nodefs.available: "2m"
```

**预防措施**：所有生产 Pod 必须设置 resources.requests 和 limits，避免超卖。配置 HorizontalPodAutoscaler 根据负载自动扩缩容。节点预留系统资源（kube-reserved 和 system-reserved）。

---

## 7. AIOps 平台联动排查

### 7.1 告警关联分析

AIOps 平台的告警中心聚合来自 Prometheus、K8s Events、应用日志的多源告警，通过拓扑关系进行关联分析：

- **同一工作负载多 Pod 告警**：若同一 Deployment 下的多个 Pod 同时告警，定位为应用版本问题，触发回滚工作流
- **同一节点多 Pod 告警**：若不同 Deployment 的 Pod 在同一节点同时异常，定位为节点故障，触发节点驱逐
- **拓扑路径传播**：沿 Cluster → Namespace → Deployment → Pod 的 ownership 链传播告警严重度分数，根因节点分数最高
- **依赖关系追溯**：ConfigMap/Secret 变更后，通过 referenced_by 关系找到受影响的 Deployment，主动触发健康检查

### 7.2 根因分析引擎

AIOps 根因分析引擎基于拓扑图执行 BFS/DFS 遍历，结合告警时间窗口和资源指标异常检测：

1. **告警去噪**：同一资源 5 分钟内的重复告警合并，降低噪音
2. **拓扑传播**：告警严重度沿 ownership 边向上传播，父节点分数 = max(子节点分数) + 衰减因子
3. **异常指标关联**：检索告警时间窗口内的异常指标（Z-score > 3），按异常程度排序
4. **知识库匹配**：将告警特征向量化，在 RAG 知识库中检索相似历史案例，推荐处置方案
5. **根因排序**：综合拓扑分数、指标异常度、历史案例匹配度，输出 Top-3 根因候选

### 7.3 自动化处置工作流

AIOps 平台支持 SOP 工作流引擎，将人工排查经验固化为自动化剧本：

- **Pod 重启工作流**：检测到 CrashLoopBackOff → 拉取上次日志 → 匹配知识库 → 执行重启或回滚
- **节点恢复工作流**：检测到 NotReady → SSH 检查 kubelet → 重启服务 → 验证恢复 → 通知值班人员
- **扩缩容工作流**：检测到 CPU 持续高于 80% → 计算目标副本数 → 执行 kubectl scale → 验证负载分散
- **存储扩容工作流**：检测到 PVC 使用率 > 90% → 评估存储后端容量 → 执行 PVC 扩容 → 验证应用写入

工作流执行采用 DAG 拓扑排序，支持条件分支和人工确认节点（写操作需确认后执行），全程审计记录。

---

## 8. 附录

### 8.1 常用 Kubectl 速查

| 场景 | 命令 |
|------|------|
| 查看 Pod 详情 | `kubectl describe pod <name> -n <ns>` |
| 查看 Pod 日志 | `kubectl logs <name> -n <ns> --tail=200 -f` |
| 查看上次崩溃日志 | `kubectl logs <name> -n <ns> --previous` |
| 进入容器终端 | `kubectl exec -it <name> -n <ns> -- sh` |
| 端口转发 | `kubectl port-forward svc/<name> 8080:80 -n <ns>` |
| 节点资源 | `kubectl top nodes` |
| Pod 资源 | `kubectl top pods -n <ns> --sort-by=cpu` |
| 滚动状态 | `kubectl rollout status deploy/<name> -n <ns>` |
| 回滚 | `kubectl rollout undo deploy/<name> -n <ns>` |
| 驱逐节点 | `kubectl drain <node> --ignore-daemonsets --delete-emptydir-data` |

### 8.2 AIOps 平台三层纳管模型对照

| 纳管层级 | CI 类型 | 入库策略 | 拓扑展现 |
|---------|---------|---------|---------|
| 持久化 CI | Cluster/Node/Namespace/Deployment/StatefulSet/DaemonSet/Service/Ingress/PV/PVC | 全属性入库 | 独立节点，owns 边关联 |
| 弱纳管 CI | ConfigMap/Secret | 只存引用关系，不存数据内容 | 独立节点，references 边关联 |
| 实时视图 | Pod/ReplicaSet/Container | 不入库，聚合到工作负载 attrs.pod_summary | 工作负载节点的概要标签 |

### 8.3 告警严重度分级

| 级别 | 触发条件 | 响应时效 | 通知方式 |
|------|---------|---------|---------|
| P0 Critical | 核心服务宕机、数据丢失风险 | 5 分钟 | 电话 + 短信 + 钉钉 |
| P1 High | 单节点故障、Pod 大量重启 | 15 分钟 | 短信 + 钉钉 |
| P2 Medium | 资源水位告警、慢查询 | 1 小时 | 钉钉 |
| P3 Low | 日志告警、配置变更 | 4 小时 | 邮件 |

### 8.4 联系方式

- SRE 值班电话：400-xxx-xxxx（7x24）
- SRE 钉钉群：AIOps 生产运维
- 升级路径：值班 SRE → SRE Lead → 架构组 → CTO
- 灾难恢复：参考《AIOps 灾难恢复手册 v3.0》

---

## 9. 变更记录

| 日期 | 版本 | 变更内容 | 变更人 |
|------|------|---------|--------|
| 2026-07-07 | v2.3 | 新增三层纳管模型联动说明、自动化处置工作流章节 | SRE 团队 |
| 2026-06-15 | v2.2 | 补充 StatefulSet 脑裂排查、Ingress 超时配置 | 张三 |
| 2026-05-20 | v2.1 | 新增存储容量耗尽场景、节点资源压力排查 | 李四 |
| 2026-04-10 | v2.0 | 整合 AIOps 平台联动排查，重构文档结构 | SRE 团队 |
| 2026-03-01 | v1.0 | 初版发布 | 王五 |

---

*本文档由 AIOps 平台知识库管理系统管理，可通过 RAG 检索引擎语义查询。文档切片大小 500 字符，重叠 100 字符，采用 TF-IDF 向量化，支持中英文混合分词检索。*
