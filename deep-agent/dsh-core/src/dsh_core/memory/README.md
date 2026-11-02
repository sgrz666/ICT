# memory — 长时记忆与上下文管理子系统 (Memory Subsystem)

> 2026-10-31 状态修正：主循环目前调用规则摘要路径，异步模型摘要方法未接入自动压缩；八段标题齐全不证明任务信息被保留，也不证明 KV-cache 命中。

**职责**：提供大模型上下文容量估算、预算监控以及多阶段对话上下文压缩机制。负责基于字符密度的快速 Token 估算与模型真实用量累计（`TokenMeter`）、免模型调用的超长工具结果确定性头尾保留截断（`OutputPruner`），以及基于 KV-cache 前缀复用理念的八段式 Markdown 结构化摘要与表面原位遮蔽（`CompactionEngine`）。

## 内容

| 文件 | 状态 | 说明 |
|---|---|---|
| [`token_meter.py`](token_meter.py) | 已实测 | Token 估算器与用量累计器，采用 4 字符/Token 启发式规则结合角色与消息结构开销 |
| [`pruner.py`](pruner.py) | 已实测 | 工具结果修剪器，超限字符按保留头部与尾部、中间插入省略标记执行零开销裁剪 |
| [`spill.py`](spill.py) | 已实测 | 超大工具输出无损落盘与多模态图像卸载：对标 `@deepseek-ai/dsh-spill-local`、`dsh-spill-policy` 与 `dsh-compaction-image-offload`，超限输出先完整写入磁盘再截断并附带可回读路径提示 |
| [`compaction.py`](compaction.py) | 已实测 | 结构化上下文压缩引擎，生成八段式（Primary Request, Key Concepts, Files, Errors, Pending, Current, Next, Critical Context）检查点并执行表面替换 |
| [`__init__.py`](__init__.py) | 已实测 | 子系统 API 导出入口 |

## 与上下层的关系

- **上层依赖**：被顶级包 [`../__init__.py`](../__init__.py) 统一导出；在智能体循环每一步（pre-step）或捕获上下文超限错误时被调度。
- **平级协同**：
  - 依赖会话子系统 [`../session/`](../session/README.md) 的 `SurfaceManager` 执行 `replace` 表面替换。
  - 通过 `BaseLlmClient` 发起 KV-cache 前缀对齐的摘要生成。
- **外部应用**：供长程教学对话（多轮物理模拟器交互、学生连续多题辅导）在有限 Context Window 下保持核心记忆不丢失。

## 已知的坑与纪律

1. **两阶段执行顺序**：必须先执行零计算成本的 `prune_tool_results`，仅当修剪后仍超出安全阈值时才触发第二阶段的大模型摘要生成，避免算力与费用浪费。
2. **系统提示词不可遮蔽**：在执行八段式摘要表面替换时，必须保留最初的 `system/message` 与最新轮次的消息，严禁将系统指令作为历史消息折叠遮蔽。
3. **前缀缓存复用**：请求大模型生成摘要时，应沿用原会话的前缀上下文并仅在末尾附加压缩指令，以最大化上游大模型服务商的 KV Cache 命中率。
