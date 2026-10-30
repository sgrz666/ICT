# upstream — 上游源码区

EduForge「复用成熟实验环境」的原料库。原则：**上游原样克隆、定点锁定；适配全部写在 EduForge 一侧**（`code/eduforge/services/engine-host/src/adapters/`），不改上游一行。

读这一份的顺序：**体积与状态看下面的表**；某一个引擎「测到哪一层了」看「逐目录实况」；实验级的读数与判据不在这里，在 [`../library/README.md`](../library/README.md)；3JCN 那一族的逐轮历史在 [`3jcn/README.md`](3jcn/README.md)。

## 内容

### 权威记录：`upstream.lock.json`

**这里记的每一条要么是从上游文件里读到的，要么是本机真实跑过的输出**；未跑的一律标 `pending`，不写成已完成。2026-10-19 资源库安装轮之后共 **11 条**：`ray-optics`（已接通）、`myphysicslab`、`rapier`、`matter-js` / `three`、`circuitjs1` / `stellarium-web-engine` / `webots` / `phet`（源码已装，构建或本体 pending）、`osp-singapore-ejss`、`3jcn`。逐条要点：

- `ray-optics`（**已接通，首批唯一**）：Ray Optics Simulation 5.5.0，Apache-2.0，master @ `daf76772`（与 `git ls-remote` 一致），浅克隆 20M / 1080 文件。含安装（901 包 / 56 s / 324M）、构建（`dist-node/rayOptics.js` 1,715,044 字节；静态完整构建产物含全量 81 个案例场景 JSON 与 770 个多语言页面）、无头调用方式、序列化与对象身份实测、已知坑（optionalDependencies 静默失败、webpack 构建必须在目录内跑、`updateSimulation` 必须显式调、浅克隆 buildPages 需要退化静态贡献者兜底等）。
- 其余各条按同一口径记录 fetch 命令、commit、许可证实测首行、体积，以及「为什么这么装」：Webots 4.2 GB 与 three.js 1.7 GB 走稀疏检出，Rapier 的 wasm 只在 npm 里，PhET 的 main 已空心化，OSP 家族只浅克隆单个分支。
- `osp-singapore-ejss` 这一条**推翻了自己上一轮的结论**：旧记录写「找不到权威可克隆的仓库」，实际是搜索方式错了（猜组织名 wejen / osp-tools / compadre-io 全 404）。本轮 `GET /orgs/OpenSourcePhysics/repos` 实测返回 13 个仓库，随即装了 6 个（1.0 GB）。教训写在纪律节。
- `3jcn` 这一条同样推翻旧记录：旧结论说「Java applet 时代、不可锁定」，实测 `https://www.new3jcn.com/` 是静态站点（HTTP 200），分类页可下载 ⇒ 装的是**目录镜像**（8/8 页、90 条链接），不是引擎。

### 安装与度量脚本（改上游清单时同步它们，别手改日志）

