# AIOps 一键交付（可部署性）

对标 Ongrid 的 `deploy/`(install.sh + upgrade.sh + docker-compose + prometheus/grafana provisioning)，本系统补齐了一整套交付能力。

## 快速开始

```bash
# 1. 预检: 需要 Docker + docker compose v2
docker --version
docker compose version

# 2. 一键安装(首次构建较慢, 含 torch CPU + 前端)
bash deploy/install.sh

# 3. 访问
#    Web: http://localhost:8000/  (admin/admin123)
```

携带监控栈（Prometheus 抓取本系统 `/metrics` + Grafana）：

```bash
bash deploy/install.sh --monitoring
# Prometheus: http://localhost:9090
# Grafana:    http://localhost:3000 (admin /.env GRAFANA_PASSWORD)
```

## 脚本

| 脚本 | 作用 |
|------|------|
| `deploy/install.sh` | 预检 Docker → 生成 .env → 构建镜像 → 启动 → 健康等待 → 输出访问信息 |
| `deploy/upgrade.sh` | 备份 db/许可证 → git pull → 重建 → 滚动重启；`--rollback` 回滚重启；`--no-git` 仅重建 |
| `deploy/uninstall.sh` | 停止并移除容器/镜像，保留数据；`--purge` 连数据删除；`--backup` 先备份 |
| `deploy/lib.sh` | 公共函数（备份/健康等待/颜色/预检） |
| `docker-compose.yml` | aiops 单服务 + 可选 monitoring profile(prometheus+grafana) |
| `Dockerfile` | 多阶段：vite 前端 + python:3.11 后端，torch CPU，健康检查 |
| `.env.example` | 部署环境变量样例（端口/Grafana 账号） |

## 数据与备份

- 数据库：`./db/aiops.db`（挂载卷持久化）
- 日志：`./logs/`
- 备份：`backups/`（`deploy/upgrade.sh` 与 `uninstall.sh --backup` 自动生成时间戳备份，保留最近 10 份）
- 许可证：`./license.lic`（只读挂载，可选）

## 监控

- 平台自暴露 `/metrics`（Prometheus text 格式，含 `aiops_http_request_count` / `aiops_*` 指标）
- `deploy/prometheus/prometheus.yml` 配置抓取 `aiops:8000/metrics`
- 启用监控栈后用 Grafana 导入即可可视化

## 在 Windows（非 Docker）运行

开发/单机可沿用原有方式：

```powershell
# 后端
python run.py
# 前端(dev)
npm run dev --prefix frontend
```
