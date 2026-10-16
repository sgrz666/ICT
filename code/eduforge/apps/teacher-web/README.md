# teacher-web — 教师端前端

React 18 + Vite 5 + TypeScript 的单页应用（包名 `@eduforge/teacher-web`）。教师在这里完成整条使用链：**选模板 → 建实验 → 提需求 → 看进度 → 预览 → 版本 → 下载产物**。浏览器只面对一个源：Engine Host 的网关同时做静态托管与 `/api` 反代（同源，预览 iframe 才能收到桥接消息）。

## 结构

- `src/App.tsx` — 顶层状态机：模板列表、实验、任务、版本、预览、产物下载的编排。
- `src/api/client.ts` — API 客户端（基于 `@eduforge/contracts` 的生成类型；`downloadVerified` 下载后本地重算哈希与登记值比对）。
- `src/hooks/useJob.ts` — 任务轮询。
- `src/components/` — 界面组件：
  - `SimulatorView.tsx`（光学仿真模拟器：内嵌原生 Ray Optics 二维几何光学模拟器，支持自由绘制元件、全屏模式与快速场景切换）。
  - `GalleryView.tsx`（81 个交互式演示案例库：分类过滤、全文检索、一键载入模拟器仿真与一键导入 AI 定制）。
  - `TemplateLibrary.tsx`（模板库）、`PromptEditor.tsx`（需求输入）、`ExperimentWorkspace.tsx`（实验工作区）、`JobProgress.tsx`（任务进度）、`PreviewFrame.tsx`（预览 iframe + postMessage 桥接）、`RevisionHistory.tsx`（版本历史）、`DownloadButton.tsx`（产物下载）、`ErrorNotice.tsx`（错误展示）。
- `src/data/` — 数据集：
  - `galleryData.json`（81 个案例场景元数据，包含中文分类、原理说明、贡献者与场景链接）。
- `dist/` — `vite build` 产物（`index.html` + `assets/`），由教师端 e2e 测试直接起真服务验证。
- 根文件：`index.html`、`vite.config.ts`、`tsconfig.json`、`package.json`（脚本 `dev` / `build` / `preview` / `typecheck`；依赖 React 18 与 `@eduforge/contracts: workspace:*`）。

## 功能特性与闭环状态

- **顶栏导航与三视图体系**：支持「🤖 AI 教学定制工坊」、「⚡ 光学仿真模拟器」、「📚 81 演示案例库」三大视图无缝切换。
- **全功能原生模拟器直接可用**：原生 Ray Optics 模拟器通过网关同源托管，内置全套绘制工具（点光源、平行光、球面镜、平面镜、透镜、曲面镜、棱镜、光栅等），支持多色模拟与实时光线追踪。
- **81 个交互式案例库全量打通**：涵盖光的反射 (16)、折射 (12)、透镜 (14)、透镜组合 (13)、渐变折射率 (7) 与其他 (19)，支持按分类与关键字即时搜索，支持一键在模拟器中运行，支持一键导入 AI 定制工坊。
- **版本回滚**：已接通后端 `POST /api/v1/experiments/{id}/rollback`，在 `RevisionHistory.tsx` 支持一键回滚历史版本并保持实验历史完整。
- **预览内实时改参**：已通过模板 `controls` 属性渲染交互控件，通过 postMessage 经包装页桥接请求服务端 `/param` 驱动上游实时仿真重新计算。

## 关系

- 类型契约来自 [`../../packages/contracts`](../../packages/contracts/README.md)（由 FastAPI OpenAPI 生成，不手写第二套 DTO）。
- 预览与下载依赖 [`../../services/engine-host`](../../services/engine-host/README.md) 的预览服务与浏览器网关。
- 金路径 e2e 在 [`../../tests/python/test_teacher_web_e2e.py`](../../tests/python/README.md)（真 Postgres + 真 Worker + 真浏览器）。
