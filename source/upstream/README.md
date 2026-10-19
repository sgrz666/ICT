# upstream — 上游源码区

EduForge「复用成熟实验环境」的原料库。原则：**上游原样克隆、定点锁定；适配全部写在 EduForge 一侧**（`code/eduforge/services/engine-host/src/adapters/`），不改上游一行。

## 内容

- `upstream.lock.json` — 上游的权威记录，**这里记的每一条要么是从上游文件里读到的，要么是本机真实跑过的输出**；未跑的一律标 `pending`，不写成已完成。2026-10-19 资源库安装轮之后共 **11 条**：`ray-optics`（已接通）、`myphysicslab`（**已实测 tsc 构建 + 无头单摆周期与解析式吻合**）、`rapier`（**已实测无头自由落体与解析式吻合**的 3D 引擎）、`matter-js`/`three`（组件已在 Node 跑通步进/几何）、`circuitjs1`/`stellarium-web-engine`/`webots`/`phet`（源码已装，构建或本体 pending）、`osp-singapore-ejss`（**本轮新装，6 个仓库/1.0 GB**，见下表；控制面已用 `probe_ejss_model.py` 实测走通**一个**模型，其余仍 pending）、`3jcn`（**本轮新装目录镜像**，无可运行产物）。逐条要点：
  - `ray-optics`（**已接通，首批唯一**）：Ray Optics Simulation 5.5.0，Apache-2.0，master @ `daf76772`（与 `git ls-remote` 一致），浅克隆 20M / 1080 文件。含安装（901 包 / 56 s / 324M）、构建（`dist-node/rayOptics.js` 1,715,044 字节；静态完整构建产物含全量 81 个案例场景 JSON 与 770 个多语言页面）、无头调用方式、序列化与对象身份实测、已知坑（optionalDependencies 静默失败、webpack 构建必须在目录内跑、`updateSimulation` 必须显式调、浅克隆 buildPages 需要退化静态贡献者兜底等）。
  - 其余各条按上面的口径逐条记录 fetch 命令、commit、许可证实测首行、体积、以及「为什么这么装」（Webots 4.2 GB 与 three.js 1.7 GB 走稀疏检出，Rapier 的 wasm 只在 npm 里，PhET 的 main 已空心化，OSP 家族只浅克隆单个分支）。
  - `osp-singapore-ejss` 这一条**推翻了自己上一轮的结论**：旧记录写「找不到权威可克隆的仓库」，实际是搜索方式错了（猜组织名 wejen / osp-tools / compadre-io 全 404）。本轮 `GET /orgs/OpenSourcePhysics/repos` 实测返回 13 个仓库，随即装了 6 个。教训写进下面的纪律节。
  - `3jcn` 这一条同样推翻旧记录：旧结论说「Java applet 时代、不可锁定」，实测 `https://www.new3jcn.com/` 是静态站点（HTTP 200），分类页可下载 ⇒ 装的是**目录镜像**（8/8 页、90 条链接），不是引擎。
