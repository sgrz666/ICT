# circuit — 直流电路核心（MNA）

**职责**：直流电阻网络的 MNA 求解、L1 校验、L2 对账（含 CircuitJS1 外部交叉验证）与单文件渲染。纯 JS，无第三方运行时依赖。

## 内容

| 文件 | 作用 |
|---|---|
| [`core.mjs`](core.mjs) | 改进节点法求解器：`solveDC` / `buildOhm` / `buildSeries` / `buildParallel` / `measureFromSolution`；解析参考 `analyticOhm / analyticSeries / analyticParallel` |
| [`check.mjs`](check.mjs) | L1：配方、电压/电阻量程、总电流上限、理由质量 |
| [`simulate.mjs`](simulate.mjs) | L2：MNA vs 解析式；读 `source/library/circuit-lab-evidence.json` 做 CircuitJS1 交叉验证 |
| [`render.mjs`](render.mjs) | 单文件 HTML：内联 `core.mjs` + `render/runtime.js`（无外部引擎），同时写 `.html.manifest.json` 绑定设计、HTML 与证据 |

## 为什么是 MNA

CircuitJS1 的 GWT 产物是 15 MB 多文件站点、需要同源加载，无法做成单文件 HTML。MNA 对线性 DC 电阻网络是精确解，单文件 27 KB；CircuitJS1 的实测证据保留为外部交叉验证，不进入运行时。详细取舍见 [`../../../catalog/templates/circuits/ohms-law/README.md`](../../../catalog/templates/circuits/ohms-law/README.md)。

## 口径与实测

- 节点 0 = 地；未知量 = 节点电压 + 电压源电流；高斯消元部分主元。
- 实测：欧姆 3 个阻值、串联 I/U1/U2、并联 I1/I2/I/Req，MNA 与解析式偏差 0；CircuitJS1 交叉验证 8/8 pass（相对误差 ≤1e-6）。
- 只覆盖线性 DC 电阻网络；RC/交流/非线性元件不在本轮范围。

## 纪律

- 拓扑改动只动 `core.mjs` 的 `build*`；不要在每个配方里复制一套方程。
- 若 MNA 与解析式不一致，先查节点编号与接地，不要放宽容差。
- CircuitJS1 证据里 `R` 字段是电压差（历史命名），交叉验证按 `i`/`v` 取数。
- 渲染与 L3 共用 [`../lib/artifact.mjs`](../lib/artifact.mjs)；复制运行资源时保留 `source/library/circuit-lab-evidence.json` 才有历史 CircuitJS1 交叉验证，缺失时只报告 `available: false`。2026-10-31 真实核心自检及 HTML/证据篡改回归通过，见 [`../artifact-integrity.test.mjs`](../artifact-integrity.test.mjs)。
