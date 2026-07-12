# 资产字段规范契约（Single Source of Truth）

> **所有前后端、数据库的字段名必须以本文件为准。**
> 新增/修改 CI 类型或连接字段时，先改本文件，再同步前后端。
> 最后更新: 2026-07-12

---

## 一、CI 类型枚举（ci_type）

| ci_type 值 | 中文名 | 连接类型(connection_type) | 所属层 |
|---|---|---|---|
| `server` | 物理服务器 | ssh | 基础设施 |
| `virtual_machine` | 虚拟机 | ssh | 基础设施 |
| `cloud_host` | 云主机 | ssh | 云资源 |
| `kubernetes_cluster` | K8s 集群 | kubernetes | 云资源 |
| `network_device` | 网络设备 | snmp | 基础设施 |
| `switch` | 交换机 | snmp | 基础设施 |
| `router` | 路由器 | snmp | 基础设施 |
| `firewall` | 防火墙 | snmp | 基础设施 |
| `load_balancer` | 负载均衡 | snmp | 基础设施 |
| `storage_device` | 存储设备 | snmp | 基础设施 |
| `database` | 数据库 | database | 基础设施 |
| `middleware` | 中间件 | http | 基础设施 |
| `business_app` | 业务应用 | http | 业务层 |
| `api_service` | API 服务 | http | 业务层 |
| `ssl_certificate` | SSL 证书 | none | 业务层 |
| `dns_record` | DNS 记录 | none | 业务层 |
| `monitoring_endpoint` | 监控端点 | http | 业务层 |
| `node` | K8s 节点 | kubernetes | K8s 持久化 |
| `namespace` | 命名空间 | kubernetes | K8s 持久化 |
| `deployment` | Deployment | kubernetes | K8s 持久化 |
| `statefulset` | StatefulSet | kubernetes | K8s 持久化 |
| `daemonset` | DaemonSet | kubernetes | K8s 持久化 |
| `service` | Service | kubernetes | K8s 持久化 |
| `ingress` | Ingress | kubernetes | K8s 持久化 |
| `pv` | PV 存储卷 | kubernetes | K8s 持久化 |
| `pvc` | PVC 存储声明 | kubernetes | K8s 持久化 |
| `configmap` | ConfigMap | kubernetes | K8s 弱纳管 |
| `secret` | Secret | kubernetes | K8s 弱纳管 |

**规则：**
- `cluster` 是旧值，**已废弃**，统一用 `kubernetes_cluster`
- `pod` / `replicaset` 是实时视图，不入 Asset 表

---

## 二、连接配置字段（connection_config JSON）

每种 connection_type 在 `connection_config` JSON 中使用的字段名：

### 2.1 SSH（connection_type = "ssh"）

| 字段名 | 类型 | 默认值 | 说明 | 敏感 |
|---|---|---|---|---|
| `ssh_user` | string | "root" | 登录用户 | |
| `ssh_password` | string | "" | 登录密码 | ✅ |
| `ssh_port` | int | 22 | SSH 端口 | |
| `ssh_private_key` | string | "" | 私钥内容 | ✅ |

**适用 ci_type**: server, virtual_machine, cloud_host

### 2.2 Kubernetes（connection_type = "kubernetes"）

| 字段名 | 类型 | 默认值 | 说明 | 敏感 |
|---|---|---|---|---|
| `k8s_api_server` | string | "" | API Server 地址，如 https://1.2.3.4:6443 | |
| `k8s_token` | string | "" | ServiceAccount Bearer Token | ✅ |
| `k8s_namespace` | string | "" | 默认命名空间（可选） | |
| `kubeconfig` | string | "" | kubeconfig JSON（与 api_server/token 二选一） | ✅ |
| `verify_ssl` | bool | false | 是否验证 SSL 证书 | |

**适用 ci_type**: kubernetes_cluster, node, namespace, deployment, statefulset, daemonset, service, ingress, pv, pvc, configmap, secret

**规则：**
- ~~`api_server`~~ / ~~`token`~~ 已废弃，统一用 `k8s_api_server` / `k8s_token`
- `kubeconfig` 与 `k8s_api_server`+`k8s_token` 二选一，优先 kubeconfig

### 2.3 Database（connection_type = "database"）

| 字段名 | 类型 | 默认值 | 说明 | 敏感 |
|---|---|---|---|---|
| `db_type` | string | "mysql" | 数据库类型: mysql/postgresql/redis/mongodb/elasticsearch | |
| `db_port` | int | 3306 | 端口 | |
| `db_user` | string | "root" | 用户名 | |
| `db_password` | string | "" | 密码 | ✅ |
| `db_name` | string | "" | 数据库名（可选） | |

**适用 ci_type**: database

**规则：**
- ~~`db_subtype`~~ 已废弃，统一用 `db_type`
- `db_port` 默认值按 db_type 联动: mysql=3306, postgresql=5432, redis=6379, mongodb=27017, elasticsearch=9200

