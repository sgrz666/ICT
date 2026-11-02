# candidates — 候选交付物

放「准备交出去的东西」：`offline-package/` 为 GATE-8 离线网页包，`labkit/` 为实验页面，`agent-runtime/` 为原生 dsh Windows 发行候选。

## agent-runtime/

`win-x64-20261031/` 是本轮原生 dsh 启智 Web 候选，使用包内 Node、运行依赖、实验资源与 Chromium Headless Shell；文件哈希和字节数以包内 `inventory.json` 为准。构建中断的 `portable-win-x64-20261031-a/` 留作现场，不作为交付件。

发行候选是生成的数据树，`runtime/node_modules/`、浏览器与 `assets/` 不逐目录维护项目侧 README，按本父层说明和 `inventory.json` 管理；根包自己的启动 README 由构建器生成。源码与复跑命令见 [agent-runtime](../../../code/eduforge/services/agent-runtime/README.md)。真实模型仍需有效凭据，候选不等于已通过全部生产验收。

## offline-package/

- `manifest.json` — 包清单：`engine_id: ray_optics`、`engine_version: 5.5.0`、`native_format_version: 5`、`scene_sha256`（登记哈希，交付时按它校验）、入口 `www/index.html`、`requires_local_static_server: true`、许可 `Apache-2.0 (Ray Optics)`。
- `www/` — 当前实测 **2162 个文件**（随构建内容变化；含上游模拟器静态产物 + 全量 81 个案例场景与多语言页面 + 模板场景经 json-url lzma 注入）。历史上曾为 477 个文件（未含全量案例库构建），数字以 `find www -type f | wc -l` 实测为准。

## labkit/

`labkit/` 是 LabKit 单文件实验的产物区（**不是离线包**）：

- `<recipe>/<name>.html` — 历史单文件页面，双击即开、零网络；2026-10-31 起插件新调用使用 `<recipe>/<uuid>/<name>`，每次分配独立目录：
  - 抛体：内联 matter-js + 物理内核，约 113–118 KB；
  - 单摆：内联 matter-js + 单摆内核，约 108 KB；
  - 直流电路：内联 MNA 求解器（无外部引擎），约 27 KB。
- `<recipe>/<name>.evidence.json` — 参数、实测/解析值、逐项误差、`design_hash`；抛体另含阻力对照，电路另含 CircuitJS1 交叉验证。
- `selftest/` — [`../../../code/eduforge/tools/labkit/selftest.mjs`](../../../code/eduforge/tools/labkit/selftest.mjs) 的自检产物（7 个配方）。

### 目录里实际有什么（2026-10-20 实测）

顶层 8 个目录：`circuit/`、`complementary/`、`oblique45/`、`ohms-law/`、`pendulum/`、`period-length/`、`selftest/`、`test/`，外加 10 个散件（截图与一次性脚本，见下）。

**贯穿所有目录的只有一件事**：每个配方一组 `<name>.html` + `<name>.evidence.json` 同名配对（页面 + 那份带 `design_hash` 的 L2 证据）。实测各目录的配对数：

| 目录 | html | json | 备注 |
|---|---|---|---|
| `circuit/` | 3 | 3 | 欧姆 / 串联 / 并联三配方 |
| `complementary/` | 2 | 2 | 互补角 |
| `oblique45/` | 2 | 2 | 另含截图与对照件（见下） |
| `ohms-law/` | 2 | 2 | |
| `pendulum/` | 2 | 3 | 多出的一份 json 是运行期附带记录，不是第 3 个页面 |
| `period-length/` | 5 | 5 | 摆长-周期多次跑留下的版本 |
| `selftest/` | 0 | 0 | 顶层无文件，按 `<模板 id>/<配方>/` 分层放 selftest 产物 |
| `test/` | 3 | 3 | 试验性产物（含 1 张截图） |

