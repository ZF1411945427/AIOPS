#!/usr/bin/env bash
# ===== AIOps 平滑升级 =====
# 用法: bash deploy/upgrade.sh [--monitoring]
# 流程: 备份 db/许可证 -> 拉取最新源码(git) -> 重建镜像 -> 滚动重启
#   --rollback  回滚到上一份备份的重启(不重建)
#   --no-git    跳过 git pull(仅重建当前源码)

set -euo pipefail
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
source "$SCRIPT_DIR/lib.sh"

ENABLE_MONITORING=0; ROLLBACK=0; NO_GIT=0
for a in "$@"; do
  case "$a" in
    --monitoring) ENABLE_MONITORING=1;;
    --rollback)   ROLLBACK=1;;
    --no-git)     NO_GIT=1;;
    *) ;;
  esac
done

COMPOSE_PROFILE=()
if [[ $ENABLE_MONITORING -eq 1 ]]; then COMPOSE_PROFILE=(--profile monitoring); fi

info "== AIOps 升级 =="

if [[ $ROLLBACK -eq 1 ]]; then
  info "回滚模式: 重新启动现有镜像(使用上一份完整镜像)"
  docker compose "${COMPOSE_PROFILE[@]}" up -d --no-build
  wait_healthy 120 aiops
  ok "已回滚(重启)到上一版本"
  exit 0
fi

# ── 1. 备份 ──
info "升级前备份..."
backup_dir="$(backup)"
ok "备份: $backup_dir"

# ── 2. 拉取最新源码 ──
if [[ $NO_GIT -eq 0 ]] && [[ -d .git ]]; then
  info "拉取最新源码..."
  git fetch --all --prune
  git pull --ff-only || { error "git pull 失败(可能本地有改动)。如需继续可用 --no-git"; exit 1; }
else
  warn "跳过 git pull"
fi

# ── 3. 重建并滚动重启 ──
info "重建镜像..."
docker compose "${COMPOSE_PROFILE[@]}" build
info "滚动重启服务(旧实例优雅退出, 新实例接管)..."
docker compose "${COMPOSE_PROFILE[@]}" up -d

wait_healthy 150 aiops
ok "升级完成"
warn "如需回滚: bash deploy/upgrade.sh --rollback (备份在 $backup_dir)"
