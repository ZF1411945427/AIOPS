"""后台定时任务监控器（P1 任务#6）

为 `main.py:background_loop()` 中的 12 个定时服务提供可观测性：
- 每个任务的 `last_run_at / last_status / last_duration / error_count / next_run_at`
- 失败任务红色高亮
- 手动触发 / 暂停 / 恢复
- 健康摘要：失败率、平均耗时、最慢任务

设计要点：
- 单例 `task_monitor`，全局共享
- in-memory + threading.Lock，无需 DB 持久化
- 暂停状态：`enabled=False`，background_loop 跳过执行
- 手动触发：在独立线程执行一次，不阻塞主循环
"""

import threading
import time
from collections import deque
from datetime import datetime
from typing import Any, Callable, Dict, List, Optional

from app.logger import logger


# 任务最大历史记录条数
HISTORY_LIMIT = 20
# 任务失败时间窗口（用于计算失败率）
FAILURE_WINDOW_SEC = 3600


class TaskRecord:
    """单个后台任务的状态记录"""

    def __init__(self, name: str, fn: Optional[Callable] = None, description: str = ""):
        self.name = name
        self.fn = fn                                  # 任务可调用对象
        self.description = description
        self.enabled = True                            # 是否启用（暂停时为 False）
        self.last_run_at: Optional[float] = None
        self.last_status: str = "idle"                 # idle/running/success/failed/skipped
        self.last_duration_ms: float = 0.0
        self.last_error: Optional[str] = None
        self.success_count = 0
        self.failure_count = 0
        self.total_runs = 0
        self.history: deque = deque(maxlen=HISTORY_LIMIT)
        self._lock = threading.Lock()

    def record_start(self):
        with self._lock:
            self.last_status = "running"
            self.last_run_at = time.time()

    def record_success(self, duration_ms: float):
        with self._lock:
            self.last_status = "success"
            self.last_duration_ms = duration_ms
            self.last_error = None
            self.success_count += 1
            self.total_runs += 1
            self.history.append({
                "at": datetime.now().isoformat(),
                "status": "success",
                "duration_ms": round(duration_ms, 1),
            })

    def record_failure(self, duration_ms: float, error: str):
        with self._lock:
            self.last_status = "failed"
            self.last_duration_ms = duration_ms
            self.last_error = error[:300] if error else ""
            self.failure_count += 1
            self.total_runs += 1
            self.history.append({
                "at": datetime.now().isoformat(),
                "status": "failed",
                "duration_ms": round(duration_ms, 1),
                "error": self.last_error,
            })

    def record_skip(self, reason: str = "paused"):
        with self._lock:
            self.last_status = "skipped"
            self.last_error = reason

    def to_dict(self) -> Dict[str, Any]:
        with self._lock:
            now = time.time()
            next_run_at = None
            if self.enabled and self.last_run_at:
                # 假设按 BACKGROUND_INTERVAL 周期执行
                from app.services.background_task_monitor import task_monitor
                next_ts = self.last_run_at + task_monitor.interval_seconds
                next_run_at = datetime.fromtimestamp(next_ts).isoformat() if next_ts > now else "即将执行"
            avg_dur = sum(h["duration_ms"] for h in self.history) / len(self.history) if self.history else 0
            return {
                "name": self.name,
                "description": self.description,
                "enabled": self.enabled,
                "last_run_at": datetime.fromtimestamp(self.last_run_at).isoformat() if self.last_run_at else None,
                "last_status": self.last_status,
                "last_duration_ms": round(self.last_duration_ms, 1),
                "last_error": self.last_error,
                "success_count": self.success_count,
                "failure_count": self.failure_count,
                "total_runs": self.total_runs,
                "avg_duration_ms": round(avg_dur, 1),
                "history_count": len(self.history),
                "next_run_at": next_run_at,
                "failure_rate": round(self.failure_count / max(self.total_runs, 1), 4),
            }


