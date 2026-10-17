# application — 应用服务层

**职责**：实验与任务的生命周期编排——模板实例化、版本回滚、任务提交/取消/查询、发布门禁、五阶段推进的阶段机。本层不碰 HTTP 细节（那是 [`../api/`](../api/README.md)）也不写 SQL（那是 [`../infrastructure/db/repositories.py`](../infrastructure/db/repositories.py)），只负责把两者按业务规则粘起来。

## 内容（逐文件）

| 文件 | 行数 | 职责 | 关键符号 |
|---|---|---|---|
| `candidate_service.py` | 381 | **Gate A 的候选业务层**：`CandidateState`（含 `content_hash`/`state_version`/`validation_hash`）、canonical JSON 与内容指纹（场景 + 教学视图，浮点归一）、`native_bytes`/`views_bytes` 这两个唯一的字节写法、`AgentRunRecord`（Agent 执行完成记录），以及 `CandidateService`：open/load/write(CAS)/bind_validation/freeze/rebase/attach_trace。没库或没 job 时显式退化为进程内缓存并如实标注 | `CandidateState`, `AgentRunRecord`, `CandidateService`, `content_fingerprint`, `canonical_json`, `native_bytes`, `views_bytes` |
| `coordinator.py` | 46 | **阶段机**：按 `STAGES` 顺序推进；依据 `job_events` 的 `stage_done` 事件断点恢复（崩溃后从首个未完成阶段续跑） | `STAGES`, `Step`, `Coordinator` |
| `experiment_service.py` | 142 | 模板实例化与版本管理：`create_from_template`（克隆基础版本）、`rollback`（回退 head，校验 owner/活跃任务） | `ExperimentService`, `ExperimentLookup`, `ExperimentNotFound`, `TemplateNotFound`, `RevisionNotFound`, `ActiveJobConflict` |
| `job_service.py` | 106 | 任务生命周期：提交前**归属与基础版本核对**（实验属于该身份、`base_revision` 属于该实验且等于当前 head）、幂等提交、取消（已成功不回滚）、查询按身份限定 | `JobService`, `assert_submittable`, `ExperimentNotOwned`, `RevisionNotOfExperiment`, `BaseNotHead` |
| `publication.py` | 83 | **发布门禁**：`record_report` 写验证报告（含候选绑定列：`candidate_id`/`content_hash`/`engine_version`/`profile`）；`publish` 在 `verdict≠passed` 时抛 `NotPublishable`，通过才调仓储发布事务 | `Publisher`, `NotPublishable` |
| `package_builder.py` | 493 | **Gate C §C.4/§C.5/§C.5b R2 统一交付构建器**：把已冻结候选变成可核对的字节——`native.json`/`teaching_views.json` 落盘并逐字节回读核对；离线包由引擎组装，但**包内场景替换成交付的那一份字节**；最终 `manifest.json` = 引擎交付元数据 + 逐文件 SHA256 + `package_sha256` 整包摘要；建完立刻让 Engine Host 用 Chromium **实测这份包**（§C.5），不通过就抛 `DeliveryIntegrityError(code="OFFLINE_NOT_RENDERED")`；**§C.5b R2 确定性离线 ZIP 构建与校验**：构建确定性 ZIP（`build_deterministic_zip` 走 `asyncio.to_thread` 调度防卡租约心跳，固定 2026-01-01 时间戳、0o100644 权限、文件字典序、防 Zip Slip、集成 LICENSE 与离线 README.md），记录 ZIP SHA256 与大小，登记 `offline_zip` 产物（`media_type="application/zip"`），提供 `verify_offline_zip` 完整性核对。工具层与 Worker 都调这里，产物 id 一律内容派生（重跑幂等） | `PackageBuilder`, `BuiltPackage`, `package_digest`, `verify_package_on_disk`, `build_deterministic_zip`, `verify_offline_zip`, `file_sha256`, `ENGINE_METADATA_KEYS`, `MANIFEST_NAME` |
| `services.py` | 29 | 聚合导出入口（向后兼容）：把上述服务类从本文件统一再导出 | `ExperimentService`, `JobService` 等 |

