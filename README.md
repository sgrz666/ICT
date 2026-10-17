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
| [`source/`](source/README.md) | 上游源码及其锁定记录 | `source/upstream/upstream.lock.json` |
| [`task/`](task/README.md) | 赛题原件 | ICT创新赛道赛题.docx |
| [`agent/`](agent/README.md) | 预留目录，当前只有一份 README | 计划放智能体侧资产 |

`node_modules/`（根目录下的 `rea-agents` 及其依赖）是依赖目录，不属于项目结构，本 README 体系不覆盖它。

## 逐目录索引

**覆盖口径（2026-10-16 实测）**：项目侧 `README.md` 共 **86 份**，覆盖 **85 个目录 + 仓库根本身**——也就是说**每个项目目录都有自己的一份 README，无缺失**；相对链接断链 **0**（用 [`AGENTS.md`](AGENTS.md) 第 5 节的命令校验，该脚本按约定跳过 `source/upstream/`，所以它显示 85 份）。（本轮补齐 11 个此前漏掉的分组层与叶子目录；`output/eduforge/candidates/README.md` 此前被 `.gitignore` 挡住无法入库，规则已改为 `candidates/*` + `!README.md`，数据仍不入库。）每一行只写「这个目录是干什么的」，具体文件、数字与坑在各目录自己的 README 里。

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

### 其余顶层目录

- [`input/`](input/README.md) — REA 分析的输入 → [`rea-smoke-test/`](input/rea-smoke-test/README.md) 冒烟样本 → [`src/`](input/rea-smoke-test/src/README.md) 样本源码 · [`research-targets/`](input/research-targets/README.md)（预留）
- [`output/`](output/README.md) — 运行产物与证据 → [`eduforge/`](output/eduforge/README.md) → [`reports/`](output/eduforge/reports/README.md) **验证证据** · [`artifacts/`](output/eduforge/artifacts/README.md) 运行期落盘 · [`candidates/`](output/eduforge/candidates/README.md) 离线包候选 · [`research/`](output/eduforge/research/README.md)（预留）
- [`plan/`](plan/README.md) — 计划、排期与逐轮记录（只追加不回改）
- [`scripts/`](scripts/README.md) — 工作区统一操作脚本（`eduforge.ps1`）
- [`source/`](source/README.md) — 上游源码与锁定记录 → [`upstream/`](source/upstream/README.md)
- [`task/`](task/README.md) — 赛题原件 · [`agent/`](agent/README.md) — 预留，当前只有一份 README

## 三条工作线

1. **EduForge 主工程**（`code/eduforge`）：pnpm workspace（TypeScript 侧：engine-host / teacher-web / contracts）+ Python 包（agent / api / application / worker / validation / entrypoints）。模板与引擎描述在 `catalog/`，实测证据在 `output/eduforge/reports/`，排期闸门在 `plan/`。
2. **上游引擎本地化**（`source/upstream`）：浅克隆 Ray Optics，锁定 commit 与构建事实；myPhysicsLab、CircuitJS1 已决定不进首批（见 `upstream.lock.json`）。
3. **REA 逆向分析**（根 `package.json` + `input/`）：`rea-agents@6.5.0` 项目内与全局双安装，CLI 与 MCP 服务器均可用；冒烟样本在 `input/rea-smoke-test`，分析产物在 `output/rea-smoke-test.json`。

## 当前状态（截至 2026-10-16）

- 切片 1（引擎本地化与协议地基）的主要目标已达成并被实测证明：成熟光学引擎可以在本地被程序化修改，改完的仿真结果与独立薄透镜公式吻合。证据链见 `plan/26.10.15_EduForge_推进计划.md` 的「实况」节。
- 测试规模：vitest 67 / pytest 125，全绿（1 项真模型用例在无 key 时显式 SKIPPED）；**这个数字只在 `code/eduforge/catalog/engines/ray-optics.yaml` 的 `test_totals` 记一处**，其他文档引用它，不各自重复。
- 教师前端最小闭环已达成：选模板 → 建实验 → 提需求 → 进度查看 → 实时仿真预览与参数调节 → 版本历史与**版本回滚** → 产物下载校验。
- 教师前端已扩展三视图：AI 定制工坊、内嵌光学仿真模拟器（自由绘制元件）、81 个交互式案例库（细节见 `code/eduforge/apps/teacher-web/README.md`）。
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
- 不写 README 的目录只有下面 8 类（磁盘实测计数截至 2026-10-16；每一类都由所属层 README 统一说明，指到具体那份）：

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

  这些目录全部在根 `.gitignore` 里（可再生、体积大或程序自管），README 写进去也不会入库；**若某类被纳管，那份「谁说明它」的父层文档要升级为该目录自己的 README**。
- 依赖与缓存目录（`node_modules/`、`.venv/`、`__pycache__/`、`.pytest_cache/`）不在目录统计里，同样由所属层说明。
- 上游源码目录（`source/upstream/ray-optics/`）保留其自带的 README，项目侧说明降级写在 [`source/upstream/README.md`](source/upstream/README.md)，不覆盖上游文件。
