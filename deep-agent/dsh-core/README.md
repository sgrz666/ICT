# dsh-core — 官方 DeepSeek Harness 核心架构剪枝与轻量化提取产物

> **2026-10-31 状态修正：研究原型，不是官方 dsh 的等价裁剪版或生产运行时。** 以下历史逐模块「已实测」只指原型自有测试通过。`sandbox/policy.py` 的字符串与 cwd 检查不提供操作系统隔离；`subagent/manager.py` 默认执行器会返回完成文本而不调用模型；主循环压缩走规则摘要；`labkit/bridge.py` 用解析值乘 0.9992 充当模拟且不执行浏览器。上述实现不能作为真实实验或原生能力的验证证据。正式路线见 [原生 agent-runtime](../../code/eduforge/services/agent-runtime/README.md)，保留本目录用于研究和反例复核，不继续扩展为主框架。

**职责**：从官方 `deepseek-harness` 源码中剪枝提取核心 Agent 基础设施能力，完全解耦 2.7 GB 的上游 Node.js monorepo、SWE-bench 评测套件及第三方重型依赖。在保留文件管理、长时记忆、会话与对话处理、受控沙箱四大核心机制的同时，以现代纯 Python（>= 3.10）实现高内聚、零 C++ 编译依赖、Windows 原生兼容的独立智能体运行内核。

## 内容

| 目录 / 文件 | 状态 | 说明 |
|---|---|---|
| [`ARCHITECTURE_STUDY.md`](ARCHITECTURE_STUDY.md) | 已交付 | DeepSeek Harness 架构精读与全量 52 类别（343 包）剪枝审计及 12 大子系统落地报告 |
| [`TEST_READY.md`](TEST_READY.md) | 已交付 | 自动化测试矩阵与质量验收签发报告（66 项测试实测 100% 绿灯通过） |
| [`pyproject.toml`](pyproject.toml) | 已实测 | 现代 Python 构建打包配置（基于 hatchling，依赖仅 `pydantic>=2.7.0`） |
| [`requirements.txt`](requirements.txt) | 已实测 | 生产运行依赖（单一依赖：pydantic） |
| [`requirements-dev.txt`](requirements-dev.txt) | 已实测 | 单元与集成测试依赖（pytest） |
| [`src/`](src/README.md) | 已实测 | 核心纯 Python 源代码根目录 |
| [`src/dsh_core/`](src/dsh_core/README.md) | 已实测 | 核心包顶级命名空间，导出 12 大核心子系统（`v0.2.0`） |
| [`src/dsh_core/file/`](src/dsh_core/file/README.md) | 已实测 | 子系统 1：安全文件管理、先读后写门禁（`FsObservationPolicy`）、原子写、精确替换与防穿透 |
| [`src/dsh_core/sandbox/`](src/dsh_core/sandbox/README.md) | 已实测 | 子系统 2：Windows 原生受控子进程、`BackgroundJobManager` 后台长任务、进程树强杀与三档策略沙箱 |
| [`src/dsh_core/session/`](src/dsh_core/session/README.md) | 已实测 | 子系统 3：格式版本 4 事件溯源日志、表面投影、声明式折叠投影（`SessionProjectionRegistry`）与 JSONL 持久化 |
| [`src/dsh_core/memory/`](src/dsh_core/memory/README.md) | 已实测 | 子系统 4：Token 估算器、超限输出无损落盘（`SpillStore`/`SpillPolicy`）、多模态图像卸载与八段式摘要压缩 |
| [`src/dsh_core/guard/`](src/dsh_core/guard/README.md) | 已实测 | 子系统 5：重复工具调用检测（`RepeatToolReminder`）与按工具超时熔断（`ToolTimeoutPolicy`） |
| [`src/dsh_core/autonomy/`](src/dsh_core/autonomy/README.md) | 已实测 | 子系统 6：任务清单（`TodoManager`）、只读规划门禁（`PlanModeManager`）与自治目标驱动（`GoalManager` + `GoalRoundDriver`） |
| [`src/dsh_core/skill/`](src/dsh_core/skill/README.md) | 已实测 | 子系统 7：`SKILL.md` 发现加载（`SkillRegistry`）、`AGENTS.md` 指令、`@file` 引用解析与动态系统提示词组装 |
| [`src/dsh_core/subagent/`](src/dsh_core/subagent/README.md) | 已实测 | 子智能体协同子系统 8：全新派生（`spawn`）与复用 KV-Cache 前缀的进程内分叉（`fork`） |
| [`src/dsh_core/interaction/`](src/dsh_core/interaction/README.md) | 已实测 | 子系统 9：三档权限审批（`ApprovalManager`）、结构化提问（`UserQuestionManager`）、交付物卡片与工作区变更追踪 |
| [`src/dsh_core/labkit/`](src/dsh_core/labkit/README.md) | 已实测 | 子系统 10：EduForge 物理与电路实验桥接（`LabKitBridge`，9 套配方、6 个 `experiment_*` 工具、5 件套实验包） |
| [`src/dsh_core/tools/`](src/dsh_core/tools/README.md) | 已实测 | 子系统 11：三阶段工具注册表（`ToolRegistry`）与 27 个内置工具套件（`register_builtin_tools`） |
| [`src/dsh_core/loop/`](src/dsh_core/loop/README.md) | 已实测 | 子系统 12：预设注册表（`AgentPresetRegistry`）与端到端可执行主循环（`AgentLoop`） |
| [`tests/`](tests/README.md) | 已实测 | 独立自动化验证套件（6 个测试文件共 66 个用例全绿） |

## 与上下层的关系

- **上游参考源**：[`../deepseek-harness/`](../deepseek-harness)（只读官方仓库锚点，`dsh-v0.2.1-rc.2`），提取其架构设计与契约，不修改上游任何文件。
- **评测与验证报告**：[`../harness-validation-reports/`](../harness-validation-reports/README.md)（记录了官方 Windows ACL 沙箱报 Win32 5 拒绝错误的现场与分析）。
- **测试套件协同**：[`tests/`](tests/README.md) 目录提供 4 层级独立测试套件，全面覆盖四大子系统的单测与教育场景端到端集成测试（参见 [`TEST_READY.md`](TEST_READY.md)）。
- **业务集成方**：供 ICT 教学智能体（代码运行与批改、物理/电路实验、学生长程问答）直接 `import dsh_core` 调用。

## 已知的坑与纪律

1. **绝对只读约束**：严禁向 `../deepseek-harness/` 写入任何文件或执行修改命令。
2. **纯 Python 与零原生编译**：核心代码仅允许标准库和 `pydantic`，不引入需要本地 MSVC 编译的 C/C++ 动态链接库。
3. **Windows 路径安全**：文件操作与沙箱执行统一通过 `assert_path_contained` 校验规范化绝对路径，杜绝 Windows 驱动器跨盘穿越或 `..` 符号链接逃逸。
4. **README 覆盖纪律**：本模块下任何新增子目录必须配备标准四段式 `README.md`，并通过 `deep-agent/_tools/check_docs.py` 门禁。
