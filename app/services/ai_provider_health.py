"""AI Provider 健康度路由 + 熔断器（P1 任务#5）

核心能力：
- **熔断器（Circuit Breaker）**：连续 N 次失败自动熔断 60s，半开态试探恢复
- **健康度表**：每个 provider 的 last_success_at / failure_count / p95_latency / total_calls / success_count
- **按健康度排序选 provider**：跳过熔断中的，优先选成功率高的
- **多 provider fallback**：失败自动切下一个，避免 15s+ 超时等待

设计要点：
- 状态机：closed（正常）→ open（熔断）→ half_open（试探）→ closed/open
- p95 用滑动窗口（最近 20 次调用）
- in-memory + threading.Lock，无需 DB 持久化（重启即清零）
- 调用 LLM 失败时记录，成功时清零 failure_count
"""

import threading
import time
from collections import deque
from datetime import datetime
from typing import Any, Dict, List, Optional, Tuple

from app.logger import logger


# ── 熔断器配置 ─────────────────────────────────────────────────────
FAILURE_THRESHOLD = 5          # 连续失败 N 次触发熔断
OPEN_DURATION_SEC = 60         # 熔断持续时间（秒）
HALF_OPEN_PROBES = 1           # 半开态允许试探次数
LATENCY_WINDOW = 20            # 延迟滑动窗口（最近 N 次调用）


# ── 熔断器状态 ─────────────────────────────────────────────────────
STATE_CLOSED = "closed"
STATE_OPEN = "open"
STATE_HALF_OPEN = "half_open"


