# skills/ — 智能体领域技能与定制规范

本目录存放交付给定制智能体（Deep Agent / Coding Agent）的可信领域规范与代码交付约束。

## 1. 职责

代码定制智能体在受限沙箱中运行，不拥有外部网络访问权限，不持有真实模型密钥。本目录下的 `SKILL.md` 文件为智能体提供各学科引擎的边界约束、数据结构规范、坐标系与单位换算约定，确保交付的代码直接符合编译与门禁验证标准。

## 2. 内容

三个子目录各只含一份 `SKILL.md`（该技能的唯一文件；不含其它附件）：

| 技能目录 | 行数 | 状态 | 内容 |
|---|---|---|---|
| [`ray-optics-customization/`](ray-optics-customization/SKILL.md) | 27 | **已启用** | Ray Optics 几何光学实验定制规范：限定交付 `src/lesson.ts` 与 `src/controls.ts`，强制 `name` 绑定对象身份、禁止非法 key 注入、严格按 `units_per_unit: 10` 换算教学单位 |
| [`mechanics-customization/`](mechanics-customization/SKILL.md) | 13 | 保留位（切片 9） | myPhysicsLab 经典力学实验定制规范 |
| [`circuit-customization/`](circuit-customization/SKILL.md) | 13 | 保留位（切片 9） | CircuitJS 电路实验定制规范 |

## 3. 与上下层的关系

- **上游依据**：依据 [`../catalog/templates/`](../catalog/templates/) 的实验模板清单与 [`../catalog/engines/`](../catalog/engines/) 引擎元数据提炼；
- **下游消费**：2026-10-16 起由 [`../python/src/eduforge/agent/deepagents_runtime.py`](../python/src/eduforge/agent/README.md) 的 `load_skill_text()` 读入并拼进主 Agent 的系统提示词（`SKILL_PATH` 指向 `ray-optics-customization/SKILL.md`；`test_deepagents_runtime.py` 一侧有对应断言）。此前本文件**零代码读取**——旧 README 声称由 `coding/deep_agent.py` 与 `agent/retrieval.py` 注入沙箱，代码里并不存在这条路径，那两个模块都不读 skills；`deep_agent.py` 至今仍是未接入状态。

## 4. 已知的坑与纪律

- 技能文件只描述领域约束与交付标准，不包含外部模型密钥或动态状态；
- 修改技能规范需与科学验证参考（[`../python/src/eduforge/validation/scientific/`](../python/src/eduforge/validation/scientific/)）保持严格物理自洽。
