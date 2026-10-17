# optics — 光学学科模板分组

**职责**：`templates/` 下的学科分组层，存放光学（geometric optics）方向的实验模板。当前只有一个模板，也是全仓库**唯一端到端接通**的模板。

## 内容

| 条目 | 类型 | 说明 |
|---|---|---|
| [`convex-lens/`](convex-lens/README.md) | 模板实例目录 | 凸透镜成像（`template_id: optics.convex_lens`，`engine_id: ray_optics`，manifest 无 `status` 字段 = 已启用）。三件套齐备：`manifest.yaml` 137 行（量程唯一定义处）、`native.json` 33 行（上游原生场景 version 5）、`lesson.md` 49 行（课文草稿，尚未接入教师端） |

本目录自身不放任何数据文件——学科层只做分组，模板事实一律在实例目录的 `manifest.yaml` 里。

## 与上下层的关系

- 上一级：[`../README.md`](../README.md) 定义模板三件套模式与结构约定；新光学模板照 `convex-lens/` 抄（`templates/<学科>/<实验>/`）。
- 引擎绑定：`manifest.yaml` 的 `engine_id: ray_optics` 指向 [`../../engines/ray-optics.yaml`](../../engines/README.md)，能力边界以引擎描述为准。
- 读取方：[`../../../services/engine-host/src/adapters/ray-optics/adapter.ts`](../../../services/engine-host/src/adapters/ray-optics/README.md) 直接按路径加载 `manifest.yaml` + `native.json`；Python 侧由 [`../../../python/src/eduforge/infrastructure/catalog.py`](../../../python/src/eduforge/infrastructure/README.md) 解析；基准 12 题全部打这个模板（[`../../../benchmarks/`](../../../benchmarks/README.md)）。
- 科学对照另一方：[`../../../python/src/eduforge/validation/scientific/`](../../../python/src/eduforge/validation/README.md) 的独立薄透镜公式。

## 已知的坑与纪律

- **路径按「学科/实验」两级写死**在适配器与探针里；新建光学模板意味着 `catalog.py` / `adapter.ts` 两侧都要能发现它，不是加个目录就自动可用。
- 上游官方 gallery 里也有一个叫 `convex-lens.json` 的 SphericalLens 场景，含球差与色散，与薄透镜参考式**不等价**——不能当理想透镜模板的种子（详见 [`../README.md`](../README.md) 纪律节）。
- 单位约定是我们自己的（上游无单位系统）：凸透镜模板 `units_per_unit: 10` 且锁 `lengthScale: 1`，改换算只改 manifest，不改代码。
- mechanics、circuits 两个学科目录已建但引擎 deferred，**不要**把「目录在位」读成「学科已支持」；反向也不成立：光学接通不代表有第二个光学模板。
