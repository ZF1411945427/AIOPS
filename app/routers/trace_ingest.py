"""
Trace 数据接入路由
- POST /api/v1/traces/otlp   接收 OTLP/HTTP JSON 推送
- POST /api/v1/traces/jaeger  从 Jaeger 后端拉取
- GET  /api/v1/traces/agent-guide  获取 Agent 安装指引
- GET  /api/v1/traces/ingest-status  获取接入状态
"""
import json
from fastapi import APIRouter, Depends, Request, Body
from fastapi.responses import JSONResponse
from sqlalchemy.orm import Session
from app.database import get_db
from app.models import Span, DataSource
from app.services.trace_ingest_service import ingest_otlp_json, fetch_from_jaeger

router = APIRouter(prefix="/api/v1/traces", tags=["trace_ingest"])


@router.post("/otlp")
async def receive_otlp(request: Request, db: Session = Depends(get_db)):
    """接收 OpenTelemetry Collector 推送的 OTLP/HTTP JSON 格式 span 数据"""
    try:
        body = await request.body()
        otlp_data = json.loads(body)
        result = ingest_otlp_json(db, otlp_data)
        return JSONResponse(result)
    except json.JSONDecodeError:
        return JSONResponse({"success": False, "message": "Invalid JSON format"}, status_code=400)
    except Exception as e:
        return JSONResponse({"success": False, "message": str(e)}, status_code=500)


@router.post("/jaeger")
def pull_from_jaeger(
    db: Session = Depends(get_db),
    jaeger_url: str = Body("", embed=True),
    service: str = Body("", embed=True),
    limit: int = Body(20, embed=True)):
    """从 Jaeger 后端 API 主动拉取 trace 数据"""
    if not jaeger_url:
        # 尝试从数据源中找 jaeger 类型
        jaeger_ds = db.query(DataSource).filter(
            DataSource.type == "jaeger", DataSource.enabled == True
        ).first()
        if jaeger_ds:
            jaeger_url = jaeger_ds.endpoint
        else:
            return JSONResponse({"success": False, "message": "No jaeger_url provided and no jaeger datasource found"})
    result = fetch_from_jaeger(db, jaeger_url, service, limit)
    return JSONResponse(result)


@router.get("/ingest-status")
def ingest_status(db: Session = Depends(get_db)):
    """获取 trace 数据接入状态"""
    total_spans = db.query(Span).count()
    total_traces = db.query(Span.trace_id).distinct().count()
    services = [r[0] for r in db.query(Span.service_name).distinct().all() if r[0]]
    # 检查是否有 jaeger 数据源
    jaeger_sources = db.query(DataSource).filter(DataSource.type == "jaeger").all()
    otel_sources = db.query(DataSource).filter(DataSource.type == "otel").all()

    # 最近 span 时间
    latest = db.query(Span).order_by(Span.created_at.desc()).first()
    latest_time = latest.created_at.strftime("%Y-%m-%d %H:%M:%S") if latest else None

    return JSONResponse({
        "total_spans": total_spans,
        "total_traces": total_traces,
        "services": sorted(services),
        "jaeger_sources": [{"id": s.id, "name": s.name, "endpoint": s.endpoint, "enabled": s.enabled} for s in jaeger_sources],
        "otel_sources": [{"id": s.id, "name": s.name, "endpoint": s.endpoint, "enabled": s.enabled} for s in otel_sources],
        "latest_span_time": latest_time,
        "otlp_endpoint": "/api/v1/traces/otlp",
    })


