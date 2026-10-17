# adapters/ray-optics — Ray Optics 适配器

**职责**：EduForge 与上游 Ray Optics 之间的唯一适配层：把「按实体名的改参请求」变成对上游原生场景的**可验证修改**，再驱动上游真实仿真并读取探测器读数。整个「改上游、出结果」的业务逻辑都在本目录。

## 内容（逐文件）

| 文件 | 行数 | 职责 | 关键符号 |
|---|---|---|---|
| `adapter.ts` | 81 | 适配器门面：从 catalog 模板解析绑定表/模板场景；统一调度改参、校验、采样、导出 | `loadBindings()`, `loadTemplateScene()`, `Candidate`, `rayOpticsAdapter`（apply/sample/validateNative/exportNative） |
| `patch.ts` | 81 | 按**实体名**（非数组下标）定位对象并做参数修改与量程校验 | `findEntityIndex()`, `setRayParameter()` |
| `upstream.ts` | 465 | 加载上游无头 bundle 驱动真实仿真，读探测器 `binData` 算光斑 RMS/质心/捕获功率；像面判据 = `rms_units` + 功率下限（**不用 `peak_share`**，避免远屏假清晰）。**Gate C §C.2 新增 `beamGeometry()`**：用屏阵列上的实测宽度做线性拟合，给出实像交点 / 虚像反向延长交点 / 高平行度三态，并在光斑铺满探测器时明确判「孔径截断，测不出来」 | `upstream()`, `Probe`, `sharpestProbe()`, `beamGeometry()`, `lensAxisXcm()`, `validateNative()`, `simulate()`, `bundlePath`, `halfSpanCm` |

## 数据流（一次改参的完整路径）

`adapter.apply()` → `patch.setRayParameter()`（名定位 + 量程校验）→ `upstream.validateNative()`（交回上游 `Scene.loadJSON()` 解释，拒绝即 422 `NATIVE_REJECTED`）→ `upstream.simulate()`（真实跑仿真）→ 读 `Detector.binData` 算读数 → 返回 `{native, validation, measurement}`。

## 与上下层的关系

- 被谁用：[`../../main.ts`](../../README.md)（`/adapters/ray_optics/apply` 路由）、[`../../preview/server.ts`](../../preview/README.md)（`/param` 预览改参复用同一适配器）。
- 上游事实：[`source/upstream/`](../../../../../../../source/upstream/README.md)（bundle 5.5.0，commit 锁在 `upstream.lock.json`）。
- 测试：[`../../../tests/adapters/ray-optics/patch.test.ts`](../../../tests/README.md)（改参语义）、[`../../../tests/engines/`](../../../tests/README.md)（仿真与科学对照）。

## 已知的坑与纪律

- **绝不返回"看起来改了"的候选**：任何修改必须交回上游解释器验证（`validateNative`），上游拒绝就是拒绝——这是与"直接改 JSON 返回假成功"的分界线。
- 定位对象按**实体名**、不按数组下标——重排/重名场景有专项测试（`patch.test.ts`），改定位逻辑先读它。
- `peak_share` 是**弃用判据**（远屏会假清晰）；选屏用 `sharpestProbe`（rms + 功率下限）。
- 改参单位与上游内部单位的换算（如 15cm → 150）发生在 `patch.ts`——别在其它层再算一份。
