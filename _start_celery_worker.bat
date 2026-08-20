@echo off
rem 启动 Celery worker（阶段二：分布式任务消费进程）
rem 用法: _start_celery_worker.bat [--pool solo]
cd /d %~dp0
set CELERY_BROKER=redis://127.0.0.1:6379/0
start /b "" "python" -m celery -A app.celery_app worker --loglevel=info --concurrency=4 --pool=solo
