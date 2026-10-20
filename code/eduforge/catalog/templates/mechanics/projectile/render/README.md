# render — 单文件页面骨架与运行时

**职责**：提供抛体实验单文件 HTML 的静态骨架、页面运行时与样式。这一层**不含物理公式**：物理来自 [`../../../../../tools/labkit/lib/projectile-core.mjs`](../../../../../tools/labkit/lib/projectile-core.mjs)，渲染器只负责把模板、数据、引擎与运行时拼成一个文件。

## 1. 文件

| 文件 | 行数 | 作用 |
|---|---|---|
| [`template.html`](template.html) | 69 | 骨架：标题 / canvas / 参数区 / 读数区 / 教学说明 / 页脚；六个占位符 |
| [`runtime.js`](runtime.js) | 684 | 读 `window.__LAB_DATA__`，预计算轨迹、画 canvas、绑定滑块、暴露 `window.__LAB` / `__RESULT` / `__STATUS` |
| [`style.css`](style.css) | 229 | 内联样式；浅色、无外部字体、响应式两栏 |

## 2. 占位符（由 `render-single-file.mjs` 替换）

| 占位符 | 内容 |
|---|---|
| `__TITLE__` | `模板标题 · 配方标题`（HTML 转义） |
| `__STYLE__` | `style.css` 全文 |
| `__DATA__` | canonical JSON：meta / design / recipe / decision / engine / **sources** / render / acceptance / evidence（`<` 转 `\u003c`）；`sources` 是四份源文件的路径与换行归一后的 sha256 |
| `__MATTER_JS__` | `vendor/matter.min.js`，剥掉横幅 URL |
| `__CORE_JS__` | `projectile-core.mjs` 源码，`export` 关键字剥掉后作为普通脚本 |
| `__RUNTIME_JS__` | `runtime.js` 全文 |

## 3. 页面运行时不变量

- **固定步长预计算**：参数变化时同步跑完 `N=ceil(T/dt)` 步，得到采样点；`requestAnimationFrame` 只做回放。物理结果与帧率无关。
- **单一物理内核**：`createProjectileCore(window.Matter, engineConfig)`，与 L2 同一份代码；页面读数与证据读数同源。
- **零网络**：CSP `default-src 'none'; script-src 'unsafe-inline'; style-src 'unsafe-inline'; img-src data:`；无外链字体、图片、CDN。
- **验证钩子**：
  - `window.__STATUS = 'loading' | 'ready' | 'error'`
  - `window.__RESULT = {params, scenarios[{id, measured, analytic}], ratio_R?, design_hash, engine}`
  - `window.__LAB.setParams({v0, h0, angle_deg?, angles_deg?, friction_air?})` → 重新计算并返回 `__RESULT`（`friction_air` 与页面滑块同一状态、同一量程，写后能从 `__RESULT.friction_air` 回读）
- **读数显示**：实测 / 解析 / 偏差三行；偏差超过 1% 标红；互补角额外显示 `R(θ₁)/R(θ₂)` 与理论值 1 的对比。
- **空气阻力（2026-10-20 新增）**：`frictionAir` 滑块默认 0（= 理想抛体，验收路径不变）。拉到 0.01 时页面额外做一次「同参数无阻力」重跑，读数表换成两行：`偏离解析式之比（阻力/无阻力）`（与 L2 证据 `ratio` **同一定义**，实测 391.23 对得上，判据 ≥5）与 `射程 R(无阻力)/R(阻力)`（2.30 倍，40.76 → 17.76 m）。注意这两个数不是一回事——早先一次探针把判据误写成「射程比 ≥5」，才暴露出这个混淆。

## 4. 坑与纪律

1. **不要在这里写公式**。页面上的虚线来自 `core.analytic()`；把公式抄进 runtime 会造成 L2 与页面两套实现。
2. **不要引入外部资源**。MathJax、字体、图标都会破坏 `file://` 离线直开；公式用纯文本 + Unicode 下标。
3. **CSP 很严**：`default-src 'none'` 会拦掉任何 `fetch`/`XHR`/外部脚本。新增功能先确认不需要网络；需要 `eval` 的库不能进这个页面。
4. **动画不改物理**：`requestAnimationFrame` 只推进 `state.time`，不得在其中调用 `Engine.update`。
5. **改模板后必跑**：`node code/eduforge/tools/labkit/selftest.mjs`；它会重新渲染并用真 Chromium 以 `file://` 验证。

- **对照叠加（2026-10-20 新增）**：`oblique45` 是单角度配方，而它要证的命题是「45° 射程最大」——
  只有一条曲线时这句话**在页面上不可验证**。因此加了一个复选框，勾上后按同一 v₀/h₀ 追加 30° 与 60°
  两条**真跑 matter-js** 的对照（不是画参考线），读数表逐场景各给一行解析式对照与偏差。
  实测 R(45°)=40.7574 > R(60°)=35.3063 > R(30°)=35.2758（互补角差 0.09%）；
  把阻力拉到 0.02 后 **R(30°) > R(45°)**，结论自己会翻——这条翻转也被写进探针当正面判据，
  防止有人以后把对照改成硬编码的漂亮曲线。
