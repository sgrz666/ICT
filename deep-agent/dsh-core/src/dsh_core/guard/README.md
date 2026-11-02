# guard/ — 工具死循环提醒与执行超时守卫子系统

**职责**：对应上游 `packages/guard/`（`@deepseek-ai/dsh-repeat-tool-reminder` 与 `@deepseek-ai/dsh-tool-call-timeout-policy`），负责在模型连续重复相同工具调用时注入阶梯式反死循环提醒（默认第 3 次温和提醒，第 5、8 次携带规范化入参详情提醒），并为每个工具提供可配置的执行超时上限。

## 内容

| 文件 | 状态 | 说明 |
|---|---|---|
| [`__init__.py`](__init__.py) | 已实测 | 子模块导出清单（`RepeatToolReminder`, `ToolTimeoutPolicy` 等） |
| [`repeat_reminder.py`](repeat_reminder.py) | 已实测 | JSON 深度键排序参数规范化、连续重复计数、通配符包含/排除过滤与阶梯提醒生成 |
| [`timeout_policy.py`](timeout_policy.py) | 已实测 | 工具级超时截止期限包装器与 `ToolCallTimeoutError` 结构化异常 |

## 与上下层的关系

- **上层消费者**：上游 `tools` 与 `loop` 调度器在 `tools/execute` 与 `tools/post-execute` 管线阶段调用本模块。
- **同层协作**：[`../session/`](../session/README.md)（提醒作为带 `{kind: "repeat-tool-reminder"}` 来源标记的上下文消息注入下一轮请求）。

## 已知的坑与纪律

1. **参数顺序无关性**：模型生成的 JSON 参数键序可能微调，`canonicalize_arguments` 通过递归排序字典键名，确保语义完全相同的调用被准确识别为重复调用。
2. **提醒预览截断**：详细提醒默认将参数预览限制在 `arguments_preview_chars = 500` 以内，避免大文件写入参数在死循环场景下二次撑爆上下文。
