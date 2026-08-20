"""分布式冷却/节流缓存（阶段二）.

将原本"进程内 dict"的失败冷却、低频窗口等状态，升级为 Redis 共享缓存，
使多进程/多机 worker 之间冷却状态全局一致，避免同一资产被重复扫描。

- Redis 可用（默认）：写 Redis，跨进程共享
- Redis 不可用：优雅降级为进程内 dict（与改造前行为一致）
"""
import os
import time
import threading
from app.config import REDIS_URL, REDIS_COOLDOWN_DB


class CooldownCache:
    """带 Redis 后端、内存降级的冷却缓存。

    用法：
        cc = CooldownCache(prefix="scrape_fail", ttl=300)
        if cc.is_in_cooldown(key):
            return
        cc.mark(key)
    """

    def __init__(self, prefix: str, ttl: int):
        self.prefix = prefix
        self.ttl = ttl
        self._memory = {}  # key -> expire_ts
        self._lock = threading.Lock()
        self._redis = None
        self._redis_ok = False
        self._init_redis()

    def _init_redis(self):
        try:
            import redis as _redis
            url = REDIS_URL
            # 换到冷却专用 db
            base, _, _rest = url.rpartition("/")
            if _rest and _rest.isdigit() and int(_rest) != REDIS_COOLDOWN_DB:
                url = f"{base}/{REDIS_COOLDOWN_DB}"
            self._redis = _redis.Redis.from_url(url, socket_timeout=1.0)
            self._redis.ping()
            self._redis_ok = True
        except Exception:
            self._redis = None
            self._redis_ok = False

    def _key(self, key) -> str:
        return f"aiops:{self.prefix}:{key}"

    def is_in_cooldown(self, key) -> bool:
        """key 是否处于冷却期（未超时）。"""
        if self._redis_ok:
            try:
                return bool(self._redis.exists(self._key(key)))
            except Exception:
                pass
        with self._lock:
            exp = self._memory.get(key)
            if exp is None:
                return False
            if time.time() < exp:
                return True
            self._memory.pop(key, None)
            return False

    def mark(self, key) -> None:
        """记录进入冷却。"""
        if self._redis_ok:
            try:
                self._redis.setex(self._key(key), self.ttl, "1")
                return
            except Exception:
                pass
        with self._lock:
            self._memory[key] = time.time() + self.ttl