## 与上下层的关系

- 依赖：[`../domain/contracts.py`](../domain/contracts.py)、[`../domain/errors.py`](../domain/errors.py)、[`../infrastructure/catalog.py`](../infrastructure/catalog.py)、[`../infrastructure/db/repositories.py`](../infrastructure/db/repositories.py)、[`../validation/reports.py`](../validation/reports.py)。
- 被谁用：[`../api/main.py`](../api/main.py) 经 [`services.py`](services.py) 取服务类；[`../worker/main.py`](../worker/main.py) 用 `Coordinator`；[`../worker/steps.py`](../worker/steps.py) 在 packaging 阶段用 `PackageBuilder`（建交付字节）+ `Publisher`（发布事务）；[`../experiment_tools/service.py`](../experiment_tools/README.md) 的 `build_package` 走同一个 `PackageBuilder`。
- 启动顺序：`Coordinator` 不知道阶段内做什么（`Step` 由 worker 注入），所以本层可被测试单独驱动（见 [`test_gate5_cancel.py`](../../../../tests/python/test_gate5_cancel.py)、[`test_gate5_recovery.py`](../../../../tests/python/test_gate5_recovery.py)）。

## 已知的坑与纪律

- **`services.py` 是兼容层**：新代码直接用 `experiment_service` / `job_service` 模块，`services.py` 只为既有 import 留门。
- 发布是**四道闸门**共同保证：`verdict=passed` + 有效租约 + 未取消 + 基础版本一致——任何一道在 `repositories.publish` 事务里再校验一次，文档描述与代码不一致时以 SQL 为准。
- `rollback` 与"活跃任务冲突"（`ActiveJobConflict`）是刻意设计：实验有在跑任务时拒绝回滚，别把它当 bug 修掉。
- 阶段机依赖 `stage_done` 事件做恢复——新增阶段必须同时改 `STAGES` 与事件写入点，否则恢复逻辑静默失效。
- **交付清单只有一个写入方**：引擎写的 `manifest.json` 是**输入**，`PackageBuilder` 读出元数据后合并逐文件哈希与整包摘要再落盘（同一路径）。要加交付元数据，得同时改引擎 `export/manifest.ts` 与本模块的 `ENGINE_METADATA_KEYS`——只改一边会在构建时报 `DELIVERY_INTEGRITY`，不会静默丢字段。
- 逐文件表按**完整路径**排除清单本身，不按文件名：上游 dist 里真有嵌套同名文件 `www/simulator/manifest/manifest.json`，按 `name == manifest.json` 排除会把它漏在哈希表外（实测 2162 vs 2163）。
- **别在 Worker 或工具层里再手写落盘与产物登记**（§C.4 之前的状态）：两条路径各自写盘时，"验证过的字节 == 发布出去的字节"无法核对，也正是在这里出过离线包根本没进生产链的问题。写盘与登记统一走 `PackageBuilder`。
- **离线包必须实测，测不了就拒绝**：`_verify_package` 在引擎客户端没有 `verify_offline_package` 方法时直接抛错，而不是默认通过——新引擎实现忘了接这个方法时，绿灯不会悄悄出现。实测结论（逐项判据 + 截图哈希）写在包目录旁的 `offline_verification.json`，不进哈希表：它是**关于**这份包的观测记录，不是包的交付内容。
- **确定性 ZIP 构建必须线程池异步化**：离线包内有 2162 个文件，压缩计算密集；若在 asyncio 事件循环中同步执行，会阻塞主线程 3 秒以上导致租约心跳（Heartbeat）饿死超时触发 `LEASE_LOST`。必须使用 `await asyncio.to_thread(build_deterministic_zip, ...)`。
