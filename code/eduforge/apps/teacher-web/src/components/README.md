# components — 展示与交互组件（10 个）

**职责**：教师端全部 UI 组件。按「顶栏三视图」组织——**AI 教学定制工坊**（实验流程）、**光学仿真模拟器**、**81 案例库**；工坊流程内按"模板 → 工作区 → 预览 → 版本 → 下载"排列。

## 内容（逐文件）

| 文件 | 行数 | 职责 | 关键符号 |
|---|---|---|---|
| `SimulatorView.tsx` | 143 | 光学仿真模拟器视图：iframe 内嵌原生 Ray Optics 模拟器（`/simulator/?zh-CN#<scene>`）；场景选择器（空白场景 / 81 案例）、7 个热门预设、全屏模式、"导入 AI 工坊" | `SimulatorView`, `SimulatorViewProps` |
| `GalleryView.tsx` | 127 | 81 案例库视图：分类过滤（全部 + 6 类）、全文检索（标题/描述/分类/贡献者）、一键载入模拟器、一键导入 AI 工坊 | `GalleryView`, `GalleryItem` |
| `TemplateLibrary.tsx` | 43 | 模板库展示与选择 | `TemplateLibrary` |
| `PromptEditor.tsx` | 68 | 需求输入与提交；**幂等键在此生成并持有** | `PromptEditor` |
| `JobProgress.tsx` | 47 | 阶段进度展示 | `JobProgress` |
| `ExperimentWorkspace.tsx` | 88 | 工坊工作区组合（输入 / 进度 / 预览 / **教学视图** / 版本 / 原生与离线包双下载） | `ExperimentWorkspace` |
| `RevisionHistory.tsx` | 75 | 版本历史与回滚入口（**head 由服务端标记，前端不推断**） | `RevisionHistory` |
| `PreviewFrame.tsx` | 178 | 预览 iframe + §5.3 桥接消息处理 + 实时参数调节滑块 | `PreviewFrame` |
| `TeachingViews.tsx` | 94 | **§C.3 教学视图面板**：渲染后端 `GET /revisions/{id}/views` 给的记录表列与行；结构读不出来就如实报错，不猜表头凑数 | `TeachingViews` |
| `DownloadButton.tsx` | 61 | 下载前先校验再存盘（调 `downloadVerified`，支持自定义 label 文本） | `DownloadButton` |
| `ErrorNotice.tsx` | 42 | 错误码 → 教师可读文案映射 | `explain()`, `ErrorNotice` |

## 组合关系

- 三视图导航由 [`../App.tsx`](../README.md) 编排：`SimulatorView` / `GalleryView` / 工坊流程（`ExperimentWorkspace` 及各子组件）。
- `GalleryView` 与 `SimulatorView` 都消费 [`../data/`](../data/README.md) 的 81 案例数据；二者通过回调把「载入模拟器 / 导入工坊」串成链路（`onOpenInSimulator` / `onImportToStudio`）。
- `PreviewFrame` 是**唯一**与 engine-host 预览协议对话的组件（postMessage 同源校验、`eduforge.ready`/`parameter_changed` 处理、滑块经 `/param` 改参）。
- `ErrorNotice` 被多个组件引用（统一错误展示）。

## 与上下层的关系

- 类型：`@eduforge/contracts`（[`../../../../packages/contracts/README.md`](../../../../packages/contracts/README.md)）与本地 [`../data/`](../data/README.md)。
- 被 [`../App.tsx`](../README.md) 编排；样式集中在 [`../styles.css`](../README.md)。

## 已知的坑与纪律

- **幂等键在 `PromptEditor` 生成并持有**：同一需求重试必须复用同一键（防重复任务）——不要在别处再生成。
- **head 不推断**：哪个版本是 head 由服务端下发，`RevisionHistory` 只展示——前端排序不算数。
- `SimulatorView` 的 iframe 指向网关同源的 `/simulator/` 静态路径——模拟器资源由 engine-host 网关托管，不经此处手写 URL 拼接以外的路径。
- 案例数据的增删以 [`../data/galleryData.json`](../data/README.md) 为唯一来源；两个视图都直接 import，不要在组件里另维护列表。
