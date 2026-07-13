# ===== Stage 1: 构建前端 (Web) =====
FROM node:20-slim AS frontend-builder
WORKDIR /build
COPY frontend/package.json frontend/package-lock.json ./
RUN npm ci --no-audit --no-fund
COPY frontend/ ./
RUN npm run build

# ===== Stage 2: 构建移动端 (H5) =====
FROM node:20-slim AS mobile-builder
WORKDIR /build
COPY mobile/package.json mobile/package-lock.json ./
RUN npm ci --no-audit --no-fund
COPY mobile/ ./
RUN npm run build:h5

# ===== Stage 3: 运行时 =====
FROM python:3.12-slim AS runtime

WORKDIR /app

# 先装 torch CPU 版（单独索引源，避免 PyPI 默认拉 GPU 版）
RUN pip install --no-cache-dir torch --index-url https://download.pytorch.org/whl/cpu

# 再装其余生产依赖
COPY requirements.txt ./
RUN pip install --no-cache-dir -r requirements.txt

# 复制后端代码
COPY app/ ./app/
COPY run.py ./

# 复制前端构建产物
COPY --from=frontend-builder /build/dist ./frontend/dist
COPY --from=mobile-builder /build/dist/build/h5 ./mobile/dist/build/h5

# 复制模型权重（BGE-small ~92MB）
COPY models/ ./models/

# 数据卷：数据库、日志、许可证
VOLUME ["/app/db", "/app/logs"]

EXPOSE 8000

HEALTHCHECK --interval=30s --timeout=10s --start-period=60s --retries=3 \
    CMD python -c "import urllib.request; urllib.request.urlopen('http://127.0.0.1:8000/login')" || exit 1

CMD ["python", "run.py"]
