# src — 契约包源码头（@eduforge/contracts）

**职责**：前后端共享的类型契约。两类内容泾渭分明：**业务 HTTP 契约**（由后端 OpenAPI 生成，勿手改）与**预览桥接协议**（§5.3，手写，与 engine-host 侧手动同步）。

## 内容（逐文件）

| 文件 | 行数 | 职责 | 关键符号 |
|---|---|---|---|
| `index.ts` | 2 | barrel 再导出：`./generated/api` 与 `./preview` | — |
| `preview.ts` | 19 | §5.3 预览桥接协议（postMessage，不在 OpenAPI 内）；与 [`../../../services/engine-host/src/preview/messages.ts`](../../../services/engine-host/src/preview/README.md) **手动保持同步** | `PreviewMessage`, `SetParameterRequest` |
| [`generated/`](generated/README.md) | — | OpenAPI 生成的业务 DTO | 见子 README |

## 与上下层的关系

- **生成方向**：Python 后端 FastAPI → OpenAPI 规约 → `tools/export_contracts.py` → [`generated/api.ts`](generated/README.md)。消费方全在 teacher-web（[`../../../apps/teacher-web/src/`](../../../apps/teacher-web/src/README.md)）。
- engine-host **不使用**本包（它有自己的 [`../../../services/engine-host/src/contracts.ts`](../../../services/engine-host/src/README.md)）——只有 `preview.ts` 与它构成"两份同协议"的手动同步对。

## 已知的坑与纪律

- **改后端 API 后必跑**：`cd code/eduforge && uv run python tools/export_contracts.py`，否则前端类型漂移。
- `generated/` 内文件头明确「不要手改」；手改会在下次导出被覆盖。
- `preview.ts` 与 engine-host 的 `PreviewMessage` 是**两份定义、一份协议**：改字段必须两边同改（合约包注释已声明）。