class CircuitBreaker:
    """单 provider 的熔断器状态机

    状态流转：
        closed --连续 N 次失败--> open --60s 后--> half_open
        half_open --试探成功--> closed
        half_open --试探失败--> open
    """

    def __init__(self, provider_id: int):
        self.provider_id = provider_id
        self.state = STATE_CLOSED
        self.failure_count = 0            # 连续失败次数（成功即清零）
        self.success_count = 0            # 累计成功次数
        self.total_calls = 0              # 累计调用次数
        self.last_failure_at: Optional[float] = None
        self.last_success_at: Optional[float] = None
        self.opened_at: Optional[float] = None    # 进入 open 状态的时刻
        self.half_open_probes_used = 0            # 半开态已用试探次数
        self.latency_window: deque = deque(maxlen=LATENCY_WINDOW)
        self.last_error: Optional[str] = None
        self._lock = threading.Lock()

    def allow_call(self) -> Tuple[bool, str]:
        """是否允许调用，返回 (允许, 原因)"""
        with self._lock:
            now = time.time()
            if self.state == STATE_OPEN:
                # 熔断时间已过 → 转入半开态
                if self.opened_at and (now - self.opened_at) >= OPEN_DURATION_SEC:
                    self.state = STATE_HALF_OPEN
                    self.half_open_probes_used = 0
                    logger.info(f"AI Provider {self.provider_id} 熔断器进入半开态")
                    return True, "half_open"
                return False, f"open(剩余{int(OPEN_DURATION_SEC - (now - (self.opened_at or now)))}s)"
            if self.state == STATE_HALF_OPEN:
                if self.half_open_probes_used < HALF_OPEN_PROBES:
                    self.half_open_probes_used += 1
                    return True, "half_open_probe"
                return False, "half_open_exhausted"
            return True, "closed"

    def record_success(self, latency_ms: float):
        with self._lock:
            self.total_calls += 1
            self.success_count += 1
            self.failure_count = 0
            self.last_success_at = time.time()
            self.latency_window.append(latency_ms)
            self.last_error = None
            # 半开态试探成功 → 恢复
            if self.state == STATE_HALF_OPEN:
                self.state = STATE_CLOSED
                self.opened_at = None
                self.half_open_probes_used = 0
                logger.info(f"AI Provider {self.provider_id} 熔断器恢复 (closed)")

    def record_failure(self, error: str = ""):
        with self._lock:
            self.total_calls += 1
            self.failure_count += 1
            self.last_failure_at = time.time()
            self.last_error = error[:200] if error else ""
            # 半开态试探失败 → 重新熔断
            if self.state == STATE_HALF_OPEN:
                self.state = STATE_OPEN
                self.opened_at = time.time()
                logger.warning(f"AI Provider {self.provider_id} 半开态试探失败，重新熔断")
                return
            # closed 态连续失败达阈值 → 熔断
            if self.state == STATE_CLOSED and self.failure_count >= FAILURE_THRESHOLD:
                self.state = STATE_OPEN
                self.opened_at = time.time()
                logger.warning(
                    f"AI Provider {self.provider_id} 连续失败 {self.failure_count} 次，熔断 {OPEN_DURATION_SEC}s"
                )

    def reset(self):
        """手动重置熔断器"""
        with self._lock:
            self.state = STATE_CLOSED
            self.failure_count = 0
            self.opened_at = None
            self.half_open_probes_used = 0
            self.last_error = None

    def p95_latency(self) -> float:
        """计算 p95 延迟（ms）"""
        with self._lock:
            if not self.latency_window:
                return 0.0
            sorted_lat = sorted(self.latency_window)
            idx = max(0, int(len(sorted_lat) * 0.95) - 1)
            return float(sorted_lat[idx])

    def avg_latency(self) -> float:
        with self._lock:
            if not self.latency_window:
                return 0.0
            return float(sum(self.latency_window) / len(self.latency_window))

    def to_dict(self) -> Dict[str, Any]:
        now = time.time()
        remaining = 0
        if self.state == STATE_OPEN and self.opened_at:
            remaining = max(0, int(OPEN_DURATION_SEC - (now - self.opened_at)))
        return {
            "provider_id": self.provider_id,
            "state": self.state,
            "failure_count": self.failure_count,
            "success_count": self.success_count,
            "total_calls": self.total_calls,
            "success_rate": round(self.success_count / self.total_calls, 4) if self.total_calls else 1.0,
            "p95_latency_ms": round(self.p95_latency(), 1),
            "avg_latency_ms": round(self.avg_latency(), 1),
            "last_success_at": datetime.fromtimestamp(self.last_success_at).isoformat() if self.last_success_at else None,
            "last_failure_at": datetime.fromtimestamp(self.last_failure_at).isoformat() if self.last_failure_at else None,
            "last_error": self.last_error,
            "open_remaining_sec": remaining,
            "failure_threshold": FAILURE_THRESHOLD,
            "open_duration_sec": OPEN_DURATION_SEC,
        }


# ── 全局健康度注册表 ───────────────────────────────────────────────

_breakers: Dict[int, CircuitBreaker] = {}
_breakers_lock = threading.Lock()


def get_breaker(provider_id: int) -> CircuitBreaker:
    """获取（或创建）provider 的熔断器"""
    with _breakers_lock:
        if provider_id not in _breakers:
            _breakers[provider_id] = CircuitBreaker(provider_id)
        return _breakers[provider_id]


def get_all_breakers() -> Dict[int, CircuitBreaker]:
    with _breakers_lock:
        return dict(_breakers)


def reset_breaker(provider_id: int) -> bool:
    """手动重置 provider 熔断器（幂等：不存在则视为已重置）"""
    breaker = _breakers.get(provider_id)
    if breaker:
        breaker.reset()
        return True
    # 未调用过的 provider 没有 breaker 记录，等价于 closed 状态，直接返回 True
    return True


def reset_all_breakers():
    with _breakers_lock:
        for b in _breakers.values():
            b.reset()


# ── 健康度感知的 provider 选择 ─────────────────────────────────────

