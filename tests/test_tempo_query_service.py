"""Tempo 查询代理单测: Jaeger 格式 → 前端格式适配。"""
from unittest import mock

from app.services import tempo_query_service as tqs


class _FakeResp:
    def __init__(self, payload, status=200):
        self._payload = payload
        self.status_code = status

    def json(self):
        return self._payload

    def raise_for_status(self):
        if self.status_code >= 400:
            raise RuntimeError("http error")


def _search_results_payload():
    return {
        "traces": [{
            "traceID": "abc123",
            "rootServiceName": "api-gateway",
            "rootTraceName": "GET /orders",
            "durationMs": 2500,
            "startTimeUnixNano": 1786676000000000000,
        }],
        "metrics": {"completedJobs": 1, "totalJobs": 1},
    }


def _trace_detail_payload():
    # Tempo 2.x batches 格式, spanId 为 base64
    import base64
    return {
        "batches": [{
            "resource": {"attributes": [{"key": "service.name", "value": {"stringValue": "api-gateway"}}]},
            "scopeSpans": [{
                "scope": {"name": "demo"},
                "spans": [
                    {
                        "spanId": base64.b64encode(bytes.fromhex("5c6f000000000001")),
                        "parentSpanId": "",
                        "name": "GET /orders",
                        "startTimeUnixNano": "1786676000000000000",
                        "endTimeUnixNano": "1786676002500000000",
                        "status": "STATUS_CODE_OK",
                        "attributes": [{"key": "http.method", "value": {"stringValue": "GET"}}],
                    },
                    {
                        "spanId": base64.b64encode(bytes.fromhex("5c6f000000000002")),
                        "parentSpanId": base64.b64encode(bytes.fromhex("5c6f000000000001")),
                        "name": "findOrder",
                        "startTimeUnixNano": "1786676000500000000",
                        "endTimeUnixNano": "1786676001300000000",
                        "status": "STATUS_CODE_ERROR",
                        "attributes": [{"key": "db.table", "value": {"stringValue": "orders"}}],
                    },
                ],
            }],
        }]
    }


class TestSearchTraces:
    def test_maps_jaeger_to_frontend(self):
        with mock.patch("requests.get") as mget:
            # 第一个调用 /api/search, 第二个 /api/services
            mget.side_effect = [
                _FakeResp(_search_results_payload()),
                _FakeResp({"data": ["api-gateway", "order-svc"]}),
            ]
            out = tqs.search_traces("http://tempo:3200", service="api-gateway", limit=50)
            assert out["total"] == 1
            t = out["traces"][0]
            assert t["trace_id"] == "abc123"
            assert t["root_service"] == "api-gateway"
            assert t["total_duration_ms"] == 2500.0
            assert out["services"] == ["api-gateway", "order-svc"]

    def test_search_down_raises(self):
        with mock.patch("requests.get", side_effect=RuntimeError("conn refused")):
            try:
                tqs.search_traces("http://tempo:3200")
                raise AssertionError("应抛出异常以便上层回退 SQLite")
            except RuntimeError:
                pass


class TestGetTrace:
    def test_maps_trace_with_topology(self):
        with mock.patch("requests.get", return_value=_FakeResp(_trace_detail_payload())):
            out = tqs.get_trace("http://tempo:3200", "abc123")
            assert out["trace_id"] == "abc123"
            assert out["total_spans"] == 2
            assert len(out["spans"]) == 2
            root = out["spans"][0]
            assert root["service_name"] == "api-gateway"
            assert root["tags"].get("http.method") == "GET"
            assert out["services"] == ["api-gateway"]
            # 同 service 批次 → 无跨服务边
            assert out["topology"]["edges"] == []
            assert out["root_start"]  # 非空
            # 第二个 span 是 ERROR
            assert out["spans"][1]["status"] == "ERROR"

    def test_not_found_returns_none(self):
        with mock.patch("requests.get", return_value=_FakeResp({}, status=404)):
            assert tqs.get_trace("http://tempo:3200", "nope") is None


class TestHelpers:
    def test_epoch_ms_to_str(self):
        assert tqs._epoch_ms_to_str(1786676000000)  # 合法时间
        assert tqs._epoch_ms_to_str(0) == ""
