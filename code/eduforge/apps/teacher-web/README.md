# teacher-web — 教师端前端

React 18 + Vite 5 + TypeScript 的单页应用（包名 `@eduforge/teacher-web`）。教师在这里完成整条使用链：**选模板 → 建实验 → 提需求 → 看进度 → 预览 → 版本 → 下载产物**。浏览器只面对一个源：Engine Host 的网关同时做静态托管与 `/api` 反代（同源，预览 iframe 才能收到桥接消息）。

## 结构

- `src/App.tsx` — 顶层状态机：模板列表、实验、任务、版本、预览、产物下载的编排。
- `src/api/client.ts` — API 客户端（基于 `@eduforge/contracts` 的生成类型；`downloadVerified` 下载后本地重算哈希与登记值比对）。
- `src/hooks/useJob.ts` — 任务轮询。
- `src/components/` — 界面组件：
  - `MomentumLabView.tsx`（**3D 动量守恒实验台**：5 个预设场景、质量 / 初速度 / 恢复系数 / 弹簧冲量 / 时间倍率、动量与动能双曲线、碰撞事件记录与说明弹层）。
  - `MomentumStage.tsx`（Three.js 3D 舞台：气垫导轨、实验车、速度箭头、碰撞脉冲、弹簧反冲与可旋转轨道相机；DOM 清理覆盖 StrictMode 双挂载）。
  - `momentumPhysics.ts`（纯物理内核：一维碰撞、恢复系数、弹簧反冲、理论碰后速度与越界终止；不依赖 React / Three.js）。
  - `momentum.css`（实验台专属主题与响应式布局，2629 行）。
  - `SimulatorView.tsx`（光学仿真模拟器：内嵌原生 Ray Optics 二维几何光学模拟器，支持自由绘制元件、全屏模式与快速场景切换）。
  - `GalleryView.tsx`（81 个交互式演示案例库：分类过滤、全文检索、一键载入模拟器仿真与一键导入 AI 定制）。
  - `TemplateLibrary.tsx`（模板库）、`PromptEditor.tsx`（需求输入）、`ExperimentWorkspace.tsx`（实验工作区，交付区提供原生场景与离线 ZIP 双下载按钮）、`JobProgress.tsx`（任务进度）、`PreviewFrame.tsx`（预览 iframe + postMessage 桥接）、`TeachingViews.tsx`（**§C.3 教学视图面板**：渲染 `GET /revisions/{id}/views` 给的记录表列与行；结构读不出来就如实说读不出来，不猜表头）、`RevisionHistory.tsx`（版本历史，容器 `id=revision-history`）、`DownloadButton.tsx`（产物下载，支持自定义 label 文本与自主 SHA256 校验）、`ErrorNotice.tsx`（错误展示）。
- `src/data/` — 数据集：
  - `galleryData.json`（81 个案例场景元数据，包含中文分类、原理说明、贡献者与场景链接）。
- `dist/` — `vite build` 产物（`index.html` + `assets/`），由教师端 e2e 测试直接起真服务验证。
- 根文件：`index.html`（页面标题已改为「EduForge 物理实验平台」）、`vite.config.ts`、`tsconfig.json`、`package.json`（脚本 `dev` / `build` / `preview` / `typecheck`；依赖 React 18、`@eduforge/contracts: workspace:*` 与 `three@^0.186.1`，类型来自 `@types/three@^0.186.0`）。

## 功能特性与闭环状态

