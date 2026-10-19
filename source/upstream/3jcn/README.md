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
