# ICT — 创新赛道项目工作区

一句话概括：这是华为云 ICT 创新赛道（赛题 2：基于 AgentArts 智能体开发平台的 Agent 设计和应用，教育方向）的本地研发工作区。当前主线是 **EduForge** —— 把成熟的开源实验引擎（首批 Ray Optics 5.5.0）接进「教师提需求 → Agent 规划修改 → 本地程序化验证 → 交付离线可跑实验」的闭环；配套部署了逆向分析工具 **REA**（Reverse Engineer Anything）用于解剖上游引擎。

## 目录地图

| 目录 | 职责 | 入口 |
|---|---|---|
| [`code/`](code/README.md) | 全部自研代码，主工程是 `code/eduforge` | [code/eduforge/README.md](code/eduforge/README.md) |
| [`input/`](input/README.md) | REA 逆向分析的输入样本 | rea-smoke-test（冒烟样本）、research-targets（预留） |
| [`output/`](output/README.md) | 运行产物与验证证据 | `output/eduforge/reports/` 是证据最集中的地方 |
| [`plan/`](plan/README.md) | 计划、排期、闸门与逐轮记录 | 推进计划 + 代码级实施方案 |
| [`scripts/`](scripts/README.md) | 工作区统一操作脚本 | [`scripts/eduforge.ps1`](scripts/README.md)（doctor/test/smoke/benchmark/up/down） |
| [`source/`](source/README.md) | 上游引擎源码、npm 实验组件、实验资源目录 | [`source/library/experiments.json`](source/library/experiments.json)（Agent 消费入口）+ `source/upstream/upstream.lock.json`（身份锁定） |
| [`task/`](task/README.md) | 赛题原件 | ICT创新赛道赛题.docx |
| [`deep-agent/`](deep-agent/README.md) | **独立验证工作区**：DeepSeek 官方 Harness（`dsh`）源码部署 + 原生 Agent 能力验证，与 EduForge 生产代码隔离 | [启动指南与逐文件索引](deep-agent/README.md)（2026-10-17 入库，本轮登记进本地图） |
| [`2026-10-18-11-03-28/`](2026-10-18-11-03-28/README.md) | **教学实验生成流水线**：一句需求 → 检索知识 → 生成单文件 HTML → 无头浏览器审查 → 返工交付 | 四个角色目录 + `run_pipeline.py`；**当前未入版本库**，`01_single_agent/.env` 已被 `.gitignore` 挡住 |
| [`1024交付/`](1024交付/README.md) | **多学科交互实验交付区**：物理/数学/化学 12 项独立交互实验离线包 + 六学科统一设计总览 + 高清动态预览 | [1024交付/README.md](1024交付/README.md) |
| [`agent/`](agent/README.md) | 预留目录，当前只有一份 README | 计划放智能体侧资产 |

`node_modules/`（根目录下的 `rea-agents` 及其依赖）是依赖目录，不属于项目结构，本 README 体系不覆盖它。

## 逐目录索引

**覆盖口径（2026-10-20 实测）**：

- 项目侧 `README.md` 磁盘实测 **133 份**（`AGENTS.md` 第 5 节命令 (2) 的口径）：**110 份已入库**、**20 份待 `git add`**（教学流水线 13 份 + 新模板 / LabKit 子目录 / `deep-agent/local-tools/` 的现场说明）、**3 份在已忽略的产物目录里**（`output/eduforge/candidates/labkit/**` 的现场说明）。
- 按 `git ls-files` 口径（含可 add 但未 add 的），入库/可入库目录共 **129 个**，**每个都有自己的 README，缺失 0**；相对链接断链 **0**（第三方树按「自带 `.git` 就剪掉」排除，其内部链接不归本体系管）。
- 上一基线：101 份 / 100 目录（2026-10-18）、108 份（2026-10-19）。增量来源是并行会话在 `source/`、`code/eduforge/catalog/templates/`、`tools/labkit/` 一侧落盘的目录说明，本轮未改那些正文，只按实测登记；本轮自己补的是教学流水线里 8 个没有 README 的子目录，以及把根 README 与工作线段落改写成可读完的短句（原先有一条 2,861 字符的单条 bullet）。
- 校验命令见 [`AGENTS.md`](AGENTS.md) 第 5 节。它按约定跳过上游树，并且剪枝规则是「**任何自带 `.git` 的子目录直接剪掉**」——`source/upstream/` 装了 30 个第三方仓库，不剪枝会既卡住又把上游 README 误计进项目侧数字。
- 每一行只写「这个目录是干什么的」，具体文件、数字与坑在各目录自己的 README 里。

