"""gRPC OTLP TraceService 服务器 — 接收微服务 gRPC OTLP 流量并入库。"""
import threading
from concurrent.futures import ThreadPoolExecutor
import grpc
from app.database import get_db_mode, get_session_for
from app.services.trace_ingest_service import ingest_otlp_protobuf
from app.logger import logger

_GRPC_HOST = "0.0.0.0"
_GRPC_PORT = 4317
_server = None


class _TraceServiceServicer:
    def Export(self, request, context):
        from opentelemetry.proto.collector.trace.v1.trace_service_pb2 import ExportTraceServiceResponse
        db = get_session_for(get_db_mode())()
        try:
            body = request.SerializeToString()
            result = ingest_otlp_protobuf(db, body)
            if not result.get("is_success"):
                logger.warning(f"[gRPC] Export failed: {result}")
            return ExportTraceServiceResponse()
        except Exception as e:
            logger.error(f"[gRPC] Export error: {e}")
            context.set_code(grpc.StatusCode.INTERNAL)
            context.set_details(str(e))
            return ExportTraceServiceResponse()
        finally:
            db.close()


def start_grpc_server():
    global _server
    if _server is not None:
        return
    from opentelemetry.proto.collector.trace.v1 import trace_service_pb2_grpc
    server = grpc.server(ThreadPoolExecutor(max_workers=10))
    trace_service_pb2_grpc.add_TraceServiceServicer_to_server(
        _TraceServiceServicer(), server
    )
    server.add_insecure_port(f"{_GRPC_HOST}:{_GRPC_PORT}")
    server.start()
    _server = server
    logger.info(f"[gRPC] OTLP TraceService listening on {_GRPC_HOST}:{_GRPC_PORT}")


def stop_grpc_server():
    global _server
    if _server:
        _server.stop(0)
        _server = None