| 脚本 | 做什么 | 产出 |
|---|---|---|
| `fetch_upstreams.sh` | 浅克隆 myphysicslab / matter-js / rapier-js / stellarium-web-engine + PhET 库 | `fetch-log.tsv`（commit、体积、文件数） |
| `fetch_phet_sims.py` | PhET 仿真逐个 `git ls-remote --heads` 枚举分支、**取版本号最大的 X.Y 发行分支**浅克隆到 `phet/sims/` | `fetch-phet-log.tsv` |
| `fetch_phet_published.py` | 2026-10-19 新增：下载 PhET **官方发布的单文件 HTML5 成品** `sims/html/<sim>/latest/<sim>_all.html` 到 `phet/published/`，逐份解出版本号与许可行、算 sha256，并数文件里指向外的 `<script src>` / `<link href>` | `phet-published.json` + `phet-published-log.tsv`（13 份共 45,591,247 字节，全部 200 OK） |
| `fetch_large.sh` | CircuitJS1 浅克隆 + three.js 稀疏克隆 + Webots 分阶段体积实测（先只取树 647 KB，再按需检出 `projects/`） | `fetch-large-log.tsv` |
| `fetch_osp_family.sh` | 2026-10-19 新增：浅克隆 Open Source Physics 家族 6 个仓库（`webejs`、`resources`、`csm`、`osp_ejs`、`osp`、`STP`）；可重复跑，已存在即跳过并登记 `already_installed` | `osp-family-log.tsv`（commit、`du -sk` 含 `.git`、status） |
| `3jcn/fetch_3jcn_index.py` | 抓 3JCN 的 8 个目录页存 `3jcn/pages/`（被 `.gitignore` 挡住），抽 `<a>` | `3jcn/3jcn-inventory.json`（实测 8/8 页、90 条链接）。只证明「目录抓得下来」，不证明演示可改参 |
| `3jcn/mirror_3jcn_site.py` | 2026-10-19 新增：把演示页的**同源依赖闭包**按站点路径镜像进 `3jcn/site/`（BFS，默认深度 3、上限 400 个文件；跨域 jQuery/bootstrap 保持原样只记清单）。本轮实测 60 个文件 / 16,930,951 B，含 `jsm/three.module.js` 1,145,222 B、`GLTFLoader.js`、`RoundedBoxGeometry.js`、`css/*.css`、`textures/*.png` | 为什么要它：旧探针看到「无异常但也没画面」就以为站点坏，其实是**镜像缺料**——页面用 `<script type="module">` 引 three.js，模块 import 失败不抛 pageerror |
| `3jcn/probe_3jcn_demo_interfaces.py` | 2026-10-19 新增：从目录页收出 **54 条演示链接**，抓前 N 份存 `3jcn/demos/`，逐页统计外部脚本数 / three.js 引用数 / `range` 滑块数 / `getElementById` 数 / 可改数值常量数与名字 | `3jcn/3jcn-demo-interface-probe.json`；跑法 `python source/upstream/3jcn/probe_3jcn_demo_interfaces.py 14` |
| `inspect_upstreams.py` | 扫描已装引擎生成 `inventory.json`。**2026-10-19 本轮再次重跑：45 个安装单元 / 25,596 文件 / 2,059,977 KB**（工作区体积不含 `.git`，所以比 `du` 小；上一轮的 44 / 25,583 / 2,015,455 是 PhET 发布成品落盘前的数）。新装 6 仓已进 UNITS，另记 `.java`/`.js`/`.wasm`/`.html` 数量与 STP 热学包目录清单；本轮再加 `phet-published-html5` 单元与 `phet.published_html5_sims` 探针（实测 13） | `inventory.json` |

### EJSS 这条线的四件工具，各管一层

- `probe_ejss_model.py` — **单个模型的控制面探针**（2026-10-19 新增）。`python source/upstream/probe_ejss_model.py <模型或zip路径> --json` 会解压 `.zip`、按文件头判断编码（`_source.ejss` 实测是 **UTF-16**，头两字节 `0xff 0xfe`；按 UTF-8 读只得到乱码），读 `_metadata.txt` 的键值，再解析 `Osejs.Model.Variables` 下的 `<Variable>` 块（名称 / 值 / 类型 / Domain / Comment，即 Agent 能改的参数表）与 `Osejs.Model.*` 的明文代码块。
  - 对 `resources/docs/CollectionTest/webejs_model_MultislitDiffraction.zip`（382,210 字节，**在 `resources` 仓不是 `webejs` 仓**）实测：`_source.ejss` 解压后 49,802 字节，public 变量 **22 个**（N=3、D=10、d=100、lambda=0.4、L=100、width/height 等），`Osejs.Model.Library` 代码块 1,841 字符（`getSingleSlitAmp` / `getMultiSlitAmp` 就在这里），`Osejs.Model.Evolution` 与 `Constraints` 均为空；结果落 `ejss-multislit-probe.json`。
  - **这份实测里有个反常识的坑**：`_metadata.txt` 声明 `source: _source.json`、`main-script:`（空），而压缩包里**只有 `_source.ejss`，没有 `_source.json`** ⇒ 这个「可部署包」对自己的运行时是不完整的，浏览器里打不开。所以「iframe 能打开」在这里连表象都没有，能走的只有「读参数表 + 执行模型自带函数」这条（下游 [`../library/interference_lab.mjs`](../library/interference_lab.mjs) 正是这么做，5/5 对上 `d·sinθ=mλ`、`D·sinθ=λ`、缺级与 `N−2` 次极大）。
