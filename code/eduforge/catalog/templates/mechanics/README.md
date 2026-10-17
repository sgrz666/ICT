# mechanics — 力学学科模板分组（保留位，引擎未接通）

**职责**：`templates/` 下的力学分组层，为第 7～8 周切片 9 接入 myPhysicsLab 预留目录结构。当前只有一个模板声明，**没有任何可跑链路**。

## 内容

| 条目 | 类型 | 状态 |
|---|---|---|
| [`pendulum/`](pendulum/README.md) | 模板实例目录 | 单摆周期与简谐振动（`template_id: mechanics.pendulum`，`engine_id: myphysicslab`，`status: pending_slice_9`）。只含 `manifest.yaml` 23 行（摆长 0.1–2.0 m、视图 `energy_graph`）；**没有 `native.json`**，也没有 `lesson.md` |

本目录自身不放数据文件。

## 与上下层的关系

- 上一级：[`../README.md`](../README.md) 的三件套模式（manifest / native / lesson）；本目录**只有第一件**，缺的 `native.json` 要等适配器落地后才能从上游场景导出。
- 引擎侧：[`../../engines/`](../../engines/README.md) 的 `myphysicslab.yaml`（deferred，不进首批的理由记在引擎描述与 [`../../../../source/upstream/upstream.lock.json`](../../../../../source/upstream/README.md)）。
- 参考式桩：[`../../../python/src/eduforge/validation/scientific/`](../../../python/src/eduforge/validation/README.md) 的 `mechanics.py`（单摆周期，未接入运行时）。
- 领域规范：[`../../../skills/mechanics-customization/SKILL.md`](../../../skills/mechanics-customization/README.md)（同为切片 9 保留位）。

## 已知的坑与纪律

- **目录在位 ≠ 学科可用**：任何文档不得写成「已支持力学实验」。启用顺序是 myPhysicsLab 适配器 → `native.json` → manifest 去掉 `status` → 验证参考式接入，缺一环都算 pending。
- 力学走 SI 单位制，与光学的「无量纲场景像素 + `units_per_unit`」不是同一套换算约定——别把光学的单位换算纪律直接搬过来。
- `status: pending_slice_9` 只写在 `manifest.yaml`，是状态唯一标记处；启用时改那里并同步引擎描述与本文件。