- **文案必须只承诺页面真有的操作**：dsh 生成的 `student_task` 原文写着「点击发射或重放…对比页面给出的其他角度」，
  而页面上只有「暂停/重播」、也没有其他角度。L1 查教学理由质量、L3 查控件是否生效，**两边都不查文案与可得控件是否一致**，
  所以这句话一路绿灯到了交付件里。这条先由 `drag-control-probe.mjs` 兜住，**现已升进 L1**：`recipes.json` 里每个配方声明 `affordances`
  （buttons/sliders/toggles/comparison），`check.mjs` 的 `checkAffordances` 拿文案去比，对不上就报 `TEXT_AFFORDANCE`；
  反例常驻 `tools/labkit/l1-text-gate-test.mjs`。改文案会改 `design_hash`，必须重跑 L2 才能渲染——这个拦截是对的，别绕。
- **声明也要被验**：`affordances` 是手工写的，上一轮就过期过一次（三个配方都漏写新加的「空气阻力」）。
  所以 `render-single-file.mjs` 把它随 `DATA.recipe` 一起交付，`drag-control-probe.mjs` 再拿这份声明
  比对**浏览器里真实渲染出来的**滑块/开关/按钮（oblique45 现 **34/34**，2026-10-20）——
  声明与页面一旦不符，红的就是产物判据，而不是等到有人照着旧清单放行文案。

- **偏差判据带分辨率下限（2026-10-20）**：实测 `T` 的偏差恒等于 −1 个步长（−0.00417 s = −dt），
  `R`/`H` 的偏差就是它按 `v·dt` 的传播 —— 这是**固定步长的分辨率下限**，不是物理误差。
  配方那 1% 的相对容差是在设计点（v₀=20、θ=45、T≈2.88 s，占比 0.14%）标定的，
  直接套到 v₀=5、θ=15（T 只有 0.26 s，一步占 1.6%）就会把学生推到"页面自己说实验不通过"的角落。
  现在每一项按下限 `max(相对容差, dt/T 或 v·dt/R)` 判，并把两个数都显示出来（"本参数下分辨率下限 x%，一步 = 0.00417 s"）。
  放宽的不是判据，是把判据的适用条件写清楚。
- **越过模板声明的可视上限会明说**：`decision.max_apex_m / max_range_m / max_flight_time_s` 过去只在设计期用，
  学生拖过界页面一声不吭。现在读数表加一行"超出模板声明的可视范围 …… 坐标已自动缩放，读数仍是引擎真值"。
  量程扫描实测：84 组参数里 19 组越界，19 组都给了提示。

- **退化态给原因不给三个 0**：`h₀=0` 且无向上初速时物体一出发就贴地，引擎"没落地"是因为根本不在空中。
  过去读数表就显示 `R=0 T=0 H=0`，学生读到的是"实验坏了"；现在这一格换成
  「h₀=0 且水平抛出 ⇒ 一出发即贴地，没有可测的飞行。把「初始高度 h₀」抬到 1 m 以上再看。」
  （`horizontal` 配方固定 θ=0，所以它的滑块即使被程序设成 30°，回显仍是 0 —— 提示按**有效参数**判，不按请求值。）

- **数据记录（2026-10-20 新增）**：操作步骤原文就写着"观察并**记录** R / T / H"，但页面上没有任何记录手段——
  和「点击发射」是同一类缺陷（文案承诺了页面没有的能力），只是这次落在"记录"这个动词上。
  现在舞台条上有「记录本次 / 清空记录」，记的是**引擎当前算出的**读数（不是解析式），
  表里带 v₀/h₀/θ/f 与 R/T/H，换参数记满三行就能自己看出 45° 附近射程最大。
  探针侧三条判据保证它不是摆设：第一条的 R 必须等于页面当前读数、连记两行的 R 必须不同、清空后要回到空态提示。

- **资产溯源写进产物本身（2026-10-20）**：`DATA.sources` 带四份源文件的路径与 sha256（骨架 / 样式 / 运行时 / 内核），
  哈希一律**换行归一后**再取。这条是被一句质疑逼出来的——「这页好像没用我们的资源和组件」。实测下来：
  vendor 的 `matter.min.js` 83,476 字节与已装的 `source/upstream/matter-js/build/matter.min.js`（83,481 字节）只差 5 处 CRLF，
  归一后同为 `72d30be0…88e24ae`；`source/components/node_modules/matter-js` 那份连字节数都相同。
  产物目录 `README.md` 里「用了仓库里的什么」一节由 `render-single-file.mjs` **跑出来再写进去**（三段整段插入的文本能否在产物 HTML 里逐字节找到、
  已装的 matter-js 拷贝与 vendor 是否同哈希），不是手抄的说明；`drag-control-probe.mjs` 再拿 `DATA.sources` 回比仓库现状。
  反例验过：往 `runtime.js` 尾部加一行注释而不重渲，两条判据同时红并点名文件（`32/34`，`…/render/runtime.js 哈希不符`），还原后回到 `34/34`。
  **同一条路径没用到什么也写在产物 README 最后一行**：3JCN / PhET / EJS 属于「改现成实验」那条路，本模板是「按模板自建」，
  `source/library/experiments.json` 里 `mechanics-projectile` 的档位是 `template_connected`——别把边界读成缺陷，也别把它读成用了资源。