- **安装与度量脚本**（改上游清单时同步它们，别手改日志）：
  - `fetch_upstreams.sh` — 浅克隆 myphysicslab / matter-js / rapier-js / stellarium-web-engine + PhET 库，逐行写 `fetch-log.tsv`（commit、体积、文件数）。
  - `fetch_phet_sims.py` — PhET 仿真逐个 `git ls-remote --heads` 枚举分支、**取版本号最大的 X.Y 发行分支**浅克隆到 `phet/sims/`，写 `fetch-phet-log.tsv`。
  - `fetch_large.sh` — CircuitJS1 浅克隆 + three.js 稀疏克隆 + Webots 分阶段体积实测（先只取树 647 KB，再按需检出 `projects/`），写 `fetch-large-log.tsv`。
  - `fetch_osp_family.sh` — 2026-10-19 新增：浅克隆 Open Source Physics 家族 6 个仓库（`webejs`、`resources`、`csm`、`osp_ejs`、`osp`、`STP`）到本目录，逐行写 `osp-family-log.tsv`（commit、`du -sk` 含 `.git` 的体积、status）；可重复跑，已存在即跳过并登记 `already_installed`。
  - `3jcn/fetch_3jcn_index.py` — 抓 3JCN 的 8 个目录页存 `3jcn/pages/`（`.gitignore` 挡住），抽 `<a>` 生成 `3jcn/3jcn-inventory.json`（实测 8/8 页、90 条链接）。只证明「目录抓得下来」，不证明演示可改参。
  - `inspect_upstreams.py` — 扫描已装引擎生成 `inventory.json`（**2026-10-19 本轮重跑：44 个安装单元 / 25,583 文件 / 2,015,455 KB，工作区体积不含 `.git`**，所以比 `du` 小；上一次的 38 / 18,473 / 1,281,191 是构建产物落盘前的数）。新装的 6 个仓库已进 UNITS，探针另记 `.java`/`.js`/`.wasm`/`.html` 数量与 STP 热学包目录清单。
  - `probe_myphysicslab.mjs` / `probe_myphysicslab_spring.mjs` + 两份 `probe-myphysicslab*.json` — myPhysicsLab 无头可控性实测与落盘结果（单摆周期、弹簧振子的胡克定律与周期）。前置：`cd source/upstream/myphysicslab && npm install --no-save typescript && npx tsc`（`build/` 是生成物，不入库）；跑法 `node source/upstream/probe_myphysicslab.mjs`。实测：上游自己的 `PendulumSim`（L=1 m、g=9.8、θ0=0.1 rad、dt=0.001 s，跑 30 s）测得周期 **2.00835 s**，一级大角度解析值 **2.00834 s**（偏差 0.0000%）、小角度值 2.00709 s（偏差 +0.0625%，正是 θ0²/16 的修正量）。⇒ myPhysicsLab 是第二个能无头出数、并能与解析式独立对照的引擎。
  - `probe_ejss_model.py` — 2026-10-19 新增：**EJSS/OSP 模型的控制面探针**。`python source/upstream/probe_ejss_model.py <模型或zip路径> --json` 会解压 `.zip`、按文件头判断编码（`_source.ejss` 实测是 **UTF-16**，头两字节 `0xff 0xfe`；按 UTF-8 读只得到乱码），读 `_metadata.txt` 的键值，再解析 `Osejs.Model.Variables` 下的 `<Variable>` 块（名称/值/类型/Domain/Comment，即 Agent 能改的参数表）与 `Osejs.Model.*` 的明文代码块。对 `resources/docs/CollectionTest/webejs_model_MultislitDiffraction.zip`（382,210 字节，在 **resources** 仓不是 webejs 仓）实测：`_source.ejss` 解压后 49,802 字节，public 变量 **22 个**（N=3、D=10、d=100、lambda=0.4、L=100、width/height 等），`Osejs.Model.Library` 代码块 1,841 字符（`getSingleSlitAmp` / `getMultiSlitAmp` 就在这里），`Osejs.Model.Evolution` 与 `Constraints` 均为空；结果落 `ejss-multislit-probe.json`。
  - **同一份实测里还有一个反常识的坑**：`_metadata.txt` 声明 `source: _source.json`、`main-script:`（空），而压缩包里**只有 `_source.ejss`，没有 `_source.json`** ⇒ 这个"可部署包"对自己的运行时是不完整的，浏览器里打不开。所以"iframe 能打开"在这里连表象都没有，能走的只有"读参数表 + 执行模型自带函数"这条：下游 `../library/interference_lab.mjs` 正是这么做的，5/5 对上了 `d·sinθ=mλ`、`D·sinθ=λ`、缺级与 `N−2` 次极大。
  - `survey_ejss_models.py` — 2026-10-19 新增：**把整批 EJSS 包量成数字**（`python source/upstream/survey_ejss_models.py --json`，结果落 `ejss-survey.json`）。扫 6 仓 84 个 zip，实测：带 `.ejss` 模型源码的包 **28 个**（其余 55 个是文档/图片/网页壳），**26 个**能程序化读出可改参数表（7~29 个变量，中位 13），**28 个**都能取到模型自己的代码块，**27 个**自带 `ejsS.v1.min.js` 运行时。同一次扫描还证伪了「自带运行时 = 能打开」：**28/28** 的 HTML 引用了包外路径（`../resources/ejss.css`，而这个文件实测在**另一个仓库** `webejs/static/assets/_ejs_library/css/` 里），**27/28** 还引用了包内不存在的目录名（生成器把标题拼进了路径，如 `One-Dimensional Kinematics Illustrations./ch2_illustrations.xhtml`）⇒ 视图层要跑得先拼树，本轮没拼也没在浏览器里验，**pending**。
