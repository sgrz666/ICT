# 照相机成像原理实验模板 (`catalog/templates/optics/camera-principle/`)

## 1. 职责
提供照相机成像原理实验的权威模板资产（`manifest.yaml`、原生场景 `native.json`、教案 `lesson.md`）。从官方案例库真实场景抽取并规范化命名实体，供教师在 EduForge AI 教学定制工坊中进行相机镜头调焦和感光成像的二次教学创作。

## 2. 内容
- [`manifest.yaml`](manifest.yaml)：声明 `template_id: optics.camera_principle`，换算系数 `units_per_unit: 10`，控制量 `lens_1.focal_length_cm`（5~30cm）与 `object_1.object_distance_cm`（35~150cm），配置 CMOS 传感器面 `sensor_1`（Detector）。
- [`native.json`](native.json)：抽取自 upstream 原版案例，包含 `lens_1`（`IdealLens`, `focalLength: 155`）、`object_1`（`PointSource`）、`sensor_1`（`Detector`）、光圈 `aperture_1`、遮光器与光路标尺。
- [`lesson.md`](lesson.md)：教学目标、物理原理与照相机物距大于二倍焦距倒立缩小实像规律。

## 3. 与上下层的关系
- **上层引用**：[`../../README.md`](../../README.md) 与 [`../README.md`](../README.md) 登记本模板；`code/eduforge/infrastructure/catalog.py` 动态扫描并提供给 API `/api/v1/templates` 与工坊。
- **验证对照**：由 `eduforge.validation.scientific.optics::thin_lens_reference` 进行凸透镜理论对照，由 Engine Host 进行真实光追仿真。

## 4. 已知的坑与纪律
- 原版场景中包含光阑、遮光器等多种元件，物理验证策略中已声明被动元件白名单，不得误报 thick lens 导致无法对照；
- 换算系数固定为 10，景物距离初始值 97.7cm 满足 $u > 2f$。
