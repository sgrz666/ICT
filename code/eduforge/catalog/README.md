# catalog — 引擎描述与教学模板

EduForge 的**数据层**：这里没有可执行代码，只有「引擎是什么」和「一节课长什么样」的声明式描述。代码从这两个目录读配置，不把事实硬编码进逻辑。

## 结构

| 目录 | 内容 | 说明 |
|---|---|---|
| [`engines/`](engines/README.md) | 引擎描述文件 | 目前 `engines/ray-optics.yaml`：上游事实、无头调用方式、能力清单、验证基线 |
| [`templates/`](templates/README.md) | 教学模板，按 `学科/实验` 两级存放 | [`templates/optics/`](templates/optics/README.md) → `convex-lens/`（已接通：manifest + 原生场景 + 课文草稿）；[`templates/mechanics/`](templates/mechanics/README.md) → `pendulum/`、[`templates/circuits/`](templates/circuits/README.md) → `ohms-law/`（均 `pending_slice_9`，只有 manifest） |

## 消费方

- Python 侧：`python/src/eduforge/infrastructure/catalog.py` 读引擎描述；`domain/contracts.py` 与模板 manifest 对应。
- TS 侧：`services/engine-host/src/adapters/ray-optics/adapter.ts` 直接读模板目录（`manifest.yaml` + `native.json`）。
- 策略层（`agent/policy.py`）按 manifest 的 `routes` 判支持与否，不硬编码「支持」。

## 纪律

- 引擎描述里的数字与结论必须是实测（探针/测试跑出来的），设计意图要显式标注；测试计数只在该文件的 `test_totals` 记一处。
- 模板的单位换算是我们自己的约定（上游无单位系统），必须在 manifest 里显式声明并锁 `lengthScale`。