- **引擎目录**（引擎本体全部由 `.gitignore` 挡住不入库，内部 README 属上游资产，保持原样；例外是 `3jcn/`——里面的抓取脚本、`3jcn-inventory.json` 与本目录 README 是项目侧资产，入库，只有 `3jcn/pages/` 的第三方 HTML 被挡）。体积为 `inventory.json` 实测：

| 目录 | 引擎 / 许可 | 装法 | 工作区体积 | 文件数 | 状态 |
|---|---|---|---|---|---|
| `ray-optics/` | Ray Optics，Apache-2.0 | `--depth 1` 全仓 | 54,610 KB | 3,241 | 已接通（唯一有模板与适配器的）；另有 5 项光学验收台 `../library/optics_hall.mjs` 5/5 pass |
| `myphysicslab/` | myPhysicsLab，Apache-2.0 | `--depth 1` 全仓 | 10,208 KB | 530 | 已实测三条线：`npx tsc` 出 322 个 ESM，无头单摆周期与解析式吻合；`build/sims/pde/StringSim.js`（PDE 绳模型）绳波 5/5；`NewtonsCradleApp.make` + `ContactSim`/`CollisionAdvance` 复现「n 进 n 出」5/5（Matter 与 Rapier 都做不到的那条） |
| `circuitjs1/` | CircuitJS1，GPL-2.0（`build.gradle` 自身声明 GPLv3） | `--depth 1` 全仓（**官方仓是 `pfalstad/circuitjs1`**） | 5,547 KB | 798 | **GWT 编译已跑通**：`compileGwt` 58 s，产物 `build/gwt/out/circuitjs1` 实测 12.4 MB / 5 个 permutation；`dist.sh` 仍失败（脚本自带 md5 校验，实测报 TestManager.java 哈希不符），但 `makeSite` 已把可部署站点拼出来（`site/`），电学三条已在同源浏览器里对上解析式（`../library/circuit-lab-evidence.json` 5/5） |
| `matter-js/` | Matter.js，MIT | `--depth 1` 全仓 | 2,085 KB | 122 | 无头步进 pass；抛体 5/5（`../library/projectile_lab.mjs`）；碰撞 2/4（`../library/collisions_lab.mjs`：完全非弹性共速 pass，弹性正碰与牛顿摆不如预期） |
| `rapier-js/` | Rapier JS 绑定，Apache-2.0 | `--depth 1` 全仓 | 2,074 KB | 179 | 仓库内 0 个 .wasm，可用产物走 `../components`；自由落体与带电粒子（脚本每步施加 qv×B）均已对解析式（`../library/field3d_lab.mjs` 5/5） |
| `three/` | three.js，MIT | `--filter=blob:none` + sparse（src、examples/jsm、build、LICENSE…） | 23,623 KB | 1,514 | 稀疏检出，纯数学已 pass |
| `stellarium-web-engine/` | Stellarium Web Engine，AGPL-3.0 | `--depth 1` 全仓 | 14,282 KB | 818 | 仓库内 0 个 .wasm，需 Emscripten 构建 |
| `webots/projects/` | Webots，Apache-2.0 | 只取树 + sparse 检出 `projects/` | 1,016,232 KB | 7,858 | 只装资源（304 世界 / 853 proto），本体未装 |
| `phet/libs/`（10 个） | PhET 通用库，MIT | `--depth 1` main | 55,726 KB | 1,730 | main 仍是完整源码 |
| `phet/sims/`（20 个） | PhET 仿真，GPL-3.0 | 按最新发行分支 `--depth 1` | 96,804 KB | 1,683 | 19 个有源码，`circuit-construction-kit-common` 实测仍是空壳 |
| `osp/` | OSP 核心库，**无 LICENSE 文件**（实测 `license_files` 为空） | `--depth 1 --single-branch` | 185,194 KB | 1,293 | 只读参考；`.java` 807 个；许可未定 ⇒ 禁止进交付包 |
| `osp_ejs/` | EJS 编译器内核，**无 LICENSE 文件** | 同上 | 15,353 KB | 636 | 只读参考；`.java` 567 个：改参 = 改 `.ejs` 再重新编译 |
| `webejs/` | Web EJS 静态运行时，GPL-3.0 | 同上 | 74,006 KB | 2,282 | `.js` 925 个、`.wasm` 0 个、`.html` 26 个：EJSS 模型在浏览器里跑的那层。本轮实测**没用到它**——`interference_lab.mjs` 走的是「读 `.ejss` 参数表 + 执行模型自带函数」，不经过这层运行时 |
| `resources/` | OSP 文档与收藏页，GPL-3.0 | 同上 | 297,553 KB | 865 | `.html` 201 个（docs/ 按会议与收藏分目录）。**双缝干涉那条实验的种子就在这里**（`docs/CollectionTest/webejs_model_MultislitDiffraction.zip`，382 KB），已用 `probe_ejss_model.py` 读出参数表并执行其物理函数；其余模型仍只是文件 |
| `STP/` | Statistical and Thermal Physics，GPL-3.0 | 同上 | 12,570 KB | 140 | `.java` 123 个；`stp/` 下实测有 idealgas、idealgasintegrals、thermalcontact、carnot、entropy、diffusion、boltzmann 等包 ⇒ 热学终于有上游真代码可对照 |
| `csm/` | Computer Simulation Methods，GPL-3.0 | 同上 | 752 KB | 198 | `.java` 195 个：MD/Ising 的独立参考实现，可当热学的第二个意见 |
| `3jcn/` | 3JCN 目录镜像，**站点未声明开源许可** | `3jcn/fetch_3jcn_index.py` 抓页 | 205 KB（pages/） | 8 页 + 清单 | 只有 90 条链接的检索清单，无产物、控制面 pending |

