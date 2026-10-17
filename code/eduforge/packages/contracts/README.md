# contracts — 前后端契约包

包名 `@eduforge/contracts`。**业务 DTO 只能有一个来源：后端 FastAPI 的 OpenAPI。** 本包把 OpenAPI 生成 TS 类型，`teacher-web` 与 `engine-host` 都从这里引，杜绝手写第二套类型两边漂移。

## 结构

- `src/generated/api.ts` — 由 `tools/export_contracts.py` 从 FastAPI `/openapi.json` 生成（22 个具名接口＝21 个 OpenAPI schema + 导出器附带的 `ApiOperations` 操作映射）。
- `src/generated/openapi.json` — 生成时的 OpenAPI 快照。
- `src/preview.ts` — 预览桥接的 postMessage 消息类型（宿主页 ↔ 预览 iframe，与后端无关，故手写）。
- `src/index.ts` — 出口（`export * from "./generated/api"; export * from "./preview";`）。
- 根文件：`package.json`、`tsconfig.json`。

## 纪律

- 改了任何业务路由（`python/src/eduforge/api/`），必须重跑 `uv run python tools/export_contracts.py`；`tests/python/test_contracts_surface.py` 会在生成物落后于后端时直接红。
- `src/generated/` 是生成目录，不手改；要改类型改后端。

## 关系

- 上游：`../../python/src/eduforge/api/`（OpenAPI 生产者）。
- 下游：`../../apps/teacher-web`（主要消费者）、`../../services/engine-host`（预览消息类型）。
