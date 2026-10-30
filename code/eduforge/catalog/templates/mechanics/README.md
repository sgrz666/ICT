# mechanics — 力学学科模板分组

**职责**：`templates/` 下的力学分组层。当前两个模板都走 **LabKit 文件级链路**（单文件 HTML），不是 EduForge 主链路：

- `projectile/`：抛体运动，`engine_id: matter_js`，三配方（平抛 / 斜抛 45° / 互补角）已通过 L1/L2/L3 实测。
- `pendulum/`：单摆周期，`engine_id: matter_js`，两配方（摆长-周期 / 振幅修正）已通过 L1/L2/L3 实测；myPhysicsLab 只保留为历史无头证据，不参与运行时。

两者都未接入 engine-host、experiment_tools 与教师端。

## 内容

| 条目 | 类型 | 状态 |
|---|---|---|
| [`projectile/`](projectile/README.md) | 模板实例目录 | 抛体运动（`template_id: mechanics.projectile`，`engine_id: matter_js`）。`manifest.yaml` + `recipes.json` + `native.json` + `lesson.md` + `render/` 齐全；LabKit 三配方 3/3 pass（L2 最大偏差 0.41%，L3 零网络），产物约 113–118 KB。**EduForge 主链路未接** |
| [`pendulum/`](pendulum/README.md) | 模板实例目录 | 单摆周期与简谐振动（`template_id: mechanics.pendulum`，`engine_id: matter_js`）。`manifest.yaml` + `recipes.json` + `native.json` + `lesson.md` + `render/` 齐全；两配方 2/2 pass（周期偏差 0.008–0.038%，30° 相对精确解 0.37%，L3 零网络），产物约 108 KB。**EduForge 主链路未接** |


本目录自身不放数据文件。

## 与上下层的关系

- 上一级：[`../README.md`](../README.md) 的三件套模式（manifest / native / lesson）；本目录两个模板都齐备，并额外带 `recipes.json` 与 `render/`（LabKit 旁路）。
- 引擎侧：[`../../engines/`](../../engines/README.md) 的 `myphysicslab.yaml` 仍是 EduForge 主链路的引擎描述；单摆模板的运行时已改用 matter-js，myPhysicsLab 只保留为历史无头证据。
- 参考式桩：[`../../../python/src/eduforge/validation/scientific/`](../../../python/src/eduforge/validation/README.md) 的 `mechanics.py`（单摆周期，未接入运行时）。
- 领域规范：[`../../../skills/mechanics-customization/SKILL.md`](../../../skills/mechanics-customization/README.md)（仍是切片 9 保留位）。

## 已知的坑与纪律

- **目录在位 ≠ 学科可用**：任何文档不得写成「已支持力学实验」。EduForge 主链路的启用顺序仍是 myPhysicsLab 适配器 → `native.json` → 验证参考式接入；LabKit 是另一条文件级链路，不能拿来证明主链路已通。
- **projectile / pendulum 都只在 LabKit 口径下成立**：它们绕开 engine-host 与 `experiment_tools`，用 matter-js 直接步进 + 单文件渲染；`EngineId` Literal 还没有 `matter_js`。写「已支持」时必须带上「LabKit 路径」，不能暗示教师端已能选到这些模板。
- 力学走 SI 单位制，与光学的「无量纲场景像素 + `units_per_unit`」不是同一套换算约定——别把光学的单位换算纪律直接搬过来。
- 单摆的 30° 判据必须用椭圆积分精确解；小角度公式只作教学对照。