@router.get("/agent-guide")
def agent_guide():
    """获取各语言/环境的 Agent 安装指引（供前端展示）"""
    return JSONResponse({
        "otlp_endpoint": "/api/v1/traces/otlp",
        "guides": {
            "java": {
                "title": "Java (Spring Boot / JAR)",
                "type": "javaagent 自动注入",
                "steps": [
                    "1. 下载 OpenTelemetry Java Agent:\n   curl -L -o opentelemetry-javaagent.jar https://github.com/open-telemetry/opentelemetry-java-instrumentation/releases/latest/download/opentelemetry-javaagent.jar",
                    "2. 启动服务时挂载 Agent:\n   java -javaagent:./opentelemetry-javaagent.jar \\\n        -Dotel.service.name=your-service-name \\\n        -Dotel.exporter.otlp.endpoint=http://<AIOps-IP>:8000/api/v1/traces/otlp \\\n        -Dotel.exporter.otlp.protocol=http/json \\\n        -jar your-app.jar",
                    "3. 或在 Dockerfile 中内置:\n   ENV JAVA_TOOL_OPTIONS=-javaagent:/otel/opentelemetry-javaagent.jar\n   ENV OTEL_SERVICE_NAME=your-service-name\n   ENV OTEL_EXPORTER_OTLP_ENDPOINT=http://<AIOps-IP>:8000/api/v1/traces/otlp\n   ENV OTEL_EXPORTER_OTLP_PROTOCOL=http/json",
                ],
            },
            "python": {
                "title": "Python (Flask / FastAPI / Django)",
                "type": "自动注入 + 手动 SDK",
                "steps": [
                    "1. 安装 OpenTelemetry 包:\n   pip install opentelemetry-distro opentelemetry-exporter-otlp\n   opentelemetry-bootstrap -a install",
                    "2. 自动注入启动:\n   opentelemetry-instrument \\\n        --service_name your-service-name \\\n        --exporter_otlp_endpoint http://<AIOps-IP>:8000/api/v1/traces/otlp \\\n        --exporter_otlp_protocol http/json \\\n        python app.py",
                    "3. 或在代码中手动配置:\n   from opentelemetry import trace\n   from opentelemetry.sdk.trace import TracerProvider\n   from opentelemetry.sdk.trace.export import BatchSpanProcessor\n   from opentelemetry.exporter.otlp.proto.http.trace_exporter import OTLPSpanExporter\n\n   provider = TracerProvider()\n   exporter = OTLPSpanExporter(endpoint='http://<AIOps-IP>:8000/api/v1/traces/otlp')\n   provider.add_span_processor(BatchSpanProcessor(exporter))\n   trace.set_tracer_provider(provider)",
                ],
            },
            "go": {
                "title": "Go (Gin / gRPC / net/http)",
                "type": "SDK 手动埋点",
                "steps": [
                    "1. 安装 OpenTelemetry Go SDK:\n   go get go.opentelemetry.io/otel \\\n        go.opentelemetry.io/otel/sdk \\\n        go.opentelemetry.io/otel/exporters/otlp/otlptrace/otlptracehttp",
                    "2. 代码初始化:\n   import (\n     \"go.opentelemetry.io/otel\"\n     \"go.opentelemetry.io/otel/exporters/otlp/otlptrace/otlptracehttp\"\n     \"go.opentelemetry.io/otel/sdk/trace\"\n   )\n\n   exporter, _ := otlptracehttp.New(ctx,\n     otlptracehttp.WithEndpoint(\"<AIOps-IP>:8000\"),\n     otlptracehttp.WithURLPath(\"/api/v1/traces/otlp\"),\n     otlptracehttp.WithInsecure(),\n   )\n   tp := trace.NewTracerProvider(\n     trace.WithBatcher(exporter),\n   )\n   otel.SetTracerProvider(tp)",
                ],
            },
            "nodejs": {
                "title": "Node.js (Express / Koa / NestJS)",
                "type": "自动注入",
                "steps": [
                    "1. 安装包:\n   npm install @opentelemetry/auto-instrumentations-node @opentelemetry/exporter-trace-otlp-http",
                    "2. 启动时加载:\n   node --require @opentelemetry/auto-instrumentations-node/register app.js\n\n   环境变量:\n   export OTEL_SERVICE_NAME=your-service-name\n   export OTEL_EXPORTER_OTLP_ENDPOINT=http://<AIOps-IP>:8000/api/v1/traces/otlp\n   export OTEL_EXPORTER_OTLP_PROTOCOL=http/json",
                ],
            },
            "k8s": {
                "title": "Kubernetes (自动注入所有 Pod)",
                "type": "OpenTelemetry Operator + Sidecar",
                "steps": [
                    "1. 安装 OTel Operator:\n   kubectl apply -f https://github.com/open-telemetry/opentelemetry-operator/releases/latest/download/opentelemetry-operator.yaml",
                    "2. 创建 Instrumentation 实例 (指向本系统):\n   apiVersion: opentelemetry.io/v1alpha1\n   kind: Instrumentation\n   metadata:\n     name: aiops-tracing\n   spec:\n     exporter:\n       endpoint: http://<AIOps-IP>:8000/api/v1/traces/otlp\n     propagators: [\"tracecontext\", \"baggage\"]\n     sampler:\n       type: parentbased_traceidratio\n       argument: \"0.25\"",
                    "3. 给 namespace 打标签启用自动注入:\n   kubectl label namespace production opentelemetry-injection=enabled\n\n   之后该 namespace 下所有 Pod 自动注入 Agent，无需改代码！",
                ],
            },
            "docker": {
                "title": "Docker (单机容器)",
                "type": "环境变量 + Volume 挂载",
                "steps": [
                    "1. Java 容器示例:\n   docker run -d \\\n     -e JAVA_TOOL_OPTIONS=-javaagent:/otel/opentelemetry-javaagent.jar \\\n     -e OTEL_SERVICE_NAME=your-service \\\n     -e OTEL_EXPORTER_OTLP_ENDPOINT=http://<AIOps-IP>:8000/api/v1/traces/otlp \\\n     -e OTEL_EXPORTER_OTLP_PROTOCOL=http/json \\\n     -v /path/to/opentelemetry-javaagent.jar:/otel/opentelemetry-javaagent.jar \\\n     your-image:latest",
                    "2. Python 容器示例:\n   docker run -d \\\n     -e OTEL_SERVICE_NAME=your-service \\\n     -e OTEL_EXPORTER_OTLP_ENDPOINT=http://<AIOps-IP>:8000/api/v1/traces/otlp \\\n     -e OTEL_EXPORTER_OTLP_PROTOCOL=http/json \\\n     your-image:latest\n     opentelemetry-instrument python app.py",
                ],
            },
            "middleware": {
                "title": "中间件 / 数据库 (MySQL/Redis/Kafka/Nginx)",
                "type": "通过调用方间接追踪",
                "steps": [
                    "说明: 中间件本身通常不需要单独安装 Agent。当上游服务（Java/Python/Go 等）通过 OpenTelemetry SDK 访问中间件时，SDK 会自动拦截数据库/缓存/MQ 调用并生成子 Span。\n\n例如 Java 应用通过 JDBC 访问 MySQL、通过 Jedis 访问 Redis、通过 Kafka Client 发消息，OTel Java Agent 都会自动创建对应的 DB/Cache/MQ Span，无需在 MySQL/Redis 上装 Agent。\n\n如果需要追踪 Nginx 入口请求:\n  - 方案1: 使用 OpenResty + otelsdk nginx 模块\n  - 方案2: 在 Nginx 后面的应用层（如 Spring Cloud Gateway）埋点\n  - 方案3: 使用 eBPF 工具（如 Pixie）在内核层无侵入采集",
                ],
            },
            "traditional": {
                "title": "传统服务 (物理机 / 虚拟机)",
                "type": "Agent + 环境变量",
                "steps": [
                    "1. 下载对应语言的 OTel Agent 到服务器:\n   Java: curl -L -o /opt/otel/opentelemetry-javaagent.jar <url>\n   Python: pip install opentelemetry-distro && opentelemetry-bootstrap -a install\n   Node: npm install -g @opentelemetry/auto-instrumentations-node",
                    "2. 修改启动脚本加环境变量:\n   export OTEL_SERVICE_NAME=your-service\n   export OTEL_EXPORTER_OTLP_ENDPOINT=http://<AIOps-IP>:8000/api/v1/traces/otlp\n   export OTEL_EXPORTER_OTLP_PROTOCOL=http/json\n\n   Java: java -javaagent:/opt/otel/opentelemetry-javaagent.jar -jar app.jar\n   Python: opentelemetry-instrument python app.py\n   Node: node --require @opentelemetry/auto-instrumentations-node/register app.js",
                ],
            },
        }
    })
