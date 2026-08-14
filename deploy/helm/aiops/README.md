# AIOps Helm Chart

Kubernetes 生产部署。后端 + 前端(SPA)单镜像, 支持 SQLite(PVC)或 Postgres。

## 前置

- Kubernetes 1.19+(支持 networking.k8s.io/v1 Ingress)
- Helm 3+
- 已构建镜像: `docker build -t aiops:latest .`(需 Postgres 驱动时加 `--build-arg WITH_POSTGRES=1`)

## 安装

```bash
# SQLite 模式(开发/单机)
helm install aiops ./deploy/helm/aiops

# Postgres 生产模式
helm install aiops ./deploy/helm/aiops -f deploy/helm/aiops/values.prod.yaml
```

## 配置

| 参数 | 默认 | 说明 |
|------|------|------|
| `image.repository` / `image.tag` | aiops / latest | 镜像 |
| `replicaCount` | 1 | 副本数 |
| `env.AIOPS_DB_URL` | "" | 留空=SQLite; 填 Postgres/MySQL 连接串 |
| `env.AIOPS_TOOLBAG` | "" | "1" 启用工具二级延迟加载 |
| `postgres.enabled` | false | 内置 Postgres StatefulSet |
| `postgres.auth.password` | aiops-secret | **生产必须改** |
| `persistence.enabled` | true | SQLite 数据卷; Postgres 模式建议 false |
| `ingress.enabled` | false | 暴露外部访问 |
| `existingSecret` | "" | 已有密钥(优先于 `secret.*`) |

## 升级 / 回滚

```bash
helm upgrade aiops ./deploy/helm/aiops -f deploy/helm/aiops/values.prod.yaml
helm rollback aiops <版本号>
```

## 卸载

```bash
helm uninstall aiops
# 数据卷(PVC)默认保留, 需手动删除以彻底清理
kubectl delete pvc -l app.kubernetes.io/instance=aiops
```
