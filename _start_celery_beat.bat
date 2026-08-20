@echo off
rem 启动 Celery beat（阶段二：周期调度器）
rem 用法: _start_celery_beat.bat
cd /d %~dp0
start /b "" "python" -m celery -A app.celery_app beat --loglevel=info