- `survey_ejss_models.py` — **把整批包量成数字**（2026-10-19 新增，`python source/upstream/survey_ejss_models.py --json` → `ejss-survey.json`）。扫 6 仓 84 个 zip：带 `.ejss` 模型源码的包 **28 个**（其余 55 个是文档 / 图片 / 网页壳），**26 个**能程序化读出可改参数表（7~29 个变量，中位 13），**28 个**都能取到模型自己的代码块，**27 个**自带 `ejsS.v1.min.js` 运行时。
  - 本轮又加了**只看仿真主页面**的一组计数（`deliverability()`）：族别是 25 个 EJS 6.02 + 1 个 webejs + 2 个没有单页仿真入口的多模型合集；26 个主页面里 **25 个远程加载数为 0（解压即用）**，只有 webejs 那一份是 6 处 CDN；**主页面引用缺失文件的数量是 0**；`var _model` + `serialize`/`unserialize` 在 26 个主页面里都在，25 个带 `// EjsS Model.Variables…` 可寻址赋值注释。
  - **两个读数边界**：① 25 个 EJS 6.02 包全部来自 `resources/docs/PP/Ch02`（一维运动学**一个章节**的题集），别读成 25 个不同学科的新实验；② 「28/28 打不开」那句是把包里所有 HTML 混在一起数的结论，坏路径都在 `EjsLauncher.html`、`<Name>_Contents.xhtml` 这类包装页上（例如 `One-Dimensional Kinematics Illustrations./ch2_illustrations.xhtml`），**仿真主页面本身是好的**——完整口径见纪律节那条。
- `assemble_ejss_offline.py` — **拼成断网能跑的包**（原名 `webejs_offline_try.py`，量完第二族后改名）。`python source/upstream/assemble_ejss_offline.py <zip> [--param 名=值]`，两族通吃：**webejs 导出**要换 5 处 CDN 并补 plotly 1.58.5 + 能跑回调的 MathJax 替身；**EJS 6.02 导出**实测仿真页 0 个 http(s) 引用、运行时就在包里 ⇒ 解压即用，只需改参数。改参不是靠猜：只改写「当前值 == `.ejss` 默认值」的那些赋值（Illustration2_6 上 y 命中 5 处、a 命中 1 处；Problem2_18 上 y_r/v_r/a 各命中 1 处），EJS 6.02 的赋值行还带 `// EjsS Model.Variables.<页>.Vars.<名>` 注释可核对。
- `ejss-offline-evidence.json` — **视图层的实测记录**（由上一条拼出来）。`--param N=5 --param lambda=0.6 --param d=40 --param D=8 --param L=80`，产物落不入库的 `.webejs-offline/`。流程是解包 → 从本机 `webejs/static/assets/_ejs_library` 拷运行时（改 5 处 CDN）→ 按名字改写 `_simulation.xhtml` 里烘焙的参数赋值。浏览器实测：`file://` 打开后 `EJSS_CORE` 与 `Plotly` 都从本地加载、6 个控件全建出来、Plotly 出 3 条 4096 点曲线，**主极大间距 1.1976 vs `λL/d`=1.2（0.2%）、次极大 3 个 = N−2**（N=5 是脚本改的）。三个坑：① MathJax 替身必须是能跑回调的 `Hub.Queue`，给空对象会在 `_simulation.xhtml:324` 抛异常、绘图链整个断；② plotly 要钉 1.x（2.x 反复抛 `reading 'length'`）；③ **`plotlyPanel` 算出来的高度是 0**，本轮手动设 400px 才画出图 ⇒ 交付形态得带外层页面或补 CSS，别当开箱即用。

