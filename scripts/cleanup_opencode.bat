@echo off
chcp 65001 >nul
echo ============================================
echo   opencode 历史数据清理
echo ============================================
echo.
echo 提示: VACUUM 压缩需要 opencode 已退出（无数据库连接占用）。
echo       若运行中清理报 "database is locked"，请先关闭 opencode 再运行。
echo.
pause
cd /d %~dp0
python cleanup_opencode.py %*
echo.
echo 清理完成。
pause
