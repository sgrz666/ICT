# 3jcn — 3JCN Physics Simulations 的目录镜像（不是引擎）

职责：把 3JCN（`https://www.new3jcn.com/`）这个静态站点的**演示目录**抓到本地，让资源库能离线检索「有哪些 3D 演示」，同时把它**不能**做的事写清楚：这里没有可运行产物，也没有任何已验证的改参接口。

## 内容

- `fetch_3jcn_index.py` — 抓取与抽取脚本。抓 8 个页面（`index.html`、`simulation.html` 与 motion/optics/thermo/electricity/modern/labs 六个分类页）存 `pages/`，再从 `<a>` 里抽 title+href，去重后写 `3jcn-inventory.json`。已存在即跳过（可重复跑），每页之间 sleep 0.4 s。跑法：`python source/upstream/3jcn/fetch_3jcn_index.py`。
- `3jcn-inventory.json` — 落盘清单（2026-10-19 实测：**8/8 页全部抓到、90 条链接**），含 `note` 字段说明「目录 ≠ 可控」。
- `pages/` — 抓下来的第三方 HTML（实测 8 个文件、205 KB，最大 `simulation.html` 48,115 字节）。被 `.gitignore` 挡住不入库，重跑脚本即得。

## 与上下层的关系

- 上层说明在 [`../README.md`](../README.md)：3JCN 是简报「适合补充进来的 2D/3D 仿真平台」表里唯一**没有 git 仓库**的一项，因此 lock 里这条锁的是抓取时间与页面字节数，不是 commit。
- 目录层：被 [`../../library/experiments.json`](../../library/experiments.json) 以 `engines[]` 里 `id: 3jcn-catalog` 登记，状态是 `reference_only`（比 `resource_installed` 更轻），不背任何实验的验收。
- 对比着看：`circuitjs1/`（构建 + 官方 JS 接口已实测）、`osp/`（源码落盘但控制面 pending）与这里构成三种不同的「装」——能跑 ≠ 能改参 ≠ 只是清单。

## 已知的坑与纪律

1. **站点无开源许可声明**（实测页面只有版权行与 `patent.html` 链接）⇒ 这里的 HTML 与任何演示产物都**不得**打进离线交付包，也不进 code/eduforge 的依赖。
2. **别把 90 条链接当 90 个可用实验**。本轮只验证了「目录抓得下来」；单个演示是否可被 Agent 改参一个都没验（pending）。简报里「程序化接口尚未核实」这句至今仍然成立。
3. 无 commit 可锁 ⇒ 可复现性靠「抓取时间 + 页面字节数」，脚本重跑若发现某页大小变了，要在 lock 的 `facts_measured` 里更新数字，不要静默覆盖。
4. `pages/` 是第三方内容，**本目录只在这一层写项目侧说明**，不逐文件登记（与 `phet/`、`ray-optics/` 的口径一致，见 [`../../README.md`](../../README.md) 与 [`../README.md`](../README.md)）。

## 2026-10-19 程序化接口实测

结构面已量、运行时未证实（2026-10-19）：镜像分类页里共 **54 条演示链接**（Phyc140 19 / Phyc240 25 / Simulation 9 / thermodynamics 1），抓下 14 份演示页（14~30 KB）后 **14/14 都带具名 `<input type=range>` 滑块且有 min/max/step/value**（`tempSlider` 0~600、`massMetalSlider` 300~700、`density1` 1~3 step 0.1、`liquidVolSlider` 1500~2900…），11/14 用 three.js，13/14 页可直接改的数值常量共 65 个 —— 控制面比 PhET 成品显式得多。但运行时**没**证实：`../library/jcn3_headless_lab.mjs` 在 `buoyant_force_exp` 上页面 0 异常却 canvas 恒 0（补 `--use-gl=angle --use-angle=swiftshader` 后 WebGL 可用仍是 0，three.js 场景没初始化），而我拿去当「读数指纹」的 6 个数字其实是滑块量程标注（100/200、1500/3000、10/100）——**是对照组（同值再派发一次事件、读数本该不变）先把这条判据打死的**，所以记 FAIL，不写「能改参」。缺的依赖也定位了：页内引用 `../css/final.css`、`../css/main3.css` 与 jQuery 3.2.1 / bootstrap 3.3.7 CDN，镜像一个都没取（three.js 出处也还没查）⇒ 离线不成立。证据 `3jcn/3jcn-demo-interface-probe.json` 与 `../library/jcn3-headless-lab-evidence.json`。

