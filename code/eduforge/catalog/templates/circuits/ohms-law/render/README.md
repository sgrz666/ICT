# render — 直流电路单文件页面

**职责**：电路实验的单文件 HTML 骨架、运行时与样式。求解来自 [`../../../../../tools/labkit/circuit/core.mjs`](../../../../../tools/labkit/circuit/core.mjs)（MNA），这一层不写方程。

## 文件

| 文件 | 作用 |
|---|---|
| [`template.html`](template.html) | 骨架：标题 / canvas / 参数 / 读数 / 教学说明 / 页脚；无外部脚本 |
| [`runtime.js`](runtime.js) | 读 `window.__LAB_DATA__`，按配方画电池/电阻/导线，绑定电压/电阻滑块，调用 `solveDC` 与解析式，暴露 `__LAB` / `__RESULT` / `__STATUS` |
| [`style.css`](style.css) | 内联样式；复用抛体页面的两栏布局 |

## 页面行为

- 三种拓扑：欧姆（单电阻）、串联（R1+R2）、并联（R1∥R2），由 `recipe.id` 决定画法与读数项。
- `window.__RESULT.scenarios[0]` 是当前状态，id 固定 `main`；L3 用 `resistance_ohm ×1.5` 探针，比较 `I`。
- `window.__LAB.setParams({voltage_v, resistance_ohm, r2_ohm})` 改参并重算；`r2_ohm` 只在串/并联生效。
- 读数表按 `recipe.metric_keys` 显示实测/解析/偏差；MNA 与解析式在双精度下一致。

## 纪律

- 不在 runtime 里写电路方程；全部走 `solveDC` 与 `analytic*`。
- 电路图是示意画法，导线坐标可调，但**拓扑必须与 `build*` 一致**；改图时同步改配方。
- 不使用外部字体/图片；CSP `default-src 'none'`。
- 改模板后跑 `node code/eduforge/tools/labkit/selftest.mjs`（含电路 3 配方）。
