# ===== AIOps 后端 + Web 前端 多阶段构建 =====
# 使用 python:3.11 匹配现有运行环境(项目在 cpython-3.11 下运行)
# torch 单独装 CPU 版以减小镜像; 移动端 H5 不在此镜像(可单独部署)

# ---- Stage 1: 前端构建 (vite) ----
FROM node:20-slim AS frontend-builder
WORKDIR /build
COPY frontend/package.json frontend/package-lock.json ./
RUN npm ci --no-audit --no-fund
COPY frontend/ ./
# Linux 环境用 NODE_OPTIONS(而非 Windows 的 set NODE_OPTIONS=...&& 语法)
RUN NODE_OPTIONS=--max-old-space-size=2048 npm run build

# ---- Stage 2: 后端运行时 ----
FROM python:3.11-slim AS runtime

WORKDIR /app
ENV PYTHONUNBUFFERED=1 \
    PYTHONDONTWRITEBYTECODE=1 \
    TZ=Asia/Shanghai \
    PIP_NO_CACHE_DIR=1

# 生产数据库驱动(PostgreSQL 为默认, 见 docker-compose; 仅内置镜像时用 --build-arg WITH_POSTGRES=0 可跳过)
ARG WITH_POSTGRES=1
RUN if [ "$WITH_POSTGRES" = "1" ]; then pip install --no-cache-dir psycopg2-binary; fi

# 先装 torch CPU 版(单独索引源, 避免 PyPI 默认拉 GPU 版)
RUN pip install --no-cache-dir torch --index-url https://download.pytorch.org/whl/cpu

# 生产依赖
COPY requirements.txt ./
RUN pip install --no-cache-dir -r requirements.txt

# 后端代码
COPY app/ ./app/
COPY run.py ./

# 前端构建产物
COPY --from=frontend-builder /build/dist ./frontend/dist

# 模型权重(BGE ~92MB)
COPY models/ ./models/

# 运行时数据卷: 日志 / 许可证(SQLite 已解耦, 数据库走外部 PostgreSQL)
VOLUME ["/app/logs"]

# 兼容遗留: docker-build 老路径不入卷, 统一用 /app
EXPOSE 8000

HEALTHCHECK --interval=30s --timeout=10s --start-period=90s --retries=3 \
    CMD python -c "import urllib.request; urllib.request.urlopen('http://127.0.0.1:8000/healthz')" || exit 1

CMD ["python", "run.py"]
