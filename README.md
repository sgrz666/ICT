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
| [`agent/`](agent/README.md) | 预留目录，当前只有一份 README | 计划放智能体侧资产 |

`node_modules/`（根目录下的 `rea-agents` 及其依赖）是依赖目录，不属于项目结构，本 README 体系不覆盖它。

## 逐目录索引

**覆盖口径（2026-10-19 实测）**：项目侧 `README.md` 共 **108 份**，命令 (1) 口径下 **100 个入库目录全部有 README，缺失 0**；相对链接断链 **0**。上一基线是 101 份 / 100 目录（2026-10-18），本轮新增 `source/components/README.md` 与 `source/library/README.md`，其余差额来自并行会话在 `code/eduforge` 一侧同期落盘的 README（本轮未改那些目录，只按实测登记）。校验命令见 [`AGENTS.md`](AGENTS.md) 第 5 节，它按约定跳过上游树，并且这一轮把剪枝规则升级成「**任何自带 `.git` 的子目录直接剪掉**」——`source/upstream/` 新装了 8 类引擎克隆（共 30 个仓库、1.8 万多个文件），不剪枝就会把上游 README 误计进项目侧数字。历史留痕：2026-10-16 补齐 11 个此前漏掉的分组层与叶子目录，2026-10-17 `deep-agent/` 验证工作区入库（9 份 README）。（`output/eduforge/candidates/README.md` 此前被 `.gitignore` 挡住无法入库，规则已改为 `candidates/*` + `!README.md`，数据仍不入库。）每一行只写「这个目录是干什么的」，具体文件、数字与坑在各目录自己的 README 里。

### [`code/`](code/README.md) — 自研代码