### 2.4 HTTP（connection_type = "http"）

| 字段名 | 类型 | 默认值 | 说明 | 敏感 |
|---|---|---|---|---|
| `http_url` | string | "" | 服务地址，如 https://api.example.com/health | |
| `http_auth` | string | "" | 认证模式: ""(无) / basic / bearer | |
| `http_credential` | string | "" | 凭据（用户名:密码 或 Token） | ✅ |

**适用 ci_type**: business_app, api_service, middleware, monitoring_endpoint

**规则：**
- ~~`app_url`~~ / ~~`app_auth`~~ / ~~`app_credential`~~ 已废弃，统一用 `http_url` / `http_auth` / `http_credential`
- ~~`http_user`~~ / ~~`http_password`~~ 已废弃，认证信息统一用 `http_auth` + `http_credential`
- `mw_subtype` / `mw_port` / `mw_admin_url` 不入 connection_config，存 `ci_attributes`

### 2.5 SNMP（connection_type = "snmp"）

| 字段名 | 类型 | 默认值 | 说明 | 敏感 |
|---|---|---|---|---|
| `snmp_community` | string | "public" | 社区名 | |
| `snmp_port` | int | 161 | 端口 | |
| `snmp_version` | string | "v2c" | 版本: v2c / v3 | |

**适用 ci_type**: network_device, switch, router, firewall, load_balancer, storage_device

**规则：**
- `snmp_version` 统一用 **`v2c`**（带 v 前缀），后端测试时需做 `version.lstrip("v")` 兼容
- ~~`community`~~ / ~~`port`~~ 已废弃，统一用 `snmp_community` / `snmp_port`

### 2.6 无连接（connection_type = "none"）

适用 ci_type: ssl_certificate, dns_record

不生成 connection_config，属性存 `ci_attributes`。

---

## 三、规格属性字段（ci_attributes JSON）

不入 connection_config 的业务属性，存 `ci_attributes`：

### 3.1 通用规格

| ci_type | 字段名 | 类型 | 说明 |
|---|---|---|---|
| server | cpu_cores | int | CPU 核心数 |
| server | memory_gb | int | 内存(GB) |
| server | disk_gb | int | 磁盘(GB) |
| server | os | string | 操作系统 |
| server | manufacturer | string | 厂商 |
| server | model | string | 型号 |
| virtual_machine | cpu_cores | int | vCPU |
| virtual_machine | memory_gb | int | 内存(GB) |
| virtual_machine | disk_gb | int | 系统盘(GB) |
| virtual_machine | os | string | 操作系统 |
| virtual_machine | hypervisor | string | 虚拟化平台 |
| cloud_host | cpu_cores | int | vCPU |
| cloud_host | memory_gb | int | 内存(GB) |
| cloud_host | disk_gb | int | 系统盘(GB) |
| cloud_host | cloud_provider | string | 云厂商 |
| cloud_host | instance_id | string | 实例 ID |
| kubernetes_cluster | version | string | K8s 版本 |
| kubernetes_cluster | node_count | int | 节点数 |

### 3.2 K8s 子资源属性

| ci_type | 字段名 | 说明 |
|---|---|---|
| node | kubelet_version | kubelet 版本 |
| node | os_image | OS 镜像 |
| node | cpu / memory | 容量 |
| node | node_status | Ready/NotReady |
| namespace | phase | 状态 |
| deployment/statefulset/daemonset | replicas | 副本数 |
| deployment/statefulset/daemonset | available | 就绪数 |
| deployment/statefulset/daemonset | pod_summary | Pod 概要 |
| service | cluster_ip | 集群 IP |
| service | type | Service 类型 |
| service | selector | 选择器 |
| configmap/secret/pvc | referenced_by | 引用者列表 |
| configmap/secret/pvc | orphan | 是否孤岛 |
| configmap/secret | data_keys | 键名列表 |

### 3.3 其他业务属性

| ci_type | 字段名 | 说明 |
|---|---|---|
| middleware | mw_subtype | 中间件类型: nginx/tomcat/rabbitmq/kafka |
| middleware | mw_port | 管理端口 |
| middleware | mw_admin_url | 管理地址 |
| storage_device | storage_type | 存储类型: nfs/san/nas/object |
| storage_device | storage_mount | 挂载路径 |
| storage_device | storage_capacity | 容量(TB) |
| ssl_certificate | cert_domain | 域名 |
| ssl_certificate | cert_issuer | 颁发者 |
| ssl_certificate | cert_expiry | 到期日期 |
| dns_record | dns_domain | 域名 |
| dns_record | dns_type | 记录类型: A/CNAME/MX/TXT |
| dns_record | dns_value | 记录值 |
| monitoring_endpoint | monitor_url | 探针地址 |
| monitoring_endpoint | monitor_type | 探针类型: prometheus/http/tcp/icmp |
| monitoring_endpoint | monitor_interval | 检查间隔(秒) |
| database | version | 数据库版本 |
| business_app | owner | 负责人 |
| api_service | owner | 负责人 |