### [`code/`](code/README.md) — 自研代码

- [`code/eduforge/`](code/eduforge/README.md) — EduForge 主工程（pnpm workspace + Python 包双栈）
  - **前端** [`apps/`](code/eduforge/apps/README.md) → [`apps/teacher-web/`](code/eduforge/apps/teacher-web/README.md) 教师端（React + Vite）
    - [`src/`](code/eduforge/apps/teacher-web/src/README.md) 源码头 → [`src/api/`](code/eduforge/apps/teacher-web/src/api/README.md) API 客户端 · [`src/components/`](code/eduforge/apps/teacher-web/src/components/README.md) 组件 · [`src/data/`](code/eduforge/apps/teacher-web/src/data/README.md) 前端数据集 · [`src/hooks/`](code/eduforge/apps/teacher-web/src/hooks/README.md) React 钩子
  - **数据层（不是代码）** [`catalog/`](code/eduforge/catalog/README.md)
    - [`catalog/engines/`](code/eduforge/catalog/engines/README.md) 引擎描述（`ray-optics.yaml` 是全仓库测试计数的唯一处）
    - [`catalog/templates/`](code/eduforge/catalog/templates/README.md) 模板按「学科/实验」两级，实测 **6 个**：
      - [`optics/`](code/eduforge/catalog/templates/optics/README.md) → [`convex-lens/`](code/eduforge/catalog/templates/optics/convex-lens/README.md) · [`concave-lens/`](code/eduforge/catalog/templates/optics/concave-lens/README.md) · [`camera-principle/`](code/eduforge/catalog/templates/optics/camera-principle/README.md)（引擎 `ray_optics`，走 engine-host 主链路）
      - [`mechanics/`](code/eduforge/catalog/templates/mechanics/README.md) → [`projectile/`](code/eduforge/catalog/templates/mechanics/projectile/README.md)（含空气阻力控件）与 [`pendulum/`](code/eduforge/catalog/templates/mechanics/pendulum/README.md)（引擎 `matter_js`）
      - [`circuits/`](code/eduforge/catalog/templates/circuits/README.md) → [`ohms-law/`](code/eduforge/catalog/templates/circuits/ohms-law/README.md)（引擎 `circuit_mna`）
      - 力学与电路这三条走的是 [`tools/labkit/`](code/eduforge/tools/labkit/README.md) 的**文件级链路**（`status: verified` = L1/L2/L3 实测通过），**不在教师端模板库里**；`engine_id` 的 `matter_js` / `circuit_mna` 在 `catalog/engines/` 下也还没有对应描述文件。
  - **契约包** [`packages/`](code/eduforge/packages/README.md) → [`contracts/`](code/eduforge/packages/contracts/README.md) → [`src/`](code/eduforge/packages/contracts/src/README.md) 手写类型 · [`src/generated/`](code/eduforge/packages/contracts/src/generated/README.md) OpenAPI 生成物（勿手改）
  - **Python 侧** [`python/`](code/eduforge/python/README.md) → [`python/src/`](code/eduforge/python/src/README.md) 模块地图 → 包根 [`eduforge/`](code/eduforge/python/src/eduforge/README.md)
    - [`agent/`](code/eduforge/python/src/eduforge/agent/README.md) 执行核心与授权防线 · [`agent/prompts/`](code/eduforge/python/src/eduforge/agent/prompts/README.md) 系统行为规范
    - [`api/`](code/eduforge/python/src/eduforge/api/README.md) FastAPI 业务接口 · [`api/routes/`](code/eduforge/python/src/eduforge/api/routes/README.md) 空占位包（路由未拆分，都在 `main.py`）
    - [`application/`](code/eduforge/python/src/eduforge/application/README.md) 用例编排 · [`domain/`](code/eduforge/python/src/eduforge/domain/README.md) 纯净核心层
    - [`worker/`](code/eduforge/python/src/eduforge/worker/README.md) 五阶段任务执行 · [`experiment_tools/`](code/eduforge/python/src/eduforge/experiment_tools/README.md) 8 项引擎原子工具
    - [`infrastructure/`](code/eduforge/python/src/eduforge/infrastructure/README.md) 外部适配 → [`clients/`](code/eduforge/python/src/eduforge/infrastructure/clients/README.md) · [`db/`](code/eduforge/python/src/eduforge/infrastructure/db/README.md) · [`storage/`](code/eduforge/python/src/eduforge/infrastructure/storage/README.md)
    - [`validation/`](code/eduforge/python/src/eduforge/validation/README.md) 验证与发布门禁 → [`scientific/`](code/eduforge/python/src/eduforge/validation/scientific/README.md) 独立科学参考式
    - [`coding/`](code/eduforge/python/src/eduforge/coding/README.md) 代码定制（切片 7 预留）· [`entrypoints/`](code/eduforge/python/src/eduforge/entrypoints/README.md) 智能体运行入口 · [`research/`](code/eduforge/python/src/eduforge/research/README.md) REA 运行器
  - **Node 侧服务** [`services/`](code/eduforge/services/README.md) → [`engine-host/`](code/eduforge/services/engine-host/README.md) 引擎宿主；新增 [`agent-runtime/`](code/eduforge/services/agent-runtime/README.md) 原生 dsh 启智 Web、教学/开发双预设与 Windows 发行入口
    - [`src/`](code/eduforge/services/engine-host/src/README.md) 源码头 → [`adapters/`](code/eduforge/services/engine-host/src/adapters/README.md) 适配器分组层 → [`adapters/ray-optics/`](code/eduforge/services/engine-host/src/adapters/ray-optics/README.md) · [`export/`](code/eduforge/services/engine-host/src/export/README.md) 离线包组装 · [`gateway/`](code/eduforge/services/engine-host/src/gateway/README.md) 浏览器网关 · [`preview/`](code/eduforge/services/engine-host/src/preview/README.md) 预览桥接
    - [`tests/`](code/eduforge/services/engine-host/tests/README.md) vitest 套件 → [`adapters/`](code/eduforge/services/engine-host/tests/adapters/README.md) → [`adapters/ray-optics/`](code/eduforge/services/engine-host/tests/adapters/ray-optics/README.md) · [`e2e/`](code/eduforge/services/engine-host/tests/e2e/README.md) 真实浏览器 · [`engines/`](code/eduforge/services/engine-host/tests/engines/README.md) 引擎级验收 · [`gateway/`](code/eduforge/services/engine-host/tests/gateway/README.md) 网关路由
  - **领域规范** [`skills/`](code/eduforge/skills/README.md) → [`ray-optics-customization/`](code/eduforge/skills/ray-optics-customization/README.md) **已启用** · [`mechanics-customization/`](code/eduforge/skills/mechanics-customization/README.md) · [`circuit-customization/`](code/eduforge/skills/circuit-customization/README.md)（后两个零代码读取）
  - **测试与工具** [`tests/`](code/eduforge/tests/README.md) → [`tests/python/`](code/eduforge/tests/python/README.md) pytest 用例 · [`tools/`](code/eduforge/tools/README.md) 验证探针与代码生成，含 [`tools/labkit/`](code/eduforge/tools/labkit/README.md)（抛体/单摆/电路的第二条链路：L1 校验 → L2 物理对账 → 单文件渲染 → L3 浏览器实测） · [`benchmarks/`](code/eduforge/benchmarks/README.md) 12 题评测集
  - **容器** [`infra/`](code/eduforge/infra/README.md) → [`agent/`](code/eduforge/infra/agent/README.md) · [`engine-host/`](code/eduforge/infra/engine-host/README.md) 镜像定义 · [`sandbox/`](code/eduforge/infra/sandbox/README.md)（切片 7 预留）· [`launcher/`](code/eduforge/infra/launcher/README.md)（切片 9 预留）

