# ohms-law — 欧姆定律模板（pending，引擎未接通）

**职责**：circuits 方向教学模板的**保留位**：欧姆定律与电阻伏安特性。上游引擎 CircuitJS1 为 deferred（本轮不进首批），模板声明完整但未接通。

## 内容（逐文件）

| 文件 | 行数 | 职责 |
|---|---|---|
| `manifest.yaml` | 34 | 模板清单：`template_id: circuits.ohms_law`、`engine_id: circuitjs`、`status: pending_slice_9`；受控参数 `resistance`（1–1000 Ω）与 `voltage`（1–24 V，`power_source_1`）；视图 `voltmeter` / `ammeter` |

## 与上下层的关系

- 参考式桩：[`../../../../python/src/eduforge/validation/`](../../../../python/src/eduforge/validation/README.md) 的 `scientific/circuits.py`（欧姆定律，未接入）。
- 引擎描述：[`../../../engines/`](../../../engines/README.md) 的 `circuitjs.yaml`（deferred）。
- 模板模式（三件套）说明见父层 [`../../README.md`](../../README.md)。

## 已知的坑与纪律

- **模板在位 ≠ 可用**：接通需先完成 CircuitJS1 适配器（切片 9，Java-GWT 工具链与 Docker 前置未就绪——理由记在 lock 文件内）。
- 两个受控参数（电阻/电压）意味着将来授权链要覆盖"多参数组合改参"——切片 9 设计时注意。
