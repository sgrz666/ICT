# infrastructure — 基础设施层

**职责**：把外部世界接入 EduForge 的适配层——模板清单文件、Postgres 持久化、Engine Host HTTP、Agent HTTP、本地文件/BOS 存储、全局配置。业务层（agent/application/worker）一律经本层访问外部资源，不直接碰 IO。

## 内容（逐文件）

| 文件 | 行数 | 职责 | 关键符号 |
|---|---|---|---|
| `catalog.py` | 199 | **清单唯一读取入口**：解析模板 `manifest.yaml`（`ControlSpec`/`TemplateSpec`）、`list_templates`、`load_native`、`find_template_dir`；**量程（取值范围）只在这一处定义** | `CatalogError`, `ControlSpec`, `TemplateSpec`, `load_template`, `list_templates`, `load_native` |
| `settings.py` | 85 | 全局配置 + **DeepSeek key 解析**：`get_deepseek_api_key()`（`deepseek`/`DEEPSEEK`/`DEEPSEEK_API_KEY`/`deepseek_api_key` 优先级 + Windows 注册表兜底 + pytest 环境禁用兜底 + 回填进程变量）；`Settings` 含 database_url / engine_host_url / agent_host_url / artifacts_dir / templates_dir / deepseek_* | `Settings`, `settings`, `get_deepseek_api_key` |

子目录（各有独立 README）：

| 子目录 | 内容 | 细节 |
|---|---|---|
| [`clients/`](clients/README.md) | Engine Host 与 Agent 的 HTTP 客户端 | `engine_client.py`（运行时唯一引擎调用点）、`agent_client.py`（仅测试） |
| [`db/`](db/README.md) | Postgres 持久层 | `repositories.py`（306 行，全包最核心的 SQL）、`models.py`/`session.py`（定义先行未接线） |
| [`storage/`](storage/README.md) | 产物存储 | `local.py`（仅测试）、`obs.py`（华为云 OBS 桩，未接入） |

## 被依赖关系（谁 import 本层）

- `catalog.py` → [`../agent/policy.py`](../agent/policy.py)、[`../application/experiment_service.py`](../application/experiment_service.py)、[`../api/main.py`](../api/main.py)。
- `db/repositories.py` → [`../api/main.py`](../api/main.py)、[`../worker/main.py`](../worker/main.py)、[`../worker/steps.py`](../worker/steps.py)、[`../application/`](../application/README.md) 全部服务；测试覆盖最广（leases/cancel/rollback/publish 都直接打它）。
- `clients/engine_client.py` → [`../worker/steps.py`](../worker/steps.py)（editing 阶段）。
- `settings.py` → [`../agent/planners.py`](../agent/README.md) 与 [`../agent/model.py`](../agent/README.md)（key 解析）、`db/session.py`（配置）；各进程入口（`api/serve.py`、`worker/run.py`）仍从环境变量自取 DSN/端口，未全部统一经 `settings`。

## 与上下层的关系

- 上层业务：[`../domain/ports.py`](../domain/README.md) 定义了抽象端口，本层是这些端口的**实际实现处与更现实的替代**（例如存储端口未被使用，`worker/steps.py` 直接写 `artifact_dir`）。
- 数据来源：模板与量程的真身在 [`../../../../catalog/templates/`](../../../../catalog/templates/README.md)；本层只负责解析约定文件名（`manifest.yaml`/`native.json`）。

## 已知的坑与纪律

- **量程只此一处**（`catalog.py`）——改物理量范围必须改模板 `manifest.yaml`，不允许在任何其它层硬编码。
- `db/repositories.py` 是裸 SQL（asyncpg），JOIN、锁（`FOR UPDATE SKIP LOCKED`）、事务语义以 SQL 为准；`domain/models.py` 的 dataclass 不是它的输入输出类型。
- 本层有多个"已定义未接线"文件（`clients/agent_client.py`、`storage/*`、`db/session.py`、`db/models.py`）——读代码时先看上面的"被依赖关系"，没有消费方的就是预留件。
- `settings.py` 与各进程入口（`api/serve.py`、`worker/run.py`）的环境变量读取是两套——改配置项要同时看两处。
