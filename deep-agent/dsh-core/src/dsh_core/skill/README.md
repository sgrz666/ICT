# skill/ — 技能注册表、工作区指令与系统提示词组装子系统

**职责**：对应上游 `packages/skill/`（`@deepseek-ai/dsh-skill`、`@deepseek-ai/dsh-skill-filesystem`、`@deepseek-ai/dsh-tool-skill`）、`packages/context/`（`@deepseek-ai/dsh-agent-instructions`、`@deepseek-ai/dsh-file-reference-local`）以及 `packages/core/system-prompt/`（`@deepseek-ai/dsh-system-prompt`），负责发现与按需加载 `SKILL.md` 领域手册、自动注入工作区 `AGENTS.md`/`CLAUDE.md` 纪律、解析用户消息中的 `@file` 引用、以及按优先级组装 KV-Cache 友好的系统提示词。

## 内容

| 文件 | 状态 | 说明 |
|---|---|---|
| [`__init__.py`](__init__.py) | 已实测 | 导出 `SkillRegistry`、`FilesystemSkillProvider`、`InstructionLoader`、`FileReferenceResolver`、`SystemPromptBuilder` |
| [`skill_registry.py`](skill_registry.py) | 已实测 | `SKILL.md` Frontmatter 解析、文件系统技能扫描、目录摘要生成与 `load_skill` 按需全文读取 |
| [`instructions.py`](instructions.py) | 已实测 | 工作区 `AGENTS.md`/`CLAUDE.md` 自动读取（64KB 上限）与 `@path/to/file` 内联文件引用展开 |
| [`system_prompt.py`](system_prompt.py) | 已实测 | 分节式系统提示词构建器，支持 `in_history` 尾部追加更新以保住模型前缀缓存 |

## 与上下层的关系

- **上层消费者**：上游 `tools`（暴露 `load_skill` 工具）与 `loop` 调度器（在每轮开始前组装提示词并解析 `@file` 引用）。
- **下层依赖**：[`../file/`](../file/README.md) 与 [`../session/`](../session/README.md)。

## 已知的坑与纪律

1. **按需加载节省 Token**：系统提示词仅注入技能名称与一句话描述（`format_catalog_section`），模型需要具体操作手册时才调用 `load_skill` 拉取正文。
2. **`in_history` 提示词更新纪律**：当运行途中切换模式（如进入/退出 Plan 模式）导致系统提示词变化时，`apply_to_session(in_history_update=True)` 将新提示词作为尾部节点追加，不篡改首条 `system/message`，从而保住前序对话的 KV-Cache 命中率。
