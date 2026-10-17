# domain — 纯净核心层（不依赖框架）

**职责**：领域层——数据契约（Pydantic 模型）、异常体系、实体定义、端口协议。全包所有模块的公共依赖，本层自身不 import 任何业务模块（只依赖 pydantic），保证"改协议只在一处发生"。

## 内容（逐文件）

| 文件 | 行数 | 职责 | 关键符号 |
|---|---|---|---|
| `contracts.py` | 199 | **最核心的数据契约**：全部 Pydantic 模型，`extra=forbid`（拒绝多余字段，改协议先动这里） | `SetParameter`, `SetView`, `EditProposal`, `WorkOrder`, `PlannerRequest`, `CreateJobRequest`, `JobAccepted`, `JobView`, `ExperimentDetail`, `ApiErrorResponse` |
| `errors.py` | 54 | 领域异常体系 | `EduForgeError`, `PolicyViolationError`, `ConflictError`, `NotFoundError`, `LeaseExpiredError`, `ScientificValidationError`, `DeliveryIntegrityError`（交付字节/清单核对不上，与"物理不成立"分开） |
| `models.py` | 87 | 领域实体 dataclass（Experiment/Job/Artifact/ValidationReport 等）。**当前仅被 `ports.py` 与 `__init__.py` 引用**，持久化层用裸 SQL 未实例化它们 | `Experiment`, `ExperimentRevision`, `Job`, `Artifact`, `ValidationReport`, `JobEvent` |
| `ports.py` | 101 | 抽象端口协议（仓储/存储/引擎/规划） | `JobRepositoryPort`, `ExperimentRepositoryPort`, `ArtifactStoragePort`, `EngineClientPort`, `AgentPlannerPort` |
| `__init__.py` | 56 | 聚合导出 | 上述各符号 |

## 被依赖关系（谁 import 本层）

- `contracts.py`：几乎全包——`agent/`、`api/`、`application/`、`worker/`、`infrastructure/clients/`、`validation/policies.py`。
- `errors.py`：`agent/planners.py`、`application/*`、`coding/*`、`infrastructure/clients/*`、`worker/*`。
- `ports.py`：仅 `worker/lease.py`（按 `JobRepositoryPort` 做类型标注）与 `__init__`——**运行时未做端口注入**，是给未来重构留的缝。
- `models.py`：同 `ports.py`，属"定义先行、接线未做"状态。

## 与上下层的关系

- 上层：所有业务模块把本层当"字典"用；[`../api/main.py`](../api/main.py) 的 response_model 直接引用 `contracts.py`，并由 [`../../../../tools/export_contracts.py`](../../../../tools/export_contracts.py) 导出为前端 TS 契约（OpenAPI → `packages/contracts`）。
- 测试：[`test_contracts_surface.py`](../../../../tests/python/test_contracts_surface.py)（契约可生成）、[`test_gate2_protocol.py`](../../../../tests/python/test_gate2_protocol.py)（EditProposal 校验）。

## 已知的坑与纪律

- `models.py` 的 dataclass 与 `infrastructure/db/repositories.py` 的裸 SQL 是**两套表示**，字段增删要人工对齐；以 SQL 为准、以 dataclass 为形。
- `contracts.py` 的 `extra=forbid` 会让"多传一个字段"变成 422——前端加字段必须先在这里加定义再跑契约导出。
- 本层禁止引入 IO/框架依赖（保持在"纯净"状态），需要 IO 的协议放进 `ports.py` 由 infrastructure 实现。