### EJSS 运行时控制面：读了两个模型，写了两个静默失效写法

证据 `ejss-runtime-evidence.json`（2026-10-19）。解压后的仿真页里 `window._model` 是全局，`initialize/step/update/play/pause/reset/serialize/unserialize` 都在。

- **烘焙的参数确实是运行时在用的值**：`Illustration2_6` 的 y=45 / a=−9.8；`Problem2_18` 的 y_r=2 / v_r=10 / a=−9.8（后者 dt=0.02，变量名与 Initialization 块结构都不同，Initialization 长度实测为 0）。
- **`step()` 不需要动画帧就能推进**，轨迹逐点落在解析抛物线上：前者 t=1.9 时 y=27.31099999999999 vs `45−4.9·1.9²`=27.311（差 ~1e-13）；后者 t=0.1/0.2/0.4 三点全对到 1e-15。运行时写值也能成：注入 y_r=3.5 / v_r=6.0 后一步得 3.61804 / 5.804，与 `3.5+6·0.02−4.9·0.02²` 逐位相同。落地时刻 3.099994 vs 解析 3.030458（+2.29%）是**步长量化**（事件只在 dt=0.1 的格点上判），不是积分误差。
- **两个不报错也不生效的写值方式**（都是踩出来之后单独测的）：① `unserialize()` 必须收到 `serialize()` 的**完整信封**（`{"model":…,"view":…}`），只把里面的 `model` 子对象传回去等于没写；② 直接改字段 `_model.y_r=1.25` 读回来是 1.25，但 `step()` 之后引擎仍按原轨迹走 ⇒ 真正的状态不在顶层字段上。所以 Agent 侧的验收必须「写 → 立即 serialize 回读比对注入值」，不能只看有没有异常。
- 另一条：**同一 tick 里调 `initialize()` 之后立刻读，`t` 并不会被重置**（实测跑完 20 步再 initialize，t 仍是 0.12）⇒ 要干净初值就重载页面。
- 这条面后来被搬到命令行并量到整批（`../library/ejss_headless_lab.mjs` 与 `../library/ejss_headless_sweep.mjs`，25 个 EJS 6.02 包三趟逐个跑）：批次数字与「选靶规则」的教训归 [`../library/README.md`](../library/README.md) 所有，这里不重复。

## 引擎目录

引擎本体全部由 `.gitignore` 挡住不入库，内部 README 属上游资产，保持原样。例外是 `3jcn/`——里面的抓取脚本、`3jcn-inventory.json` 与本目录 README 是项目侧资产，入库，只有 `3jcn/pages/` 的第三方 HTML 被挡。体积为 `inventory.json` 实测（工作区口径，不含 `.git`）。

