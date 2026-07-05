"""
OTel 自定义 JSON Exporter - 把 OTel SDK 生成的 span 序列化为 OTLP/HTTP JSON 推送到 AIOps
原因: OTel Python SDK 1.43 的 OTLPSpanExporter 只支持 http/protobuf, 不支持 http/json,
而 AIOps 后端用 json.loads 解析只接受 JSON, 故自定义 exporter 做序列化转换。
"""
import os
import requests
from opentelemetry import trace
from opentelemetry.sdk.trace import TracerProvider
from opentelemetry.sdk.trace.export import SpanExporter, SpanExportResult, SimpleSpanProcessor
from opentelemetry.sdk.resources import Resource, SERVICE_NAME
from opentelemetry.instrumentation.flask import FlaskInstrumentor
from opentelemetry.instrumentation.requests import RequestsInstrumentor

OTLP_ENDPOINT = os.environ.get(
    "OTEL_EXPORTER_OTLP_ENDPOINT",
    "http://127.0.0.1:8000/api/v1/traces/otlp",
)

_KIND_MAP = {
    0: "SPAN_KIND_UNSPECIFIED",
    1: "SPAN_KIND_INTERNAL",
    2: "SPAN_KIND_SERVER",
    3: "SPAN_KIND_CLIENT",
    4: "SPAN_KIND_PRODUCER",
    5: "SPAN_KIND_CONSUMER",
}
_STATUS_MAP = {0: "STATUS_CODE_UNSET", 1: "STATUS_CODE_OK", 2: "STATUS_CODE_ERROR"}


def _attr_value(v):
    if isinstance(v, bool):
        return {"boolValue": v}
    if isinstance(v, int):
        return {"intValue": str(v)}
    if isinstance(v, float):
        return {"doubleValue": v}
    return {"stringValue": str(v)}


class JsonOtlpExporter(SpanExporter):
    """把 OTel span 序列化为 OTLP/HTTP JSON, POST 到 AIOps /api/v1/traces/otlp"""

    def export(self, spans):
        try:
            payload = self._build_payload(spans)
            resp = requests.post(
                OTLP_ENDPOINT, json=payload, timeout=5,
                headers={"Content-Type": "application/json"},
            )
            print(f"[JsonOtlpExporter] exported {len(spans)} spans -> {resp.status_code} {resp.text[:200]}")
        except Exception as e:
            print(f"[JsonOtlpExporter] export error: {e}")
        return SpanExportResult.SUCCESS

    def _build_payload(self, spans):
        resource_spans_map = {}
        for sp in spans:
            res_key = id(sp.resource)
            if res_key not in resource_spans_map:
                res_attrs = [
                    {"key": k, "value": _attr_value(v)}
                    for k, v in sp.resource.attributes.items()
                ]
                resource_spans_map[res_key] = {
                    "resource": {"attributes": res_attrs},
                    "spans": [],
                }
            resource_spans_map[res_key]["spans"].append(self._span_to_dict(sp))
        return {
            "resourceSpans": [
                {
                    "resource": g["resource"],
                    "scopeSpans": [
                        {"scope": {"name": "aiops-demo"}, "spans": g["spans"]}
                    ],
                }
                for g in resource_spans_map.values()
            ]
        }

    def _span_to_dict(self, sp):
        d = {
            "traceId": format(sp.context.trace_id, "032x"),
            "spanId": format(sp.context.span_id, "016x"),
            "name": sp.name,
            "kind": _KIND_MAP.get(sp.kind, "SPAN_KIND_UNSPECIFIED"),
            "startTimeUnixNano": str(sp.start_time),
            "endTimeUnixNano": str(sp.end_time),
            "attributes": [
                {"key": k, "value": _attr_value(v)}
                for k, v in sp.attributes.items()
            ],
            "status": {"code": _STATUS_MAP.get(sp.status.status_code, "STATUS_CODE_UNSET")},
        }
        if sp.parent:
            d["parentSpanId"] = format(sp.parent.span_id, "016x")
        return d

    def shutdown(self):
        pass


def setup_tracing(service_name):
    """初始化 OTel TracerProvider, 注入自定义 JSON exporter"""
    resource = Resource.create({SERVICE_NAME: service_name})
    provider = TracerProvider(resource=resource)
    exporter = JsonOtlpExporter()
    provider.add_span_processor(SimpleSpanProcessor(exporter))
    trace.set_tracer_provider(provider)
    print(f"[tracing] service={service_name} -> {OTLP_ENDPOINT}")


def instrument_app(app):
    """自动埋点 Flask + requests (生成 HTTP 调用 span + 传播 trace context)"""
    FlaskInstrumentor().instrument_app(app)
    RequestsInstrumentor().instrument()
    print("[tracing] Flask + requests instrumented")
