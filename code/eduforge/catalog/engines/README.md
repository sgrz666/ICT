# engines — 引擎描述

每个接通的实验引擎一份 YAML，回答三个问题：**上游到底是什么**（版本、原生格式、序列化行为）、**怎么无头调用它**（入口、导出、启动仿真的必要条件）、**我们验证过什么**（基线、测试计数）。

## 内容

- `ray-optics.yaml` — 首个也是当前首批唯一接通的引擎（Ray Optics Simulation 5.5.0，Apache-2.0）。要点：
  - `native_format`：场景 JSON，`data_version: 5`；版本策略**委托给上游 loadJSON**（不写 `!== 5` 硬拒绝，读回 `scene.error`）；上游无单位系统，教学单位换算是模板自己的约定；对象身份只能是 `name`（数组下标绑定已被实测否决）。
  - `headless`：无头调用走 `dist-node/rayOptics.js`（1,715,044 字节），观测取 Detector 读数（power/normal/shear/binData），不经浏览器；**必须显式调 `simulator.updateSimulation(false, false)`**，否则 `simulationComplete` 永不触发、进程静默退出。
  - `capabilities`：只声明实测过的（如 `set_parameter`、`sample_measurement`、`export_native_scene` 为真；`export_offline_package` 已支持带 i18n 预注入补丁的离线包生成）。
  - `verification_baseline`：探针与报告路径、`measured_at`、**`test_totals`（全仓库唯一计数处）**、passed/rejected/not_yet_measured 三张清单。
- `myphysicslab.yaml` — 经典力学仿真引擎描述（Apache-2.0，第 7～8 周切片 9 保留位，标记 `status: pending_slice_9`）。
- `circuitjs.yaml` — 电路仿真引擎描述（GPL-2.0，第 7～8 周切片 9 保留位，标记 `status: pending_slice_9`）。

## 与其他层的关系

- 上游来源与构建事实：`../../../../source/upstream/upstream.lock.json`（本文件引用其 `upstream_id`）。
- 模板：`../templates/`（按 `engine_id` 关联）。
- 代码消费：`../../python/src/eduforge/infrastructure/catalog.py`、`../../services/engine-host/src/adapters/ray-optics/`。

## 纪律

- 新增引擎前，先在 `source/upstream/upstream.lock.json` 登记 decision；本文件只收「已接通」的引擎。
- 任何「已实测」条目必须能在 `output/eduforge/reports/` 或测试里找到证据；没跑过写 `pending`，不写成已完成。