| 目录 | 引擎 / 许可 | 装法 | 工作区体积 | 文件数 | 一句话状态 |
|---|---|---|---|---|---|
| `ray-optics/` | Ray Optics，Apache-2.0 | `--depth 1` 全仓 | 54,610 KB | 3,241 | **已接通**（唯一有模板与适配器的）；另有 5 项光学验收台 5/5 pass |
| `myphysicslab/` | myPhysicsLab，Apache-2.0 | `--depth 1` 全仓 | 10,208 KB | 530 | 已实测三条线（单摆 / 绳波 / 牛顿摆），见下 |
| `circuitjs1/` | CircuitJS1，GPL-2.0（`build.gradle` 自身声明 GPLv3） | `--depth 1` 全仓（**官方仓是 `pfalstad/circuitjs1`**） | 5,547 KB | 798 | **GWT 编译已跑通**，有可部署产物，见下 |
| `matter-js/` | Matter.js，MIT | `--depth 1` 全仓 | 2,085 KB | 122 | 无头步进 pass；抛体 5/5，碰撞 2/4（不如预期的两条见下） |
| `rapier-js/` | Rapier JS 绑定，Apache-2.0 | `--depth 1` 全仓 | 2,074 KB | 179 | 仓库内 0 个 `.wasm`，可用产物走 [`../components/`](../components/README.md)；自由落体与带电粒子均已对解析式 |
| `three/` | three.js，MIT | `--filter=blob:none` + sparse（src、examples/jsm、build、LICENSE…） | 23,623 KB | 1,514 | 稀疏检出，纯数学已 pass |
| `stellarium-web-engine/` | Stellarium Web Engine，AGPL-3.0 | `--depth 1` 全仓 | 14,282 KB | 818 | 仓库内 0 个 `.wasm`，需 Emscripten 构建（**未构建**） |
| `webots/projects/` | Webots，Apache-2.0 | 只取树 + sparse 检出 `projects/` | 1,016,232 KB | 7,858 | 只装资源（304 世界 / 853 proto），**本体未装** |
| `phet/libs/`（10 个） | PhET 通用库，MIT | `--depth 1` main | 55,726 KB | 1,730 | main 仍是完整源码 |
| `phet/sims/`（20 个） | PhET 仿真，GPL-3.0 | 按最新发行分支 `--depth 1` | 96,804 KB | 1,683 | 19 个有源码，`circuit-construction-kit-common` 实测仍是空壳 |
| `phet/published/`（13 个） | PhET 官方发布成品，**成品 HTML 是 CC BY-NC 4.0**（源码 GPL-3.0、库 MIT 是另外两套义务） | `fetch_phet_published.py` 取 `sims/html/<sim>/latest/<sim>_all.html` | 44,522 KB | 13 | 逐只无头量成**四档**（展示 13/13、可读 6/13、可写 **1/13**、API **0/13**）；判据与三次口径修正归 [`../library/README.md`](../library/README.md) 所有 |
| `osp/` | OSP 核心库，**无 LICENSE 文件**（实测 `license_files` 为空） | `--depth 1 --single-branch` | 185,194 KB | 1,293 | 只读参考；`.java` 807 个；许可未定 ⇒ 禁止进交付包 |
| `osp_ejs/` | EJS 编译器内核，**无 LICENSE 文件** | 同上 | 15,353 KB | 636 | 只读参考；`.java` 567 个：改参 = 改 `.ejs` 再重新编译（**这条链本轮没跑**） |
| `webejs/` | Web EJS 静态运行时，GPL-3.0 | 同上 | 74,006 KB | 2,282 | `.js` 925、`.wasm` 0、`.html` 26：EJSS 模型在浏览器里跑的那层。本轮实测**没用到它**——走的是「读 `.ejss` 参数表 + 执行模型自带函数」，不经过这层运行时 |
| `resources/` | OSP 文档与收藏页，GPL-3.0 | 同上 | 297,553 KB | 865 | `.html` 201 个（docs/ 按会议与收藏分目录）。**双缝干涉那条实验的种子在这里**（`docs/CollectionTest/webejs_model_MultislitDiffraction.zip`，382 KB），已读出参数表并执行其物理函数；其余模型仍只是文件 |
| `STP/` | Statistical and Thermal Physics，GPL-3.0 | 同上 | 12,570 KB | 140 | `.java` 123 个；`stp/` 下实测有 idealgas、idealgasintegrals、thermalcontact、carnot、entropy、diffusion、boltzmann 等包 ⇒ 热学终于有上游真代码可对照 |
| `csm/` | Computer Simulation Methods，GPL-3.0 | 同上 | 752 KB | 198 | `.java` 195 个：MD / Ising 的独立参考实现，可当热学的第二个意见 |
| `3jcn/` | 3JCN 目录镜像 + 14 份演示页（`demos/` 被 `.gitignore` 挡住），**站点未声明开源许可** | `fetch_3jcn_index.py` 抓目录、`probe_3jcn_demo_interfaces.py` 抓演示 | 205 KB（`pages/`） | 8 页 + 2 份清单 | 结构面已量、**运行时只到「UI 可驱动」**；逐轮历史与离线口径归 [`3jcn/README.md`](3jcn/README.md) 所有，见下 |

