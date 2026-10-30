# pendulum — 单摆核心（matter-js）

**职责**：单摆的物理内核、L1 校验、L2 对账与单文件渲染。纯 JS，Node 与浏览器共用同一份 `core.mjs`。

## 内容

| 文件 | 作用 |
|---|---|
| [`core.mjs`](core.mjs) | `createPendulumCore(Matter)` → `calibrate / swing`；另有 `pendulumAnalytic()`（小角度 + AGM 椭圆积分精确解） |
| [`check.mjs`](check.mjs) | L1：配方存在、扫描点量程、理由质量；多场景配方忽略 `params` 并给 warning |
| [`simulate.mjs`](simulate.mjs) | L2：matter-js 摆角过零测周期，对照 `T0` 与 `Texact`；写 evidence |
| [`render.mjs`](render.mjs) | 单文件 HTML：内联 matter-js + `core.mjs` + `render/runtime.js` |

## 口径

- `gravity=9.8`、`gravity.scale=1e-6`、`dt=1/240`、`frictionAir=0`、约束 `stiffness=1, damping=0`。
- 从 `+θ0` 释放，角度过零（负→正）为周期边界；取第 2 个之后的间隔均值。
- 实测：L=0.5/1/2 m、θ0=5° 时周期偏差 0.008–0.038%；30° 相对精确解 0.37%；T(2.0)/T(0.5)=2.0005。

## 纪律

- 物理只写 `core.mjs`；`simulate.mjs` 只调用它，页面运行时也只调用它。
- 小角度公式只用于教学对照，判据必须用精确解；30° 时两者差约 1.7%。
- 约束长度有 ~4e-5 m 的拉伸，不能把「摆长严格不变」当断言。