- [`code/eduforge/`](code/eduforge/README.md) — EduForge 主工程（pnpm workspace + Python 包双栈）
  - **前端** [`apps/`](code/eduforge/apps/README.md) → [`apps/teacher-web/`](code/eduforge/apps/teacher-web/README.md) 教师端（React + Vite）
    - [`src/`](code/eduforge/apps/teacher-web/src/README.md) 源码头 → [`src/api/`](code/eduforge/apps/teacher-web/src/api/README.md) API 客户端 · [`src/components/`](code/eduforge/apps/teacher-web/src/components/README.md) 组件 · [`src/data/`](code/eduforge/apps/teacher-web/src/data/README.md) 前端数据集 · [`src/hooks/`](code/eduforge/apps/teacher-web/src/hooks/README.md) React 钩子
  - **数据层（不是代码）** [`catalog/`](code/eduforge/catalog/README.md)
    - [`catalog/engines/`](code/eduforge/catalog/engines/README.md) 引擎描述（`ray-optics.yaml` 是全仓库测试计数的唯一处）
    - [`catalog/templates/`](code/eduforge/catalog/templates/README.md) 模板按「学科/实验」两级：
      - [`optics/`](code/eduforge/catalog/templates/optics/README.md) → [`convex-lens/`](code/eduforge/catalog/templates/optics/convex-lens/README.md) **已接通**（三件套齐备）
      - [`mechanics/`](code/eduforge/catalog/templates/mechanics/README.md) → [`pendulum/`](code/eduforge/catalog/templates/mechanics/pendulum/README.md) `pending_slice_9`
      - [`circuits/`](code/eduforge/catalog/templates/circuits/README.md) → [`ohms-law/`](code/eduforge/catalog/templates/circuits/ohms-law/README.md) `pending_slice_9`
  - **契约包** [`packages/`](code/eduforge/packages/README.md) → [`contracts/`](code/eduforge/packages/contracts/README.md) → [`src/`](code/eduforge/packages/contracts/src/README.md) 手写类型 · [`src/generated/`](code/eduforge/packages/contracts/src/generated/README.md) OpenAPI 生成物（勿手改）
  - **Python 侧** [`python/`](code/eduforge/python/README.md) → [`python/src/`](code/eduforge/python/src/README.md) 模块地图 → 包根 [`eduforge/`](code/eduforge/python/src/eduforge/README.md)
    - [`agent/`](code/eduforge/python/src/eduforge/agent/README.md) 执行核心与授权防线 · [`agent/prompts/`](code/eduforge/python/src/eduforge/agent/prompts/README.md) 系统行为规范
    - [`api/`](code/eduforge/python/src/eduforge/api/README.md) FastAPI 业务接口 · [`api/routes/`](code/eduforge/python/src/eduforge/api/routes/README.md) 空占位包（路由未拆分，都在 `main.py`）
    - [`application/`](code/eduforge/python/src/eduforge/application/README.md) 用例编排 · [`domain/`](code/eduforge/python/src/eduforge/domain/README.md) 纯净核心层
    - [`worker/`](code/eduforge/python/src/eduforge/worker/README.md) 五阶段任务执行 · [`experiment_tools/`](code/eduforge/python/src/eduforge/experiment_tools/README.md) 8 项引擎原子工具
    - [`infrastructure/`](code/eduforge/python/src/eduforge/infrastructure/README.md) 外部适配 → [`clients/`](code/eduforge/python/src/eduforge/infrastructure/clients/README.md) · [`db/`](code/eduforge/python/src/eduforge/infrastructure/db/README.md) · [`storage/`](code/eduforge/python/src/eduforge/infrastructure/storage/README.md)
    - [`validation/`](code/eduforge/python/src/eduforge/validation/README.md) 验证与发布门禁 → [`scientific/`](code/eduforge/python/src/eduforge/validation/scientific/README.md) 独立科学参考式
    - [`coding/`](code/eduforge/python/src/eduforge/coding/README.md) 代码定制（切片 7 预留）· [`entrypoints/`](code/eduforge/python/src/eduforge/entrypoints/README.md) 智能体运行入口 · [`research/`](code/eduforge/python/src/eduforge/research/README.md) REA 运行器
  - **Node 侧服务** [`services/`](code/eduforge/services/README.md) → [`engine-host/`](code/eduforge/services/engine-host/README.md) 引擎宿主
    - [`src/`](code/eduforge/services/engine-host/src/README.md) 源码头 → [`adapters/`](code/eduforge/services/engine-host/src/adapters/README.md) 适配器分组层 → [`adapters/ray-optics/`](code/eduforge/services/engine-host/src/adapters/ray-optics/README.md) · [`export/`](code/eduforge/services/engine-host/src/export/README.md) 离线包组装 · [`gateway/`](code/eduforge/services/engine-host/src/gateway/README.md) 浏览器网关 · [`preview/`](code/eduforge/services/engine-host/src/preview/README.md) 预览桥接
    - [`tests/`](code/eduforge/services/engine-host/tests/README.md) vitest 套件 → [`adapters/`](code/eduforge/services/engine-host/tests/adapters/README.md) → [`adapters/ray-optics/`](code/eduforge/services/engine-host/tests/adapters/ray-optics/README.md) · [`e2e/`](code/eduforge/services/engine-host/tests/e2e/README.md) 真实浏览器 · [`engines/`](code/eduforge/services/engine-host/tests/engines/README.md) 引擎级验收 · [`gateway/`](code/eduforge/services/engine-host/tests/gateway/README.md) 网关路由
  - **领域规范** [`skills/`](code/eduforge/skills/README.md) → [`ray-optics-customization/`](code/eduforge/skills/ray-optics-customization/README.md) **已启用** · [`mechanics-customization/`](code/eduforge/skills/mechanics-customization/README.md) · [`circuit-customization/`](code/eduforge/skills/circuit-customization/README.md)（后两个零代码读取）
  - **测试与工具** [`tests/`](code/eduforge/tests/README.md) → [`tests/python/`](code/eduforge/tests/python/README.md) pytest 用例 · [`tools/`](code/eduforge/tools/README.md) 验证探针与代码生成 · [`benchmarks/`](code/eduforge/benchmarks/README.md) 12 题评测集
  - **容器** [`infra/`](code/eduforge/infra/README.md) → [`agent/`](code/eduforge/infra/agent/README.md) · [`engine-host/`](code/eduforge/infra/engine-host/README.md) 镜像定义 · [`sandbox/`](code/eduforge/infra/sandbox/README.md)（切片 7 预留）· [`launcher/`](code/eduforge/infra/launcher/README.md)（切片 9 预留）

### [`deep-agent/`](deep-agent/README.md) — DeepSeek Harness 验证工作区

