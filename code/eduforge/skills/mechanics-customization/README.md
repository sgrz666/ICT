# mechanics-customization — 力学定制技能（保留位，零代码读取）

**职责**：为第 7～8 周切片 9 接入 myPhysicsLab 预留的领域规范占位文件。**当前没有任何代码读取它**——它既不在 `SKILL_PATH` 指向的路径上，也没有注入提示词的路径。

## 内容（逐文件）

| 文件 | 行数 | 结构 |
|---|---|---|
| `SKILL.md` | 13 | frontmatter（`name: mechanics-customization`，description 标注「第 7～8 周预留」）+ 一节**核心约定**：实验体系采用 SI 单位制（m、s、kg、rad）；交付文件同为 `src/lesson.ts` 与 `src/controls.ts`；以能量守恒定律作为门禁物理验证基准 |

本目录只含这一份 `SKILL.md`。

## 与上下层的关系

- 配套模板：[`../../catalog/templates/mechanics/pendulum/`](../../catalog/templates/mechanics/pendulum/README.md)（同为 `status: pending_slice_9`，只有 manifest、无 `native.json`）。
- 配套引擎描述：[`../../catalog/engines/`](../../catalog/engines/README.md) 的 `myphysicslab.yaml`（deferred）。
- 参考式桩：[`../../python/src/eduforge/validation/scientific/`](../../python/src/eduforge/validation/README.md) 的 `mechanics.py`（单摆周期，未接入运行时）。
- 分组层说明：[`../README.md`](../README.md)；已接通的那条线见 [`../ray-optics-customization/README.md`](../ray-optics-customization/README.md)。

## 已知的坑与纪律

- **文件在位 ≠ 已生效**：写在这里的约定不会进任何提示词、也不被任何测试断言。把它接进 `SKILL_PATH` 之前，任何文档不得声称「力学定制已受领域规范约束」。
- 接入方式（切片 9 要做的事）：`SKILL_PATH` 现在是硬编码的单个路径，多引擎需要改成按模板/引擎选择——不要为了省事往 `build_system_prompt()` 里塞两份全文。
- SI 单位制与光学的「无量纲场景像素 + `units_per_unit`」不是同一套约定；能量守恒门禁的判据形式也需要另行设计（光学用的是 RMS 光斑半径 + 功率下限，弃用 peak_share）。
- 目录名用复数 `mechanics-`，而电路那条线用单数 `circuit-`——引用路径以磁盘名为准，别按构词法猜。
