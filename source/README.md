# source — 上游源码、实验组件与资源目录

EduForge 的思路是「复用成熟实验环境」，所以把上游开源引擎的源码请进工作区，**原样保留、定点锁定**，适配代码全部写在 [`../code/eduforge`](../code/eduforge/README.md) 一侧，不改上游一行。2026-10-19 这一轮把资源库要装的东西补齐：引擎源码、npm 组件、以及一层让 Agent 能直接消费的实验目录。

## 内容

- [`upstream/`](upstream/README.md) — 上游源码区。自有文件是 `upstream.lock.json`（身份与构建结论的唯一权威）、三个安装/度量脚本、脚本生成的 `inventory.json`，以及 9 类引擎的克隆目录（`ray-optics/`、`myphysicslab/`、`circuitjs1/`、`matter-js/`、`rapier-js/`、`three/`、`stellarium-web-engine/`、`webots/`、`phet/{libs,sims}/`）。
- [`components/`](components/README.md) — npm 组件区：`three@0.186.1`、`@dimforge/rapier3d@0.21.0`、`@dimforge/rapier3d-compat@0.21.0`、`matter-js@0.20.0` 钉版本安装，附可加载性实测脚本与结果。这类库的 wasm/编译产物只随 npm 发布，克隆仓库拿不到。
- [`library/`](library/README.md) — 实验资源目录：`experiments.json` 把 18 个实验（P0 9 / P1 7 / P2 2）映射到具体引擎、种子文件、Agent 可改参数与独立验收公式；`check_catalog.py` 负责证明里面每条路径在磁盘上真实存在（2026-10-19 实测 `paths checked: 49 | missing: 0`）。

## 安装实况（2026-10-19）

- 已安装单元 **38 个**，工作区文件 **18,473** 个、**1,281,191 KB**（不含 `.git`，按 `upstream/inventory.json`）；`upstream/` 整目录含 `.git` 实测 2,814,787 KB ≈ 2.7 GB，其中 Webots 的 `projects/` 稀疏检出占 1,016,232 KB。
- 无头可跑通的第一条物理量是 3D 自由落体：`rapier3d-compat` 步进 60 次后 y = 15.075，解析参考 15.095，偏差 0.020 m。光学那条线（Ray Optics）此前已实测；其余引擎本轮只到「源码落盘」，构建与适配器仍 `pending`。

## 纪律

- 上游目录是「只读参考」：需要修改行为时，在 engine-host 的 adapters 层包一层，不在上游仓库里打补丁。
- 版本与构建事实以 `upstream.lock.json` 为唯一权威；它只记实测（跑过的命令与输出），未跑的一律标 `pending`。
- 新增上游引擎时，先在 lock 文件登记（含 decision/reason），再决定是否克隆。
- **装不上权威来源就不装**。找不到官方仓库、或许可与来源存疑的（本轮的 OSP@Singapore/EJSS、3JCN），只进 `library/experiments.json` 的 `not_installed`，写清实测过的搜索与 404 结果，不把来路不明的代码请进工作区。
- **大仓不整仓克隆**。Webots 整仓 4.2 GB、three.js 整仓 1.7 GB，一律用 `--filter=blob:none` + `sparse-checkout` 只取需要的目录，并把「为什么这么装、装了多大」记进 lock 与 `fetch_large.sh`。
- **装了不等于接通**。`library/experiments.json` 的状态词分四层（`template_connected` / `resource_installed` / `component_headless_verified` / `reference_only`），写文档、写汇报时按这四层说，不许把「源码已克隆」表述成「实验已支持 AI 定制」。
