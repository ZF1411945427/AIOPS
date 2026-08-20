"""Celery 分发辅助（阶段二）.

startup 后台服务通过本模块决定：任务走 Celery worker，还是回退进程内执行。

- AIOPS_CELERY_ENABLED=true 且 Redis 可达 → 投递 Celery 任务（分布式路径）
- 否则 --> 回退进程内执行（与改造前行为一致），保证 Redis 挂了不中断业务
"""
import os
import threading
from app.logger import logger

_CELERY_ENABLED = os.environ.get("AIOPS_CELERY_ENABLED", "false").lower() == "true"

# 惰性探测 Redis / Celery 可达性（缓存结果，定期重试）
_redis_available = None
_probe_lock = threading.Lock()
_last_probe = 0.0


def celery_enabled() -> bool:
    """返回是否应使用 Celery 分布式路径（开关开启 且 Redis 可达）。"""
    if not _CELERY_ENABLED:
        return False
    return _redis_ok()


def _redis_ok() -> bool:
    global _redis_available, _last_probe
    import time as _time
    now = _time.time()
    # 5s 内复用探测结果，避免每轮都连 Redis
    if _redis_available is not None and now - _last_probe < 5:
        return _redis_available
    with _probe_lock:
        if now - _last_probe < 5:
            return bool(_redis_available)
        _last_probe = now
        try:
            from app.config import REDIS_URL
            import redis as _redis
            r = _redis.Redis.from_url(REDIS_URL, socket_timeout=1.0)
            _redis_available = bool(r.ping())
        except Exception:
            _redis_available = False
        if not _redis_available:
            logger.warning("Redis 不可达，Celery 回退为进程内执行")
        return bool(_redis_available)


def dispatch(task_name: str, *args, **kwargs) -> bool:
    """投递 Celery 任务；不可用时返回 False（调用方回退进程内）."""
    try:
        from app.celery_app import celery_app
        celery_app.send_task(task_name, args=args, kwargs=kwargs)
        return True
    except Exception as e:
        logger.warning(f"Celery 投递失败({task_name})，回退进程内: {e}")
        return False
