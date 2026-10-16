# python — pytest 用例

EduForge Python 侧的全部测试：**17 个文件（16 个用例 + `conftest.py`）**。跑法：工程根 `uv run pytest`（`-q`）。这里的共同风格是**起真东西**：真 Postgres（pgserver）、真 uvicorn、真 Worker 子进程、真浏览器，只有规划用命令行注入的固定提案。

## 文件地图

| 文件 | 行数 | 覆盖 |
|---|---|---|
| `conftest.py` | 70 | 夹具（库、应用、临时环境） |
| `test_agent_tools_acceptance.py` | 410 | 8 项实验引擎原子工具与 Agent 工具调用循环验收测试：端到端验证 5 项验收准则（真实导入、多参数与测量表格生效、连续编辑父子链演进、离线包解开可用、Trace留痕与科学验证通过）；涵盖并发 RevisionConflict、自愈修复循环、以及无穷远像与虚像物理极值边界 |
| `test_gate2_protocol.py` | 126 | 修改协议：pydantic 校验、阈值（清晰 ≥0.8 / 弥散 ≤0.4 / 之间不可判）与控制组 |
| `test_gate5_api_chain.py` | 242 | §6.1 使用链：选模板→建实验→提交(幂等)→查任务→取消→查实验→下载产物；产物完整性（哈希锁定、缺失 404、不符 500、`storage_key` 越界 403） |
| `test_gate5_cancel.py` | 143 | 取消语义（已成功不回滚、活跃任务状态一致性） |
| `test_gate5_lease.py` | 245 | 租约领取/续租/抢占（`FOR UPDATE SKIP LOCKED` 语义） |
| `test_gate5_recovery.py` | 111 | 崩溃恢复（第二个 Worker 从持久化事实重建并完成） |
| `test_gate5_rollback.py` | 164 | §6.1 版本回滚：原子事务迁回目标版本保留历史、跨实验版本非法拦截、活跃任务冲突防御（409） |
| `test_gate6_planning.py` | 152 | 规划图与策略链（桩模型，无需 DeepSeek 密钥） |
| `test_planner_port.py` | 132 | 规划端口契约（`GraphPlanner` 与 `planner_from_env` 行为） |
| `test_entrypoints.py` | 116 | §6.3 智能体入口：华为云 AgentArts 运行时契约、本地 HTTP 规划与策略错误码映射 |
| `test_benchmarks.py` | 43 | §7.4 基准评测回归：区分 screening / direct / agent_graph 三种评测，无 key 显式 SKIPPED 杜绝规则伪充 |
| `test_plan_architecture_alignment.py` | 205 | 方案全貌架构对齐：验证 domain/models/errors、agent/retrieval、coding/workspace/budget、worker/lease、research/rea_runner、infrastructure 各模块自洽性 |
| `test_chain_worker.py` | 361 | 生产链路：API 提交→Worker 五阶段→原子发布→产物字节级校验；策略拒绝与验证不过都落 `failed` 且不动 head；支持复合操作（改焦距+设置记录表）、焦点平行光束与虚像成像物理边界验证 |
| `test_publish_chain.py` | 304 | 发布链（原子性、版本可恢复） |
| `test_contracts_surface.py` | 132 | §6.2 守卫：每个业务接口 2xx 都必须指向具名 DTO（生成物落后于后端即红） |
| `test_teacher_web_e2e.py` | 288 | 切片 8 金路径：真浏览器驱动教师前端走完整使用链（含版本回滚、下载文件本地重算哈希校验） |

## 测试 → 被测代码（主要映射）

| 测试 | 主要打到的源码 |
|---|---|
| `test_agent_tools_acceptance` | [`experiment_tools/`](../../python/src/eduforge/experiment_tools/README.md)（8 项工具服务）、[`agent/tool_agent.py`](../../python/src/eduforge/agent/README.md)（Agent 工具循环） |
| `test_chain_worker` / `test_publish_chain` | [`worker/`](../../python/src/eduforge/worker/README.md)（五阶段）、[`application/`](../../python/src/eduforge/application/README.md)（发布门禁）、[`infrastructure/db/`](../../python/src/eduforge/infrastructure/README.md) |
| `test_gate5_*` | [`api/`](../../python/src/eduforge/api/README.md)、[`application/coordinator.py`](../../python/src/eduforge/application/README.md)、`repositories.py` |
| `test_gate6_planning` / `test_planner_port` | [`agent/`](../../python/src/eduforge/agent/README.md)（图、策略、端口） |
| `test_entrypoints` | [`entrypoints/`](../../python/src/eduforge/entrypoints/README.md) |
| `test_teacher_web_e2e` | 真进程 `worker.run` + `api.serve` + 浏览器（GATE-8 侧） |
| `test_contracts_surface` | [`api/main.py`](../../python/src/eduforge/api/README.md) 的 response_model |
| `test_plan_architecture_alignment` | 全包（含"已定义未接入"预留模块） |


## 与其他层的关系

- 协议与实现的对应：被测代码在 [`../../python/src/`](../../python/src/README.md)；引用的事实基准在 [`../../catalog/engines/ray-optics.yaml`](../../catalog/engines/ray-optics.yaml)。
- 与 TS 侧用例的分界见 [`../README.md`](../README.md)。
