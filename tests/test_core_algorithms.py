"""核心算法单测: 异常检测(sigma/ewma/mad/gap) + DTW + 告警规则评估 + PromQL 解析。

全部用 SimpleNamespace fake 对象, 零 DB/网络依赖, 验证算法正确性而非基础设施。
"""
import math
from datetime import datetime, timedelta
from types import SimpleNamespace

import pytest

from app.services import anomaly_service
from app.services import alert_service
from app.services import dtw_service
from app.services import promql_parser


# ─── helpers ───
def rec(value, ts=None):
    return SimpleNamespace(value=value, timestamp=ts, asset_id=1)


def config(asset_id=1, metric_name="cpu_usage", window_size=10, sensitivity=3.0, name="cfg"):
    return SimpleNamespace(
        asset_id=asset_id, metric_name=metric_name,
        window_size=window_size, sensitivity=sensitivity, name=name,
    )


def no_recent_alert(db, *a, **k):
    return False


class FakeQuery:
    """链式调用 fake: query().filter().filter().order_by().limit().all()/first()"""

    def __init__(self, rows=None):
        self._rows = list(rows or [])

    def filter(self, *a, **k):
        return self

    def order_by(self, *a, **k):
        return self

    def limit(self, n):
        return FakeQuery(self._rows[:n] if n else self._rows)

    def all(self):
        return list(self._rows)

    def first(self):
        return self._rows[0] if self._rows else None

    def count(self):
        return len(self._rows)


def fake_db_with(rows):
    return SimpleNamespace(query=lambda *a, **k: FakeQuery(rows))


# ─── DTW ───
class TestDTW:
    def test_identical_sequences_zero(self):
        assert dtw_service.dtw_distance([1, 2, 3], [1, 2, 3]) == 0.0

    def test_shifted_sequences_small(self):
        # 相位偏移的相同形状序列, DTW 距离应远小于逐点欧氏距离
        d = dtw_service.dtw_distance([1, 2, 3, 4, 5], [2, 3, 4, 5, 6])
        assert 0 <= d < 5.0

    def test_flat_vs_spike(self):
        assert dtw_service.dtw_distance([0, 0, 0, 0], [0, 0, 10, 0]) > 0

    def test_empty_sequences(self):
        assert dtw_service.dtw_distance([], []) == 0.0


# ─── anomaly_service ───
class TestSigma:
    def test_normal_no_trigger(self, monkeypatch):
        monkeypatch.setattr(anomaly_service, "_has_recent_alert", no_recent_alert)
        records = [rec(v) for v in [10.1, 9.9, 10.0, 10.2, 9.8, 10.0, 10.1, 9.9, 10.0, 10.0]]
        assert anomaly_service._detect_sigma(None, config(), records) is None

    def test_spike_triggers_critical(self, monkeypatch):
        monkeypatch.setattr(anomaly_service, "_has_recent_alert", no_recent_alert)
        records = [rec(100.0)] + [rec(10.0)] * 9
        alert = anomaly_service._detect_sigma(None, config(sensitivity=2.0), records)
        assert alert is not None
        assert alert.status == "triggered"
        assert alert.severity in ("warning", "critical")

    def test_zero_stddev_no_trigger(self, monkeypatch):
        monkeypatch.setattr(anomaly_service, "_has_recent_alert", no_recent_alert)
        records = [rec(10.0)] * 10
        assert anomaly_service._detect_sigma(None, config(), records) is None

    def test_recent_alert_suppresses(self, monkeypatch):
        # _has_recent_alert 返回 True 时抑制告警
        monkeypatch.setattr(anomaly_service, "_has_recent_alert", lambda *a, **k: True)
        records = [rec(100.0)] + [rec(10.0)] * 9
        assert anomaly_service._detect_sigma(None, config(sensitivity=2.0), records) is None


class TestEWMA:
    def test_stable_series_no_trigger(self, monkeypatch):
        monkeypatch.setattr(anomaly_service, "_has_recent_alert", no_recent_alert)
        records = [rec(v) for v in [10.0, 10.1, 9.9, 10.0, 10.05, 9.95, 10.0, 10.1, 9.9, 10.0]]
        assert anomaly_service._detect_ewma(None, config(), records) is None

    def test_abrupt_jump_triggers(self, monkeypatch):
        monkeypatch.setattr(anomaly_service, "_has_recent_alert", no_recent_alert)
        records = [rec(100.0)] + [rec(10.0)] * 9
        alert = anomaly_service._detect_ewma(None, config(), records)
        assert alert is not None


