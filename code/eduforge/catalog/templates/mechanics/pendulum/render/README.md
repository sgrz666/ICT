# render — 单摆单文件页面

**职责**：单摆实验的单文件 HTML 骨架、运行时与样式。物理来自 [`../../../../../tools/labkit/pendulum/core.mjs`](../../../../../tools/labkit/pendulum/core.mjs)，这一层不写公式。

## 文件

| 文件 | 作用 |
|---|---|
| [`template.html`](template.html) | 骨架：标题 / canvas / 参数 / 当前读数 / 配方扫描 / 教学说明 / 页脚 |
| [`runtime.js`](runtime.js) | 读 `window.__LAB_DATA__`，预计算摆动、画摆球与角度、绑定摆长/初始角滑块、暴露 `__LAB` / `__RESULT` / `__STATUS` |
| [`style.css`](style.css) | 内联样式；复用抛体页面的两栏布局 |

## 页面行为

- 初始状态取 evidence 第一个场景的参数（period-length 是 L=0.5、θ=5）。
- `window.__RESULT.scenarios[0]` 是**当前**交互状态，id 固定为配方的第一个场景 id（L0.5 / deg5），用于 L3 读数对账。
- `window.__LAB.setParams({length_m, angle0_deg})` 改参并重算；L3 用 `length_m ×1.25` 探针。
- 「配方扫描」表独立计算配方全部扫描点，供学生对比，不参与 `__RESULT`。
- 画布按当前摆长取景（`max(1.0, L×1.25)`），L 变化时整体缩放。

## 纪律

- 不在 runtime 里写周期公式；全部走 `core.swing()` 与 `pendulumAnalytic()`。
- 不使用外部字体/图片；CSP `default-src 'none'`。
- 改模板后跑 `node code/eduforge/tools/labkit/selftest.mjs`（含单摆 2 配方）。
