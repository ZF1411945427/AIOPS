"""Drain 日志聚类 + Granger 因果检验 单测(补全 P3-2 真实实现).

RCA 服务模块顶部 import 了 app.routers.agent_sse(既有循环依赖链), 故 Granger 侧用
「延迟导入 + 失败降级」避免破坏测试环境; Drain 为轻量路由模块, 直接导入安全。
"""
import pytest

from app.routers import drain

# ─── Drain 树形聚类 ───
class TestDrain:
    def test_groups_similar_timeouts(self):
        logs = [
            "ERROR 连接失败 127.0.0.1 33 timeout",
            "ERROR 连接失败 127.0.0.1 45 timeout",
            "ERROR 连接失败 192.168.1.1 100 timeout",
        ]
        clusters = drain.drain_cluster(logs)
        assert len(clusters) == 1          # 全部归入同一模板
        assert clusters[0]["count"] == 3
        # 升级后: 可变 token 被归一为类型占位符 <IP>/<NUM>(而非一概 <*>)
        assert "<" in clusters[0]["template"] and ">" in clusters[0]["template"]
        assert clusters[0]["template"] == "ERROR 连接失败 <IP> <NUM> timeout"

    def test_keeps_distinct_single(self):
        logs = ["A 1", "B 2"]
        assert len(drain.drain_cluster(logs)) == 2

    def test_numeric_token_wildcard(self):
        # 纯数字应被归一为 <NUM> 通配, 使不同数值归并
        clusters = drain.drain_cluster(["cpu 80", "cpu 90"])
        assert len(clusters) == 1
        assert "<NUM>" in clusters[0]["template"] or "<*>" in clusters[0]["template"]
        assert clusters[0]["count"] == 2

    def test_ip_token_wildcard(self):
        clusters = drain.drain_cluster(["conn 127.0.0.1", "conn 10.0.0.5"])
        assert len(clusters) == 1 and clusters[0]["count"] == 2

    def test_empty(self):
        assert drain.drain_cluster([]) == []


# ─── Granger 因果逻辑 ───
def _granger_params():
    """延迟导入 rca_algos_service。

    该模块顶部 import 了 app.routers.agent_sse, 存在既有循环依赖链; 与运行时一样,
    先加载 app.services.mcp_tools 打通导入顺序, 再取 rca_algos_service。
    """
    import app.services.mcp_tools  # noqa: F401 — 打通既有导入顺序(与 app.main 一致)
    from app.services import rca_algos_service as rca
    return rca


class TestAlignSeries:
    def test_timestamp_intersection(self):
        rca = _granger_params()
        sa = [{"timestamp": 1, "value": 1.0}, {"timestamp": 2, "value": 2.0},
              {"timestamp": 3, "value": 3.0}]
        sb = [{"timestamp": 2, "value": 20.0}, {"timestamp": 3, "value": 30.0},
              {"timestamp": 4, "value": 40.0}]
        x, y = rca._align_series(sa, sb)
        assert x == [2.0, 3.0]
        assert y == [20.0, 30.0]

    def test_no_overlap(self):
        rca = _granger_params()
        sa = [{"timestamp": 1, "value": 1.0}]
        sb = [{"timestamp": 2, "value": 2.0}]
        assert rca._align_series(sa, sb) == ([], [])


class TestGrangerMath:
    def test_directional_significance(self):
        """合成数据: a(噪声)→b(带滞后响应), a→b 应显著、b→a 不显著。"""
        rca = _granger_params()
        import numpy as np
        from statsmodels.tsa.stattools import grangercausalitytests as gct
        import warnings as _w

        rng = np.random.RandomState(42)
        n = 150
        a = rng.randn(n)
        b = np.zeros(n)
        for i in range(1, n):
            b[i] = 0.7 * a[i - 1] + 0.1 * b[i - 1] + 0.3 * rng.randn()

        def best_p(resp, cause):
            data = np.column_stack([resp, cause])
            with _w.catch_warnings():
                _w.simplefilter("ignore")
                res = gct(data, maxlag=2, verbose=False)
            ps = []
            for _lag, item in res.items():
                d = item[0] if isinstance(item, tuple) else item
                ps.append(float(d["ssr_ftest"][1]))
            return min(ps)

        p_a2b = best_p(b, a)
        p_b2a = best_p(a, b)
        assert p_a2b < 0.05, f"a→b 应显著, 实际 p={p_a2b}"
        assert p_b2a > 0.05, f"b→a 应不显著, 实际 p={p_b2a}"


class TestRunGrangerE2E:
    """端到端跑 run_granger: monkeypatch _asset_metric_series 提供合成时序, 验证结论方向。"""

    def _fake_db(self, asset):
        from types import SimpleNamespace
        def _query(_model):
            return SimpleNamespace(
                filter=lambda *a, **k: SimpleNamespace(first=lambda: asset),
            )
        return SimpleNamespace(query=_query)

    def test_detects_a_to_b(self, monkeypatch):
        rca = _granger_params()
        from types import SimpleNamespace
        import numpy as np
        rng = np.random.RandomState(7)
        n = 150
        a = rng.randn(n)
        b = np.zeros(n)
        for i in range(1, n):
            b[i] = 0.7 * a[i - 1] + 0.1 * b[i - 1] + 0.3 * rng.randn()
        ts = [t for t in range(n)]

        def fake_series(_db, _asset_id, metric_name, hours=24, limit=5000):
            vals = a if metric_name == "a" else b
            return [{"timestamp": ts[i], "value": vals[i]} for i in range(n)]

        monkeypatch.setattr(rca, "_asset_metric_series", fake_series)
        db = self._fake_db(SimpleNamespace(id=1, name="svr", ip="1.1.1.1"))
        res = rca.run_granger(db, asset_id=1, metric_a="a", metric_b="b",
                              hours=24, maxlag=2)
        assert res["ok"] is True
        dirs = {d["pair"]: d for d in res["directions"]}
        assert dirs["a→b"]["significant_95"] is True
        assert dirs["b→a"]["significant_95"] is False
        assert res["method"] == "granger-causality (statsmodels ssr_ftest)"

    def test_insufficient_samples(self, monkeypatch):
        rca = _granger_params()
        from types import SimpleNamespace
        monkeypatch.setattr(rca, "_asset_metric_series",
                            lambda *a, **k: [{"timestamp": 1, "value": 1.0}])
        db = self._fake_db(SimpleNamespace(id=1, name="svr", ip="1.1.1.1"))
        res = rca.run_granger(db, asset_id=1, metric_a="a", metric_b="b",
                              hours=24, maxlag=3)
        assert res["ok"] is False
        assert "样本不足" in res["error"]
