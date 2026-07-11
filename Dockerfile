# 多阶段构建：前端 Vue + 后端 FastAPI 单镜像
# 运行时后端用 StaticFiles 托管 frontend/dist，单容器同时服务 /api 与静态资源

# -------- Stage 1: 构建前端 --------
FROM node:20-alpine AS frontend-builder
WORKDIR /app/frontend
COPY frontend/package.json frontend/package-lock.json* ./
RUN npm ci --no-audit --no-fund
COPY frontend/ ./
RUN npm run build

# -------- Stage 2: 运行后端 + 内嵌前端 dist --------
FROM python:3.11-slim AS runtime
ARG APP_VERSION=1.0.0
ARG APP_BUILD_TIME=
ARG GIT_SHA=
ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    PIP_NO_CACHE_DIR=1 \
    PIP_DISABLE_PIP_VERSION_CHECK=1 \
    APP_VERSION=${APP_VERSION} \
    APP_BUILD_TIME=${APP_BUILD_TIME} \
    GIT_SHA=${GIT_SHA}

WORKDIR /app

RUN apt-get update \
    && apt-get install -y --no-install-recommends ca-certificates \
    && rm -rf /var/lib/apt/lists/*

# 安装 Python 依赖（使用预编译 wheel，不需要 gcc）
COPY backend/requirements.txt /app/backend/requirements.txt
RUN pip install --only-binary :all: --no-cache-dir -r /app/backend/requirements.txt

# 拷贝后端代码（保留 backend/ 目录结构，与 main.py 的路径解析一致）
COPY backend/ /app/backend/

# 拷贝前端构建产物到 main.py 期望位置（backend_dir/../frontend/dist）
# backend_dir = /app/backend → /app/backend/../frontend/dist = /app/frontend/dist
RUN mkdir -p /app/frontend
COPY --from=frontend-builder /app/frontend/dist /app/frontend/dist

WORKDIR /app/backend

# 数据持久化目录（~/.workbuddy-tool 在 root 下）
RUN mkdir -p /root/.workbuddy-tool
VOLUME /root/.workbuddy-tool

EXPOSE 8000 8002

# uvicorn 启动 main:app，监听 0.0.0.0:8000
CMD ["uvicorn", "main:app", "--host", "0.0.0.0", "--port", "8000"]