class TestMAD:
    def test_stable_series_no_trigger(self, monkeypatch):
        monkeypatch.setattr(anomaly_service, "_has_recent_alert", no_recent_alert)
        records = [rec(v) for v in [10.0, 10.1, 9.9, 10.2, 9.8, 10.0, 10.1, 9.9, 10.0, 10.0]]
        assert anomaly_service._detect_mad(None, config(), records) is None

    def test_outlier_triggers(self, monkeypatch):
        monkeypatch.setattr(anomaly_service, "_has_recent_alert", no_recent_alert)
        records = [rec(100.0)] + [rec(v) for v in [10.0, 10.1, 9.9, 10.2, 9.8, 10.0, 10.1, 9.9, 10.0]]
        alert = anomaly_service._detect_mad(None, config(), records)
        assert alert is not None


class TestRecentGap:
    def test_large_gap_detected(self):
        now = datetime.now()
        records = [rec(10.0, now), rec(5.0, now - timedelta(minutes=30))]
        assert anomaly_service._has_recent_gap(records) is True

    def test_no_gap(self):
        now = datetime.now()
        records = [rec(10.0, now), rec(5.0, now - timedelta(seconds=30))]
        assert anomaly_service._has_recent_gap(records) is False

    def test_single_record_no_gap(self):
        assert anomaly_service._has_recent_gap([rec(10.0)]) is False


# ─── alert_service 规则评估 ───
def _rule(condition=">", threshold=80.0, metric_name="cpu_usage"):
    return SimpleNamespace(
        condition=condition, threshold=threshold, metric_name=metric_name,
        config_json='{"z_score": 3}', asset_id=1,
    )


class TestMetricRawEval:
    def test_gt_trigger(self):
        rule = _rule(">", 80.0)
        triggered, v, _ = alert_service._eval_metric_raw(rule, rec(95.0), None)
        assert triggered and v == 95.0

    def test_gt_no_trigger(self):
        rule = _rule(">", 80.0)
        triggered, _, _ = alert_service._eval_metric_raw(rule, rec(70.0), None)
        assert not triggered

    def test_lt_and_eq(self):
        assert alert_service._eval_metric_raw(_rule("<", 20.0), rec(10.0), None)[0]
        assert alert_service._eval_metric_raw(_rule("=", 50.0), rec(50.0), None)[0]
        assert not alert_service._eval_metric_raw(_rule("<", 20.0), rec(50.0), None)[0]


class TestAnomalyEval:
    def test_insufficient_samples(self):
        triggered, _, msg = alert_service._eval_anomaly(_rule(), rec(95.0), fake_db_with([]))
        assert not triggered and "样本不足" in msg

    def test_anomaly_trigger(self):
        now = datetime.now()
        hist = [SimpleNamespace(value=10.0, timestamp=now) for _ in range(20)]
        triggered, _, _ = alert_service._eval_anomaly(_rule(">", 3.0), rec(50.0), fake_db_with(hist))
        assert triggered


class TestForecastEval:
    def test_insufficient_samples(self):
        triggered, _, msg = alert_service._eval_forecast(_rule(">", 100.0), rec(10.0), fake_db_with([]))
        assert not triggered and "样本不足" in msg

    def test_upward_trend_triggers(self):
        now = datetime.now()
        # 真实 DB: order_by(desc).limit().all() 返回降序, _metric_history 再 reversed → 升序
        hist = [SimpleNamespace(value=float(i), timestamp=now) for i in range(59, -1, -1)]
        triggered, _, _ = alert_service._eval_forecast(_rule(">", 60.0), rec(59.0), fake_db_with(hist))
        assert triggered


# ─── promql_parser ───
class TestPromQLParser:
    def test_parse_metric(self):
        q = promql_parser.parse_promql('rate(cpu_usage{instance="web-1"}[5m])')
        assert q.metric_name == "cpu_usage"
        assert q.labels.get("instance") == "web-1"
        assert q.range_window is not None
        assert q.aggregator == "rate"

    def test_parse_without_window(self):
        q = promql_parser.parse_promql("up")
        assert q.metric_name == "up"
        assert q.range_window is None

    def test_is_valid(self):
        assert promql_parser.is_valid("rate(http_requests_total[5m])")
        assert not promql_parser.is_valid("")

    def test_parse_window(self):
        assert promql_parser._parse_window("5m") == 300
        assert promql_parser._parse_window("1h") == 3600
