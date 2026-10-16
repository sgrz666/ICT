# generated — OpenAPI 生成物（勿手改）

**职责**：由后端 OpenAPI 规约生成的业务 DTO。本目录的全部内容都是**生成物**：文件头注明了"不要手改"，改动会在下次导出被覆盖。

## 内容（逐文件）

| 文件 | 行数 | 职责 | 关键符号 |
|---|---|---|---|
| `api.ts` | 134 | 由 `openapi.json` 生成的前端可用 TS 类型与操作清单 | `ApiErrorResponse`、`TemplateSummary`/`ControlSummary`、`ExperimentCreated`/`ExperimentDetail`、`RevisionSummary`/`RevisionList`/`RevisionArtifacts`、`JobAccepted`/`JobView`/`JobEvent`、`CreateJobRequest`/`RollbackRequest`/`ArtifactSummary`、`ApiOperations`、`OPENAPI_VERSION` |
| `openapi.json` | 1119 | 后端 FastAPI 导出的 OpenAPI 原始规约（生成输入） | — |

## 生成链

后端 [`../../../../python/src/eduforge/api/README.md`](../../../../python/src/eduforge/api/README.md)（FastAPI 的 response_model）→ OpenAPI → [`../../../../tools/export_contracts.py`](../../../../tools/README.md) → `openapi.json` + `api.ts`（本目录）。

## 与上下层的关系

- 再导出：[`../index.ts`](../README.md) barrel → 前端 `@eduforge/contracts` 整体引入。
- 消费方：teacher-web 全部组件与钩子（精确清单见 [`../../../../apps/teacher-web/src/README.md`](../../../../apps/teacher-web/src/README.md)）。

## 已知的坑与纪律

- **不要手改**：任何修改请在 Python 侧改 response_model 后重跑导出脚本。
- `openapi.json` 与 `api.ts` 必须同批更新（同一脚本产出）——只出现其一说明导出中断，重跑。
