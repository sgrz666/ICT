# source — 上游源码、实验组件与资源目录

EduForge 的思路是「复用成熟实验环境」，所以把上游开源引擎的源码请进工作区，**原样保留、定点锁定**，适配代码全部写在 [`../code/eduforge`](../code/eduforge/README.md) 一侧，不改上游一行。2026-10-19 这一轮把资源库要装的东西补齐：引擎源码、npm 组件、以及一层让 Agent 能直接消费的实验目录。

## 内容

- [`upstream/`](upstream/README.md) — 上游源码区。自有文件是 `upstream.lock.json`（身份与构建结论的唯一权威）、三个安装/度量脚本、脚本生成的 `inventory.json`，以及 9 类引擎的克隆目录（`ray-optics/`、`myphysicslab/`、`circuitjs1/`、`matter-js/`、`rapier-js/`、`three/`、`stellarium-web-engine/`、`webots/`、`phet/{libs,sims}/`）。
- [`components/`](components/README.md) — npm 组件区：`three@0.186.1`、`@dimforge/rapier3d@0.21.0`、`@dimforge/rapier3d-compat@0.21.0`、`matter-js@0.20.0` 钉版本安装，附可加载性实测脚本与结果。这类库的 wasm/编译产物只随 npm 发布，克隆仓库拿不到。
- [`library/`](library/README.md) — 实验资源目录：`experiments.json` 把 18 个实验（P0 9 / P1 7 / P2 2）映射到具体引擎、种子文件、Agent 可改参数与独立验收公式；`check_catalog.py` 负责证明里面每条路径在磁盘上真实存在（2026-10-19 实测 `paths checked: 55 | missing: 0`）。

## 安装实况（2026-10-19）

- 已安装单元 **38 个**，工作区文件 **18,473** 个、**1,281,191 KB**（不含 `.git`，按 `upstream/inventory.json`）；`upstream/` 整目录含 `.git` 实测 2,814,787 KB ≈ 2.7 GB，其中 Webots 的 `projects/` 稀疏检出占 1,016,232 KB。
- 本机无头跑出物理量的已有 10 条：光学 5 条（平面镜 200.5 vs 解析 200、折射 449.5 vs 450、临界角落在 (40°,42°] 对上 41.81°、凹透镜束宽反解 |f|=100.00000000000037、三棱镜两 n 落点 −165.5/−186.5 vs 自写矢量斯涅尔 −165.815/−186.609，见 `library/optics-hall-evidence.json` 5/5 pass）、单摆（myPhysicsLab 积分器，2.00835 s vs 解析 2.00834 s）、弹簧振子（加速度 −1.1999976 vs −kx/m=−1.2，周期 3.14159 vs 2π√(m/k)=3.14159，能量漂移 0%）、抛体（matter-js，射程 30.2733 vs 30.3046、最高点 10.1746 vs 10.2041、互补角射程比 0.9991，`library/projectile-lab-evidence.json` 5/5 pass）、3D 自由落体（Rapier，15.075 vs 15.095）、3D 带电粒子（Rapier + 脚本每步施加 qv×B，半径 3.3597 vs mv/(|q|B)=3.3333、周期 5.23603 vs 5.23599、螺距 7.8566 vs 7.8540，`library/field3d-lab-evidence.json` 5/5 pass）。其余引擎本轮只到「源码落盘」，构建与适配器仍 `pending`。另有两条「跑通但不及格」的实测：Matter 的自由-自由弹性正碰不守恒动能（10 J → 1.21 J），牛顿摆「n 进 n 出」Matter 与 Rapier 都复现不了（`library/collisions-lab-evidence.json` 6/9 pass）。
- CircuitJS1 的 GWT 编译本轮**首次跑通**：`compileGwt`（任务名不是 gwtCompile）58 s，产物 `upstream/circuitjs1/build/gwt/out/circuitjs1` 实测 12.4 MB / 5 个 permutation；复现方式是不碰上游——直接调用 `~/.gradle/wrapper/dists` 里已下载的 gradle-8.14.3 可执行文件（wrapper 钉的 8.7 与 Java 23 不兼容），此前为跑通而改的 `gradle-wrapper.properties` 已 `checkout` 还原。`dist.sh` 仍未通过（脚本自带 md5 校验，实测报 TestManager.java 哈希不符）。⇒ 电学三条 P0/P1 从「源码落盘」前进到「有可部署产物，缺适配器与读数接口实测」。
- 「无头能出数」还不等于「教师能一句话定制并拿到离线包」——上面这 10 条都还没有模板三件套与适配器接线（当前只有凸透镜那条线有），那是 `code/eduforge` 侧的下一步。

## 纪律

- 上游目录是「只读参考」：需要修改行为时，在 engine-host 的 adapters 层包一层，不在上游仓库里打补丁。
- 版本与构建事实以 `upstream.lock.json` 为唯一权威；它只记实测（跑过的命令与输出），未跑的一律标 `pending`。
- 新增上游引擎时，先在 lock 文件登记（含 decision/reason），再决定是否克隆。
- **装不上权威来源就不装**。找不到官方仓库、或许可与来源存疑的（本轮的 OSP@Singapore/EJSS、3JCN），只进 `library/experiments.json` 的 `not_installed`，写清实测过的搜索与 404 结果，不把来路不明的代码请进工作区。
- **大仓不整仓克隆**。Webots 整仓 4.2 GB、three.js 整仓 1.7 GB，一律用 `--filter=blob:none` + `sparse-checkout` 只取需要的目录，并把「为什么这么装、装了多大」记进 lock 与 `fetch_large.sh`。
- **装了不等于接通**。`library/experiments.json` 的状态词分四层（`template_connected` / `resource_installed` / `component_headless_verified` / `reference_only`），写文档、写汇报时按这四层说，不许把「源码已克隆」表述成「实验已支持 AI 定制」。
