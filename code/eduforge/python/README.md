# python — Python 侧源码

EduForge 的 Python 包（`eduforge`）放在这里，采用 src 布局。**Python 依赖与测试配置在工程根的 [`../pyproject.toml`](../pyproject.toml)**（hatchling 构建，wheel 包 `python/src/eduforge`，`testpaths = ["tests/python"]`）；本目录只放源码，虚拟环境 `.venv/` 也建在工程根。

## 结构

- [`src/`](src/README.md) — 包源码 `eduforge`，按分层组织：`agent`（LangGraph 规划）、`api`（FastAPI 业务接口）、`application`（阶段机与发布）、`domain`（协议 DTO）、`infrastructure`（catalog/engine client/Postgres 仓储）、`validation`（策略与独立科学参考）、`worker`（任务执行进程）。逐模块/逐文件细节从 [`src/eduforge/README.md`](src/eduforge/README.md) 进入。
- `src/eduforge/**/__pycache__/` — 运行缓存，已列入 `.gitignore`，非交付内容。

## 常用命令

```bash
cd .. && uv sync          # 环境建在工程根
uv run pytest             # 测试在 ../tests/python
uv run python -m eduforge.worker.run   # 跑 Worker
```
