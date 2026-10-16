# api — 前端 API 客户端

**职责**：前端与 Python 业务 API 之间的唯一客户端封装：业务 DTO 取数、错误码转换、产物下载与**哈希三方校验**。

## 内容（逐文件）

| 文件 | 行数 | 职责 | 关键符号 |
|---|---|---|---|
| `client.ts` | 119 | 封装全部业务调用；下载产物后**自己重算 sha256**（字节 / 响应头 / 清单三方校验） | `ApiError`, `api`, `sha256Hex()`, `downloadVerified()`, `VerifiedArtifact` |

## `api` 对象的调用面

`templates` / `createExperiment` / `submitJob`（携带幂等键）/ `job` / `experiment` / `revisions` / `artifacts` / `cancelJob` / `rollbackExperiment` / `registerPreview`。

## 与上下层的关系

- 类型来源：[`../../../../packages/contracts/README.md`](../../../../packages/contracts/README.md)（`@eduforge/contracts`）。
- 消费方：[`../components/PromptEditor.tsx`](../components/README.md)、[`../components/DownloadButton.tsx`](../components/README.md)、[`../hooks/useJob.ts`](../hooks/README.md)、[`../App.tsx`](../README.md)。

## 已知的坑与纪律

- `downloadVerified` 的三方校验（下载字节 / `x-content-sha256` 响应头 / 清单登记值）**不得简化**——这是"下载的确实是验证过的字节"的最终保证。
- `ApiError` 携带后端错误码；教师可读文案由 [`../components/ErrorNotice.tsx`](../components/README.md) 的 `explain()` 统一映射——新增错误码在那一处加，不散落。
