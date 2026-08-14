#!/usr/bin/env bash
# ===== AIOps 部署公共函数库(install/upgrade/uninstall 共享) =====
# 用法: source "$(dirname "$0")/lib.sh"

set -euo pipefail

# 定位项目根(本文件位于 <root>/deploy/)
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
PROJECT_ROOT="$(cd "$SCRIPT_DIR/.." && pwd)"

cd "$PROJECT_ROOT"

# ── 颜色 ──
if [[ -t 1 ]]; then
  C_RED='\033[0;31m'; C_GREEN='\033[0;32m'; C_YELLOW='\033[0;33m'; C_CYAN='\033[0;36m'; C_NC='\033[0m'
else
  C_RED=''; C_GREEN=''; C_YELLOW=''; C_CYAN=''; C_NC=''
fi

info()  { echo -e "${C_CYAN}[INFO ]${C_NC} $*"; }
ok()    { echo -e "${C_GREEN}[ OK  ]${C_NC} $*"; }
warn()  { echo -e "${C_YELLOW}[WARN ]${C_NC} $*"; }
error() { echo -e "${C_RED}[ERROR]${C_NC} $*" >&2; }

# ── 预检: 依赖命令 ──
require_cmds() {
  local missing=0
  for c in "$@"; do
    if ! command -v "$c" >/dev/null 2>&1; then
      error "缺少命令: $c (请先安装)"
      missing=1
    fi
  done
  if [[ $missing -ne 0 ]]; then
    error "请安装缺失依赖后重试"
    return 1
  fi
  return 0
}

# ── 备份: 数据库 + 许可证(时间戳目录) ──
backup() {
  local stamp; stamp="$(date +%Y%m%d_%H%M%S)"
  local dest="$PROJECT_ROOT/backups/$stamp"
  mkdir -p "$dest"
  if [[ -f db/aiops.db ]]; then
    cp db/aiops.db "$dest/aiops.db"
    info "已备份数据库 -> $dest/aiops.db"
  else
    warn "未找到 db/aiops.db, 跳过数据库备份"
  fi
  if [[ -f license.lic ]]; then
    cp license.lic "$dest/license.lic"
    info "已备份许可证 -> $dest/license.lic"
  fi
  # 保留最近 10 份备份
  (cd backups 2>/dev/null && ls -1t | tail -n +11 | xargs -r rm -rf) || true
  echo "$dest"
}

# ── 健康等待: 轮询直到 compose 服务健康或超时 ──
wait_healthy() {
  local timeout="${1:-120}"
  local svc="${2:-aiops}"
  info "等待 $svc 就绪(最多 ${timeout}s)..."
  local waited=0
  while [[ $waited -lt $timeout ]]; do
    local status
    status="$(docker compose ps --format '{{.Service}} {{.Health}}' 2>/dev/null | awk -v s="$svc" '$1==s{print $2}')"
    if [[ "$status" == "healthy" ]]; then
      ok "$svc 已就绪"
      return 0
    fi
    sleep 3
    waited=$((waited + 3))
  done
  warn "等待 $svc 健康超时(可能仍在启动)。请稍后手动检查: docker compose ps"
  return 0
}
