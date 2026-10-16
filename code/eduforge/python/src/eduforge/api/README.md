# api — FastAPI 业务接口

**职责**：EduForge 对教师前端暴露的全部业务 HTTP 接口：模板列表、实验创建、任务提交/取消/查询、版本历史、产物列表与下载。路由**集中在 `main.py` 一个文件**（`routes/` 未拆分），安全边界（owner 注入、路径越界、下载哈希校验）都在这层实现。

## 内容（逐文件）

| 文件 | 行数 | 职责 | 关键符号 |
|---|---|---|---|
| `main.py` | 273 | 应用工厂 `create_app(dsn, artifact_dir)` + 全部路由 + owner 注入中间件 + 下载安全校验 | `create_app`, `LOCAL_DEV_OWNER` |
| `serve.py` | 19 | uvicorn 进程入口 `python -m uvicorn eduforge.api.serve:app`；**只从环境变量取 DSN/ARTIFACT_DIR，缺则拒绝启动** | `app` |
| `routes/__init__.py` | 0 | 路由子包标记；**实际未拆分出独立路由文件** | — |

## 端点清单（`main.py` 实现）

| 方法与路径 | 行为 |
|---|---|
| `GET /api/v1/templates` | 模板列表（读 catalog） |
| `POST /api/v1/experiments` | 由模板建实验（克隆基础版本） |
| `GET /api/v1/experiments/{id}` | 实验详情（含 head 版本、控件快照） |
| `POST /api/v1/experiments/{id}/rollback` | 版本回滚（校验 owner/活跃任务） |
| `GET /api/v1/experiments/{id}/revisions` | 版本列表 |
| `POST /api/v1/jobs` | 提交任务（`Idempotency-Key` 头，幂等） |
| `GET /api/v1/jobs/{id}` | 任务状态与事件时间线 |
| `POST /api/v1/jobs/{id}/cancel` | 取消（已成功不回滚） |
| `GET /api/v1/revisions/{id}/artifacts` | 版本产物列表 |
| `GET /api/v1/artifacts/{id}/download` | 产物下载（见下） |

## 下载安全（本层最需要读的一段）

`download` 依 `storage_key` 从 `artifact_dir` 读文件并做三重防护：
1. **path 越界**：解析后不在 `artifact_dir` 内 → 403；
2. **重算 sha256** 与数据库登记比对，不一致 → 500（"字节只认磁盘"的哈希锁）；
3. 响应携带 `x-content-sha256` 头，前端还会独立复算（三方校验：字节 / 响应头 / 清单）。

## 与上下层的关系

- 依赖：[`../application/services.py`](../application/services.py)（应用服务聚合入口）、[`../infrastructure/catalog.py`](../infrastructure/catalog.py)（模板）、[`../infrastructure/db/repositories.py`](../infrastructure/db/repositories.py)（仓储）、[`../domain/contracts.py`](../domain/contracts.py)（response_model）。
- 被谁用：[`serve.py`](serve.py) 起 uvicorn；契约导出脚本 [`../../../../tools/export_contracts.py`](../../../../tools/export_contracts.py) 从本应用的 OpenAPI 生成前端 TS 契约；测试 [`test_gate5_api_chain.py`](../../../../tests/python/test_gate5_api_chain.py)、[`test_contracts_surface.py`](../../../../tests/python/test_contracts_surface.py) 等直接 `create_app`。
- 前端侧消费方：[`../../../../apps/teacher-web/src/api/client.ts`](../../../../apps/teacher-web/src/api/client.ts)。

## 已知的坑与纪律

- **改 API 必跑契约导出**：`uv run python tools/export_contracts.py`，否则 TS 契约漂移（见 [`../../../../packages/contracts/README.md`](../../../../packages/contracts/README.md)）。
- `api/routes/` 目录存在但**没有拆分路由**——别按目录名臆测代码位置。
- owner 由中间件注入（本地开发用 `LOCAL_DEV_OWNER` 常量），版本回滚等操作按 owner 校验；改鉴权逻辑先看该中间件。
- `serve.py` 缺环境变量宁可拒绝启动，不允许回退默认 DSN——部署侧注意。