class BackgroundTaskMonitor:
    """后台任务监控单例"""

    def __init__(self):
        self._tasks: Dict[str, TaskRecord] = {}
        self._lock = threading.Lock()
        self.interval_seconds = 10  # 与 main.py BACKGROUND_INTERVAL 一致
        self._initialized = False

    def register(self, name: str, fn: Optional[Callable] = None, description: str = "") -> TaskRecord:
        """注册任务（幂等）"""
        with self._lock:
            if name not in self._tasks:
                self._tasks[name] = TaskRecord(name, fn=fn, description=description)
            elif fn:
                self._tasks[name].fn = fn
            return self._tasks[name]

    def get(self, name: str) -> Optional[TaskRecord]:
        return self._tasks.get(name)

    def record_start(self, name: str):
        task = self.get(name)
        if task:
            task.record_start()

    def record_success(self, name: str, duration_ms: float):
        task = self.get(name)
        if task:
            task.record_success(duration_ms)
        else:
            logger.debug(f"background_task_monitor: 未注册任务 {name}")

    def record_failure(self, name: str, duration_ms: float, error: str):
        task = self.get(name)
        if task:
            task.record_failure(duration_ms, error)

    def record_skip(self, name: str, reason: str = "paused"):
        task = self.get(name)
        if task:
            task.record_skip(reason)

    def is_enabled(self, name: str) -> bool:
        task = self.get(name)
        return bool(task and task.enabled)

    def toggle_pause(self, name: str) -> Dict[str, Any]:
        """暂停/恢复任务"""
        task = self.get(name)
        if not task:
            return {"ok": False, "message": f"任务 {name} 不存在"}
        task.enabled = not task.enabled
        state = "已恢复" if task.enabled else "已暂停"
        logger.info(f"后台任务 {name} {state}")
        return {"ok": True, "enabled": task.enabled, "message": f"任务 {name} {state}"}

    def trigger_now(self, name: str) -> Dict[str, Any]:
        """手动触发任务（异步执行，不阻塞）"""
        task = self.get(name)
        if not task:
            return {"ok": False, "message": f"任务 {name} 不存在"}
        if not task.fn:
            return {"ok": False, "message": f"任务 {name} 未绑定可调用对象"}
        if task.last_status == "running":
            return {"ok": False, "message": f"任务 {name} 正在运行中"}

        def _run():
            t0 = time.time()
            task.record_start()
            try:
                # 独立 DB session
                from app.database import get_session_for, get_db_mode
                db = get_session_for(get_db_mode())()
                try:
                    task.fn(db)
                finally:
                    db.close()
                dur = (time.time() - t0) * 1000
                task.record_success(dur)
                logger.info(f"手动触发任务 {name} 成功 ({dur:.0f}ms)")
            except Exception as e:
                dur = (time.time() - t0) * 1000
                task.record_failure(dur, str(e))
                logger.warning(f"手动触发任务 {name} 失败: {e}")

        threading.Thread(target=_run, daemon=True, name=f"trigger_{name}").start()
        return {"ok": True, "message": f"任务 {name} 已触发，后台执行中"}

    def snapshot(self) -> List[Dict[str, Any]]:
        """所有任务状态快照"""
        with self._lock:
            return [t.to_dict() for t in self._tasks.values()]

    def health_summary(self) -> Dict[str, Any]:
        """健康摘要：失败率、平均耗时、最慢任务、失败任务清单"""
        tasks = self.snapshot()
        total = len(tasks)
        running = [t for t in tasks if t["last_status"] == "running"]
        failed = [t for t in tasks if t["last_status"] == "failed"]
        disabled = [t for t in tasks if not t["enabled"]]
        avg_dur = sum(t["avg_duration_ms"] for t in tasks) / total if total else 0
        slowest = max(tasks, key=lambda t: t["last_duration_ms"]) if tasks else None
        return {
            "total_tasks": total,
            "running_count": len(running),
            "failed_count": len(failed),
            "disabled_count": len(disabled),
            "avg_duration_ms": round(avg_dur, 1),
            "slowest_task": {
                "name": slowest["name"],
                "duration_ms": slowest["last_duration_ms"],
            } if slowest else None,
            "failed_tasks": [{"name": t["name"], "error": t["last_error"]} for t in failed],
            "interval_seconds": self.interval_seconds,
        }


# 全局单例
task_monitor = BackgroundTaskMonitor()


def init_task_monitor(tasks: List[Dict[str, Any]]):
    """初始化任务清单（在 main.py 启动时调用一次）

    tasks: [{name, fn, description}, ...]
    """
    if task_monitor._initialized:
        return
    for t in tasks:
        task_monitor.register(t["name"], fn=t.get("fn"), description=t.get("description", ""))
    task_monitor._initialized = True
    logger.info(f"background_task_monitor 已注册 {len(tasks)} 个后台任务")
