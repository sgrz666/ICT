# application — 应用服务层

**职责**：实验与任务的生命周期编排——模板实例化、版本回滚、任务提交/取消/查询、发布门禁、五阶段推进的阶段机。本层不碰 HTTP 细节（那是 [`../api/`](../api/README.md)）也不写 SQL（那是 [`../infrastructure/db/repositories.py`](../infrastructure/db/repositories.py)），只负责把两者按业务规则粘起来。

## 内容（逐文件）

| 文件 | 行数 | 职责 | 关键符号 |
|---|---|---|---|
| `coordinator.py` | 46 | **阶段机**：按 `STAGES` 顺序推进；依据 `job_events` 的 `stage_done` 事件断点恢复（崩溃后从首个未完成阶段续跑） | `STAGES`, `Step`, `Coordinator` |
| `experiment_service.py` | 133 | 模板实例化与版本管理：`create_from_template`（克隆基础版本）、`rollback`（回退 head，校验 owner/活跃任务） | `ExperimentService`, `ExperimentLookup`, `ExperimentNotFound`, `TemplateNotFound`, `RevisionNotFound`, `ActiveJobConflict` |
| `job_service.py` | 54 | 任务生命周期：提交（幂等）、取消（已成功不回滚）、查询（含事件时间线） | `JobService` |
| `publication.py` | 67 | **发布门禁**：`record_report` 写验证报告；`publish` 在 `verdict≠passed` 时抛 `NotPublishable`，通过才调仓储发布事务 | `Publisher`, `NotPublishable` |
| `services.py` | 29 | 聚合导出入口（向后兼容）：把上述服务类从本文件统一再导出 | `ExperimentService`, `JobService` 等 |

## 与上下层的关系

- 依赖：[`../domain/contracts.py`](../domain/contracts.py)、[`../domain/errors.py`](../domain/errors.py)、[`../infrastructure/catalog.py`](../infrastructure/catalog.py)、[`../infrastructure/db/repositories.py`](../infrastructure/db/repositories.py)、[`../validation/reports.py`](../validation/reports.py)。
- 被谁用：[`../api/main.py`](../api/main.py) 经 [`services.py`](services.py) 取服务类；[`../worker/main.py`](../worker/main.py) 用 `Coordinator`；[`../worker/steps.py`](../worker/steps.py) 用 `Publisher`（validating/packaging 阶段）。
- 启动顺序：`Coordinator` 不知道阶段内做什么（`Step` 由 worker 注入），所以本层可被测试单独驱动（见 [`test_gate5_cancel.py`](../../../../tests/python/test_gate5_cancel.py)、[`test_gate5_recovery.py`](../../../../tests/python/test_gate5_recovery.py)）。

## 已知的坑与纪律

- **`services.py` 是兼容层**：新代码直接用 `experiment_service` / `job_service` 模块，`services.py` 只为既有 import 留门。
- 发布是**四道闸门**共同保证：`verdict=passed` + 有效租约 + 未取消 + 基础版本一致——任何一道在 `repositories.publish` 事务里再校验一次，文档描述与代码不一致时以 SQL 为准。
- `rollback` 与"活跃任务冲突"（`ActiveJobConflict`）是刻意设计：实验有在跑任务时拒绝回滚，别把它当 bug 修掉。
- 阶段机依赖 `stage_done` 事件做恢复——新增阶段必须同时改 `STAGES` 与事件写入点，否则恢复逻辑静默失效。
