# python — pytest 用例

EduForge Python 侧的全部测试：**16 个文件（15 个用例 + `conftest.py`）**。跑法：工程根 `uv run pytest`（`-q`）。这里的共同风格是**起真东西**：真 Postgres（pgserver）、真 uvicorn、真 Worker 子进程、真浏览器，只有规划用命令行注入的固定提案。

## 文件地图

| 文件 | 覆盖 |
|---|---|
| `conftest.py` | 夹具（库、应用、临时环境） |
| `test_gate2_protocol.py` | 修改协议：pydantic 校验、阈值（清晰 ≥0.8 / 弥散 ≤0.4 / 之间不可判）与控制组 |
| `test_gate5_api_chain.py` | §6.1 使用链：选模板→建实验→提交(幂等)→查任务→取消→查实验→下载产物；产物完整性（哈希锁定、缺失 404、不符 500、`storage_key` 越界 403） |
| `test_gate5_cancel.py` / `test_gate5_lease.py` / `test_gate5_recovery.py` | 任务取消、租约、崩溃恢复（第二个 Worker 从持久化事实重建并完成） |
| `test_gate5_rollback.py` | §6.1 版本回滚：原子事务迁回目标版本保留历史、跨实验版本非法拦截、活跃任务冲突防御（409） |
| `test_gate6_planning.py` / `test_planner_port.py` | 规划图与策略链（桩模型，无需 DeepSeek 密钥） |
| `test_entrypoints.py` | §6.3 智能体入口：华为云 AgentArts 运行时契约、本地 HTTP 规划与策略错误码映射 |
| `test_benchmarks.py` | §7.4 基准评测回归：12 题筛查集实跑且通过率 100% |
| `test_plan_architecture_alignment.py` | 方案全貌架构对齐：验证 domain/models/errors、agent/retrieval、coding/workspace/budget、worker/lease、research/rea_runner、infrastructure 各模块自洽性 |
| `test_chain_worker.py` | 生产链路：API 提交→Worker 五阶段→原子发布→产物字节级校验；策略拒绝与验证不过都落 `failed` 且不动 head |
| `test_publish_chain.py` | 发布链（原子性、版本可恢复） |
| `test_contracts_surface.py` | §6.2 守卫：每个业务接口 2xx 都必须指向具名 DTO（生成物落后于后端即红） |
| `test_teacher_web_e2e.py` | 切片 8 金路径：真浏览器驱动教师前端走完整使用链（含版本回滚、下载文件本地重算哈希校验） |

## 与其他层的关系

- 协议与实现的对应：被测代码在 [`../../python/src/`](../../python/src/README.md)；引用的事实基准在 [`../../catalog/engines/ray-optics.yaml`](../../catalog/engines/ray-optics.yaml)。
- 与 TS 侧用例的分界见 [`../README.md`](../README.md)。
