# scientific — 独立科学参考式

**职责**：用与上游仿真器**完全独立**的解析公式做对照计算。"独立"是方法学要求——公式手写、不 import 上游任何代码，否则"同一实现算两遍"不构成验证。validating 阶段拿上游仿真结果与本目录公式的预测值对照，差值进 [`../policies.py`](../policies.py) 的检查项。

## 内容（逐文件）

| 文件 | 行数 | 职责 | 关键符号 |
|---|---|---|---|
| `optics.py` | 25 | 薄透镜成像参考计算：v = fu/(u−f)，区分实像/虚像/无穷远边界。**唯一在链路上工作的参考式** | `thin_lens_reference` |
| `mechanics.py` | 16 | 单摆周期计算**桩**（为 mechanics 模板预留）；仅测试可达 | `calculate_pendulum_period` |
| `circuits.py` | 14 | 欧姆定律计算**桩**（为 circuits 模板预留）；仅测试可达 | `calculate_ohms_law` |

## 与上下层的关系

- 被谁用：[`../policies.py`](../policies.py) 的 `build_report`（validating 阶段）；测试 [`../../../../../tests/python/test_gate2_protocol.py`](../../../../../tests/python/test_gate2_protocol.py)。
- 对应模板：optics → [`../../../../../catalog/templates/`](../../../../../catalog/templates/README.md)（已接通）；mechanics/circuits 的模板仍是 `pending_slice_9` 状态——本目录的两个桩与之同步等待。

## 已知的坑与纪律

- **边界语义**：u=f（无穷远）与 u<f（虚像）是物理分界，不是数值噪声——改 `optics.py` 前先看它的分支与被哪个检查项消费。
- 桩文件不可当"已实现"引用；新建引擎参考式时按 optics.py 的模式（纯函数、零依赖、只算数）。
- 参考式与上游仿真**不得共用常量**（如焦距换算系数），否则独立性被破坏。
