# upstream — 上游源码区

EduForge「复用成熟实验环境」的原料库。原则：**上游原样克隆、定点锁定；适配全部写在 EduForge 一侧**（`code/eduforge/services/engine-host/src/adapters/`），不改上游一行。

## 内容

- `upstream.lock.json` — 上游的权威记录，**这里记的每一条要么是从上游文件里读到的，要么是本机真实跑过的输出**；未跑的一律标 `pending`，不写成已完成。2026-10-19 资源库安装轮之后共 **11 条**：`ray-optics`（已接通）、`myphysicslab`（**已实测 tsc 构建 + 无头单摆周期与解析式吻合**）、`rapier`（**已实测无头自由落体与解析式吻合**的 3D 引擎）、`matter-js`/`three`（组件已在 Node 跑通步进/几何）、`circuitjs1`/`stellarium-web-engine`/`webots`/`phet`（源码已装，构建或本体 pending）、`osp-singapore-ejss` 与 `3jcn`（明确不装，附实测过的 404 与 TLS 失败证据）。逐条要点：
  - `ray-optics`（**已接通，首批唯一**）：Ray Optics Simulation 5.5.0，Apache-2.0，master @ `daf76772`（与 `git ls-remote` 一致），浅克隆 20M / 1080 文件。含安装（901 包 / 56 s / 324M）、构建（`dist-node/rayOptics.js` 1,715,044 字节；静态完整构建产物含全量 81 个案例场景 JSON 与 770 个多语言页面）、无头调用方式、序列化与对象身份实测、已知坑（optionalDependencies 静默失败、webpack 构建必须在目录内跑、`updateSimulation` 必须显式调、浅克隆 buildPages 需要退化静态贡献者兜底等）。
  - 其余 9 条按上面的口径逐条记录 fetch 命令、commit、许可证实测首行、体积、以及「为什么这么装」（Webots 4.2 GB 与 three.js 1.7 GB 走稀疏检出，Rapier 的 wasm 只在 npm 里，PhET 的 main 已空心化）。
- **安装与度量脚本**（改上游清单时同步它们，别手改日志）：
  - `fetch_upstreams.sh` — 浅克隆 myphysicslab / matter-js / rapier-js / stellarium-web-engine + PhET 库，逐行写 `fetch-log.tsv`（commit、体积、文件数）。
  - `fetch_phet_sims.py` — PhET 仿真逐个 `git ls-remote --heads` 枚举分支、**取版本号最大的 X.Y 发行分支**浅克隆到 `phet/sims/`，写 `fetch-phet-log.tsv`。
  - `fetch_large.sh` — CircuitJS1 浅克隆 + three.js 稀疏克隆 + Webots 分阶段体积实测（先只取树 647 KB，再按需检出 `projects/`），写 `fetch-large-log.tsv`。
  - `inspect_upstreams.py` — 扫描已装引擎生成 `inventory.json`（38 个安装单元 / 18,473 文件 / 1,281,191 KB，**工作区体积不含 `.git`**，所以比 `du` 小）。
  - `probe_myphysicslab.mjs` / `probe_myphysicslab_spring.mjs` + 两份 `probe-myphysicslab*.json` — myPhysicsLab 无头可控性实测与落盘结果（单摆周期、弹簧振子的胡克定律与周期）。前置：`cd source/upstream/myphysicslab && npm install --no-save typescript && npx tsc`（`build/` 是生成物，不入库）；跑法 `node source/upstream/probe_myphysicslab.mjs`。实测：上游自己的 `PendulumSim`（L=1 m、g=9.8、θ0=0.1 rad、dt=0.001 s，跑 30 s）测得周期 **2.00835 s**，一级大角度解析值 **2.00834 s**（偏差 0.0000%）、小角度值 2.00709 s（偏差 +0.0625%，正是 θ0²/16 的修正量）。⇒ myPhysicsLab 是第二个能无头出数、并能与解析式独立对照的引擎。
- **引擎目录**（全部由 `.gitignore` 挡住不入库；内部 README 属上游资产，保持原样）。体积为 `inventory.json` 实测：