9 个入库目录，各自都有 README；**文件级清单与「怎么启动」不在这里复制**，看 [deep-agent/README.md](deep-agent/README.md) 的「精细目录索引」与「如何启动」两节（从裸机克隆、三条构建命令的实测退出码、Web UI / headless CLI / 复跑五项测试、Windows 权限置备与回滚、启动失败对照表）。

- [`harness-validation-reports/`](deep-agent/harness-validation-reports/README.md) — 结论层：7 份报告（安装 / API 联调 / Agent 循环实测 / 架构笔记 / 集成评估 / 品牌重构 v1 与 v2）+ 可重放补丁
- [`_logs/`](deep-agent/_logs/README.md) — 证据层：54 份现场（19 份编号构建与启动日志 + 11 组 `<stem>.jsonl/.err/.meta` 运行三元组 + 2 份单文件）
- [`_tools/`](deep-agent/_tools/README.md) — 复现层：`run_headless.sh`、`summarize_events.mjs`、文档门 `check_docs.py` → [`_tools/prompts/`](deep-agent/_tools/prompts/README.md) 五项任务原文与只读探针
- [`_probe/`](deep-agent/_probe/README.md) — 前提层：故意带缺陷的 `cart.py` + 暴露它的测试，以及官方要求的逐字快照
- [`patches/`](deep-agent/patches/README.md) — 官方 `--patch` 覆盖层（含「不足以移动会话 cwd」的实测结论）
- [`dsh-acl-recovery/`](deep-agent/dsh-acl-recovery/README.md) — 系统权限改动的备份、回滚脚本与完整记录
- [`harness-ui-workspace/`](deep-agent/harness-ui-workspace/README.md) — Web UI 核验沙盒（含审批放行后真实写入的文件）
- 不入库：`deepseek-harness/`（2.7 GB 上游源码，验证对象本体）、`harness-smoke-workspace/`（一次性工作区 + 嵌套 `.git`）、`_corepack/`、`.dsh-home/`（含 `.credentials.yaml`，敏感）

### 其余顶层目录

- [`input/`](input/README.md) — REA 分析的输入 → [`rea-smoke-test/`](input/rea-smoke-test/README.md) 冒烟样本 → [`src/`](input/rea-smoke-test/src/README.md) 样本源码 · [`research-targets/`](input/research-targets/README.md)（预留）
- [`output/`](output/README.md) — 运行产物与证据 → [`eduforge/`](output/eduforge/README.md) → [`reports/`](output/eduforge/reports/README.md) **验证证据** · [`artifacts/`](output/eduforge/artifacts/README.md) 运行期落盘 · [`candidates/`](output/eduforge/candidates/README.md) 离线包候选 · [`research/`](output/eduforge/research/README.md)（预留）
- [`plan/`](plan/README.md) — 计划、排期与逐轮记录（只追加不回改）
- [`scripts/`](scripts/README.md) — 工作区统一操作脚本（`eduforge.ps1`）
- [`source/`](source/README.md) — 实验资源库三层 → [`upstream/`](source/upstream/README.md) 上游引擎源码（44 个安装单元，16 个引擎/资源目录）· [`components/`](source/components/README.md) npm 组件与可加载性实测 · [`library/`](source/library/README.md) 实验目录（18 个优先实验映射到引擎与验收公式）
- [`task/`](task/README.md) — 赛题原件 · [`agent/`](agent/README.md) — 预留，当前只有一份 README

## 三条工作线

