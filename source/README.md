# source — 上游源码、实验组件与资源目录

EduForge 的思路是「复用成熟实验环境」，所以把上游开源引擎的源码请进工作区，**原样保留、定点锁定**，适配代码全部写在 [`../code/eduforge`](../code/eduforge/README.md) 一侧，不改上游一行。2026-10-19 这一轮把资源库要装的东西补齐：引擎源码、npm 组件、以及一层让 Agent 能直接消费的实验目录。

## 内容

- [`upstream/`](upstream/README.md) — 上游源码区。自有文件是 `upstream.lock.json`（身份与构建结论的唯一权威）、九个安装/度量/探针/拼装脚本（`fetch_upstreams.sh`、`fetch_phet_sims.py`、`fetch_large.sh`、`fetch_osp_family.sh`、`3jcn/fetch_3jcn_index.py`、`fetch_phet_published.py`、`survey_ejss_models.py`、`probe_ejss_model.py` 与本轮新增 `assemble_ejss_offline.py`）、脚本生成的 `inventory.json`，以及 **16 个**引擎/资源目录（原有 `ray-optics/`、`myphysicslab/`、`circuitjs1/`、`matter-js/`、`rapier-js/`、`three/`、`stellarium-web-engine/`、`webots/`、`phet/{libs,sims}/`，本轮新增 OSP 家族 `osp/`、`osp_ejs/`、`webejs/`、`resources/`、`STP/`、`csm/` 与 `3jcn/` 目录镜像）。
- [`components/`](components/README.md) — npm 组件区：`three@0.186.1`、`@dimforge/rapier3d@0.21.0`、`@dimforge/rapier3d-compat@0.21.0`、`matter-js@0.20.0` 钉版本安装，附可加载性实测脚本与结果。这类库的 wasm/编译产物只随 npm 发布，克隆仓库拿不到。
- [`library/`](library/README.md) — 实验资源目录：`experiments.json` 把 18 个实验（P0 9 / P1 7 / P2 2）映射到具体引擎、种子文件、Agent 可改参数与独立验收公式；`check_catalog.py` 负责证明里面每条路径在磁盘上真实存在（2026-10-19 本轮实测 `paths checked: 100 | missing: 0`）。

## 安装实况（2026-10-19 装齐，2026-10-20 校正状态）

**这一节只讲「装到哪一步了」和「哪句话不能再说」。** 逐条实测数字的家在两个子目录里，不在这里重复：引擎身份/体积/构建 → [`upstream/README.md`](upstream/README.md)（权威是 `upstream.lock.json` 与 `upstream/inventory.json`）；实验读数与判据 → [`library/README.md`](library/README.md)。

### 磁盘上的规模

| 项 | 实测（2026-10-19 第二次重跑） |
|---|---|
| 已安装单元 | **45 个** |
| 工作区文件 | **25,596** 个 / **2,059,977 KB ≈ 2.0 GB**（不含 `.git`） |
| 比上一轮多出来的 | PhET 官方发布成品 `phet/published/` 13 份 / 44,522 KB |
| `upstream/` 整目录含 `.git` | **4,069,625 KB ≈ 3.9 GB**（Webots 的 `projects/` 稀疏检出 1,795,644 KB；OSP 家族 6 仓 1,057,753 KB；`du -sk`） |
| 16 个引擎/资源目录 | 原有 9 类 + 本轮 OSP 家族 6 仓（`osp`、`osp_ejs`、`webejs`、`resources`、`STP`、`csm`）+ 3JCN 目录镜像 |

上一轮记的 38 / 18,473 / 1,281,191 是 CircuitJS1 构建产物落盘**之前**的数，已被本轮重跑取代。

### 18 条优先实验：物理层全过，交付层三条接上

- **读数全部拿到**：18 条都跑出了「引擎自己算出来的数」并与独立解析式对上——无头 15 条 + 同源浏览器里读 CircuitJS1 电气量 3 条。逐条数值、容差、pass 比例都在 [`library/README.md`](library/README.md) 的「18 条实测数与解析式对照」表里，这里不重抄。
- **但只到物理层**：18 条里目前 **3 条**升到 `template_connected`（2026-10-20 实测 `experiments.json`）——`optics-concave-lens` 走 engine-host 主链路，`mechanics-pendulum` 与 `mechanics-projectile` 走 `code/eduforge/tools/labkit/` 的文件级链路（单文件 HTML）；主链路的 `EngineId` 里还只有 `ray_optics` / `myphysicslab` / `circuitjs`，**没有** `matter_js` 与 `circuit_mna`。其余 15 条仍是「物理验过、交付没接」。
- **两条「跑通但不及格」也照写**：Matter 的自由-自由弹性正碰不守恒动能（10 J → 1.21 J）；牛顿摆「n 进 n 出」Matter 与 Rapier 都复现不了（`library/collisions-lab-evidence.json` 6/9 pass）⇒ 牛顿摆那条最后是换用上游 myPhysicsLab 的事件式碰撞引擎才成立的。
- **验收台自己的缺陷也算发现**：CircuitJS1 那三条重跑时揪出两处空判据（元件种类守卫拿短码匹配类名所以恒为空、`runUntil` 用绝对时钟而 `importCircuit` 不重置时间）⇒ 旧那条 RC pass 不可靠，已按「导入后的充电钟」重做。现在一条命令能无头重跑（`library/circuit_headless_lab.mjs`，4/4 pass、连跑两遍一致）。

