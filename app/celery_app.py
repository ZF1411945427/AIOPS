"""Celery 应用（阶段二：分布式任务队列）.

- broker: Redis（REDIS_URL，默认 redis://127.0.0.1:6379/0）
- backend: Redis（结果缓存，用于任务状态追踪）
- 采集/探活等重任务封装为 Celery task，由独立 worker 进程消费，
  支持多进程/多机横向扩展。
"""
from celery import Celery
from app.config import REDIS_URL

celery_app = Celery(
    "aiops",
    broker=REDIS_URL,
    backend=REDIS_URL,
    include=[
        "app.celery_tasks",
    ],
)

celery_app.conf.update(
    task_serializer="json",
    result_serializer="json",
    accept_content=["json"],
    timezone="Asia/Shanghai",
    enable_utc=True,
    task_track_started=True,
    task_acks_late=True,
    worker_prefetch_multiplier=1,
    broker_connection_retry_on_startup=True,
    task_default_queue="aiops.tasks",
)

# beat 定时调度：周期采集 / 资产探活
from celery.schedules import crontab

celery_app.conf.beat_schedule = {
    "datasource-scrape": {
        "task": "app.celery_tasks.scrape_all_sources_task",
        "schedule": 30.0,  # 每 30s 触发一轮
    },
    "asset-probe": {
        "task": "app.celery_tasks.probe_assets_task",
        "schedule": 60.0,  # 每 60s 触发一轮
    },
}
