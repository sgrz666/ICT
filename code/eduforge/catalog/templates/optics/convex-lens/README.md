# convex-lens — 凸透镜成像模板（已接通）

**职责**：首个也是当前唯一全链路打通的实验模板：凸透镜成像。基准 12 题全部围绕它；「改焦距 / 视图控制 / 越界拒绝」三类评测都打这个模板。

## 内容（逐文件）

| 文件 | 行数 | 职责 |
|---|---|---|
| `manifest.yaml` | 137 | 模板清单：受控参数（`focal_length_cm`、`object_distance_cm` 等，**量程唯一定义处**）、可导出视图、教学规则 |

| `native.json` | 33 | 初始场景（上游 Ray Optics 原生格式，供适配器加载） |
| `lesson.md` | 49 | 教学文案（随离线包分发给教师） |

## 模板实例模式（三个叶子目录的共同结构）

`manifest.yaml`（教学层：参数/视图/规则）+ `native.json`（引擎层：上游原生场景）+ 可选 `lesson.md`（交付层：教学文案）。实体 id、量程、视图都在 manifest 声明，代码侧由 [`../../../../python/src/eduforge/infrastructure/`](../../../../python/src/eduforge/infrastructure/README.md) 的 `catalog.py` 解析——**量程只此一处**。

## 与上下层的关系

- 被消费：engine-host 适配器（[`../../../../services/engine-host/src/adapters/ray-optics/`](../../../../services/engine-host/src/adapters/ray-optics/README.md)：加载场景与绑定表）、基准题集（[`../../../../benchmarks/`](../../../../benchmarks/README.md)）。
- 科学对照另一方：[`validation/scientific/`](../../../../python/src/eduforge/validation/README.md)。
- 引擎描述：[`../../../engines/ray-optics.yaml`](../../../engines/README.md)。

## 已知的坑与纪律

- **改量程只改 `manifest.yaml`**；改场景结构必须过上游 `validateNative`（"绝不返回看起来改了的候选"纪律）。
- `native.json` 是上游原生格式——不要手工做"看起来对"的字段增删，先在引擎侧验证通过再落盘。
- 新模板照本目录的三件套结构组织（父层模式说明见 [`../../README.md`](../../README.md)）。
