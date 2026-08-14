#!/usr/bin/env bash
# ===== AIOps 卸载 =====
# 用法: bash deploy/uninstall.sh
# 默认: 停止并移除容器/镜像/网络, 保留数据库与日志(数据安全)
#   --purge    连数据库/日志/备份一起删除(不可恢复)
#   --backup   卸载前先备份(推荐)

set -euo pipefail
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
source "$SCRIPT_DIR/lib.sh"

PURGE=0; DO_BACKUP=0
for a in "$@"; do
  case "$a" in --purge) PURGE=1;; --backup) DO_BACKUP=1;; *) ;; esac
done

info "== AIOps 卸载 =="

# 可选备份
if [[ $DO_BACKUP -eq 1 ]]; then
  info "卸载前备份..."
  backup_dir="$(backup)"
  ok "备份: $backup_dir"
fi

# ── 停止并移除容器 ──
if docker compose ps >/dev/null 2>&1; then
  info "停止并移除容器..."
  docker compose down --remove-orphans
fi

# 清理镜像
if [[ $PURGE -eq 1 ]]; then
  info "删除 aiops 镜像..."
  docker image rm aiops:latest >/dev/null 2>&1 || true
fi

if [[ $PURGE -eq 1 ]]; then
  warn "PURGE 模式: 删除数据库/日志/备份(不可恢复)"
  rm -rf db backups logs
  warn "已删除数据目录"
else
  ok "已停止服务。数据库(db/)与日志(logs/)已保留"
  warn "如需彻底清理, 请执行: bash deploy/uninstall.sh --purge --backup"
fi
ok "卸载完成"
