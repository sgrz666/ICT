# adapters — 适配器层测试的分组目录

**职责**：按引擎存放适配器的**纯单测**（不启动浏览器、不起服务、不加载上游仿真 bundle）。与 [`../engines/`](../engines/README.md) 的分界就在这儿：这里钉「改参语义」，那里真跑仿真断言读数。

## 内容

| 条目 | 文件数 | 说明 |
|---|---|---|
| [`ray-optics/`](ray-optics/README.md) | 1 | `patch.test.ts` 123 行，四个 describe 块：控制组逐位一致、单位映射、绑定稳定性、量程与数值健壮性 |

## 与上下层的关系

- 被测源码：[`../../../src/adapters/ray-optics/`](../../src/adapters/README.md)。`patch.test.ts` 只 import `src/adapters/ray-optics/patch` 的 `findEntityIndex` / `setRayParameter` 与 `src/contracts` 的类型，**不 import `upstream.ts`**——所以它跑得比引擎级测试快，也不需要上游构建产物。
- 场景来源：测试内 `SCENE_PATH` 指向 `../../../../../catalog/templates/optics/convex-lens/native.json`（真实模板场景，不是测试内造的假场景）；绑定表 `BINDINGS` 在测试文件里手写（`lens_1` / `IdealLens` / `focal_length_cm` / 5–50 / `units_per_unit: 10`）。
- 套件入口：[`../../README.md`](../README.md)；跑法 `pnpm -r test`（workspace 全量）。

## 已知的坑与纪律

- **「控制组逐位一致」在这层就要成立**：把参数改成它自己的初始值，序列化结果必须与原始场景逐位无变化。这条贯穿全部测试的不变量在单测里最便宜，别把它只留给 e2e。
- 测试里的 `BINDINGS` 与模板 `manifest.yaml` 的绑定是同信息两份表示，**不会自动同步**；改 manifest 量程或 `units_per_unit` 后要检查这里是否仍构成有效对照。
- 用例规模计数**不在本目录记**：唯一计数处是 [`../../../catalog/engines/ray-optics.yaml`](../../../../catalog/engines/README.md) 的 `test_totals`，各 README 只引用。
- 接新引擎时新建 `adapters/<engine>/`，与 `src/adapters/<engine>/` 一一对应；不要往 ray-optics 目录里塞别的引擎用例。