1. **EduForge 主工程**（`code/eduforge`）：pnpm workspace（TypeScript 侧：engine-host / teacher-web / contracts）+ Python 包（agent / api / application / worker / validation / entrypoints）。模板与引擎描述在 `catalog/`，实测证据在 `output/eduforge/reports/`，排期闸门在 `plan/`。
2. **实验资源库**（`source/`）：上游引擎本地化 + 组件安装 + 实验目录三层。`source/upstream` 已装 **16 个引擎/资源目录、44 个安装单元**（工作区文件 2,015,455 KB ≈ 1.9 GB，含 `.git` 实测 4,024,957 KB ≈ 3.8 GB），身份与构建结论锁在 `upstream.lock.json`；2026-10-19 本轮把简报里七项平台**全部落到磁盘**（新增 OSP 家族 6 仓 `osp/`、`osp_ejs/`、`webejs/`、`resources/`、`STP/`、`csm/` 与 3JCN 目录镜像 `3jcn/`），同时撤销了上一轮「这两项找不到权威来源所以不装」的结论——实测组织名是 `OpenSourcePhysics`、3JCN 是可抓的静态站；`source/components` 用 npm 钉版本装 three / Rapier / Matter.js（Rapier 的 wasm 只在 npm 里发布）；`source/library/experiments.json` 把 18 个优先实验映射到引擎、种子文件、可改参数与独立验收公式，简报里这 **18 条已全部在真引擎里跑出与解析式对账的读数**（本轮新增：理想气体 6/6、绳波 5/5、开普勒 6/6、牛顿摆 5/5——最后这条是换用上游 myPhysicsLab 的事件式碰撞引擎才成立的，Matter/Rapier 两条线复现不了 n 进 n 出；双缝干涉 5/5，走的是 EJSS 模型自己的函数）。仍在 `not_installed` 的只剩 PhET 官方发布成品一条。**但这 18 条只到「物理验证」这一层**：模板三件套与 engine-host 适配器仍只有凸透镜那条线接了，教师的一句话定制与离线包交付还没打通；「装上了」与「Agent 能改参」也仍是两件事——OSP 家族 6 仓里只有双缝干涉这一个模型的控制面被实测走通（读 `.ejss` 参数表 + 执行模型自带 JS，不需要编译），官方那条 `.ejs → 编译 → webejs 加载` 链路一步没跑，3JCN 只有目录清单；OSP 全部 6 仓里带 EJSS 模型源码的包实测 **28 个**（26 个能程序化读出可改参数表，7~29 个变量），但视图层 **0 个**验过——每个包的 HTML 都引用了包外资源，`survey_ejss_models.py` 把「自带运行时=能打开」这条证伪了。
3. **REA 逆向分析**（根 `package.json` + `input/`）：`rea-agents@6.5.0` 项目内与全局双安装，CLI 与 MCP 服务器均可用；冒烟样本在 `input/rea-smoke-test`，分析产物在 `output/rea-smoke-test.json`。

## 当前状态（2026-10-16 基线；3D 动量实验室于 2026-10-18 追加）

- 切片 1（引擎本地化与协议地基）的主要目标已达成并被实测证明：成熟光学引擎可以在本地被程序化修改，改完的仿真结果与独立薄透镜公式吻合。证据链见 `plan/26.10.15_EduForge_推进计划.md` 的「实况」节。
- 测试规模：vitest 74 / pytest 137，全绿（1 项真模型用例在无 key 时显式 SKIPPED）；**这个数字只在 `code/eduforge/catalog/engines/ray-optics.yaml` 的 `test_totals` 记一处**，其他文档引用它，不各自重复。
- 教师前端最小闭环已达成：选模板 → 建实验 → 提需求 → 进度查看 → 实时仿真预览与参数调节 → 版本历史与**版本回滚** → 产物下载校验。
- 教师前端已扩展四视图：AI 定制工坊、内嵌光学仿真模拟器（自由绘制元件）、81 个交互式案例库、3D 动量守恒实验室（气垫导轨碰撞、弹簧反冲、动量 / 动能双曲线；细节见 `code/eduforge/apps/teacher-web/README.md`）。
- 尚未闭环的（不要当成已完成）：DeepSeek 真实模型对照（缺 `DEEPSEEK_API_KEY`，已用桩模型覆盖图结构与策略链）、切片 7 容器沙箱（本机无 Docker Desktop）、Go 离线启动器、单文件 HTML 交付形态（上游运行时 HTTP 取词，`file://` 直开不成立，需 i18n 预注入）。

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
uv run pytest               # 125 个 pytest 用例

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
- 不写 README 的目录只有下面 10 类（磁盘实测计数截至 2026-10-16，新增两类截至 2026-10-18；每一类都由所属层 README 统一说明，指到具体那份）：

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

  这些目录全部在根 `.gitignore` 里（可再生、体积大或程序自管），README 写进去也不会入库；**若某类被纳管，那份「谁说明它」的父层文档要升级为该目录自己的 README**。
- 依赖与缓存目录（`node_modules/`、`.venv/`、`__pycache__/`、`.pytest_cache/`）不在目录统计里，同样由所属层说明。
- 上游源码目录（`source/upstream/ray-optics/`）保留其自带的 README，项目侧说明降级写在 [`source/upstream/README.md`](source/upstream/README.md)，不覆盖上游文件。
