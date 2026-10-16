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
| [`agent/`](agent/README.md) | 预留目录，当前为空 | 计划放智能体侧资产 |

`node_modules/`（根目录下的 `rea-agents` 及其依赖）是依赖目录，不属于项目结构，本 README 体系不覆盖它。

## 三条工作线

1. **EduForge 主工程**（`code/eduforge`）：pnpm workspace（TypeScript 侧：engine-host / teacher-web / contracts）+ Python 包（agent / api / application / worker / validation / entrypoints）。模板与引擎描述在 `catalog/`，实测证据在 `output/eduforge/reports/`，排期闸门在 `plan/`。
2. **上游引擎本地化**（`source/upstream`）：浅克隆 Ray Optics，锁定 commit 与构建事实；myPhysicsLab、CircuitJS1 已决定不进首批（见 `upstream.lock.json`）。
3. **REA 逆向分析**（根 `package.json` + `input/`）：`rea-agents@6.5.0` 项目内与全局双安装，CLI 与 MCP 服务器均可用；冒烟样本在 `input/rea-smoke-test`，分析产物在 `output/rea-smoke-test.json`。

## 当前状态（截至 2026-10-16）

- 切片 1（引擎本地化与协议地基）的主要目标已达成并被实测证明：成熟光学引擎可以在本地被程序化修改，改完的仿真结果与独立薄透镜公式吻合。证据链见 `plan/26.10.15_EduForge_推进计划.md` 的「实况」节。
- 测试规模：vitest 54 / pytest 72，全绿；**这个数字只在 `code/eduforge/catalog/engines/ray-optics.yaml` 的 `test_totals` 记一处**，其他文档引用它，不各自重复。
- 教师前端最小闭环已达成：选模板 → 建实验 → 提需求 → 进度查看 → 实时仿真预览与参数调节 → 版本历史与**版本回滚** → 产物下载校验。
- 尚未闭环的（不要当成已完成）：DeepSeek 真实模型对照（缺 `DEEPSEEK_API_KEY`，已用桩模型覆盖图结构与策略链）、切片 7 容器沙箱（本机无 Docker Desktop）、Go 离线启动器、单文件 HTML 交付形态（上游运行时 HTTP 取词，`file://` 直开不成立，需 i18n 预注入）。

## 常用命令

```powershell
# 工作区统一入口（推荐）
.\scripts\eduforge.ps1 doctor        # 环境与端口健康度检查
.\scripts\eduforge.ps1 test          # 跑全量 pytest (72) 与 vitest (54)
.\scripts\eduforge.ps1 smoke         # 真实 Chromium 端到端金路径测试
.\scripts\eduforge.ps1 benchmark -Profile screening  # 12 题筛查基准评测

# REA（根目录）
npm run rea:doctor          # 就绪检查
rea analyze-javascript-application ./input/rea-smoke-test

# EduForge Python 侧
cd code/eduforge
uv run pytest               # 72 个 pytest 用例

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
- 构建产物、缓存、依赖目录（`node_modules/`、`.venv/`、`dist/`、`__pycache__/`、`.pytest_cache/`）不写 README，由所属层统一说明。
- 上游源码目录（`source/upstream/ray-optics/`）保留其自带的 README，项目侧说明降级写在 [`source/upstream/README.md`](source/upstream/README.md)，不覆盖上游文件。