新增两份项目侧文件：`probe_3jcn_demo_interfaces.py`（结构面探针）与驱动台 `../../library/jcn3_headless_lab.mjs`。`demos/` 与 `pages/` 一样被 `.gitignore` 挡住不入库——里面全是第三方 HTML，站点未声明开源许可，只作本机分析用。

二 pass（同日，已补依赖闭包后）：新增 `mirror_3jcn_site.py` 把同源依赖按站点路径镜像进 `site/`（本次 60 个文件 / 16,930,951 B，含 `jsm/three.module.js` 1,145,222 B、`jsm/GLTFLoader.js`、`jsm/RoundedBoxGeometry.js`、`css/*.css`、`textures/*.png`），并把驱动台改成只认「数字紧跟物理单位」的读数（排除 INPUT 文本）+ 支持 `--url` 走同源伺服（ES module 在 `file://` 下被 CORS 挡）。重跑 `Phyc140/flat_mirror_prob.html`：对照组 `control_noop=true`、`reverts_to_baseline=true`、写值回读匹配（xSlider 2→2.5）——**判据本身终于可信了**，但 `readout_changed=false` 且 **canvas 仍为 0**。真正的卡点这次定位到具体一条：诊断脚本抓到页面实际 import 的是 `../js/three.module.js`，返回 404 （站点有 `js/` 与 `jsm/` 两套目录，本页走的是 `js/`），而跨域 jQuery/bootstrap 之外还有 3 个 URL 抓取失败 ⇒ 依赖闭包没补全，3JCN 的**运行时控制面仍未证实**，判 `accepted_but_no_observable_change`（写值得进、看不到物理后果，正是简报警告的那一类）。下一步：按页面真实引用补 `js/` 目录再复跑；`site/` 与 `demos/`、`pages/` 一样被 `.gitignore` 挡住不入库。

三 pass（同日）：把驱动台对准**真站在跑**的页面（https://www.new3jcn.com/Phyc140/flat_mirror_prob.html）重测，拿到第一条正向证据——渲染对照组「不作任何操作连取两帧」`898e13f2824b == 898e13f2824b`（画面自己不动，所以画面差异可以当判据），canvas 存在（1 个），写 `xSlider` 2→2.5 之后**整页 PNG 变成 `a8c46ff79ebf`** ⇒ Agent 的输入确实改到了 3D 场景。但把值改回 2 之后画面**没有回到基线帧**（`reverted_to_baseline=false`），双向判据不成立 ⇒ 仍判 `accepted_but_no_observable_change`（FAIL），不能升格成「可控」。两种解释都没排除：页面是单向状态（位置只往前走/需要 Reset 才复原），或我的复原写法没触发它的监听。下一步就做这一件区分：改回原值后再点页面自己的 Reset，看画面是否回到基线——回到就是复原路径问题，不回到就是页面单向状态。顺带两条自查：`mirror_3jcn_site.py` 现在会跟 JS→JS 的 import（上一版只跟 png/json/glb，所以 addon 里的 `../js/three.module.js` 永远没进队列，表现是「无异常但没画面」，而真站上该文件 200 / 1,167,393 B 好好地存在）；但**缓存跳过那段有 bug**——命中缓存时直接 continue，导致已抓过的页面不再被解析、闭包补不全（本轮 mirrored 0 files 就是这个），修好之前 `site/` 不能当离线交付用。

