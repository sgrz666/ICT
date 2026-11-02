# interaction/ — 人机交互、人工审批与交付物核验子系统

**职责**：对应上游 `packages/interaction/` 与 `packages/deliverables/`，为 Agent 提供安全受控的人机交互通道，包括高风险操作人工审批放行、结构化多选题澄清提问、以及向用户正式签发关键交付物。

## 内容

| 文件 | 状态 | 说明 |
|---|---|---|
| [`__init__.py`](__init__.py) | 已实测 | 模块导出清单（`ApprovalManager`, `QuestionManager`, `DeliverablesManager` 等） |
| [`approval.py`](approval.py) | 已实测 | 操作敏感度评估、人工审批策略、放行/拒绝回调处理与审计日志挂接 |
| [`questions.py`](questions.py) | 已实测 | 面向教师/用户的结构化单选与多选题澄清机制，用于需求模糊时的意图对齐 |
| [`deliverables.py`](deliverables.py) | 已实测 | 正式交付物注册、哈希校验、版本状态维护与交付包归档元数据管理 |

## 与上下层的关系

- **上层消费者**：上游 `tools`（暴露 `ask_question`, `request_approval`, `submit_deliverable` 工具）与交互式 Web 前端/CLI。
- **下层依赖**：[`../session/`](../session/README.md)（所有交互提问与审批记录均作为会话事件持久化入账）。

## 已知的坑与纪律

1. **审批不可逾越**：高危写操作或外部请求必须经由审批管理器判断策略，策略标为 `require_approval` 的场景严禁静默放行。
2. **结构化问题规范**：澄清提问强制要求提供预设候选选项，避免发散式自由问答降低交互效率。
