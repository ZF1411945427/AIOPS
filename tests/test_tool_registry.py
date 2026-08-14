"""工具注册表装饰器链单元测试 (H3 扩展)。

对齐 ongrid tools/decorators 的 chain_test.go: 验证 timeout/ratelimit/audit/review_gate/
metric/tenant_bind 装饰器把元数据正确写到函数属性。
"""
import os
import sys
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from app.services.tool_registry import (
    tool_timeout,
    tool_ratelimit,
    tool_audit,
    tool_review_gate,
    tool_metric,
    tool_tenant_bind,
    apply_decorator_meta,
)


def test_tool_timeout_sets_attr():
    @tool_timeout(10)
    def sample():
        pass
    assert sample._tool_timeout == 10


def test_tool_ratelimit_sets_attr():
    @tool_ratelimit(60)
    def sample():
        pass
    assert sample._tool_ratelimit_per_minute == 60


def test_tool_audit_flag():
    @tool_audit()
    def sample():
        pass
    assert sample._tool_audit is True

    @tool_audit(False)
    def sample2():
        pass
    assert sample2._tool_audit is False


def test_review_gate_flag():
    @tool_review_gate()
    def sample():
        pass
    assert sample._tool_review_gate is True


def test_metric_flag():
    @tool_metric()
    def sample():
        pass
    assert sample._tool_metric is True


def test_tenant_bind_flag():
    @tool_tenant_bind()
    def sample():
        pass
    assert sample._tool_tenant_bind is True


def test_decorator_stack_composes():
    @tool_timeout(30)
    @tool_ratelimit(120)
    @tool_audit()
    @tool_review_gate()
    def sample():
        pass
    assert sample._tool_timeout == 30
    assert sample._tool_ratelimit_per_minute == 120
    assert sample._tool_audit is True
    assert sample._tool_review_gate is True


def test_apply_decorator_meta():
    def sample():
        pass
    apply_decorator_meta(sample, timeout=5, ratelimit_per_minute=10)
    assert sample._tool_timeout == 5
    assert sample._tool_ratelimit_per_minute == 10
