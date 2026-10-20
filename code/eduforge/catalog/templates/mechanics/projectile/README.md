# projectile — 抛体运动模板（LabKit 路径）

**职责**：把「平抛 / 斜抛 45° / 互补角」三个配方做成可被 Agent 选择、可被物理对账、可被渲染成单文件 HTML 的模板。**本模板走 LabKit 文件级链路，不经过 engine-host 适配器，也不在教师端模板库里出现**——它还没有并入 EduForge 主链路（`EngineId` 仍是 `ray_optics / myphysicslab / circuitjs`，`policies.build_report` 仍只认光学）。

## 1. 状态

| 项 | 实测 |
|---|---|
| L1 参数校验 | 三个配方默认参数全过（`experiment_validate`） |
| L2 物理对账 | 3/3 pass；最大偏差 0.41%（容差 1%）；阻力对照组 391.2×（要求 >5×） |
| L3 单文件实测 | 3/3 pass；零网络、canvas 3.0–3.5%、改参有效、console error 0、读数误差 ≤1.4e-7 |
| 产物体积 | 113.2–113.6 KB（内联 matter-js 0.20.0） |
| 复现命令 | `node code/eduforge/tools/labkit/selftest.mjs` |
| 教师端 / engine-host | **未接入**，不要写成「已支持」 |

## 2. 文件

| 文件 | 作用 |
|---|---|
| [`manifest.yaml`](manifest.yaml) | catalog 兼容的**扁平**清单：`template_id: mechanics.projectile`、`engine_id: matter_js`、三个 control（v0 / angle_deg / h0）、`status: verified` |
| [`recipes.json`](recipes.json) | 配方、决策量程、验收容差、渲染配置；**嵌套结构放这里，不放 manifest** |
| [`native.json`](native.json) | 场景骨架：`Circle`，`frictionAir: 0`（默认 0.01 会让抛体变成有阻力运动） |
| [`lesson.md`](lesson.md) | 三个配方的实验目的 / 步骤 / 观察要点 / 常见误区 |
| [`render/`](render/README.md) | 单文件骨架、页面运行时、样式 |

## 3. 配方

| id | 默认参数 | 验收指标（容差） | 教学意图 |
|---|---|---|---|
| `horizontal` | `v0=15, angle_deg=0, h0=20` | T 1% / R 1% / apex_y 0.5% | 飞行时间只由高度决定，射程与 v0 成正比 |
| `oblique45` | `v0=20, angle_deg=45, h0=0` | T 1% / R 1% / H 1% | 45° 时 `sin2θ=1`，射程最大 |
| `complementary` | `v0=20, h0=0, angles_deg=[30,60]` | `ratio_R` 1% | 互补角 `sin2θ` 相同，射程相等 |

决策量程：`v0 5..40 m/s`、`h0 0..30 m`、斜抛角 `15..75°`；画面约束 `R≤120 m`、`T≤8 s`、`H≤45 m`。超限时 L1 返回 `feasible_hint`（例如「θ=60° 时 v0 ≤ 34.2 才能让 R ≤ 120 m」）。

## 4. 契约与坑

1. **`catalog.py` 是手写逐行解析器**：`controls` 必须是扁平 `key: value`，`views` 的停止键是 `exports:`。所以字段顺序固定为 `controls → views → exports → routes`；嵌套的 recipes / acceptance / render 一律放 `recipes.json`，否则会被当成 control 项解析坏。
2. **`status: verified` 只影响 catalog 的 pending 判断**（`startswith("pending")` 才返回空模板）；它**不**代表已接入教师端。
3. **`engine_id: matter_js` 目前只被 LabKit 使用**；`domain/contracts.py` 的 `EngineId` Literal 还没有它，接入主链路时要加。
4. **matter-js 的阻力模型不是二次阻力**：`frictionAir` 是每个步长对速度的线性衰减，不是 `½CρAv²` 那种二次阻力。2026-10-20 起它作为第四个控件开放给教师与 Agent（`manifest.yaml` 的 `friction_air`，量程 0~0.03，**默认 0**），但页面上必须按「线性阻尼」解释，不得写成"真实空气阻力"；默认 0 是有意的——L2/L3 的「引擎 vs 解析式」对照只在无阻力时成立，默认值一动，历史证据就作废。
5. **不引用 gallery 场景**：本模板的 `native.json` 只有一个质点，轨迹完全由参数决定；没有上游场景的球差/色散一类物理偏差。

## 5. 关系

- 核心库：[`../../../../tools/labkit/`](../../../../tools/labkit/README.md)（check / simulate / render / verify）。
- dsh 工具：[`../../../../../../deep-agent/local-tools/dsh-labkit/`](../../../../../../deep-agent/local-tools/dsh-labkit/README.md) 的 `experiment_recipes` 直接读本目录的 `recipes.json`。
- 历史物理证据：[`../../../../../../source/library/projectile-lab-evidence.json`](../../../../../../source/library/projectile-lab-evidence.json)（5/5，matter-js，重构后逐字段一致）。
- 上级分组：[`../README.md`](../README.md)；模式说明：[`../../README.md`](../../README.md)。
