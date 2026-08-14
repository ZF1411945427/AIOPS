"""AI Provider 健康熔断器单元测试 (H3 扩展)。

对齐 ongrid 内核的 index 熔断逻辑, 验证 CircuitBreaker 状态机(closed->open->half_open->closed)。
"""
import os
import sys
import time
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from app.services.ai_provider_health import CircuitBreaker, get_breaker, reset_breaker, _breakers
from app.services.ai_provider_health import FAILURE_THRESHOLD, OPEN_DURATION_SEC, STATE_OPEN, STATE_HALF_OPEN


def test_breaker_open_after_threshold_failures():
    cb = CircuitBreaker(provider_id=1)
    assert cb.allow_call()[0] is True
    for _ in range(FAILURE_THRESHOLD):
        cb.record_failure("boom")
    ok, reason = cb.allow_call()
    assert ok is False
    assert "open" in reason


def test_breaker_half_open_after_cooldown():
    cb = CircuitBreaker(provider_id=2)
    for _ in range(FAILURE_THRESHOLD):
        cb.record_failure("x")
    assert cb.state == STATE_OPEN
    # 绕过冷却时间 -> 进入半开态, 允许一次探测
    cb.opened_at = time.time() - OPEN_DURATION_SEC - 1
    ok, reason = cb.allow_call()
    assert ok is True
    assert reason == "half_open"


def test_success_in_half_open_recovers():
    cb = CircuitBreaker(provider_id=3)
    for _ in range(FAILURE_THRESHOLD):
        cb.record_failure("x")
    cb.opened_at = time.time() - OPEN_DURATION_SEC - 1  # 冷却结束
    assert cb.allow_call()[0] is True  # 半开探测放行
    cb.record_success(100.0)           # 探测成功 -> 恢复 closed
    assert cb.state != STATE_OPEN
    assert cb.allow_call()[0] is True


def test_success_records_latency_metrics():
    cb = CircuitBreaker(provider_id=4)
    for _ in range(5):
        cb.record_success(100.0)
    assert cb.avg_latency() == 100.0
    assert cb.p95_latency() <= 100.0
    assert cb.success_count == 5


def test_reset_breaker_closes():
    cb = get_breaker(5)
    for _ in range(FAILURE_THRESHOLD):
        cb.record_failure("e")
    assert cb.state == STATE_OPEN
    assert reset_breaker(5) is True
    ok, reason = cb.allow_call()
    assert ok is True
    assert reason == "closed"
    _breakers.pop(5, None)


def test_get_breaker_returns_singleton():
    cb1 = get_breaker(99)
    cb2 = get_breaker(99)
    assert cb1 is cb2
    _breakers.pop(99, None)
