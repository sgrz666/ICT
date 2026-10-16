# skills/ — 智能体领域技能与定制规范

本目录存放交付给定制智能体（Deep Agent / Coding Agent）的可信领域规范与代码交付约束。

## 1. 职责

代码定制智能体在受限沙箱中运行，不拥有外部网络访问权限，不持有真实模型密钥。本目录下的 `SKILL.md` 文件为智能体提供各学科引擎的边界约束、数据结构规范、坐标系与单位换算约定，确保交付的代码直接符合编译与门禁验证标准。

## 2. 内容

- [`ray-optics-customization/SKILL.md`](ray-optics-customization/SKILL.md)：Ray Optics 几何光学实验定制规范。限定交付 `src/lesson.ts` 与 `src/controls.ts`，强调必须使用 `name` 绑定对象身份、禁止非法 key 注入、严格按 `units_per_unit: 10` 换算教学单位；
- [`mechanics-customization/SKILL.md`](mechanics-customization/SKILL.md)：myPhysicsLab 经典力学实验定制规范（第 7～8 周切片 9 保留位）；
- [`circuit-customization/SKILL.md`](circuit-customization/SKILL.md)：CircuitJS 电路实验定制规范（第 7～8 周切片 9 保留位）。

## 3. 与上下层的关系

- **上游依据**：依据 [`../catalog/templates/`](../catalog/templates/) 的实验模板清单与 [`../catalog/engines/`](../catalog/engines/) 引擎元数据提炼；
- **下游消费**：由 [`../python/src/eduforge/coding/deep_agent.py`](../python/src/eduforge/coding/deep_agent.py) 与 [`../python/src/eduforge/agent/retrieval.py`](../python/src/eduforge/agent/retrieval.py) 作为系统提示词与检索证据注入执行沙箱。

## 4. 已知的坑与纪律

- 技能文件只描述领域约束与交付标准，不包含外部模型密钥或动态状态；
- 修改技能规范需与科学验证参考（[`../python/src/eduforge/validation/scientific/`](../python/src/eduforge/validation/scientific/)）保持严格物理自洽。
