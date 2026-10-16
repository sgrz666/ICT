# engines — 引擎描述

每个接通的实验引擎一份 YAML，回答三个问题：**上游到底是什么**（版本、原生格式、序列化行为）、**怎么无头调用它**（入口、导出、启动仿真的必要条件）、**我们验证过什么**（基线、测试计数）。

## 内容

| 文件 | 状态 | 说明 |
|---|---|---|
| `ray-optics.yaml` | **已接通**（首批唯一） | 描述最全：原生格式、无头调用、能力清单、验证基线（含 `test_totals`） |
| `myphysicslab.yaml` | `pending_slice_9` | 保留位；理由与决定记在 lock 文件，本文件只留 `engine_id` 与状态 |
| `circuitjs.yaml` | `pending_slice_9` | 同上（Java-GWT 工具链与 Docker 前置未就绪） |

- `ray-optics.yaml` — Ray Optics Simulation 5.5.0（Apache-2.0）。要点：
  - `native_format`：场景 JSON，`data_version: 5`；版本策略**委托给上游 loadJSON**（不写 `!== 5` 硬拒绝，读回 `scene.error`）；上游无单位系统，教学单位换算是模板自己的约定；对象身份只能是 `name`（数组下标绑定已被实测否决）。
  - `headless`：无头调用走 `dist-node/rayOptics.js`（1,715,044 字节），观测取 Detector 读数（power/normal/shear/binData），不经浏览器；**必须显式调 `simulator.updateSimulation(false, false)`**，否则 `simulationComplete` 永不触发、进程静默退出。
  - `capabilities`：只声明实测过的（如 `set_parameter`、`set_view`、`sample_measurement`、`export_native_scene` 为真；`export_offline_package` 经随包静态服务打开已实测通过；单文件直开因上游 iframe 内部 i18n HTTP fetch 受限已实测留痕）。
  - `verification_baseline`：探针与报告路径、`measured_at`、**`test_totals`（全仓库唯一计数处）**、passed/rejected/not_yet_measured 三张清单。
- `myphysicslab.yaml` — 经典力学仿真引擎描述（Apache-2.0，第 7～8 周切片 9 保留位，标记 `status: pending_slice_9`）。
- `circuitjs.yaml` — 电路仿真引擎描述（GPL-2.0，第 7～8 周切片 9 保留位，标记 `status: pending_slice_9`）。

## 与其他层的关系

- 上游来源与构建事实：[`source/upstream/upstream.lock.json`](../../../../source/upstream/README.md)（本文件引用其 `upstream_id`）。
- 模板：[`../templates/`](../templates/README.md)（按 `engine_id` 关联）。
- 代码消费：[`catalog.py`](../../python/src/eduforge/infrastructure/catalog.py)（Python 侧读取入口）、[`engine-host 适配器`](../../services/engine-host/src/adapters/ray-optics/README.md)。

## 纪律

- 新增引擎前，先在 `source/upstream/upstream.lock.json` 登记 decision；本文件只收「已接通」的引擎。
- 任何「已实测」条目必须能在 `output/eduforge/reports/` 或测试里找到证据；没跑过写 `pending`，不写成已完成。
