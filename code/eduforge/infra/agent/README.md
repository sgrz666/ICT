# agent — Python 侧镜像定义（Dockerfile）

**职责**：构建「Python 业务 + Agent 规划」服务的容器镜像：Python 3.12 slim 底座，装依赖，拷入 `python/` 源码与 `catalog/` 数据。

## 内容

| 文件 | 行数 | 关键步骤 |
|---|---|---|
| `Dockerfile` | 24 | `FROM python:3.12-slim` → 装 curl → `COPY python/pyproject.toml` 后 `pip install -e /app` → 拷 `python/` 与 `catalog/` → `EXPOSE 8000 8001` → `CMD ["python", "-m", "eduforge.api.main"]` |

## 与上下层的关系

- 被 [`../compose.local.yaml`](../compose.local.yaml) 的 `agent` 服务引用（构建上下文为工程根）。
- 依赖的源码与数据：[`../../python/`](../../python/README.md)、[`../../catalog/`](../../catalog/README.md)。

## 已知的坑与纪律

- **容器入口与本地入口不同**：本地路径是 `uvicorn eduforge.api.serve:app`（缺环境变量即拒绝启动），容器命令是 `python -m eduforge.api.main`——容器路径的实际可运行性**尚未实测**（pending），首次用容器时先验证。
- `EXPOSE 8000 8001` 但 compose 只映射 `8001`——端口意图以 compose 为准。
- `pip install -e /app` 假设 `pyproject.toml` 位于 `/app` 根——改工程布局要同步本文件。
