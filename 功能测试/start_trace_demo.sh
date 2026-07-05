#!/bin/bash
# 启动 3 个 Flask 微服务, 代码内 OTel 自动埋点 + 自定义 JSON exporter 推送到 AIOps
cd /data/trace-demo

# 先杀掉旧进程
pkill -f "app.py 500" 2>/dev/null
sleep 1

export OTEL_EXPORTER_OTLP_ENDPOINT=http://127.0.0.1:8000/api/v1/traces/otlp

# data 服务 (5003)
OTEL_SERVICE_NAME=demo-data \
  nohup /data/trace-demo/venv/bin/python app.py 5003 \
  > /data/trace-demo/data.log 2>&1 &
echo "data service started, pid=$!"

# backend 服务 (5002)
OTEL_SERVICE_NAME=demo-backend \
  nohup /data/trace-demo/venv/bin/python app.py 5002 \
  > /data/trace-demo/backend.log 2>&1 &
echo "backend service started, pid=$!"

# frontend 服务 (5001)
OTEL_SERVICE_NAME=demo-frontend \
  nohup /data/trace-demo/venv/bin/python app.py 5001 \
  > /data/trace-demo/frontend.log 2>&1 &
echo "frontend service started, pid=$!"

sleep 4
echo "=== listening ports ==="
ss -tlnp | grep -E "500[123]"
echo "=== processes ==="
ps -ef | grep "app.py 500" | grep -v grep