### 七项平台落盘，但「装齐」和「可控」是两件事

简报「二、适合补充进来的 2D/3D 仿真平台」的全部七项都落到磁盘：Matter.js、Three + Rapier（npm 组件）、Stellarium Web Engine（源码，无 `.wasm`，需 Emscripten 构建）、Webots（`projects/` 稀疏检出，本体未装）、OSP@Singapore/EJSS（6 仓约 1.0 GB）、3JCN（静态站目录镜像 8 页 / 90 链接）。

- **可控被拆成两条路来测**：官方那条「改 `.ejs` → `osp_ejs` 编译 → `webejs` 运行时加载」**至今一步没跑**；另一条「程序化读出 `.ejss` 的参数表 + 执行模型自带的 JS 函数」已在多缝衍射模型上实测 5/5，**不需要编译**，也正是 Agent 实际要用的形态。
- **EJSS 有多少面**：分层数字（28 个带源码的包 / 26 个能读参数表 / 视图层验过 1 个 / 运行时控制面验过 2 个 / 整批 25 包进回归）见 [`library/README.md`](library/README.md) 的 EJSS 一节；「自带运行时就能打开」这句是按页面分开量过的（坏路径都在 `EjsLauncher.html`、`<Name>_Contents.xhtml` 这类包装页上，仿真主页面引用缺失数为 0），上一轮那句「其余 27 个包的内部路径要先修」过宽，作废。
- **PhET 两条腿都有了**：20 个仿真源码 + 13 份官方单文件 HTML5 成品，逐只无头量成四档（展示 13/13、可读 6/13、可写 **1/13**、API **0/13**）⇒ 「成品一律改不动物理量」被推翻一半，但「都改得动」同样不成立，成品还带 CC BY-NC 4.0。四档的判据与三次口径修正见 [`library/README.md`](library/README.md)。
- **Stellarium 与 Webots 本轮只到「源码落盘」**，构建与适配器仍 `pending`。
- **CircuitJS1 的 GWT 编译本轮首次跑通**（`compileGwt` 58 s，产物 12.4 MB / 5 个 permutation，且不碰上游——细节与 `dist.sh` 为什么仍未通过，记在 [`upstream/README.md`](upstream/README.md)）⇒ 电学三条从「源码落盘」前进到「有可部署产物」。
- **本机 Java 已装**（实测 `java version "23" 2024-09-17`），所以 OSP/STP/csm 这类 Java 工程**不是装了解不开**，编译链在；但本轮一次都没编译，别把这句当已完成。

## 纪律

- 上游目录是「只读参考」：需要修改行为时，在 engine-host 的 adapters 层包一层，不在上游仓库里打补丁。
- 版本与构建事实以 `upstream.lock.json` 为唯一权威；它只记实测（跑过的命令与输出），未跑的一律标 `pending`。
- 新增上游引擎时，先在 lock 文件登记（含 decision/reason），再决定是否克隆。
- **来源没查清就不装；但「查不到」必须是查过的结果，不是猜的结果**。本轮把上一轮的两条「找不到权威来源」全部推翻了：OSP@Singapore/EJSS 的官方组织是 `OpenSourcePhysics`（旧记录只猜了 wejen/osp-tools/compadre-io 三个名字就判不装），3JCN 是可抓的静态站（旧记录判「Java applet 时代不可锁定」）。现在的口径：先打 `api.github.com/orgs/<候选>/repos`、`api.github.com/search/repositories`、站点 HTTP 头，拿到返回再写结论；仍装不成的才进 `library/experiments.json` 的 `not_installed`，并把实测过的命令与返回码一起写清本轮连第三条旧结论一起推翻了：PhET 官方发布成品曾被记成「装不上」，实测形态是 `sims/html/<sim>/latest/<sim>_all.html`，13 份全部 200 OK。⇒ `not_installed` 现在是空的，但「查不到」的教训同样适用：换一种 URL 形态再试一次才算查过。。
- **许可未定 = 只读参考**。`upstream/osp/` 与 `upstream/osp_ejs/` 仓库根实测没有 LICENSE/COPYING 文件，3JCN 站点未声明开源许可，Stellarium 是 AGPL-3.0 ⇒ 这三类都不进任何离线交付包，要用先取得书面授权并登记进 lock。
- **大仓不整仓克隆**。Webots 整仓 4.2 GB、three.js 整仓 1.7 GB，一律用 `--filter=blob:none` + `sparse-checkout` 只取需要的目录，并把「为什么这么装、装了多大」记进 lock 与 `fetch_large.sh`。
- **装了不等于接通**。`library/experiments.json` 的状态词有七级（`template_connected` 有模板有适配器 / `engine_headless_verified` 上游引擎无头出数并对上解析式 / `component_headless_verified` npm 组件同左 / `engine_browser_verified` 只在同源浏览器里出数 / `resource_installed` 只有源码 / `installed_catalog_only` 只有目录清单 / `reference_only` 只作参考），定义写死在该文件的 `status_words` 里，`check_catalog.py` 会拒绝没定义的状态词。写文档、写汇报时按这几级说，不许把「源码已克隆」表述成「实验已支持 AI 定制」。
