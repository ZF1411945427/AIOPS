"""RCA 算法单测: log_rca(日志根因) 与 idice(因果归因)。

覆盖 _baseline / z-score 判定 / 资产关系邻居 / 相关性排序。
零 DB 依赖(fake query), 验证算法正确性。
"""
from types import SimpleNamespace
from datetime import datetime

from app.services import rca_algos_service


def _asset(**kw):
    base = dict(id=1, name="web-01", ip="10.0.0.1")
    base.update(kw)
    return SimpleNamespace(**base)


def _metric_row(name, ts, value):
    return SimpleNamespace(name=name, timestamp=ts, value=value)


def make_db(asset, metrics, relations=None):
    """构造链式 fake db: query(Asset).filter(...).first() + query(MetricRecord).filter(...).order_by(...).limit().all()"""

    class Q:
        def __init__(self, rows):
            self._rows = rows

        def filter(self, *a, **k):
            return self

        def order_by(self, *a, **k):
            return self

        def limit(self, n):
            return Q(self._rows)

        def all(self):
            return list(self._rows)

        def first(self):
            return self._rows[0] if self._rows else None

    class DB:
        def __init__(self):
            self.metrics = metrics
            self.asset = asset
            self.relations = relations or []

        def query(self, model):
            name = getattr(model, "__name__", "")
            if name == "Asset":
                return Q([self.asset])
            if name == "AssetRelation":
                return Q(self.relations)
            return Q(self.metrics)

    return DB()


class TestBaseline:
    def test_baseline_stats(self):
        mean, std, n = rca_algos_service._baseline([1, 2, 3, 4, 5])
        assert mean == 3.0
        assert abs(std - 1.414) < 0.01
        assert n == 5

    def test_baseline_empty(self):
        assert rca_algos_service._baseline([]) == (0.0, 0.0, 0.0)

    def test_baseline_single(self):
        assert rca_algos_service._baseline([7.0]) == (7.0, 0.0, 1)


class TestRunLogRca:
    def test_missing_asset(self):
        db = make_db(None, [])
        out = rca_algos_service.run_log_rca(db, 1)
        assert out.get("ok") is False

    def test_anomaly_detected_via_zscore(self):
        now = datetime.now()
        # 最后的尖峰 100 vs 基线 ~10 → z 远超 2
        metrics = [ _metric_row("cpu_usage", now, 10.0) for _ in range(20) ] + [
            _metric_row("cpu_usage", now, 100.0)
        ]
        db = make_db(_asset(), metrics)
        out = rca_algos_service.run_log_rca(db, 1)
        assert out["ok"] is True
        assert len(out["anomaly_metrics"]) >= 1
        assert out["root_cause_hypotheses"]

    def test_no_anomaly_default_hypothesis(self):
        now = datetime.now()
        metrics = [ _metric_row("cpu_usage", now, 10.0 + i % 3) for i in range(20) ]
        db = make_db(_asset(), metrics)
        out = rca_algos_service.run_log_rca(db, 1)
        assert out["ok"] is True
        assert out["root_cause_hypotheses"]  # 兜底假设

    def test_related_neighbors(self):
        now = datetime.now()
        rel = SimpleNamespace(parent_id=1, child_id=2, relation_type="depends_on")
        metrics = [ _metric_row("cpu_usage", now, 10.0) for _ in range(20) ] + [
            _metric_row("cpu_usage", now, 100.0)
        ]

        class Q:
            def __init__(self, rows):
                self._rows = rows
            def filter(self, *a, **k):
                return self
            def order_by(self, *a, **k):
                return self
            def limit(self, n):
                return Q(self._rows)
            def all(self):
                return list(self._rows)
            def first(self):
                return self._rows[0] if self._rows else None

        neighbor_asset = _asset(id=2, name="web-02")

        class DB:
            def __init__(self):
                self._asset_calls = 0

            def query(self, model):
                name = getattr(model, "__name__", "")
                if name == "Asset":
                    self._asset_calls += 1
                    # 第一次调用返回主资产, 后续调用返回邻居资产
                    row = _asset() if self._asset_calls == 1 else neighbor_asset
                    return Q([row])
                if name == "AssetRelation":
                    return Q([rel])
                return Q(metrics)

        out = rca_algos_service.run_log_rca(DB(), 1)
        assert out["related_assets"]
        assert out["related_assets"][0]["asset_id"] == 2


class TestRunIdice:
    def test_missing_asset(self):
        out = rca_algos_service.run_idice(make_db(None, {}), 1, "cpu")
        assert out.get("ok") is False

    def test_insufficient_target_samples(self):
        now = datetime.now()
        metrics = [_metric_row("cpu", now, 5.0) for _ in range(3)]
        out = rca_algos_service.run_idice(make_db(_asset(), metrics), 1, "cpu")
        assert out["ok"] is True
        assert out["attributions"] == []

    def test_correlation_finds_influence(self):
        now = datetime.now()
        # target 与 other 强正相关(同涨同跌), 应被识别为高相关因果指标
        vals_t = [float(i) for i in range(20)]
        vals_o = [float(i) + 0.5 for i in range(20)]
        metrics = [
            _metric_row("cpu", now, v) for v in vals_t
        ] + [
            _metric_row("mem", now, v) for v in vals_o
        ]
        out = rca_algos_service.run_idice(make_db(_asset(), metrics), 1, "cpu")
        assert out["ok"] is True
        assert len(out["attributions"]) >= 1
        assert out["attributions"][0]["metric"] == "mem"
        assert abs(out["attributions"][0]["correlation"]) > 0.9

    def test_low_correlation_excluded(self):
        now = datetime.now()
        vals_t = [float(i) for i in range(20)]
        vals_r = [float((i * 37) % 20) for i in range(20)]  # 伪随机, 低相关
        metrics = [
            _metric_row("cpu", now, v) for v in vals_t
        ] + [
            _metric_row("noise", now, v) for v in vals_r
        ]
        out = rca_algos_service.run_idice(make_db(_asset(), metrics), 1, "cpu")
        names = [a["metric"] for a in out["attributions"]]
        assert "noise" not in names
