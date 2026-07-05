"""
链路追踪接入 demo - Flask 微服务
3 个服务形成调用链: frontend(5001) -> backend(5002) -> data(5003)
用 OTel SDK 自动埋点 Flask+requests, 自定义 JSON exporter 推送 OTLP/JSON 到 AIOps
"""
import os
import sys
import time
import requests
from flask import Flask, jsonify

sys.path.insert(0, "/data/trace-demo")
from otel_json_exporter import setup_tracing, instrument_app

SERVICE_NAME = os.environ.get("OTEL_SERVICE_NAME", "demo-service")
setup_tracing(SERVICE_NAME)

app = Flask(__name__)
instrument_app(app)


@app.route("/")
def index():
    # frontend 入口: 调用 backend 处理
    r = requests.get("http://127.0.0.1:5002/api/process", timeout=5)
    return jsonify({"service": "demo-frontend", "status": "ok", "backend": r.json()})


@app.route("/api/process")
def process():
    # backend: 处理业务, 调用 data 层
    time.sleep(0.1)
    r = requests.get("http://127.0.0.1:5003/api/data", timeout=5)
    return jsonify({"service": "demo-backend", "status": "processed", "data": r.json()})


@app.route("/api/data")
def data():
    # data 层: 模拟数据库查询
    time.sleep(0.05)
    return jsonify({"service": "demo-data", "record": "order-12345", "ts": time.time()})


if __name__ == "__main__":
    port = int(sys.argv[1]) if len(sys.argv) > 1 else 5001
    app.run(host="127.0.0.1", port=port)