### [`deep-agent/`](deep-agent/README.md) — DeepSeek Harness 验证工作区

10 个入库目录，各自都有 README；**文件级清单与「怎么启动」不在这里复制**，看 [deep-agent/README.md](deep-agent/README.md) 的「精细目录索引」与「如何启动」两节（从裸机克隆、三条构建命令的实测退出码、Web UI / headless CLI / 复跑五项测试、Windows 权限置备与回滚、启动失败对照表）。

- [`harness-validation-reports/`](deep-agent/harness-validation-reports/README.md) — 结论层：7 份报告（安装 / API 联调 / Agent 循环实测 / 架构笔记 / 集成评估 / 品牌重构 v1 与 v2）+ 可重放补丁
- [`_logs/`](deep-agent/_logs/README.md) — 证据层：54 份现场（19 份编号构建与启动日志 + 11 组 `<stem>.jsonl/.err/.meta` 运行三元组 + 2 份单文件）
- [`_tools/`](deep-agent/_tools/README.md) — 复现层：`run_headless.sh`、`summarize_events.mjs`、文档门 `check_docs.py` → [`_tools/prompts/`](deep-agent/_tools/prompts/README.md) 五项任务原文与只读探针
- [`_probe/`](deep-agent/_probe/README.md) — 前提层：故意带缺陷的 `cart.py` + 暴露它的测试，以及官方要求的逐字快照
- [`patches/`](deep-agent/patches/README.md) — 官方 `--patch` 覆盖层（含「不足以移动会话 cwd」的实测结论）
- [`dsh-acl-recovery/`](deep-agent/dsh-acl-recovery/README.md) — 系统权限改动的备份、回滚脚本与完整记录
- [`harness-ui-workspace/`](deep-agent/harness-ui-workspace/README.md) — Web UI 核验沙盒（含审批放行后真实写入的文件）
- [`local-tools/`](deep-agent/local-tools/README.md) — **dsh 本地插件层**（不改上游树）：`dsh-labkit` 把 LabKit 注册成六个 `experiment_*` 原生工具，带 `physics-lab` agent preset 与交付包，一句话产出一节实验课（HTML + 教师手册 + 学生任务单）
- [`dsh-core/`](deep-agent/dsh-core/README.md) — **Python 研究原型**：自有测试通过不代表官方运行时等价，隔离、子智能体、压缩和实验验证仍有缺口；正式运行路线为原生 [`agent-runtime/`](code/eduforge/services/agent-runtime/README.md)
- 不入库：`deepseek-harness/`（2.7 GB 上游源码，验证对象本体）、`harness-smoke-workspace/`（一次性工作区 + 嵌套 `.git`）、`_corepack/`、`.dsh-home/`（含 `.credentials.yaml`，敏感）

