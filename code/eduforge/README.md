# eduforge — EduForge 主工程

**EduForge：复用成熟实验环境的本地 Agent 定制与验证闭环。** 教师选一个实验模板、提修改需求，Agent 规划出对上游引擎原生场景的修改，Engine Host 程序化执行，独立科学参考代码验证结果，最后交付一个离线可跑的网页实验包。首批唯一接通的引擎是 Ray Optics（光学）。

工程根（本目录）是一个 **pnpm workspace + Python 包的双栈工程**：

- TypeScript 侧（`pnpm-workspace.yaml` 声明 `services/*`、`apps/*`、`packages/*`）：`services/engine-host`（引擎宿主服务）、`apps/teacher-web`（教师前端）、`packages/contracts`（前后端共享契约）。
- Python 侧（`pyproject.toml`，包名 `eduforge`，Python >=3.12,<3.13）：`python/src/eduforge`（agent 规划 / api / application / worker / validation / infrastructure / domain）。
- 根目录文件：`package.json`（workspace 壳，`pnpm -r test`）、`pyproject.toml`（Python 依赖与 pytest 配置，`testpaths = ["tests/python"]`）、`pnpm-lock.yaml` / `uv.lock`（双栈锁文件）。

## 目录地图

| 目录 | 职责 | 细节 |
|---|---|---|
| [`apps/`](apps/README.md) | 教师端前端（React + Vite） | [`apps/teacher-web/`](apps/teacher-web/README.md) |
| [`catalog/`](catalog/README.md) | 引擎描述与教学模板（数据，不是代码） | [`catalog/engines/`](catalog/engines/README.md)、[`catalog/templates/`](catalog/templates/README.md) |
| [`packages/`](packages/README.md) | 跨栈共享契约包 | [`packages/contracts/`](packages/contracts/README.md) |
| [`python/`](python/README.md) | Python 包源码 | [`python/src/`](python/src/README.md)（agent/api/application/coding/domain/infrastructure/research/validation/worker/entrypoints） |
| [`services/`](services/README.md) | Node 侧服务 | [`services/engine-host/`](services/engine-host/README.md)（适配器、预览桥接、浏览器网关、离线导出） |
| [`skills/`](skills/README.md) | 定制智能体可信领域规范 | [`skills/ray-optics-customization/`](skills/ray-optics-customization/SKILL.md) |
| [`infra/`](infra/README.md) | 容器编排与 Dockerfile | [`infra/compose.local.yaml`](infra/compose.local.yaml) |
| [`tests/`](tests/README.md) | pytest 套件 | [`tests/python/`](tests/python/README.md)（16 个用例 + conftest.py） |
| [`tools/`](tools/README.md) | 验证探针与代码生成工具 | rayoptics_probe.cjs、gate2_binding.cjs、browser_gate1*.py、export_contracts.py |
| `benchmarks/` | 12 题基准评测数据集与运行器 | `tasks.jsonl`（三类题型）、`profiles.yaml`、`runner.py` |

## 一次修改的调用链（设计见 plan/§2.2）

教师前端提交 → FastAPI（`python/src/eduforge/api`）落库 → Worker（`worker/`）领任务跑五阶段（planning → editing → building → validating → packaging）→ Engine Host（`services/engine-host`）的 ray-optics 适配器改上游原生场景 → 上游仿真出数 → `validation/scientific` 用独立薄透镜参考式对照 → 通过后发布，产物供下载。

## 当前状态与边界

- 已实测闭环：上游场景程序化修改、仿真结果与独立公式吻合（切片 1–8 主要目标达成；教师端版本回滚与实时改参闭环；单文件 HTML 离线直开通过 i18n 预注入补丁解决；代码定制与沙箱预算模块就绪）；测试规模达 vitest 54 / pytest 91 全绿，计数唯一记在 [`catalog/engines/ray-optics.yaml`](catalog/engines/ray-optics.yaml) 的 `test_totals`。
- 未闭环：真实模型线上规划（缺 `DEEPSEEK_API_KEY`，已用桩模型覆盖图结构与策略链）、容器沙箱运行时（切片 7，无 Docker 环境时优雅降级）。
- 完整排期与逐轮进度在 [`../../plan/26.10.15_EduForge_推进计划.md`](../../plan/26.10.15_EduForge_推进计划.md)；上游事实在 [`../../source/upstream/upstream.lock.json`](../../source/upstream/upstream.lock.json)；验证证据在 [`../../output/eduforge/reports/`](../../output/eduforge/reports/README.md)。

## 常用命令

```bash
# Python 侧（工程根目录）
uv sync                       # 按 uv.lock 建环境（.venv 在本目录）
uv run pytest                 # 91 个用例
uv run python -m eduforge.worker.run   # 手动跑一个 Worker
uv run python benchmarks/runner.py     # 运行 12 题基准评测集

# TypeScript 侧
pnpm install                  # 按 pnpm-lock.yaml
pnpm -r test                  # 54 个 vitest 用例
pnpm --filter @eduforge/engine-host start   # Engine Host 监听 127.0.0.1:8010
pnpm --filter @eduforge/teacher-web dev     # 教师前端
uv run python tools/export_contracts.py     # OpenAPI → TS 契约（改了 API 必跑）
```
