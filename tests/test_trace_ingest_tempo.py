"""trace_ingest_service: Tempo 深度接线(OTLP 转发)单测。"""
import json as _json
import sys
import types
import uuid
from unittest import mock

from app.services import trace_ingest_service as tis


def _otlp_payload(service="tmp-svc"):
    return {
        "resourceSpans": [{
            "resource": {"attributes": [{"key": "service.name", "value": {"stringValue": service}}]},
            "scopeSpans": [{"scope": {"name": "t"}, "spans": [{
                "traceId": uuid.uuid4().hex[:32],
                "spanId": uuid.uuid4().hex[:16],
                "name": "op",
                "startTimeUnixNano": "1786676000000000000",
                "endTimeUnixNano": "1786676000500000000",
                "status": {"code": "STATUS_CODE_OK"},
            }]}],
        }]
    }


class _FakeDB:
    def __init__(self):
        self.added = []
        self.commits = 0

    def query(self, model):
        class Q:
            def filter(self, *a, **k):
                return self

            def first(self):
                return None
        return Q()

    def add(self, o):
        self.added.append(o)

    def commit(self):
        self.commits += 1


class TestForwardToTempo:
    def test_no_url_disabled(self):
        with mock.patch.object(tis, "_TEMPO_OTLP_URL", ""):
            assert tis._forward_to_tempo({"resourceSpans": []}) is False

    def test_forward_success(self):
        with mock.patch.object(tis, "_TEMPO_OTLP_URL", "http://tempo:4318/v1/traces"):
            with mock.patch("requests.post") as mpost:
                mpost.return_value.status_code = 202
                mpost.return_value.__bool__ = lambda s: True
                assert tis._forward_to_tempo({"x": 1}) is True
                mpost.assert_called_once()

    def test_forward_down_silent(self):
        with mock.patch.object(tis, "_TEMPO_OTLP_URL", "http://127.0.0.1:1/v1/traces"):
            with mock.patch("requests.post", side_effect=Exception("conn refused")):
                assert tis._forward_to_tempo({"x": 1}) is False


class TestIngestWithTempoFlag:
    def test_unset_no_flag(self):
        with mock.patch.object(tis, "_TEMPO_OTLP_URL", ""):
            r = tis.ingest_otlp_json(_FakeDB(), _otlp_payload())
            assert "tempo_forwarded" not in r
            assert r["ingested"] == 1

    def test_set_flag_present_even_if_down(self):
        with mock.patch.object(tis, "_TEMPO_OTLP_URL", "http://tempo:4318/v1/traces"):
            with mock.patch.object(tis, "_forward_to_tempo", return_value=False):
                r = tis.ingest_otlp_json(_FakeDB(), _otlp_payload())
                assert r.get("tempo_forwarded") is True
                assert r["ingested"] == 1

    def test_forward_called_with_raw(self):
        sent = []
        payload = _otlp_payload()

        def fake_forward(raw):
            sent.append(raw)
            return True

        with mock.patch.object(tis, "_TEMPO_OTLP_URL", "http://tempo:4318/v1/traces"):
            with mock.patch.object(tis, "_forward_to_tempo", fake_forward):
                r = tis.ingest_otlp_json(_FakeDB(), payload)
                assert r.get("tempo_forwarded") is True
                # 转发的是原始 resourceSpans
                assert sent[0]["resourceSpans"][0]["resource"]["attributes"][0]["key"] == "service.name"