### [`1024交付/`](1024交付/README.md) — 多学科教学实验离线交付区

包含 12 门基础学科教学交互实验的独立离线发布包、全套运行态 GIF 高清动图与六学科统一设计风格页面。

- [`六学科统一质感.html`](1024交付/六学科统一质感.html) — 六大学科一致性设计语言总览
- [`物理/`](1024交付/物理/README.md) — 4 个物理实验包（伏安法测电阻、探究浮力规律、杠杆实验、验证动量守恒）
- [`数学/`](1024交付/数学/README.md) — 4 个数学探究包（二次函数、截正方体、椭圆离心率、长方体外接球）
- [`化学/`](1024交付/化学/README.md) — 4 个化学实验包（有机分子球棍模型、盐类水解、指示剂与pH、铁与硫酸铜反应）
- [`GIF预览/`](1024交付/GIF预览/README.md) — 全量实验高清录屏 GIF 动图展示库

### [`2026-10-18-11-03-28/`](2026-10-18-11-03-28/README.md) — 教学实验生成流水线

一句需求进、离线可跑的交互实验 HTML 出。四个角色 + 一个编排器 + 主题配置表，**整个目录尚未入版本库**；每个目录都有自己的 README，跑法与已知边界在该目录根部的 README 里，这里只给层级地图。

