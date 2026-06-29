"""
Trace 数据接入服务 — 接收 OpenTelemetry Collector 推送的 OTLP/HTTP JSON 格式 span 数据。
支持两种接入方式：
1. OTLP/HTTP 推送（Collector → 本系统 /api/v1/traces/otlp）
2. Jaeger API 拉取（本系统主动从 Jaeger 后端拉取）
"""
import json
from datetime import datetime, timezone
from sqlalchemy.orm import Session
from app.models import Span


def _nano_to_datetime(nano_str: str) -> datetime:
    """OTLP 时间戳是纳秒字符串，转为 Python datetime"""
    try:
        nano = int(nano_str)
        seconds = nano / 1_000_000_000
        return datetime.fromtimestamp(seconds, tz=timezone.utc).replace(tzinfo=None)
    except (ValueError, TypeError):
        return datetime.now()


def _extract_attr_value(attr_value: dict) -> str:
    """从 OTLP attribute value 中提取实际值"""
    if not attr_value:
        return ""
    for vt in ("stringValue", "intValue", "doubleValue", "boolValue", "arrayValue"):
        if vt in attr_value:
            v = attr_value[vt]
            if vt == "boolValue":
                return str(v)
            return str(v)
    return json.dumps(attr_value, ensure_ascii=False)


def _parse_attributes(attrs: list) -> dict:
    """解析 OTLP attributes 列表为 dict"""
    result = {}
    if not attrs:
        return result
    for attr in attrs:
        key = attr.get("key", "")
        value = _extract_attr_value(attr.get("value", {}))
        if key:
            result[key] = value
    return result


def _get_service_name(resource: dict) -> str:
    """从 resource.attributes 中提取 service.name"""
    attrs = resource.get("attributes", []) if resource else []
    for attr in attrs:
        if attr.get("key") == "service.name":
            return _extract_attr_value(attr.get("value", {}))
    return "unknown"


def _get_span_kind(kind_str: str) -> str:
    """映射 OTLP span kind"""
    mapping = {
        "SPAN_KIND_UNSPECIFIED": "unspecified",
        "SPAN_KIND_INTERNAL": "internal",
        "SPAN_KIND_SERVER": "server",
        "SPAN_KIND_CLIENT": "client",
        "SPAN_KIND_PRODUCER": "producer",
        "SPAN_KIND_CONSUMER": "consumer",
    }
    return mapping.get(kind_str, kind_str or "unspecified")


def _get_span_status(status_obj: dict) -> str:
    """映射 OTLP span status"""
    code = status_obj.get("code", "STATUS_CODE_UNSET") if status_obj else "STATUS_CODE_UNSET"
    if code in ("STATUS_CODE_ERROR",):
        return "ERROR"
    if code in ("STATUS_CODE_OK",):
        return "OK"
    return "OK"


def ingest_otlp_json(db: Session, otlp_data: dict) -> dict:
    """
    解析 OTLP/HTTP JSON 格式的 trace 数据并写入 Span 表。

    OTLP JSON 结构:
    {
      "resourceSpans": [
        {
          "resource": { "attributes": [{"key": "service.name", "value": {"stringValue": "xxx"}}] },
          "scopeSpans": [
            {
              "spans": [
                {
                  "traceId": "hexstring",
                  "spanId": "hexstring",
                  "parentSpanId": "hexstring",
                  "name": "operation name",
                  "kind": "SPAN_KIND_SERVER",
                  "startTimeUnixNano": "1690000000000000000",
                  "endTimeUnixNano": "1690000000500000000",
                  "status": {"code": "STATUS_CODE_ERROR"},
                  "attributes": [{"key": "http.method", "value": {"stringValue": "GET"}}]
                }
              ]
            }
          ]
        }
      ]
    }
    """
    resource_spans = otlp_data.get("resourceSpans", [])
    if not resource_spans:
        return {"success": False, "message": "No resourceSpans found", "ingested": 0}

    total = 0
    errors = 0
    services_seen = set()

    for rs in resource_spans:
        resource = rs.get("resource", {})
        service_name = _get_service_name(resource)
        services_seen.add(service_name)

        scope_spans = rs.get("scopeSpans", [])
        for ss in scope_spans:
            spans = ss.get("spans", [])
            for sp in spans:
                try:
                    trace_id = sp.get("traceId", "")
                    span_id = sp.get("spanId", "")
                    parent_span_id = sp.get("parentSpanId", "")

                    if not trace_id or not span_id:
                        errors += 1
                        continue

                    start_time = _nano_to_datetime(sp.get("startTimeUnixNano", "0"))
                    end_time = _nano_to_datetime(sp.get("endTimeUnixNano", "0"))
                    duration_ms = 0.0
                    if end_time > start_time:
                        duration_ms = (end_time - start_time).total_seconds() * 1000

                    # 解析 attributes
                    tags = _parse_attributes(sp.get("attributes", []))
                    # 加上 resource 级别的属性
                    res_attrs = _parse_attributes(resource.get("attributes", []))
                    for k, v in res_attrs.items():
                        if k not in tags:
                            tags[k] = v
                    # 加上 kind 和 status message
                    tags["otel.kind"] = _get_span_kind(sp.get("kind", ""))
                    status_obj = sp.get("status", {})
                    if status_obj.get("message"):
                        tags["otel.status_message"] = status_obj["message"]

                    status = _get_span_status(status_obj)

                    # 去重：同一 trace_id + span_id 不重复写入
                    existing = db.query(Span).filter(
                        Span.trace_id == trace_id,
                        Span.span_id == span_id,
                    ).first()
                    if existing:
                        # 更已有 span
                        existing.service_name = service_name
                        existing.operation_name = sp.get("name", "")
                        existing.start_time = start_time
                        existing.end_time = end_time
                        existing.duration_ms = duration_ms
                        existing.status = status
                        existing.tags = json.dumps(tags, ensure_ascii=False)
                    else:
                        db.add(Span(
                            trace_id=trace_id,
                            span_id=span_id,
                            parent_span_id=parent_span_id,
                            service_name=service_name,
                            operation_name=sp.get("name", ""),
                            start_time=start_time,
                            end_time=end_time,
                            duration_ms=round(duration_ms, 1),
                            status=status,
                            tags=json.dumps(tags, ensure_ascii=False),
                        ))
                    total += 1
                except Exception as e:
                    errors += 1
                    continue

    db.commit()
    return {
        "success": True,
        "message": f"Ingested {total} spans from {len(services_seen)} services",
        "ingested": total,
        "errors": errors,
        "services": list(services_seen),
    }