\* 逐库 / 逐仿真的文件数与 commit 见 `inventory.json` 与 `fetch-phet-log.tsv`；上表两个数字是 `inventory.json` 里对应单元的求和（2026-10-19 实测）。

## 逐目录实况

只写**这一层**的实测，实验级读数请去 [`../library/README.md`](../library/README.md)。

### `myphysicslab/` — 第二个能无头出数并对解析式的引擎

前置：`cd source/upstream/myphysicslab && npm install --no-save typescript && npx tsc`（`build/` 是生成物，不入库）；跑法 `node source/upstream/probe_myphysicslab.mjs`。

- 单摆（`probe_myphysicslab.mjs` / `probe_myphysicslab_spring.mjs` + 两份 `probe-myphysicslab*.json`）：上游自己的 `PendulumSim`（L=1 m、g=9.8、θ0=0.1 rad、dt=0.001 s，跑 30 s）测得周期 **2.00835 s**，一级大角度解析值 **2.00834 s**（偏差 0.0000%），小角度值 2.00709 s（+0.0625%，正是 θ0²/16 的修正量）。
- `npx tsc` 出 322 个 ESM；`build/sims/pde/StringSim.js`（PDE 绳模型）绳波 5/5；`NewtonsCradleApp.make` + `ContactSim` / `CollisionAdvance` 复现「n 进 n 出」5/5——**这条 Matter 与 Rapier 都做不到**。

### `circuitjs1/` — GWT 编译首次跑通，且不碰上游

- `compileGwt`（**任务名不是 `gwtCompile`**）58 s，产物 `build/gwt/out/circuitjs1` 实测 12.4 MB / 5 个 permutation。
- **复现方式**：直接调用 `~/.gradle/wrapper/dists` 里已下载的 `gradle-8.14.3` 可执行文件——wrapper 钉的 **8.7 与本机 Java 23 不兼容**。此前为跑通而改的 `gradle-wrapper.properties` 已 `checkout` 还原。
- `dist.sh` **仍失败**（脚本自带 md5 校验，实测报 TestManager.java 哈希不符），但 `makeSite` 已把可部署站点拼出来（`site/`）。
- 电学三条已在同源浏览器里对上解析式（`../library/circuit-lab-evidence.json` 5/5）。

### `matter-js/` — 步进与抛体过，两条碰撞不如预期

无头步进 pass；抛体 5/5（`../library/projectile_lab.mjs`）；碰撞 2/4（`../library/collisions_lab.mjs`：完全非弹性共速 pass，**弹性正碰不守恒动能**、牛顿摆 n 进 n 出复现不了）。

### `3jcn/` — 结构面、运行时、离线口径，分三段说

- **结构面（`3jcn-demo-interface-probe.json`）**：镜像分类页共 **54 条演示链接**（Phyc140 19 / Phyc240 25 / Simulation 9 / thermodynamics 1）；抓下 14 份演示页（14~30 KB）后 **14/14 都带具名 `<input type=range>` 滑块且有 min/max/step/value**（`tempSlider` 0~600、`massMetalSlider` 300~700、`density1` 1~3 step 0.1、`liquidVolSlider` 1500~2900…），11/14 用 three.js，13/14 页可直接改的数值常量共 65 个 ⇒ 控制面比 PhET 成品显式得多。
- **运行时（判据是被自己的对照组打死的）**：`../library/jcn3_headless_lab.mjs` 在 `buoyant_force_exp` 上页面 0 异常却 canvas 恒 0（补 `--use-gl=angle --use-angle=swiftshader`、WebGL 明确可用仍是 0，three.js 场景没初始化），而拿去当「读数指纹」的 6 个数字其实是滑块量程标注（100/200、1500/3000、10/100）——**同值再派发一次事件、读数本该不变**这条对照组先把判据钉死，所以记 FAIL、不写「能改参」。缺的依赖也定位了：页内引用 `../css/final.css`、`../css/main3.css` 与 jQuery 3.2.1 / bootstrap 3.3.7 CDN，镜像一个都没取（three.js 出处当时也还没查）⇒ 离线不成立。
- **同日四 pass 把歧义判别干净**：真站与本地镜像双路一致——写滑块画面变、程序化改回原值不回基线、但**点页面自己的 Reset 精确回到基线帧**，且「不作操作两帧一致」的渲染对照组都成立 ⇒ **3JCN 记为 UI 可驱动**（画面通道成立，先前失败在我的复原写法）；只是该页采不到物理量数字读数，「改参 → 解析式对账」仍空，故不升格为已验证实验。mirror 的缓存跳过 bug 已修（命中缓存仍解析）、`js/three.module.js` 已抓到；曾报的 3 条 `Cannot read properties of undefined (reading 'position')` 也已闭合。
- **剩下的都在这里看**：逐页离线闭合情况、canvas 元素像素口径的分档、`apparent_weight` 那一档完整 5/5、批量 31 页的旧口径作废与九 pass 两条结论（`_vendor/three.module.js` 是 threejs.org 的**拆分产物**，缺 `three.core.js` 必 404；`diagnose_offline_load.mjs` 才发现 **ES module 的 import 失败不抛 `pageerror`**，只收异常数的探针在这条上是哑的）——归 [`3jcn/README.md`](3jcn/README.md) 所有，本文件不复制数字，避免两处各过期。

