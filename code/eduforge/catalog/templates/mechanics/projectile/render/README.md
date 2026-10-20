# render — 单文件页面骨架与运行时

**职责**：提供抛体实验单文件 HTML 的静态骨架、页面运行时与样式。这一层**不含物理公式**：物理来自 [`../../../../../tools/labkit/lib/projectile-core.mjs`](../../../../../tools/labkit/lib/projectile-core.mjs)，渲染器只负责把模板、数据、引擎与运行时拼成一个文件。

## 1. 文件

| 文件 | 行数 | 作用 |
|---|---|---|
| [`template.html`](template.html) | 62 | 骨架：标题 / canvas / 参数区 / 读数区 / 教学说明 / 页脚；六个占位符 |
| [`runtime.js`](runtime.js) | 520 | 读 `window.__LAB_DATA__`，预计算轨迹、画 canvas、绑定滑块、暴露 `window.__LAB` / `__RESULT` / `__STATUS` |
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
  - `window.__LAB.setParams({v0, h0, angle_deg?, angles_deg?})` → 重新计算并返回 `__RESULT`
- **读数显示**：实测 / 解析 / 偏差三行；偏差超过 1% 标红；互补角额外显示 `R(θ₁)/R(θ₂)` 与理论值 1 的对比。

## 4. 坑与纪律

1. **不要在这里写公式**。页面上的虚线来自 `core.analytic()`；把公式抄进 runtime 会造成 L2 与页面两套实现。
2. **不要引入外部资源**。MathJax、字体、图标都会破坏 `file://` 离线直开；公式用纯文本 + Unicode 下标。
3. **CSP 很严**：`default-src 'none'` 会拦掉任何 `fetch`/`XHR`/外部脚本。新增功能先确认不需要网络；需要 `eval` 的库不能进这个页面。
4. **动画不改物理**：`requestAnimationFrame` 只推进 `state.time`，不得在其中调用 `Engine.update`。
5. **改模板后必跑**：`node code/eduforge/tools/labkit/selftest.mjs`；它会重新渲染并用真 Chromium 以 `file://` 验证。