- **顶栏导航与四视图体系**：支持「🤖 AI 教学定制工坊」、「⚡ 光学仿真模拟器」、「📚 81 演示案例库」、「3D 动量实验室」四大视图切换；进入动量实验室时顶栏强调色切换为实验台自身的黄绿色。
- **全功能原生模拟器直接可用**：原生 Ray Optics 模拟器通过网关同源托管，内置全套绘制工具（点光源、平行光、球面镜、平面镜、透镜、曲面镜、棱镜、光栅等），支持多色模拟与实时光线追踪。
- **81 个交互式案例库全量打通**：涵盖光的反射 (16)、折射 (12)、透镜 (14)、透镜组合 (13)、渐变折射率 (7) 与其他 (19)，支持按分类与关键字即时搜索，支持一键在模拟器中运行。
- **3D 动量守恒实验室（2026-10-18 新增）**：气垫导轨上的一维碰撞。内置等质量正碰、轻车撞重车、完全非弹性、追及碰撞、弹簧反冲 5 个预设；质量、初速度、恢复系数、弹簧冲量与时间倍率均可调。3D 场景含速度矢量、质量配重、碰撞脉冲与可旋转视角；右侧实时显示两车动量、系统总动量与动能账本，底部可切换动量 / 动能曲线并标出碰撞时刻。该视图只依赖浏览器与 Three.js，不调用 Engine Host，因此单独起 Vite 也能完整使用。
- **案例库与 AI 定制工坊严格隔离（Gate C §C.6 R4）**：案例库明确标识「🤖 AI 定制」与「仅演示（不可 AI 定制）」，当前打通并挂载 3 个具备完整清单与验证规约的 AI 定制模板（凸透镜成像、凹透镜发散与成像、照相机成像原理）；其余 78 个案例在导入时明确拦截并给出横幅提示，自动切换至模拟器原生只读仿真，严禁静默退回通用凸透镜模板。
- **版本回滚**：已接通后端 `POST /api/v1/experiments/{id}/rollback`，在 `RevisionHistory.tsx` 支持一键回滚历史版本并保持实验历史完整。
- **预览内实时改参**：已通过模板 `controls` 属性渲染交互控件，通过 postMessage 经包装页桥接请求服务端 `/param` 驱动上游实时仿真重新计算。
- **教学视图已上屏（§C.3，2026-10-17 Chromium 实测）**：`TeachingViews.tsx` 渲染后端 `GET /api/v1/revisions/{id}/views` 给的记录表列与行；数据源是发布时冻结在 `lesson` 里的那一份，界面上那一行与磁盘上的 `teaching_views.json` 逐值比对（用例 `test_teacher_web_e2e.py` 同时断言 u=30 / f=15 / v=30 / 实像 / 放大率 −1）。**仍未做**：视图的导出（下载成表格文件）与切换版本时的实时增量刷新只做到"选版本即重取"。
- **交付场景按 `storage_key` 认领**：一次发布现在登记 native、教学视图、离线包清单三份产物，`App.tsx` 不再取 `artifacts[0]`——靠下标认交付物会在多产物版本上悄悄预览错东西。
- **完整离线实验包一键下载与校验（Gate C §C.5b R2）**：交付区域显式并列「下载原生场景」与「下载完整离线实验包 (.zip)」，通过 `client.downloadVerified` 调用后端流式下载 API，并在浏览器内存自主比对 SHA256 摘要，校验无误后直接落盘保存。
- **种子版本可信真实预览与数据表来源标识（Gate C §C.5c R3）**：未发布原始种子版本通过新增 `GET /api/v1/revisions/{id}/native` 安全读取库中真实原生数据，彻底消除对通用模板的假预览；`TeachingViews.tsx` 为测量表表头标注数据来源（理论参考值 vs 场景参数）并在附注中对理论计算与物理观测进行区分提示。

## 实测与边界（2026-10-18）

- `pnpm --filter @eduforge/teacher-web typecheck` 与 `pnpm --filter @eduforge/teacher-web build` 均通过；构建产物 `dist/assets/index-*.js` 实测 815.07 kB（gzip 229.46 kB），Vite 报出 >500 kB 的拆包提示，**尚未做路由级拆包**。
- 3D 实验室用真 Chromium（Playwright + SwiftShader）实测：在 1440×900 下验证了拖拽视角、相机复位、参数滑杆、场景切换、动量 / 动能曲线切换、说明弹层与「再次实验」；390×844 下验证了响应式布局与启动按钮。三个场景的关键读数与手算一致（等质量碰后交换速度、完全非弹性 e=0 共速 1.33 m/s、反冲总动量 0.000），控制台无 WebGL / React 报错。
- **尚未做**：动量物理内核没有独立单测文件，当前靠浏览器实测与手算对照（pending）；WebGL 不可用时只显示错误说明，没有 2D canvas 降级版。

## 关系

- 类型契约来自 [`../../packages/contracts`](../../packages/contracts/README.md)（由 FastAPI OpenAPI 生成，不手写第二套 DTO）。
- 预览与下载依赖 [`../../services/engine-host`](../../services/engine-host/README.md) 的预览服务与浏览器网关。
- 3D 动量实验室是纯前端视图，不经过 `api/client.ts`，也不依赖引擎宿主。
- 金路径 e2e 在 [`../../tests/python/test_teacher_web_e2e.py`](../../tests/python/README.md)（真 Postgres + 真 Worker + 真浏览器）。
