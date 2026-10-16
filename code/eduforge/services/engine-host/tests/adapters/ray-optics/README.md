# adapters/ray-optics（测试）— 改参语义单测

**职责**：对适配器改参逻辑做纯单测（不启动浏览器、不跑仿真）：实体定位与参数写入的语义都在这层被钉死。

## 内容

| 文件 | 行数 | 覆盖 |
|---|---|---|
| `patch.test.ts` | 123 | 控制组逐位一致、单位映射（15cm → 150）、**不就地改写**、重排/重名处理、量程与数值健壮性 |

## 与上下层的关系

- 被测：[`../../../src/adapters/ray-optics/patch.ts`](../../../src/adapters/ray-optics/README.md)（`setRayParameter` / `findEntityIndex`）。
- 向上汇总在父层 [`../../README.md`](../../README.md)。

## 已知的坑与纪律

- "不就地改写"是硬约束：改参必须产出新对象（重跑幂等的前提）——测试失败先查是否有人写回了原对象。
- 定位语义的边界（重排/重名）只在 `patch.test.ts` 被测——改 `findEntityIndex` 前先读它。