四 pass（同日，判别实验跑完）：把「改回原值画面没回来」这个歧义用一个实验分开——复原之后再点页面自己的 Reset。结果在**真站与本地镜像两条路上都一样**：真站 baseline 帧 `898e13f2824b` → 写 `xSlider` 2→2.5 变 `a8c46ff79ebf` → 程序化改回 2 **仍不回基线** → 点页面 Reset 后回到 `898e13f2824b`；本地镜像同一套（`734c3edec38e` → 变 → 不回 → Reset 回 `734c3edec38e`），且两路的渲染对照组都成立（不作操作两帧一致，画面静态）。⇒ 判别结论明确：**画面通道是成立的，失败在我的复原写法**（把 input.value 改回去再派发事件，并不等价于页面自己那条 Reset 路径）。因此 3JCN 现在可以记为「**UI 可驱动**」：Agent 写滑块能改到 3D 画面、且页面自己的 Reset 能复原——但**还不能升格成已验证的实验**：这只页面没有可采的物理量数字读数（`readout_tokens` 为空），"改参→解析式对账"那一半仍然空白，简报的警告依然适用。镜像侧还剩一条明确缺口：本地跑出现 3 条 `Cannot read properties of undefined (reading 'position')` 而真站 0 条，说明依赖闭包仍差东西（最可能是 GLTF 模型由 JS 拼路径、没被 BFS 抓到），补齐才算离线可用。

五 pass（同日，离线闭环补齐）：正则 BFS 之所以补不全，是因为演示页把资源路径**拼在 JS 运行时字符串**里（`models/free_kick/scene.gltf` + `scene.bin` 2,030,680 B + 打包贴图 3,115,426 B 就是这么来的）。改用 `audit_offline_gaps.mjs`：以**浏览器真实发出的请求**为清单，逐个映射到 `site/` 并按需抓缺项（本页同源请求 13 个，盘上已有 8、缺 5、全部补齐，真站自身 0 个未返回）。补齐后本地伺服重跑驱动台，与真站**逐哈希一致**：canvas=1、不作操作两帧一致（`898e13f2824b`）、写 `xSlider` 2→2.5 → `a8c46ff79ebf`、点页面 Reset 回到 `898e13f2824b`，页面异常 0 条。⇒ 3JCN 现在不只是「UI 可驱动」，而是「**本地离线可跑、可被自动化驱动、且与真站像素一致**」；仍缺的那一半也说清楚：这只页面没有数字读数，改参→解析式对账还得换一只页面（或直接读 3D 场景里的文字）才能补上。

六 pass（同日，换页面拿到完整闭环）：`Phyc140/apparent_weight_exp.html` 在**本地镜像 + 自建同源伺服**下连跑两遍，5 只具名滑块（`posSlider`、`massMetalSlider` 300~700、`tempMetalSlider`、`massLiquidSlider` 1200~2000、`tempLiquidSlider`）**全部判 `agent_writable_and_observable`（PASS）**：写值回读一致、「同值再派发事件画面不变」对照组守住、写值后整页 PNG 变、改回原值画面**回到基线帧**（`reverted_to_baseline=true`，与上一只平面镜页不同——那只要靠页面 Reset 才回得去），页面异常 0 条，两遍结果一致。⇒ 3JCN 这一族现在有了「离线可跑 + Agent 改参 + 可观测响应 + 可复原」的第一只完整样本。还差的那一半也说清：**读数没有 DOM 数字**（`readout_tokens` 为空，读数画在 3D 文字里），所以「改参→解析式对账」仍未做，这一只不能标成 `engine_*_verified`，只能标成 **UI 可驱动且可观测**。另外修了自己一个工具缺陷：驱动台把逐条结果写成 `"…%s…" % (…)`（JavaScript 里这是取模），控制台整行只剩 NaN，5/5 通过的运行看起来像坏了——现在改回 `console.log(fmt, …)` 并留了注释。
