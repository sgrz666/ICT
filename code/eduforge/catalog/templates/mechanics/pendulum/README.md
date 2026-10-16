# pendulum — 单摆模板（pending，引擎未接通）

**职责**：mechanics 方向教学模板的**保留位**：单摆周期与简谐振动。上游引擎 myPhysicsLab 为 deferred（本轮不进首批），模板声明完整但未接通。

## 内容（逐文件）

| 文件 | 行数 | 职责 |
|---|---|---|
| `manifest.yaml` | 23 | 模板清单：`template_id: mechanics.pendulum`、`engine_id: myphysicslab`、`status: pending_slice_9`；受控参数 `length`（摆长，0.1–2.0 m）；视图 `energy_graph`（动能势能转化曲线） |

## 与上下层的关系

- 参考式桩：[`../../../../python/src/eduforge/validation/`](../../../../python/src/eduforge/validation/README.md) 的 `scientific/mechanics.py`（单摆周期，未接入）。
- 引擎描述：[`../../../engines/`](../../../engines/README.md) 的 `myphysicslab.yaml`（deferred，理由记在引擎描述与 lock 文件内）。
- 模板模式（三件套）说明见父层 [`../../README.md`](../../README.md)。

## 已知的坑与纪律

- **模板在位 ≠ 可用**：接通需先完成 myPhysicsLab 适配器（切片 9）；在此之前基准与链路都不覆盖它，任何文档不得写成"已支持力学实验"。
- `status: pending_slice_9` 字段是状态唯一标记处，启用时改这里并同步引擎描述。
