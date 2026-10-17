# adapters — 引擎适配器的分组层

**职责**：按引擎存放适配器。每个上游引擎一个子目录，把「上游原生场景格式」与「EduForge 的改参/校验/仿真/导出语义」之间的翻译关在这一层，`main.ts` 与 Python 侧都不直接碰上游内部结构。

## 内容

| 条目 | 类型 | 说明 |
|---|---|---|
| [`ray-optics/`](ray-optics/README.md) | 唯一在位的适配器 | `upstream.ts` 465 行（真实无头仿真入口，`createRequire` 加载上游 `dist-node/rayOptics.js`；含屏读数→光束几何拟合）、`patch.ts` 81 行（实体定位与参数写入语义）、`adapter.ts` 81 行（模板 manifest/native 加载与绑定表） |

分组层本身不放代码文件，也不放 `index.ts` 之类的注册表——**当前不存在按引擎动态注册的机制**，路径是硬编码到 `ray-optics` 的。

## 与上下层的关系

- 上层入口：[`../main.ts`](../README.md) 的 GATE-3 验收面把 apply / validate 请求派到 ray-optics 适配器；Python 侧经 HTTP 调 `/adapters/ray_optics/apply`（HTTP 客户端在 [`../../../../python/src/eduforge/infrastructure/`](../../../../python/src/eduforge/infrastructure/README.md)）。
- 读取的数据：模板在 [`../../../catalog/templates/optics/convex-lens/`](../../../../catalog/templates/optics/convex-lens/README.md)（`manifest.yaml` + `native.json`），引擎事实在 [`../../../catalog/engines/ray-optics.yaml`](../../../../catalog/engines/README.md)。
- 上游本体：`source/upstream/ray-optics/`，身份由 `source/upstream/upstream.lock.json` 的 commit 锁定；路径解析集中在 [`../upstream_paths.ts`](../README.md)。
- 测试：[`../../../tests/adapters/`](../../tests/adapters/README.md)（纯单测）、[`../../../tests/engines/`](../../tests/engines/README.md)（真跑仿真的引擎级验收）。

## 已知的坑与纪律

- **mechanics / circuits 没有适配器目录，且不是遗漏**：myPhysicsLab 与 CircuitJS1 是 deferred（切片 9），引擎未接通时不预建空适配器目录——空目录会诱导别人以为半接通。要接新引擎时新建 `<engine>/`，沿用 ray-optics 的三文件分工（upstream / patch / adapter）。
- 适配器用的是本服务**自有**的 [`../contracts.ts`](../README.md) 类型（`LensBinding`、`RayScene`、`Operation` 等），与 `packages/contracts` 那套是并行定义、互不相引；改形状没有自动同步兜底。
- 对象身份一律走 `name` 字段绑定：上游 `objs` 数组顺序不稳定，用下标寻址会在拖动/删除后错位（这条纪律同时写在 [`../../../skills/ray-optics-customization/SKILL.md`](../../../../skills/ray-optics-customization/README.md)）。
- 改参必须过上游 `validateNative`，绝不返回「看起来改了」的候选；量程判断的权威在模板 manifest，适配器不该另存一份。