## 消费方

- `code/eduforge/services/engine-host`：适配器 `require` 上游 `dist-node/rayOptics.js` 做无头仿真；预览服务与浏览器网关托管完整 `dist/`（提供 `/simulator/`、`/gallery/`、`/cn/` 等原版路由）；离线导出复刻上游 dist。
- `code/eduforge/apps/teacher-web`：在「⚡ 光学仿真模拟器」和「📚 81 演示案例库」中直接集成并消费上游原生场景与模拟器。
- `code/eduforge/tools/`：探针脚本（`EDUFORGE_RAYOPTICS` 环境变量可指到别处的上游检出）。

## 纪律

- 升级上游 = 重新克隆 + 更新 lock 文件的 commit 与实测记录，**不**在旧检出上打补丁。
- lock 文件里的「实测」条目必须可复现；写新条目时把命令和输出一起记。
- **稀疏检出的仓库必须把 LICENSE/NOTICE 一并检出**。three.js 第一次稀疏只取了 `src / examples/jsm / build`，仓库根 LICENSE 不在盘上——MIT 组件缺许可证文本是合规缺陷，不是小事（已补，见 lock 里 three 的 known_pits）。
- **PhET 成品要说就按档说**。四档数字与三次口径修正的家在 [`../library/README.md`](../library/README.md)（展示 13/13 / 可读 6/13 / 可写 1/13 / API 0/13）；对外描述既不要说「都能被 Agent 定制」，也不要再说「物理量一律改不动」——后一句本轮被实测推翻了一半。另有三条仪器教训同样记在那份里：报错要按「哪一次加载」归账、画面对照要排掉「变成报错页」、单位正则要同时收 `mA` 与 `milliamps`（第一版因此把成立的写通路判成 FAIL）。
- **别把「装上了」写成「接通了」**。本目录现在的状态分四层，逐层的凭据分别在 `../library/README.md`（读数）与本文件上面的实况小节（构建/运行时）：
  1. **Ray Optics 已接通**：有模板、有适配器、出过离线包，五项光学也已用 `../library/optics_hall.mjs` 对了解析式（5/5 pass）。
  2. **能无头出数并对解析式，但没模板没适配器**：myPhysicsLab（单摆、弹簧、绳波 PDE 5/5、牛顿摆 5/5）、Rapier（自由落体、带电粒子、弹性碰撞、理想气体与三条状态律 6/6、开普勒三定律 6/6）、Matter（抛体、碰撞）。
  3. **组件与浏览器态这条路**：Matter / three 的 npm 组件在本机 Node 跑通步进与几何；CircuitJS1 走「同源浏览器 + 官方 JS 接口」（能改参能读数）。此前这类页面因为要人点浏览器而进不了回归，本轮 `../library/ejss_headless_lab.mjs` 证明可以用本机 chromium 无头驱动，且**已经搬到 CircuitJS1 上**（`../library/circuit_headless_lab.mjs` 一条命令跑完整套验收台，顺带暴露并修掉验收台自己的两处判据缺陷）。
  4. **只有源码或目录落盘**：Webots 本体、Stellarium 构建仍 `pending`；PhET 生产包已逐只量成四档（见上）；3JCN 只到「结构面已量 + UI 可驱动」，改参与解析式对账那一半仍空。
  ⇒ 对外讲资源库进度按这四层说，别跨层借证据。
