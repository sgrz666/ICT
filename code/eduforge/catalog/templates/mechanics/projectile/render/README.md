# render — 单文件页面骨架与运行时

**职责**：提供抛体实验单文件 HTML 的静态骨架、页面运行时与样式。这一层**不含物理公式**：物理来自 [`../../../../../tools/labkit/lib/projectile-core.mjs`](../../../../../tools/labkit/lib/projectile-core.mjs)，渲染器只负责把模板、数据、引擎与运行时拼成一个文件。

## 1. 文件

| 文件 | 行数 | 作用 |
|---|---|---|
| [`template.html`](template.html) | 62 | 骨架：标题 / canvas / 参数区 / 读数区 / 教学说明 / 页脚；六个占位符 |
| [`runtime.js`](runtime.js) | 580 | 读 `window.__LAB_DATA__`，预计算轨迹、画 canvas、绑定滑块、暴露 `window.__LAB` / `__RESULT` / `__STATUS` |
| [`style.css`](style.css) | 229 | 内联样式；浅色、无外部字体、响应式两栏 |

## 2. 占位符（由 `render-single-file.mjs` 替换）

| 占位符 | 内容 |
|---|---|
| `__TITLE__` | `模板标题 · 配方标题`（HTML 转义） |
| `__STYLE__` | `style.css` 全文 |
| `__DATA__` | canonical JSON：meta / design / recipe / decision / engine / render / acceptance / evidence（`<` 转 `\u003c`） |
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
  比对**浏览器里真实渲染出来的**滑块/开关/按钮（三条判据，oblique45 现 26/26）——
  声明与页面一旦不符，红的就是产物判据，而不是等到有人照着旧清单放行文案。
