"""进程内 TTL 缓存：用于仪表盘统计等高频查询，减少 DB 负载."""
from cachetools import TTLCache
import functools

_default_cache = TTLCache(maxsize=128, ttl=15)


def cached(ttl: int = 15, maxsize: int = 128):
    """装饰器：缓存函数返回值，TTL 默认 15 秒.

    用法：
        @cached(ttl=30)
        def get_dashboard_stats(db): ...
    """
    _cache = TTLCache(maxsize=maxsize, ttl=ttl)

    def decorator(func):
        @functools.wraps(func)
        def wrapper(*args, **kwargs):
            key = f"{func.__name__}:{hash(str(args) + str(sorted(kwargs.items())))}"
            if key in _cache:
                return _cache[key]
            result = func(*args, **kwargs)
            _cache[key] = result
            return result
        wrapper.cache_clear = _cache.clear
        return wrapper
    return decorator


def get_cache():
    return _default_cache