- [`01_single_agent/`](2026-10-18-11-03-28/01_single_agent/README.md) 需求理解（模型 + 提示词 → 8 字段 JSON）→ [`output/`](2026-10-18-11-03-28/01_single_agent/output/README.md) `需求_*.json`
- [`02_retrieval_agent/`](2026-10-18-11-03-28/02_retrieval_agent/README.md) 知识检索（BM25 多路召回 + 类别保底，不用模型）→ [`knowledge/`](2026-10-18-11-03-28/02_retrieval_agent/knowledge/README.md) 两主题 × 五类共 10 份 md · [`output/`](2026-10-18-11-03-28/02_retrieval_agent/output/README.md) `知识包_*.json`
- [`03_generator_agent/`](2026-10-18-11-03-28/03_generator_agent/README.md) 生成单文件 HTML（清洗 → 校验 → 修复 → 兜底）→ [`output/`](2026-10-18-11-03-28/03_generator_agent/output/README.md) 页面与 meta · [`templates/`](2026-10-18-11-03-28/03_generator_agent/templates/README.md) 兜底模板（四个占位符，且它只会产出电路页面）
- [`04_review_agent/`](2026-10-18-11-03-28/04_review_agent/README.md) 质量审查（规则 + 无头浏览器真操作）→ [`output/`](2026-10-18-11-03-28/04_review_agent/output/README.md) `审查报告_*.json` · [`tests/`](2026-10-18-11-03-28/04_review_agent/tests/README.md) 两个自测夹具（故障注入负例实测 27.5 分不通过；公式解析正例）
- [`runs/`](2026-10-18-11-03-28/runs/README.md) — 14 次端到端运行的完整档案（含 `交付_教学资源.html` 取历史最高分那一版；`20261018-133036` 只有 `输入.txt`，那是一次中断的运行）

### 其余顶层目录

- [`input/`](input/README.md) — REA 分析的输入 → [`rea-smoke-test/`](input/rea-smoke-test/README.md) 冒烟样本 → [`src/`](input/rea-smoke-test/src/README.md) 样本源码 · [`research-targets/`](input/research-targets/README.md)（预留）
- [`output/`](output/README.md) — 运行产物与证据 → [`eduforge/`](output/eduforge/README.md) → [`reports/`](output/eduforge/reports/README.md) **验证证据** · [`artifacts/`](output/eduforge/artifacts/README.md) 运行期落盘 · [`candidates/`](output/eduforge/candidates/README.md) 离线包候选 · [`research/`](output/eduforge/research/README.md)（预留）
- [`plan/`](plan/README.md) — 计划、排期与逐轮记录（只追加不回改）
- [`scripts/`](scripts/README.md) — 工作区统一操作脚本（`eduforge.ps1`）
- [`source/`](source/README.md) — 实验资源库三层 → [`upstream/`](source/upstream/README.md) 上游引擎源码（45 个安装单元，16 个引擎/资源目录）· [`components/`](source/components/README.md) npm 组件与可加载性实测 · [`library/`](source/library/README.md) 实验目录（18 个优先实验映射到引擎与验收公式）
- [`task/`](task/README.md) — 赛题原件 · [`agent/`](agent/README.md) — 预留，当前只有一份 README

## 四条工作线

### 1. EduForge 主工程（`code/eduforge`）

pnpm workspace（TypeScript：engine-host / teacher-web / contracts）+ Python 包（agent / api / application / worker / validation / entrypoints）。模板与引擎描述在 `catalog/`，实测证据在 `output/eduforge/reports/`，排期闸门在 `plan/`。**另有第二条链路 LabKit**（`tools/labkit/`：设计 → 物理对账 → 单文件 HTML → 浏览器实测），覆盖抛体、单摆、直流电路三个模板，绕开 engine-host 与数据库——入口与状态见 [`code/eduforge/README.md`](code/eduforge/README.md)。