\* 逐库/逐仿真的文件数与 commit 见 `inventory.json` 与 `fetch-phet-log.tsv`；上表两个数字是 `inventory.json` 里对应单元的求和（2026-10-19 实测）。

## 消费方

- `code/eduforge/services/engine-host`：适配器 `require` 上游 `dist-node/rayOptics.js` 做无头仿真；预览服务与浏览器网关托管完整 `dist/`（提供 `/simulator/`、`/gallery/`、`/cn/` 等原版路由）；离线导出复刻上游 dist。
- `code/eduforge/apps/teacher-web`：在「⚡ 光学仿真模拟器」和「📚 81 演示案例库」中直接集成并消费上游原生场景与模拟器。
- `code/eduforge/tools/`：探针脚本（`EDUFORGE_RAYOPTICS` 环境变量可指到别处的上游检出）。

## 纪律

- 升级上游 = 重新克隆 + 更新 lock 文件的 commit 与实测记录，**不**在旧检出上打补丁。
- lock 文件里的「实测」条目必须可复现；写新条目时把命令和输出一起记。
- **稀疏检出的仓库必须把 LICENSE/NOTICE 一并检出**。three.js 第一次稀疏只取了 `src / examples/jsm / build`，仓库根 LICENSE 不在盘上——MIT 组件缺许可证文本是合规缺陷，不是小事（已补，见 lock 里 three 的 known_pits）。
- **别把「装上了」写成「接通了」**。本目录现在的状态分四层：① Ray Optics 已接通（有模板、有适配器、出过离线包），并已用 `../library/optics_hall.mjs` 把平面镜/折射/全反射/凹透镜/三棱镜五项对了解析式（5/5 pass）；② myPhysicsLab、Rapier、Matter 已实测「无头能出数、数值能与解析式对照」（myPhysicsLab：单摆、弹簧、**绳波（PDE `sims/pde/StringSim`）5/5**、**牛顿摆（`NewtonsCradleApp.make` + `ContactSim` 事件式碰撞）5/5**；Rapier：自由落体、带电粒子、弹性碰撞、**理想气体压强与三条状态律 6/6**、**开普勒三定律 6/6**；Matter：抛体、碰撞），但还没有模板与适配器；③ Matter/three 的 npm 组件在本机 Node 里跑通了步进与几何；CircuitJS1 走的是「同源浏览器 + 官方 JS 接口」这条第四类路径（能改参能读数，但不是无头，进不了 CI）；④ 其余引擎只是源码或目录落盘（3JCN 镜像、Webots 本体、Stellarium 构建、PhET 生产包），构建或控制面仍 pending；OSP 家族 6 仓里**只有双缝干涉这一个模型**的控制面被实测走通（`probe_ejss_model.py` 读参数表 + 执行模型自带函数，5/5），整批包的面则由 `survey_ejss_models.py` 量出来了（28 个模型 / 26 个有参数表 / 视图层 0 个验过），其余模型仍属这一层。对外描述资源库进度时按这四层说。
- **上游没装成之前，别急着写「找不到权威来源」**。本轮两条旧结论都被推翻了：OSP 的组织名是 `OpenSourcePhysics`（旧记录猜 wejen/osp-tools/compadre-io 全 404 就判「不装」），3JCN 是静态站（旧记录判「Java applet 时代不可锁定」）。正确动作是先打 `api.github.com/orgs/<候选>/repos`、`api.github.com/search/repositories?q=…` 与站点 HTTP 头，拿到返回再下结论；结论被推翻时在 lock 里写明撤销了哪句（本轮已写）。
- **仓库根没有 LICENSE 文件 = 许可未定，不是「默认可以用」**。`osp/` 与 `osp_ejs/` 实测无 LICENSE/COPYING，只能只读参考；要进任何交付包，先取得书面授权说明并登记进 lock。
- **EJSS 的 `<Domain>` 不是「可改」的开关**。它只在带参数页的模型里出现，导出包普遍省略；如果按 `domain == "public"` 过滤，26 个有参数表的模型会被误判成 0 个。`probe_ejss_model.py` 现在按「省略也算可调，只排除 internal/private」计数，并把 `domain_declared` 单独记下来。
- **「包里带运行时」不能推出「浏览器里能打开」**。`survey_ejss_models.py` 实测 28/28 个模型包的 HTML 引用了包外资源（`ejss.css` 其实在 `webejs/static/assets/_ejs_library/css/`），27/28 还引用了包内不存在的目录名（生成器把标题拼进了路径）。要交付视图层得先拼树，再在浏览器里实测；两步都没做之前，只能说「源码与参数面已验证」，不能说「离线可打开」。
- 改过上游清单（增删目录、换分支、换克隆方式）后，**重跑 `inspect_upstreams.py` 与 `python source/library/check_catalog.py`**，两边数字与路径要一致；后者 missing 不为 0 就不算装完。本轮实测：72 条路径 / missing 0，44 个安装单元。
- 遍历本目录的脚本必须先剪枝：`phet/`、`webots/`、`three/` 等每个引擎目录都自带 `.git`，文件总数上万，用 `rglob`/`find` 全走一遍会明显变慢（AGENTS.md 第 4 节同一口径）。
