# tests/ — dsh-core 独立自动化验证套件

> 2026-10-31 状态修正：测试覆盖原型当前实现与确定性夹具；无模型、无浏览器、无操作系统隔离的测试不能签发这些真实能力的验收。

## 1. 职责说明 (Responsibilities)

本目录承载 `deep-agent/dsh-core` 的 4 层级独立自动化测试套件（Tier 1 功能覆盖、Tier 2 边界极值与安全防御、Tier 3 跨模块协同契约、Tier 4 教育智能体真实业务场景），提供：
1. **脱离上游大仓的独立验证能力**：不依赖 `deep-agent/deepseek-harness` 庞大的 Node.js / Cordis 运行时或 SWE-bench 评测体系，纯 Python 驱动；
2. **确定性无网络运行保障**：内置 `MockSandbox` 与 `MockLlmClient`，在脱网、无 API Key、无计费支出的环境下全量跑通；
3. **Windows 本地原生执行保真**：覆盖 Windows 环境下的路径斜杠归一化、子进程编码、超时进程树清理（`taskkill /F /T`）以及零提权路径沙箱约束。

---

## 2. 目录内容 (Contents)

| 文件名 | 职责与覆盖范围 | 实测测试用例数 |
|---|---|---|
| [`conftest.py`](conftest.py) | Pytest 共享夹具：临时工作区隔离、Mock LLM 客户端工厂、预置教育实验样本与会话事件生成器 | N/A (Fixtures) |
| [`test_file_management.py`](test_file_management.py) | 文件管理子系统验证：`FileManager` 行号窗口读取、原子保存、`StrReplaceEditor` 精确唯一替换、3 行上下文 diff 生成、纯 Python grep/glob、路径越界防御 | 21 用例（实测全绿） |
| [`test_sandbox.py`](test_sandbox.py) | 沙箱受控执行子系统验证：`ProcessSandbox` 命令执行与退出码、`SandboxPolicy` 三档权限拦截、超时进程树清理、Windows Shell 适配、`MockSandbox` 模拟 | 11 用例（实测全绿） |
| [`test_session.py`](test_session.py) | 会话与对话流转验证：`SessionEvent` v4 规范校验、`SurfaceManager` 表面折叠与节点索引、`JsonlPersistence` 增量落盘与反序列化恢复、`ReactLoopState` 轮次状态机 | 7 用例（实测全绿） |
| [`test_memory.py`](test_memory.py) | 长时记忆与上下文压缩验证：`TokenMeter` 4字符密度估算与用量累加、`OutputPruner` 超长工具结果中段省略裁剪、`CompactionEngine` 8段式结构化摘要与表面就地替换 | 8 用例（实测全绿） |
| [`test_integration.py`](test_integration.py) | 跨模块端到端集成测试：学生代码自动评测与报错自纠自修、物理/电路实验参数文件修改、长程教学对话两阶段压缩检查点流转、会话崩溃恢复反序列化 | 4 用例（实测全绿） |
| [`test_advanced_subsystems.py`](test_advanced_subsystems.py) | 全量新增高级子系统与 `AgentLoop` 端到端验证：`FsObservationPolicy`（`FS_NOT_OBSERVED`/`FS_STALE`）、`BackgroundJobManager`、`SpillPolicy` 落盘保留与 `ImageOffloadPolicy`、`SessionProjectionRegistry` 与 `SessionQueryService`、`RepeatToolReminder` 与 `ToolTimeoutPolicy`、`TodoManager`/`PlanModeManager`/`GoalManager`（3 轮防早退）与 `GoalRoundDriver`、`SkillRegistry`/`InstructionLoader`/`FileReferenceResolver`/`SystemPromptBuilder`、`SubagentManager`（`spawn` vs `fork` KV-Cache 前缀继承）、`ApprovalManager`/`UserQuestionManager`/`DeliverableManager`/`WorkspaceChangeTracker`、`LabKitBridge` 9 配方 5 件套生成、`AgentLoop` + `AgentPresetRegistry` 多轮闭环 | 15 用例（实测全绿） |

---

## 3. 与上下层关系 (Relationship to Upper/Lower Layers)

- **上层消费者**：
  - `deep-agent/dsh-core/TEST_READY.md`：本套件运行结果、覆盖率统计与验收签发报告；
  - 仓库根门禁 `deep-agent/_tools/check_docs.py` 与 `AGENTS.md` 自动化质量巡检；
  - 上层编排者与审计者（`orchestrator`, `teamwork_auditor`）。
- **下层被测对象**：
  - `deep-agent/dsh-core/src/dsh_core/file/`
  - `deep-agent/dsh-core/src/dsh_core/sandbox/`
  - `deep-agent/dsh-core/src/dsh_core/session/`
  - `deep-agent/dsh-core/src/dsh_core/memory/`

---

## 4. 已知的坑与纪律 (Known Pitfalls & Disciplines)

1. **工作区隔离纪律**：每个测试必须通过 `tmp_path` 夹具生成独立测试工作区，严禁在 `deep-agent/dsh-core/` 或上游 `deepseek-harness/` 源码目录内直接产生任何临时文件；
2. **Windows 进程残留陷阱**：在测试子进程超时清理时，如果子进程衍生了下级进程，单纯 `proc.kill()` 会在 Windows 下造成孤儿进程悬挂；必须验证 `taskkill /F /T` 能够彻底整树清理；
3. **真实断言纪律**：严禁编写无实质断言的空测试（如 `assert True` 或单纯检查 Mock 调用次数而不验证业务返回值与副作用）；测试必须对磁盘落地内容、JSONL 记录结构、Token 压缩比进行明确数值比对；
4. **单轮运行命令**：
   ```powershell
   python -m pytest deep-agent/dsh-core/tests -v
   ```
