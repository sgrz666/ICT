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
| [`recipes.json`](recipes.json) | 配方、决策量程、验收容差、渲染配置；**嵌套结构放这里，不放 manifest**；每条配方还声明 `affordances`（`buttons` / `sliders` / `toggles` / `comparison` / `capabilities`），见第 4 节第 6 条 |
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
6. **`affordances` 是「文案能承诺什么」的唯一声明处**。三条配方各自声明页面上真有什么：`horizontal` = 按钮 `暂停 / 重播` + 滑块 `初速度 / 初始高度 / 空气阻力`、无开关、`comparison: false`；`oblique45` 多一个 `发射角` 滑块与 `叠加` 开关、`comparison: true`；`complementary` 的开关是 `保持互补`、`comparison: true`。L1（`tools/labkit/lib/check.mjs`）会拿 `student_task` 的承诺去比对这份声明，不符就报 `TEXT_AFFORDANCE`——这条门是因为一句「点击发射或重放…对比其他角度」的文案一路绿灯进了交付件才加的。改控件名 / 加控件 / 去掉对照，都要同轮改这里的声明，否则 Agent 写的文案会被 L1 拦住（那正是期望行为）或者放走假承诺。声明还会经 `render-single-file.mjs` 写进产物 `DATA`，探针比对的是**产物里的声明 vs 真实渲染**。
7. **`capabilities` 不是一句可以许愿的话术**：它声明的是「这个页面能做成什么实验」（`调参 / 播放控制 / 记录数据 / 角度对照 / 阻力对照`），而每一项都必须由 [`../../../../tools/labkit/drag-control-probe.mjs`](../../../../tools/labkit/drag-control-probe.mjs) 里**已经跑过的一次真实交互**反推出来——`记录数据` 要「记录本次」真写进表且第 1 行读数等于页面读数、清空后回到空态提示；`角度对照` 要勾上开关后场景数到 3 且 id 不重复；`阻力对照` 要拖了阻力后射程显著变小且 `ratio_vs_clean` 有值。探针双向报错：声明了却推不出来（许愿式声明）和页面有却没声明（漏报）各算一条判据。这条纪律加进来是因为控件名单单只有名字，「有滑块」不等于「拖了会动」——2026-10-20 实测 `31/31 pass`（产物 `output/eduforge/candidates/labkit/oblique45/oblique45-range-max.html`）。

## 5. 关系

- 核心库：[`../../../../tools/labkit/`](../../../../tools/labkit/README.md)（check / simulate / render / verify）。
- dsh 工具：[`../../../../../../deep-agent/local-tools/dsh-labkit/`](../../../../../../deep-agent/local-tools/dsh-labkit/README.md) 的 `experiment_recipes` 直接读本目录的 `recipes.json`。
- 历史物理证据：[`../../../../../../source/library/projectile-lab-evidence.json`](../../../../../../source/library/projectile-lab-evidence.json)（5/5，matter-js，重构后逐字段一致）。
- 上级分组：[`../README.md`](../README.md)；模式说明：[`../../README.md`](../../README.md)。