### 2. 实验资源库（`source/`）

三层结构：`upstream/` 上游引擎源码、`components/` npm 组件、`library/` 实验目录。**逐条实测数字的家在 [`source/library/README.md`](source/library/README.md) 与 [`source/upstream/README.md`](source/upstream/README.md)，本文件只留能一眼读完的结论**：

- **装了多大**：16 个引擎/资源目录、45 个安装单元，工作区约 2.0 GB（含各仓 `.git` 约 3.9 GB）；身份与构建结论锁在 [`source/upstream/upstream.lock.json`](source/upstream/upstream.lock.json)。2026-10-19 把简报里七项平台全部落到磁盘（新增 OSP 家族 6 仓与 3JCN 目录镜像），并**撤销**上一轮「这两项找不到权威来源所以不装」的结论——组织名实测是 `OpenSourcePhysics`，3JCN 是可抓的静态站。`not_installed` 已清零。
- **18 条优先实验**（`source/library/experiments.json`）：全部在真引擎里跑出过与解析式对账的读数。状态词分七档，写在 `experiments.json` 开头的 `status_words` 里，就是为了不把「装了源码」说成「接通了」。
- **PhET 官方成品 13 份被量成四档**：展示级 13/13、可读级 6/13、**可写级 1/13**（只有 ohms-law 能用键盘改 V/R 且电流对上 `I=V/R`，6/6 pass，最大偏差 0.18% 是画面显示位数）、API 级 0/13（没有可调用 PhET-iO）。⇒ 「一律改不动」被推翻一半，「都改得动」同样不成立；成品还带 CC BY-NC 4.0 非商业条款。
- **EJSS/OSP 整批进了回归脚本**：`ejss_headless_sweep.mjs` 把 25 个 EJS 6.02 包在无头浏览器里逐个跑，实测 25/25 零异常加载、25/25 控制面全套、25/25 轨迹可复现、24/25 写值落地（两个没过的都是探针选中了模型每步重算的派生量，不是包不可控）。官方那条 `.ejs → 编译 → webejs 加载` 链路一步没跑。
- **电学走浏览器态**：`circuit_headless_lab.mjs` 把 CircuitJS1 验收台 4/4 场景跑通、连跑两遍一致；过程中揪出验收台自己两处空判据，旧的那条 RC pass 因此被判定不可靠并按充电钟重做。
- **3JCN 只到「UI 可驱动」**：`apparent_weight_exp` 拿到第一只完整一档（5/5 滑块可写、可观测、可复原），但采不到 DOM 数字读数，跨域 jQuery/bootstrap 还没代理 ⇒ 不标 `engine_*_verified`。判据与四趟历史见 [`source/library/README.md`](source/library/README.md) 的 3JCN 一节。

一句话纪律：**「装上了」「能打开」「Agent 能改参」「能交付离线包」是四件事**，本仓库的每一条状态词都只声称自己实测过的那一层。

### 3. REA 逆向分析

根 `package.json` + `input/`：`rea-agents@6.5.0` 项目内与全局双安装，CLI 与 MCP 服务器均可用；冒烟样本在 `input/rea-smoke-test`，分析产物在 `output/rea-smoke-test.json`。

### 4. 教学实验生成流水线（`2026-10-18-11-03-28/`，2026-10-18 起）

一句需求 → 结构化理解 → BM25 知识检索 → 生成单文件 HTML → 规则 + 无头浏览器审查 → 返工循环，交付历史最高分那一版。四个角色 + 一个编排器，跑法是仓库里 `python run_pipeline.py "生成一个浮力实验"`；两个端到端场景实测成绩 90.9 分（电路，1 轮）与 100 分（浮力，2 轮）。

**这个目录目前还没进版本库**（`git ls-files` 里 0 条），里面的 `01_single_agent/.env` 存着 `LLM_API_KEY`，已由根 `.gitignore` 的 `.env` 规则挡住（2026-10-20 加）。它与 EduForge、LabKit 是**并行的第三套实现**，不要混着引用状态。详见该目录自己的 [`README.md`](2026-10-18-11-03-28/README.md)。

