# pendulum — 单摆周期与简谐振动（LabKit 路径）

**职责**：把「摆长与周期」「振幅与小角度近似」两个配方做成可被 Agent 选择、可物理对账、可渲染成单文件 HTML 的模板。**走 LabKit 文件级链路，不经过 engine-host 适配器，也不在教师端模板库里出现**；EduForge 主链路的 `EngineId` 仍是 `ray_optics / myphysicslab / circuitjs`。

## 1. 状态

| 项 | 实测 |
|---|---|
| L1 参数校验 | 两个配方默认扫描点全过 |
| L2 物理对账 | 2/2 pass；L0.5/L1/L2 周期偏差 0.008–0.038%，T(2.0)/T(0.5)=2.0005（要求 2±1%）；30° 相对椭圆积分精确解 0.37% |
| L3 单文件实测 | 2/2 pass；零网络、canvas 0.75–0.85%、改参有效、console error 0、读数误差 0 |
| 产物体积 | 107.7 KB（内联 matter-js 0.20.0） |
| 复现命令 | `node code/eduforge/tools/labkit/selftest.mjs`（7 个配方全跑，含本模板 2 个） |
| 教师端 / engine-host | **未接入** |

## 2. 文件

| 文件 | 作用 |
|---|---|
| [`manifest.yaml`](manifest.yaml) | catalog 兼容扁平清单：`template_id: mechanics.pendulum`、`engine_id: matter_js`、两个 control（length_m / angle0_deg）、`status: verified` |
| [`recipes.json`](recipes.json) | 两个配方、决策量程、验收容差、渲染配置 |
| [`native.json`](native.json) | 场景骨架：`RigidBody`，length 1.0 m、angle0 5° |
| [`lesson.md`](lesson.md) | 两个配方的实验目的 / 步骤 / 观察要点 / 误区 |
| [`render/`](render/README.md) | 单文件骨架、运行时、样式 |

## 3. 配方

| id | 扫描点 | 验收指标（容差） | 教学意图 |
|---|---|---|---|
| `period-length` | L=0.5/1/2 m，θ₀=5° | T 1% / 比值 1% | 周期与摆长平方根成正比；L 翻 4 倍，T 变 2 倍 |
| `angle-correction` | L=1 m，θ₀=5/10/30° | T 1%（对照椭圆积分精确解） | 小角度近似只在 θ₀ 小时成立；30° 时周期比公式预测长约 1.7% |

决策量程：`L 0.2–3.0 m`、`θ₀ 1–30°`、周期上限 6 s。多场景配方是**固定扫描**：模型传的 `params` 会被忽略（只作为页面初值的参考），页面内仍可拖动摆长/初始角。

## 4. 为什么是 matter-js，不是 myPhysicsLab

- myPhysicsLab 的 `PendulumSim` 无头精度更高（2.00835 vs 2.00834），但浏览器端要 esbuild + 多模块图，单文件交付不成立。
- matter-js 实测：5° 误差 0.04%、10° 0.15%、30° 相对椭圆积分精确解 0.49%，满足本项目「θ₀≤10° 用 1%、30° 按椭圆积分修正 0.5%」的口径。
- **测量口径**：从 +θ₀ 释放，角度过零（负→正）为周期边界；取第 2 个之后的间隔均值，避开起步半拍。

## 5. 关系

- 核心库：[`../../../../tools/labkit/pendulum/`](../../../../tools/labkit/pendulum/README.md)（core / check / simulate / render）。
- dsh 工具：`experiment_recipes` 无参调用会列出本模板；`experiment_build` 传 `template_id: mechanics.pendulum`。
- 历史物理证据：[`../../../../../../source/upstream/probe-myphysicslab.json`](../../../../../../source/upstream/probe-myphysicslab.json)（myPhysicsLab 无头 2.00835 s，作为另一条引擎线的记录；不参与本模板运行时）。
- 上级分组：[`../README.md`](../README.md)；模式说明：[`../../README.md`](../../README.md)。

## 6. 已知的坑与纪律

1. **`frictionAir` 必须为 0**；阻尼只作为后续可选参数，默认 0。
2. **matter-js 的约束有微小拉伸**（实测 ~4e-5 m），不足以影响周期，但不要把「摆长严格不变」写成断言。
3. **多场景扫描不接受逐场景改参**；`params` 会被忽略并给出 warning，页面内可自由拖动。
4. **30° 不要用小角度公式做判据**；必须用 `4√(L/g)·K(sin(θ₀/2))`（AGM 实现）。
5. **catalog.py 仍是手写逐行解析器**：`recipes.json` 是旁路，字段顺序固定为 `controls → views → exports → routes`。
