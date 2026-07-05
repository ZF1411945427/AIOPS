#!/bin/bash
# 启动 3 个 Flask 微服务, OTLP 通过反向隧道推送到本地 AIOps(8000)
cd /data/trace-demo

pkill -9 -f "app.py 500" 2>/dev/null
sleep 1

# OTLP 端点指向服务器3的 18000 端口(反向 SSH 隧道 -> 本地 8000)
export OTEL_EXPORTER_OTLP_ENDPOINT=http://127.0.0.1:18000/api/v1/traces/otlp

OTEL_SERVICE_NAME=demo-data \
  nohup /data/trace-demo/venv/bin/python app.py 5003 \
  > /data/trace-demo/data.log 2>&1 &
echo "data service started, pid=$!"

OTEL_SERVICE_NAME=demo-backend \
  nohup /data/trace-demo/venv/bin/python app.py 5002 \
  > /data/trace-demo/backend.log 2>&1 &
echo "backend service started, pid=$!"

OTEL_SERVICE_NAME=demo-frontend \
  nohup /data/trace-demo/venv/bin/python app.py 5001 \
  > /data/trace-demo/frontend.log 2>&1 &
echo "frontend service started, pid=$!"

sleep 4
echo "=== listening ports ==="
ss -tlnp | grep -E "500[123]"
echo "=== processes ==="
ps -ef | grep "app.py 500" | grep -v grep
