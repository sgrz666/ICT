# 凹透镜发散与成像实验模板 (`catalog/templates/optics/concave-lens/`)

## 1. 职责
提供凹透镜发散与成像实验的权威模板资产（`manifest.yaml`、原生场景 `native.json`、教案 `lesson.md`）。供教师在 EduForge AI 教学定制工坊中进行凹透镜发散光路和虚像规律的二次教学创作。

## 2. 内容
- [`manifest.yaml`](manifest.yaml)：声明 `template_id: optics.concave_lens`，换算系数 `units_per_unit: 10`，控制量 `lens_1.focal_length_cm`（-50~-5cm）与 `object_1.object_distance_cm`（10~60cm），配置 3 块探测屏（10cm/20cm/30cm）。
- [`native.json`](native.json)：Ray Optics 原生场景 JSON，固定命名实体 `lens_1`（`IdealLens`, `focalLength: -100`）、`object_1`（`PointSource`）与探测屏。
- [`lesson.md`](lesson.md)：教学目标、物理原理与薄凹透镜高斯成像公式解析。

## 3. 与上下层的关系
- **上层引用**：[`../../README.md`](../../README.md) 与 [`../README.md`](../README.md) 登记本模板；`code/eduforge/infrastructure/catalog.py` 动态扫描并提供给 API `/api/v1/templates` 与工坊。
- **验证对照**：由 `eduforge.validation.scientific.optics::thin_lens_reference` 进行薄透镜独立理论对照，由 Engine Host 进行真实光追仿真。

## 4. 已知的坑与纪律
- 凹透镜焦距必须为负值（上游 `IdealLens.focalLength < 0`），不得传入非负数；
- 换算系数固定为 10，与 lengthScale: 1 保持自洽。