def fetch_from_jaeger(db: Session, jaeger_url: str, service: str = "", limit: int = 20) -> dict:
    """
    从 Jaeger 后端 API 拉取 trace 数据并写入 Span 表。

    Jaeger API 端点:
    - GET /api/traces?service=xxx&limit=20
    - GET /api/traces/{trace_id}
    """
    import urllib.request
    import urllib.error

    try:
        url = jaeger_url.rstrip("/")
        if service:
            url += f"/api/traces?service={service}&limit={limit}"
        else:
            url += f"/api/traces?limit={limit}"

        req = urllib.request.Request(url, headers={"Accept": "application/json"})
        with urllib.request.urlopen(req, timeout=15) as resp:
            data = json.loads(resp.read().decode("utf-8"))

        jaeger_traces = data.get("data", [])
        total = 0
        services_seen = set()

        for jt in jaeger_traces:
            trace_id = jt.get("traceID", "")
            jaeger_spans = jt.get("spans", [])
            jaeger_processes = jt.get("processes", {})

            for jsp in jaeger_spans:
                span_id = jsp.get("spanID", "")
                parent_span_id = ""
                refs = jsp.get("references", [])
                for ref in refs:
                    if ref.get("refType") == "CHILD_OF":
                        parent_span_id = ref.get("spanID", "")
                        break

                # 从 process 获取 service name
                proc_id = jsp.get("processID", "")
                proc = jaeger_processes.get(proc_id, {})
                proc_tags = proc.get("tags", [])
                service_name = "unknown"
                for tag in proc_tags:
                    if tag.get("key") == "serviceName":
                        service_name = tag.get("value", "unknown")
                        break
                services_seen.add(service_name)

                # 时间戳: Jaeger 用微秒
                start_us = jsp.get("startTime", 0)
                dur_us = jsp.get("duration", 0)
                start_time = datetime.fromtimestamp(start_us / 1_000_000)
                end_time = datetime.fromtimestamp((start_us + dur_us) / 1_000_000)
                duration_ms = dur_us / 1000.0

                # tags
                tags = {}
                for tag in jsp.get("tags", []):
                    tags[tag.get("key", "")] = str(tag.get("value", ""))
                for tag in proc_tags:
                    if tag.get("key") != "serviceName":
                        tags[tag.get("key", "")] = str(tag.get("value", ""))

                # status
                status = "OK"
                for tag in jsp.get("tags", []):
                    if tag.get("key") == "error" and tag.get("value") is True:
                        status = "ERROR"
                        break

                # 去重
                existing = db.query(Span).filter(
                    Span.trace_id == trace_id,
                    Span.span_id == span_id,
                ).first()
                if existing:
                    existing.service_name = service_name
                    existing.operation_name = jsp.get("operationName", "")
                    existing.start_time = start_time
                    existing.end_time = end_time
                    existing.duration_ms = round(duration_ms, 1)
                    existing.status = status
                    existing.tags = json.dumps(tags, ensure_ascii=False)
                else:
                    db.add(Span(
                        trace_id=trace_id,
                        span_id=span_id,
                        parent_span_id=parent_span_id,
                        service_name=service_name,
                        operation_name=jsp.get("operationName", ""),
                        start_time=start_time,
                        end_time=end_time,
                        duration_ms=round(duration_ms, 1),
                        status=status,
                        tags=json.dumps(tags, ensure_ascii=False),
                    ))
                total += 1

        db.commit()
        return {
            "success": True,
            "message": f"Fetched {total} spans from {len(services_seen)} services via Jaeger",
            "ingested": total,
            "services": list(services_seen),
        }
    except urllib.error.URLError as e:
        return {"success": False, "message": f"Jaeger 连接失败: {e}", "ingested": 0}
    except Exception as e:
        return {"success": False, "message": f"Jaeger 拉取异常: {e}", "ingested": 0}
