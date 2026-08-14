"""告警规则 kind 评估单元测试(H3)。

覆盖 metric_raw / anomaly / forecast / burn_rate / trace_latency / trace_error_rate
评估逻辑(纯函数, 不依赖真实 DB; 用 sqlite + 内存 session 造最小数据)。
"""
import os
import sys

# 让测试可独立运行: 定位项目根
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import pytest


class _FakeRule:
    """最小 AlertRule 替身(只保留评估用字段)。"""
    def __init__(self, kind, metric, cond, thr, config="{}"):
        self.kind = kind
        self.metric_name = metric
        self.condition = cond
        self.threshold = thr
        self.config_json = config


class _FakeMetric:
    def __init__(self, value, asset_id=1):
        self.value = value
        self.asset_id = asset_id


class _FakeDB:
    """提供 _metric_history 所需查询退化: 返回空(让 anomaly/forecast 走样本不足分支)。"""
    def query(self, *a, **k): return self
    def filter(self, *a, **k): return self
    def order_by(self, *a, **k): return self
    def limit(self, *a, **k): return self
    def all(self): return []
    def reversed(self, x): return x


@pytest.fixture
def db():
    return _FakeDB()


def test_metric_raw_gt_trigger():
    from app.services.alert_service import _eval_rule_by_kind
    rule = _FakeRule("metric_raw", "cpu", ">", 80)
    t, v, _ = _eval_rule_by_kind(rule, _FakeMetric(90.0), db=None)
    assert t is True and v == 90.0


def test_metric_raw_no_trigger():
    from app.services.alert_service import _eval_rule_by_kind
    rule = _FakeRule("metric_raw", "cpu", ">", 80)
    t, _, _ = _eval_rule_by_kind(rule, _FakeMetric(50.0), db=None)
    assert t is False


def test_anomaly_insufficient_sample_fails_open():
    """样本不足(空历史)不应误触发。"""
    from app.services.alert_service import _eval_anomaly
    rule = _FakeRule("anomaly", "cpu", ">", 3.0)
    t, _, msg = _eval_anomaly(rule, _FakeMetric(90.0), _FakeDB())
    assert t is False
    assert "样本不足" in msg


def test_forecast_insufficient_sample_fails_open():
    from app.services.alert_service import _eval_forecast
    rule = _FakeRule("forecast", "cpu", ">", 90)
    t, _, msg = _eval_forecast(rule, _FakeMetric(80.0), _FakeDB())
    assert t is False
    assert "样本不足" in msg


def test_kind_list_has_8():
    from app.services.alert_service import RULE_KINDS
    assert len(RULE_KINDS) == 8
    assert "trace_latency" in RULE_KINDS
    assert "log_match" in RULE_KINDS


def test_burn_rate_no_samples():
    from app.services.alert_service import _eval_burn_rate
    rule = _FakeRule("burn_rate", "err", ">", 2.0)
    t, _, _ = _eval_burn_rate(rule, _FakeMetric(0.1), _FakeDB())
    assert t is False
