# coding — 代码定制（沙箱 / 预算，切片 7 预留）

**职责**：为"代码定制"路线（教师需求无法用改参数满足时，允许生成受控代码扩展实验）准备的沙箱化代码生成与执行能力：执行预算、OpenSandbox 工厂、工作区管理、受限 Deep Agent 执行器。

**当前状态：未接入运行时**。主链路 [`../worker/steps.py`](../worker/steps.py) 在 planning 阶段对 `route=='code'` 直接抛 `CODE_ROUTE_NOT_EXECUTED` 拒绝，本目录仅测试可达（见 [`test_plan_architecture_alignment.py`](../../../../tests/python/test_plan_architecture_alignment.py)）。

## 内容（逐文件）

| 文件 | 行数 | 职责 | 关键符号 |
|---|---|---|---|
| `__init__.py` | 16 | 聚合导出各子模块符号 | — |
| `budget.py` | 18 | 执行预算常量：时长/轮次/重试/导出上限 | `ExecutionBudget` |
| `deep_agent.py` | 86 | Deep Agent 受限执行器：沙箱内执行、回收白名单文件 | `customize`, `EXPORT_PATHS` |
| `sandbox_factory.py` | 43 | OpenSandbox 工厂：检查 docker 与依赖是否就绪 | `SandboxFactory` |
| `workspace.py` | 48 | 工作区输入准备与导出白名单校验 | `WorkspaceManager`, `ALLOWED_EXPORT_PATHS` |

## 与上下层的关系

- 依赖：[`../domain/errors.py`](../domain/errors.py)；不依赖任何业务模块（刻意保持可隔离）。
- 预期接入点（尚未发生）：worker planning 阶段的 `route=='code'` 分支、以及 [`../../../../infra/sandbox/`](../../../../infra/sandbox/) 的容器运行时（无 Docker 时优雅降级）。
- 设计约束：白名单导出（`EXPORT_PATHS` / `ALLOWED_EXPORT_PATHS`）是安全边界——沙箱产物只能按名单回收，不允许任意路径出笼。

## 已知的坑与纪律

- **接入本目录 = 一次系统级变更**：必须先移除 `steps.py` 的 `CODE_ROUTE_NOT_EXECUTED` 拒绝、补授权链校验（`policy.authorize` 的 code 分支已经预留了任务长度校验）、并确保沙箱不可用时拒绝而不是降级为"本机直跑"。
- 无 Docker 环境（本机现状）下 `SandboxFactory` 会优雅报告不可用；这只是"就绪检查"，别把检查通过当成沙箱已可用。
- 导出白名单分散在两处——[`deep_agent.py`](deep_agent.py) 的 `EXPORT_PATHS` 与 [`workspace.py`](workspace.py) 的 `ALLOWED_EXPORT_PATHS`，改导出规则时两边都要看并保持互洽。