## 当前状态（2026-10-16 基线；3D 动量实验室于 2026-10-18 追加）

- 切片 1（引擎本地化与协议地基）的主要目标已达成并被实测证明：成熟光学引擎可以在本地被程序化修改，改完的仿真结果与独立薄透镜公式吻合。证据链见 `plan/26.10.15_EduForge_推进计划.md` 的「实况」节。
- 测试规模的**唯一计数处**是 `code/eduforge/catalog/engines/ray-optics.yaml` 的 `test_totals`（本轮同步 README 时该处为 vitest 84 / pytest 158，其中 1 项真模型用例在无 key 时显式 SKIPPED）。本文件与其余 README 只引用那一处：历史上同一份文档里同时残留过 103/125/137 与 54/74 四个过期值，就是各自抄数造成的。
- 教师前端最小闭环已达成：选模板 → 建实验 → 提需求 → 进度查看 → 实时仿真预览与参数调节 → 版本历史与**版本回滚** → 产物下载校验。
- 教师前端已扩展四视图：AI 定制工坊、内嵌光学仿真模拟器（自由绘制元件）、81 个交互式案例库、3D 动量守恒实验室（气垫导轨碰撞、弹簧反冲、动量 / 动能双曲线；细节见 `code/eduforge/apps/teacher-web/README.md`）。
- 尚未闭环的（不要当成已完成）：DeepSeek 真实模型对照（缺 `DEEPSEEK_API_KEY`，已用桩模型覆盖图结构与策略链）、切片 7 容器沙箱（本机无 Docker Desktop）、Go 离线启动器、单文件 HTML 交付形态（Ray Optics 那条上游运行时 HTTP 取词，`file://` 直开不成立，需 i18n 预注入；PhET 成品这边实测可以单文件离线起，物理量则逐只不同：13 份里没有一份有参数 API，默认只有 6 份读得到数值、只有 ohms-law 一份实测能改参并验算（见 `source/library/phet-ohms-writeproof.json`））。

## 常用命令

```powershell
# 工作区统一入口（推荐）
.\scripts\eduforge.ps1 doctor        # 环境与端口健康度检查
.\scripts\eduforge.ps1 test          # 跑全量 pytest (125) 与 vitest (67)
.\scripts\eduforge.ps1 smoke         # 真实 Chromium 端到端金路径测试
.\scripts\eduforge.ps1 benchmark -Profile screening  # 12 题筛查基准评测

# REA（根目录）
npm run rea:doctor          # 就绪检查
rea analyze-javascript-application ./input/rea-smoke-test

# EduForge Python 侧
cd code/eduforge
uv run pytest               # 全量 pytest（用例数只记在 catalog/engines/ray-optics.yaml 的 test_totals）

# EduForge TypeScript 侧
cd code/eduforge
pnpm -r test                # 54 个 vitest 用例
pnpm --filter @eduforge/teacher-web dev   # 教师前端开发服务器
```

## 版本控制

- 远程仓库：`https://github.com/sgrz666/ICT`（main 分支）。
- 入库范围：全部自研代码、计划与证据文档、上游锁定记录（`source/upstream/upstream.lock.json`）、赛题原件。
- 不入库（见 `.gitignore`）：`node_modules/`、`.venv/`、`__pycache__/`、`dist*/`、`.pytest_cache/` 等可重新生成的依赖与构建产物；`output/eduforge/candidates/`（离线包产物）；`.workbuddy/`（本地 Agent 工作区数据）；`source/upstream/ray-optics/`（628M 上游检出、自带 `.git`，身份由 lock 文件的 commit 固定，需要时重新克隆）。

## 本工作区的 README 约定