**只有 `oblique45/` 是"带档案"的那一个**，因为空气阻力控件那轮的全部现场都留在它身上：`_original-design.json`（当初那份设计，`renderSingleFile` 的输入，留着才能重渲染出逐字节相同的页面）、`oblique45-range-max.before-drag.html/.png`（加控件**之前**的版本，用来对比）、`oblique45-range-max-drag010.png`（把 `friction_air` 拉到 0.01 之后的画面，射程肉眼可见变短）、3 张截图、`LICENSE.matter.txt`，以及本目录唯一的现场说明 [`oblique45/README.md`](labkit/oblique45/README.md)（参数 `v0=20/θ=45/h0=0`、设计指纹、内联引擎与 vendor 逐字节相同的 sha256）。其余配方目录没有这些件，也**没有自己的 README**——读法以本文件为准。

关于 `LICENSE.matter.txt`：页面把 matter-js 整个内联进 HTML，MIT 许可应当随包走。目前**只有 `oblique45/` 放了它**，`complementary/`、`pendulum/`、`period-length/` 这三条同样内联 matter-js 的线里没有——这是交付前要补的一处（`circuit/`、`ohms-law/` 走自包含 MNA，不需要）。

### 顶层那些散件是什么

`_drag-off.png` / `_drag-on.png` / `drag-control-off.png` / `drag-control-on.png` 是阻力控件开/关的对照截图；`pendulum-shot.png` / `pendulum-final.png` / `circuit-shot.png` / `series-final.png` 是各条线跑通时留的证据截图；`_rebuild.mjs` 与 `_l3.mjs` 是**一次性手工驱动脚本**（分别做「用 `_original-design.json` + 现有 evidence 重渲染并跑 L3」和「只对现有 HTML 跑 L3」），它们假设 CWD 是仓库根、直接 import `code/eduforge/tools/labkit/lib/` 里的实现。正式复现请走 `code/eduforge/tools/labkit/` 的 selftest 与 drag probe，这两个文件只是当轮排障留下的现场，可以删。

与 `offline-package/` 的区别：离线包是「上游 dist 整包 + 随包静态服务」，单文件是「引擎/求解器整体内联 + `file://` 直开」。前者适合多文件引擎（Ray Optics、CircuitJS1 完整 UI），后者适合可内联的引擎或自包含求解器（matter-js、MNA）。两者都已被 `.gitignore` 挡住，产物不入库——所以 `labkit/` 里除了 `oblique45/README.md` 这样的现场说明，都不指望被 clone 出来的人看到，**要留在版本库里的结论请写进本文件**。

## static-html/

`static-html/phet/` 是**已下载 PhET 单文件实验**的清洗打包区（44 MB，13 个）：

- `<sim>.html` — 13 个 PhET `*_all.html` 的清洗版：删 Cloudflare/canonical 外链、注入 CSP 锁网、写来源与 sha256；模拟器本身仍是 PhET 原样。
- `index.html` — 13 张实验卡片 + 18 个登记实验的覆盖表（12 个有 PhET 单文件，6 个标注「未覆盖（多文件资源，待打包）」）。
- `manifest.json` — 每个 sim 的版本、映射实验、源/产物 sha256、离线实测结果（SVG/canvas 数、`network_responses=0`、CSP 拦截数、模拟器 console error）。

覆盖缺口：`mechanics-spring-hooke`、`mechanics-projectile`、`mechanics-newtons-cradle`、`waves-string`、`mech3d-free-fall-collision`、`em3d-charged-particle-in-b` 没有对应的 PhET 单文件资源；前四个在 3JCN 里是 Three.js 多文件页，后两个无现成单文件资源。打包脚本见 [`../../../code/eduforge/tools/pack_static_html.mjs`](../../../code/eduforge/tools/pack_static_html.mjs)。

## 已知限制

- **必须本地静态服务**：上游运行时 HTTP 取 i18n 词条，`file://` 直开不成立；「单文件 HTML」形态还差一层 i18n 预注入，未做。
- 体积大，已列入根 `.gitignore`；可再生（导出实现见 `code/eduforge/services/engine-host/src/export/offline-package.ts`，测试 `tests/e2e/gate8_offline.test.ts`）。