def select_healthy_provider(providers: List[Any]) -> Tuple[Optional[Any], List[int], List[int]]:
    """从 provider 列表中选择健康的 provider

    返回：(选中的 provider, 候选 id 列表, 被熔断跳过的 id 列表)
    排序规则：
        1. 跳过熔断 open 态
        2. 按 success_rate 降序
        3. 按 p95_latency 升序
    """
    if not providers:
        return None, [], []

    skipped: List[int] = []
    candidates: List[Tuple[Any, CircuitBreaker]] = []

    for p in providers:
        if not p or not getattr(p, "is_enabled", False):
            continue
        breaker = get_breaker(p.id)
        allowed, _ = breaker.allow_call()
        if allowed:
            candidates.append((p, breaker))
        else:
            skipped.append(p.id)

    if not candidates:
        return None, [p.id for p in providers if p], skipped

    # 按健康度排序：success_rate 降序 → p95 升序
    candidates.sort(key=lambda x: (-x[1].success_count / max(x[1].total_calls, 1), x[1].p95_latency()))
    selected = candidates[0][0]
    candidate_ids = [p.id for p, _ in candidates]
    return selected, candidate_ids, skipped


# ── 带 fallback 的 LLM 调用 ────────────────────────────────────────

def call_llm_with_fallback(providers: List[Any], messages: List[Dict],
                           tools: Optional[List[Dict]] = None,
                           timeout_override: Optional[int] = None,
                           max_tokens_override: Optional[int] = None) -> Tuple[Dict, Dict[str, Any]]:
    """带熔断 + fallback 的 LLM 调用

    返回：(LLM 响应, 调用元信息)
    元信息：{provider_id, attempted, skipped, breaker_states}
    """
    from app.services.agent_service import call_llm

    selected, candidate_ids, skipped = select_healthy_provider(providers)
    meta: Dict[str, Any] = {
        "selected_provider_id": selected.id if selected else None,
        "attempted_ids": [],
        "skipped_ids": skipped,
        "candidate_ids": candidate_ids,
        "fallback_count": 0,
    }

    if not selected:
        return {"error": "所有 provider 不可用或已熔断"}, meta

    # 按健康度排序的候选列表，逐个尝试
    ordered_providers = [p for p in providers if p and getattr(p, "is_enabled", False) and p.id in candidate_ids]
    ordered_providers.sort(key=lambda p: (
        -get_breaker(p.id).success_count / max(get_breaker(p.id).total_calls, 1),
        get_breaker(p.id).p95_latency(),
    ))

    last_error = ""
    for provider in ordered_providers:
        breaker = get_breaker(provider.id)
        allowed, reason = breaker.allow_call()
        if not allowed:
            continue

        t0 = time.time()
        try:
            resp = call_llm(
                provider, messages, tools,
                timeout_override=timeout_override,
                max_tokens_override=max_tokens_override,
            )
            latency_ms = (time.time() - t0) * 1000

            if "error" in resp:
                # 调用返回错误（超时/HTTP 错误）
                breaker.record_failure(str(resp.get("error", "")))
                last_error = str(resp.get("error", ""))
                meta["attempted_ids"].append(provider.id)
                meta["fallback_count"] += 1
                logger.info(f"AI Provider {provider.id} 调用失败，尝试下一个: {last_error[:100]}")
                continue

            # 成功
            breaker.record_success(latency_ms)
            meta["attempted_ids"].append(provider.id)
            meta["selected_provider_id"] = provider.id
            return resp, meta
        except Exception as e:
            latency_ms = (time.time() - t0) * 1000
            breaker.record_failure(str(e))
            last_error = str(e)
            meta["attempted_ids"].append(provider.id)
            meta["fallback_count"] += 1
            logger.warning(f"AI Provider {provider.id} 异常: {e}")
            continue

    return {"error": f"所有 provider 不可用，最后错误: {last_error}"}, meta


def health_snapshot() -> List[Dict[str, Any]]:
    """返回所有 provider 熔断器状态快照"""
    breakers = get_all_breakers()
    return [b.to_dict() for b in breakers.values()]
