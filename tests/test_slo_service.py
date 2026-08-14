"""SLO / Error Budget 单测: 燃烧速率计算 / VM 查询解析 / 状态机。

核心业务逻辑(_calc_burn / _query_vm_availability / 状态分级)纯逻辑可测,
对齐监控维度 9.0 的工程纵深要求。
"""
from types import SimpleNamespace

from app.services import slo_service


def _slo(**kw):
    base = dict(id=1, service_name="api-gateway", slo_target=0.99, window_days=30, status="healthy",
                total_requests=0, error_requests=0)
    base.update(kw)
    return SimpleNamespace(**base)


class TestQueryVmAvailability:
    def test_no_metrics_returns_none_availability(self, monkeypatch):
        monkeypatch.setattr(slo_service.metric_v2_service, "query_promql_range",
                            lambda *a, **k: {"status": "is_success", "data": {"result": []}})
        out = slo_service._query_vm_availability("svc")
        assert out["availability"] is None
        assert out["total"] == 0 and out["errors"] == 0

    def test_aggregates_total_and_errors(self, monkeypatch):
        def fake_query(query, start, end, step):
            if "_5xx_errors" in query or "http_errors" in query or "_failures" in query:
                return {"status": "is_success", "data": {"result": [
                    {"metric": {}, "values": [["t", "2"]]}
                ]}}
            if "_errors" in query or "_error_count" in query:
                return {"status": "is_success", "data": {"result": [
                    {"metric": {}, "values": [["t", "3"]]}
                ]}}
            # 其余 total 类: _requests/_total/_count/http_requests/_success
            return {"status": "is_success", "data": {"result": [
                {"metric": {}, "values": [["t", "10"], ["t2", "5"]]}
            ]}}

        monkeypatch.setattr(slo_service.metric_v2_service, "query_promql_range", fake_query)
        out = slo_service._query_vm_availability("svc")
        assert out["total"] == 75  # 5 个 total pattern 各 15
        assert out["errors"] == 12  # 3 个 ERR 各 2 + 2 个 ERR2 各 3
        assert abs(out["availability"] - (1 - 12 / 75)) < 0.001


class TestCalcBurn:
    def test_no_availability_returns_zero_burn(self, monkeypatch):
        monkeypatch.setattr(slo_service, "_query_vm_availability",
                            lambda *a, **k: {"total": 0, "errors": 0, "availability": None})
        out = slo_service._calc_burn(_slo(), None)
        assert out["burn_rate"] == 0.0
        assert out["budget_remaining"] == 100.0
        assert out["availability"] is None

    def test_healthy_burn_low(self, monkeypatch):
        # 可用性 99.5% vs 目标 99% → 错误率 0.005 vs 允许 0.01 → burn 0.5
        monkeypatch.setattr(slo_service, "_query_vm_availability",
                            lambda *a, **k: {"total": 10000, "errors": 50, "availability": 0.995})
        out = slo_service._calc_burn(_slo(), None)
        assert abs(out["burn_rate"] - 0.5) < 0.001
        assert out["budget_remaining"] < 90  # burn=0.5 → 消耗 40%

    def test_error_budget_consumed(self, monkeypatch):
        # 完全不可用 → 错误率 1.0, burn_rate = 1.0/0.01 = 100
        monkeypatch.setattr(slo_service, "_query_vm_availability",
                            lambda *a, **k: {"total": 100, "errors": 100, "availability": 0.0})
        out = slo_service._calc_burn(_slo(), None)
        assert out["burn_rate"] > 10
        assert out["budget_remaining"] == 0.0


class TestCalculateAllSlo:
    def test_healthy_slo_no_alert(self, monkeypatch):
        class FakeDB:
            def __init__(self):
                self.commits = 0
                self.added = []

            def query(self, model):
                if model.__name__ == "SLOConfig":
                    return SimpleNamespace(all=lambda: [_slo()])
                return SimpleNamespace(filter=lambda *a, **k: SimpleNamespace(
                    first=lambda: None))

            def add(self, obj):
                self.added.append(obj)

            def commit(self):
                self.commits += 1

            def refresh(self, obj):
                if not getattr(obj, "id", None):
                    obj.id = 1

        monkeypatch.setattr(slo_service, "_query_vm_availability",
                            lambda *a, **k: {"total": 100, "errors": 0, "availability": 1.0})
        out = slo_service.calculate_all_slo(FakeDB())
        assert out["updated"] == 1
        assert out["alerts_created"] == 0

    def test_slo_alert_created_on_critical(self, monkeypatch):
        created = []

        class FakeDB:
            def __init__(self):
                self.commits = 0
                self.added = []

            def query(self, model):
                if model.__name__ == "SLOConfig":
                    return SimpleNamespace(all=lambda: [_slo()])
                return SimpleNamespace(
                    filter=lambda *a, **k: SimpleNamespace(
                        order_by=lambda *a, **k: SimpleNamespace(
                            limit=lambda n: [])) if False else SimpleNamespace(
                            first=lambda: None))

            def add(self, obj):
                self.added.append(obj)
                if getattr(obj, "metric_name", None):
                    created.append(obj)

            def commit(self):
                self.commits += 1

            def refresh(self, obj):
                if not getattr(obj, "id", None):
                    obj.id = 1

        # 关键: mock _create_slo_alert 与 _trigger_slo_remediation 避免通知/WS
        monkeypatch.setattr(slo_service, "_query_vm_availability",
                            lambda *a, **k: {"total": 100, "errors": 100, "availability": 0.0})
        monkeypatch.setattr(slo_service, "_create_slo_alert",
                            lambda db, slo, burn, status: SimpleNamespace(id=1, metric_name=f"slo_{slo.service_name}"))
        monkeypatch.setattr(slo_service, "_trigger_slo_remediation", lambda db, alert: [])

        out = slo_service.calculate_all_slo(FakeDB())
        assert out["alerts_created"] == 1
