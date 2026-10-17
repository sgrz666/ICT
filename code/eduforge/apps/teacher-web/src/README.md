# src — 教师前端源码头（React + Vite）

**职责**：教师端单页应用的全部源码。顶层三件事：状态编排（`App.tsx`）、入口挂载（`main.tsx`）、样式（`styles.css`）；三个子目录各自封装一类关注点——API 客户端（[`api/`](api/README.md)）、组件（[`components/`](components/README.md)）、钩子（[`hooks/`](hooks/README.md)）。

## 内容（根层逐文件）

| 文件 | 行数 | 职责 | 关键符号 |
|---|---|---|---|
| `App.tsx` | 348 | **顶层状态编排 + 三视图导航**：AI 定制工坊（选模板 → 建实验 → 轮询任务 → 刷版本 → 回滚 → 实时调参转提交）/ 光学仿真模拟器 / 81 案例库 | `App` |
| `main.tsx` | 11 | 入口：挂载 `<App/>` 并引入样式 | — |
| `styles.css` | 614 | 深色主题样式（顶栏三视图、模拟器工具栏、案例库网格、实验流程等） | — |

## 子目录

| 子目录 | 职责 | 细节 |
|---|---|---|
| [`api/`](api/README.md) | 业务取数、错误转换、下载校验 | `client.ts` |
| [`components/`](components/README.md) | 11 个组件（三视图 + 工坊流程 + 教学视图面板） | `SimulatorView.tsx` / `GalleryView.tsx` / `PreviewFrame.tsx` |
| [`data/`](data/README.md) | 81 案例库数据（`galleryData.json`） | 模拟器与案例库两视图的共同数据源 |
| [`hooks/`](hooks/README.md) | 任务轮询钩子 | `useJob.ts` |

## 与上下层的关系

- **类型全部来自 `@eduforge/contracts`**（[`../../../packages/contracts/README.md`](../../../packages/contracts/README.md)）——前端不手写 DTO。
- 被谁服务：开发期 vite dev；集成期由浏览器网关（[`../../../services/engine-host/src/gateway/README.md`](../../../services/engine-host/src/gateway/README.md)）把静态站 + `/api` + 预览合成单一源。
- 数据流：`App` → [`api/client.ts`](api/client.ts) → Python API；预览链路 `PreviewFrame` → 网关 → 预览路由（同源）。

## 已知的坑与纪律

- **不在前端手写 DTO**：契约以 `packages/contracts` 的生成物为准，改后端后先跑 `tools/export_contracts.py` 再动前端。
- "实时调参预览"与"正式版本提交"是两条路径：前者走预览桥接（不改库），后者经 `App.tsx` 编排提交任务——别把预览改参当提交。