- **上游没装成之前，别急着写「找不到权威来源」**。本轮两条旧结论都被推翻了：OSP 的组织名是 `OpenSourcePhysics`（旧记录猜 wejen / osp-tools / compadre-io 全 404 就判「不装」），3JCN 是静态站（旧记录判「Java applet 时代不可锁定」）。正确动作是先打 `api.github.com/orgs/<候选>/repos`、`api.github.com/search/repositories?q=…` 与站点 HTTP 头，拿到返回再下结论；结论被推翻时在 lock 里写明撤销了哪句（本轮已写）。
- **仓库根没有 LICENSE 文件 = 许可未定，不是「默认可以用」**。`osp/` 与 `osp_ejs/` 实测无 LICENSE/COPYING，只能只读参考；要进任何交付包，先取得书面授权说明并登记进 lock。
- **EJSS 的 `<Domain>` 不是「可改」的开关**。它只在带参数页的模型里出现，导出包普遍省略；如果按 `domain == "public"` 过滤，26 个有参数表的模型会被误判成 0 个。`probe_ejss_model.py` 现在按「省略也算可调，只排除 internal/private」计数，并把 `domain_declared` 单独记下来。
- **「包里带运行时」不能推出「浏览器里能打开」；反过来，「这个包里有打不开的文件」也不能推出「仿真页打不开」**。`survey_ejss_models.py` 对整包所有 HTML 计数得 28/28 引用包外资源、27/28 引用包内不存在的目录名——一度被我写成「这批包都得先拼树」，那是把 `EjsLauncher.html`、`<Name>_Contents.xhtml` 这类包装页和仿真主页面混在一起了。按页面分开量之后：26 个有仿真主页面的包里，主页面引用缺失文件的为 **0**，远程加载为 0 的有 **25**（唯一例外是 webejs 那份，6 处 CDN，已在浏览器里拼树跑通）。教训留在两处：交付前要在浏览器实测（`assemble_ejss_offline.py` 做通过的那份含三处必需修补：本地运行时、plotly 1.x、能跑回调的 MathJax 替身），以及**计数要写清统计口径**，否则同一批数字能同时支持两个相反的结论。
- **两个静默失效的探针/写法，都会把「没有」读成「坏」**。① `probe_ejss_model.decode()` 原来先试 utf-16：不带 BOM 的偶数长度 UTF-8 会被它静默解成乱码，survey 一度报「26 个包都没有 `_model`、0 个包要改 CDN」——靠直连 grep 的对照值（`var _model` 2、`src="http` 4）才抓住。② 对 EJSS 模型 `unserialize()` 只喂 `serialize()` 里的 `model` 子对象、或直接改 `_model.<字段>`，都不报错也不生效。共同点：失败是静默的，所以判据里必须带「写后回读」与「换一种读法对照」。
- 改过上游清单（增删目录、换分支、换克隆方式）后，**重跑 `inspect_upstreams.py` 与 `python source/library/check_catalog.py`**，两边数字与路径要一致；后者 missing 不为 0 就不算装完。本轮实测：100 条路径 / missing 0，45 个安装单元。
- 遍历本目录的脚本必须先剪枝：`phet/`、`webots/`、`three/` 等每个引擎目录都自带 `.git`，文件总数上万，用 `rglob` / `find` 全走一遍会明显变慢（AGENTS.md 第 4 节同一口径）。