---

## 四、资产主表字段（assets 表）

| 列名 | 类型 | 说明 |
|---|---|---|
| id | int PK | 自增主键 |
| name | string | 资产名称（K8s 子资源含 `/` 路径前缀） |
| type | string | 旧字段，值 = ci_type（兼容） |
| ci_type | string | CI 类型（见第一节） |
| ip | string | IP 或地址 |
| status | string | online / offline / degraded / deprecated |
| lifecycle_status | string | 生命周期（从 AssetLifecycle 表关联） |
| tags | string | 标签（逗号分隔或 JSON） |
| k8s_cluster | string | 所属 K8s 集群名（K8s 子资源用） |
| parent_id | int FK | 父资产 ID |
| connection_type | string | ssh / kubernetes / database / http / snmp / none |
| connection_config | JSON string | 连接配置（见第二节） |
| ci_attributes | JSON string | 规格属性（见第三节） |
| created_at | datetime | 创建时间 |
| last_checked | datetime | 最后检查时间 |
| latency_ms | int | 延迟(ms) |

---

## 五、敏感字段掩码规则

后端 `detail` 接口返回时，敏感字段用 `"***"` 掩码，同时返回 `has_<field>` 布尔标记：

| 字段 | 掩码标记 |
|---|---|
| ssh_password | has_ssh_password |
| ssh_private_key | has_ssh_private_key |
| k8s_token | has_k8s_token |
| kubeconfig | has_kubeconfig |
| db_password | has_db_password |
| http_credential | has_http_credential |

**前端编辑规则：**
- `openEdit` 加载后，所有密码字段置空（不显示 `***`）
- 保存时：密码字段为空 → 不更新（后端保留原值）；非空 → 更新
- 前端用 `has_*` 标记显示「已设置 / 未设置」提示

---

## 六、DataSource 表字段映射

`data_sources` 表的 `auth_config` JSON 字段名必须与 `connection_config` 保持一致：

| DataSource type | auth_config 字段 | 与 assets.connection_config 的关系 |
|---|---|---|
| kubernetes | k8s_api_server, k8s_token, verify_ssl | 完全一致 |
| ssh | ssh_user, ssh_password, ssh_port | 完全一致（不再用 username/password/port） |
| prometheus | endpoint | 直接用 data_sources.endpoint 列 |
| docker | docker_host | 独立字段 |

**规则：**
- DataSource.auth_config 不再使用 `username` / `password` / `port`，统一用 `ssh_*` 前缀
- 跨表复用连接配置时直接复制 JSON，无需字段映射

---

## 七、字段命名规范

1. **前缀即类型**：`ssh_*`、`k8s_*`、`db_*`、`http_*`、`snmp_*` 一目了然
2. **不缩写**：`password` 不写 `passwd`，`credential` 不写 `cred`
3. **snake_case**：全小写 + 下划线，前后端一致
4. **废弃字段标注**：本文件中 ~~删除线~~ 标注的字段为已废弃值，新代码不得使用
5. **单一数据源**：本文件是唯一权威，代码中不得自行发明字段名

---

## 八、AI 会话关联表字段规范

### 1. alert_session_links（告警-会话关联）

| 字段名 | 类型 | 说明 |
|---|---|---|
| id | int | 主键 |
| alert_id | int | 关联告警 ID (FK → alerts.id) |
| session_id | int | 关联会话 ID (FK → chat_sessions.id) |
| context_summary | text | 关联时的上下文摘要 |
| created_at | datetime | 创建时间 |

### 2. asset_session_links（资产-会话关联）

| 字段名 | 类型 | 说明 |
|---|---|---|
| id | int | 主键 |
| asset_id | int | 关联资产 ID (FK → assets.id) |
| session_id | int | 关联会话 ID (FK → chat_sessions.id) |
| context_summary | text | 关联时的上下文摘要 |
| created_at | datetime | 创建时间 |

### 3. chat_sessions.context（会话上下文 JSON）

用于存储当前会话关联的告警或资产 ID，Agent 在处理消息时会自动读取此字段注入 Prompt。

```json
{
  "alert_id": 42,
  "alert_metric": "cpu_usage",
  "alert_severity": "critical",
  "asset_id": 10,
  "asset_name": "web-server-01",
  "asset_ip": "192.168.1.100"
}
```

**更新逻辑：**
- 关联告警时：写入 `alert_id` + 告警元数据 + `asset_id`
- 关联资产时：写入 `asset_id` + 资产元数据（若已有 alert_id，清空告警上下文以避免冲突）
