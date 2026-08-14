#!/usr/bin/env bash
# ===== AIOps 一键安装 =====
# 用法: bash deploy/install.sh [--monitoring]
#   --monitoring  同时启动 Prometheus + Grafana 监控栈
# 依赖: docker, docker compose v2

set -euo pipefail
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
source "$SCRIPT_DIR/lib.sh"

ENABLE_MONITORING=0
if [[ "${1:-}" == "--monitoring" ]]; then ENABLE_MONITORING=1; fi

info "== AIOps 一键安装 =="
ok "项目根: $PROJECT_ROOT"

# ── 1. 预检 ──
if ! require_cmds docker; then exit 1; fi
if ! docker compose version >/dev/null 2>&1; then
  error "需要 docker compose (v2) 插件, 请升级 Docker"
  exit 1
fi
if docker info >/dev/null 2>&1; then
  ok "Docker 运行中"
else
  error "Docker 未运行/无权限, 请先启动 Docker"
  exit 1
fi

# ── 2. 环境文件 ──
if [[ ! -f .env ]]; then
  cp .env.example .env
  ok "已从 .env.example 生成 .env(可修改端口等)"
fi

# ── 3. 构建并启动 ──
COMPOSE_PROFILE=()
if [[ $ENABLE_MONITORING -eq 1 ]]; then
  COMPOSE_PROFILE=(--profile monitoring)
  info "启用监控栈(Prometheus + Grafana)"
fi

info "构建镜像(首次较慢, 含 torch CPU + 前端)..."
docker compose "${COMPOSE_PROFILE[@]}" build
info "启动服务..."
docker compose "${COMPOSE_PROFILE[@]}" up -d

wait_healthy 150 aiops

# ── 4. 输出访问信息 ──
PORT="$(awk -F= '/^AIOPS_PORT=/{print $2}' .env 2>/dev/null || echo 8000)"
if [[ -z "$PORT" ]]; then PORT=8000; fi
ok "AI 运维平台已就绪:"
echo "  Web:    http://localhost:${PORT}/"
echo "  登录:   admin / admin123 (请尽快修改)"
if [[ $ENABLE_MONITORING -eq 1 ]]; then
  echo "  Prometheus: http://localhost:9090"
  echo "  Grafana:    http://localhost:3000 (admin/见 .env GRAFANA_PASSWORD)"
fi
warn "首次启动会初始化数据库/嵌入模型, 请稍候"
