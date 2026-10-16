# EduForge Python 业务与 Agent 规划服务 Dockerfile
FROM python:3.12-slim

WORKDIR /app

ENV PYTHONUNBUFFERED=1 \
    PYTHONDONTWRITEBYTECODE=1

# 安装系统依赖
RUN apt-get update && apt-get install -y --no-install-recommends \
    curl \
    && rm -rf /var/lib/apt/lists/*

# 安装 Python 依赖
COPY python/pyproject.toml /app/
RUN pip install --no-cache-dir -e /app

# 拷贝源码
COPY python /app/python
COPY catalog /app/catalog

EXPOSE 8000 8001

CMD ["python", "-m", "eduforge.api.main"]