- **变更纪律**：任何 Agent（或人）改完代码，必须同轮更新受影响目录的 README——什么时候更新、更新哪份、怎么验证，完整规则见 [`AGENTS.md`](AGENTS.md)。README 与代码同变。
- 每个组织目录都有一份**手写**的 `README.md`，讲清四件事：这个目录负责什么、里面具体有什么（真实文件名）、它与上下层的关系、已知的坑与纪律。
- **覆盖纪律**：Git 跟踪的每个目录都要有自己的 `README.md`——包括只做分组的中间层目录（如 `catalog/templates/optics/`、`engine-host/src/adapters/`），它们容易被跳过而让下一层 README 变成「没有父亲的孩子」。新增目录时按同一风格写一份，并在父层 README 登记。
- 不写 README 的目录只有下面 11 类（磁盘实测计数截至 2026-10-16，新增三类截至 2026-10-18 至 2026-10-20；每一类都由所属层 README 统一说明，指到具体那份）：

| 目录类别 | 目录数 | 谁说明它 |
|---|---|---|
| `source/upstream/ray-optics/` 内部 | 205 | 上游资产保持原样（上游自带 9 份 README），项目侧说明在 [`source/upstream/README.md`](source/upstream/README.md) |
| `output/eduforge/candidates/offline-package/www/` | 89 | 数据叶子（2162 个静态文件），模式写在 [`output/eduforge/candidates/README.md`](output/eduforge/candidates/README.md) |
| `output/eduforge/pgdata/` | 26 | Postgres 数据目录，见 [`output/eduforge/README.md`](output/eduforge/README.md) |
| 各类 `dist/` 构建产物（`teacher-web/dist`、`engine-host/dist`） | 8 | 构建输出，见 [`code/eduforge/apps/teacher-web/README.md`](code/eduforge/apps/teacher-web/README.md) 与 [`code/eduforge/services/engine-host/README.md`](code/eduforge/services/engine-host/README.md) |
| `output/eduforge/artifacts/revisions/<uuid>/` | 5 | 内容派生的运行期目录，结构图在 [`output/eduforge/artifacts/README.md`](output/eduforge/artifacts/README.md) |
| `code/eduforge/output/` | 3 | 工程内临时落盘（基准 runner 换 CWD 时产生），登记在 [`code/eduforge/README.md`](code/eduforge/README.md) 目录地图 |
| `.workbuddy/` | 2 | 本地 Agent 工作区数据，不入库，见本文「版本控制」节 |
| `output/eduforge/candidates/offline-package/` | 1 | 整包内容与 manifest 字段逐条写在 [`output/eduforge/candidates/README.md`](output/eduforge/candidates/README.md) |
| `deep-agent/deepseek-harness/` 内部 | 不实测：2.7 GB 上游源码树，全量遍历会先钻进去（实测卡到超时）；上游自带 README 保持原样 | [`deep-agent/README.md`](deep-agent/README.md) 目录地图 + [`deep-agent/AGENTS.md`](deep-agent/AGENTS.md) 第 3 节 |
| `deep-agent/` 运行时目录（`.dsh-home/`、`_corepack/`、`harness-smoke-workspace/`、`_probe/__pycache__/`） | 4 类 | 会话与凭据缓存（含 `.credentials.yaml`，敏感、勿外发）、pnpm 缓存、一次性 Agent 工作区（嵌套 `.git`）、字节码；说明在 [`deep-agent/README.md`](deep-agent/README.md) 目录地图与「如何启动」第 7 步 |
| `2026-10-18-11-03-28/runs/<时间戳>/` | 14 | 每次端到端运行的现场档案（实测 1,258 KB）；`.gitignore` 已按 `runs/*` + `!README.md` 处理，结构与判读全在 [`2026-10-18-11-03-28/runs/README.md`](2026-10-18-11-03-28/runs/README.md) |

  这些目录全部在根 `.gitignore` 里（可再生、体积大或程序自管），README 写进去也不会入库；**若某类被纳管，那份「谁说明它」的父层文档要升级为该目录自己的 README**。
- 依赖与缓存目录（`node_modules/`、`.venv/`、`__pycache__/`、`.pytest_cache/`）不在目录统计里，同样由所属层说明。
- 上游源码目录（`source/upstream/ray-optics/`）保留其自带的 README，项目侧说明降级写在 [`source/upstream/README.md`](source/upstream/README.md)，不覆盖上游文件。