| 目录 | 引擎 / 许可 | 装法 | 工作区体积 | 文件数 | 状态 |
|---|---|---|---|---|---|
| `ray-optics/` | Ray Optics，Apache-2.0 | `--depth 1` 全仓 | 54,610 KB | 3,241 | 已接通（唯一）；另有 5 项光学验收台 `../library/optics_hall.mjs` 5/5 pass |
| `myphysicslab/` | myPhysicsLab，Apache-2.0 | `--depth 1` 全仓 | 10,208 KB | 530 | 已实测：`npx tsc` 出 322 个 ESM，无头单摆周期与解析式吻合 |
| `circuitjs1/` | CircuitJS1，GPL-2.0 | `--depth 1` 全仓（**官方仓是 `pfalstad/circuitjs1`**） | 5,547 KB | 798 | Java 编译已打通（Gradle 8.14.3；8.7 与 Java 23 不兼容）；可运行 dist 仍未产出 |
| `matter-js/` | Matter.js，MIT | `--depth 1` 全仓 | 2,085 KB | 122 | 无头步进 pass；抛体已对解析式（`../library/projectile_lab.mjs` 5/5） |
| `rapier-js/` | Rapier JS 绑定，Apache-2.0 | `--depth 1` 全仓 | 2,074 KB | 179 | 仓库内 0 个 .wasm，可用产物走 `../components`；自由落体与带电粒子（脚本每步施加 qv×B）均已对解析式（`../library/field3d_lab.mjs` 5/5） |
| `three/` | three.js，MIT | `--filter=blob:none` + sparse（src、examples/jsm、build、LICENSE…） | 23,623 KB | 1,514 | 稀疏检出，纯数学已 pass |
| `stellarium-web-engine/` | Stellarium Web Engine，AGPL-3.0 | `--depth 1` 全仓 | 14,282 KB | 818 | 仓库内 0 个 .wasm，需 Emscripten 构建 |
| `webots/projects/` | Webots，Apache-2.0 | 只取树 + sparse 检出 `projects/` | 1,016,232 KB | 7,858 | 只装资源（304 世界 / 853 proto），本体未装 |
| `phet/libs/`（10 个） | PhET 通用库，MIT | `--depth 1` main | 55,726 KB | 1,730 | main 仍是完整源码 |
| `phet/sims/`（20 个） | PhET 仿真，GPL-3.0 | 按最新发行分支 `--depth 1` | 96,804 KB | 1,683 | 19 个有源码，`circuit-construction-kit-common` 实测仍是空壳 |

\* 逐库/逐仿真的文件数与 commit 见 `inventory.json` 与 `fetch-phet-log.tsv`；上表两个数字是 `inventory.json` 里对应单元的求和（2026-10-19 实测）。

## 消费方

- `code/eduforge/services/engine-host`：适配器 `require` 上游 `dist-node/rayOptics.js` 做无头仿真；预览服务与浏览器网关托管完整 `dist/`（提供 `/simulator/`、`/gallery/`、`/cn/` 等原版路由）；离线导出复刻上游 dist。
- `code/eduforge/apps/teacher-web`：在「⚡ 光学仿真模拟器」和「📚 81 演示案例库」中直接集成并消费上游原生场景与模拟器。
- `code/eduforge/tools/`：探针脚本（`EDUFORGE_RAYOPTICS` 环境变量可指到别处的上游检出）。

## 纪律

- 升级上游 = 重新克隆 + 更新 lock 文件的 commit 与实测记录，**不**在旧检出上打补丁。
- lock 文件里的「实测」条目必须可复现；写新条目时把命令和输出一起记。
- **稀疏检出的仓库必须把 LICENSE/NOTICE 一并检出**。three.js 第一次稀疏只取了 `src / examples/jsm / build`，仓库根 LICENSE 不在盘上——MIT 组件缺许可证文本是合规缺陷，不是小事（已补，见 lock 里 three 的 known_pits）。
- **别把「装上了」写成「接通了」**。本目录现在的状态分四层：① Ray Optics 已接通（有模板、有适配器、出过离线包），并已用 `../library/optics_hall.mjs` 把平面镜/折射/全反射/凹透镜/三棱镜五项对了解析式（5/5 pass）；② myPhysicsLab 与 Rapier 已实测「无头能出数、数值能与解析式对照」，但还没有模板与适配器；③ Matter/three 的 npm 组件在本机 Node 里跑通了步进与几何；④ 其余引擎只是源码落盘，构建或本体仍 pending。对外描述资源库进度时按这四层说。
- 改过上游清单（增删目录、换分支、换克隆方式）后，**重跑 `inspect_upstreams.py` 与 `python source/library/check_catalog.py`**，两边数字与路径要一致；后者 missing 不为 0 就不算装完。
- 遍历本目录的脚本必须先剪枝：`phet/`、`webots/`、`three/` 等每个引擎目录都自带 `.git`，文件总数上万，用 `rglob`/`find` 全走一遍会明显变慢（AGENTS.md 第 4 节同一口径）。
