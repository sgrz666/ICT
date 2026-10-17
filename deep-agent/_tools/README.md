# _tools/ — 复现驱动

## 职责

阶段 E 的**执行入口**：用官方 `dsh --profile headless --json` 在一次性工作区里跑真实 DeepSeek API，把事件流落成可审计的日志，并压成人能读的调用表。测试必须由 Harness Agent 完成，本目录只负责「启动它 + 记录它」，不含任何代做逻辑。

## 内容

| 文件 | 是什么 | 为什么长这样 |
|---|---|---|
| [run_headless.sh](run_headless.sh) | 一次 headless 运行的封装：`bash run_headless.sh <日志名> <prompt文件> [额外参数]` | 它导出 `COREPACK_HOME`（避开本机全局 corepack 的 EPERM）、`DSH_HOME`（隔离到本目录，不写 C 盘）、`TSX_TSCONFIG_PATH`（源码启动在仓库外工作的必要条件，坑 1）、`DEEPSEEK_API_KEY`（从 `deepseek-harness/.env` 读，**永不打印**）；从工作区目录启动 node 使会话 `cwd` 与沙箱可写根落到工作区；`WORKSPACE_DIR=` 可换工作区 |
| [summarize_events.mjs](summarize_events.mjs) | 把 `_logs/<stem>.jsonl` 压成调用表 | 按 `session / turn_start / step_start / tool_call / tool_result / step_end / turn_end / final` 顺序输出编号、工具名、输入截断、状态与结果截断，并汇总 turns/steps/调用数/工具失败数/各工具计数/token 合计与 `exit`+`elapsed_seconds`。所有报告里的数字都由它产出，避免手抄 |
| [prompts/t1.txt](prompts/t1.txt) … [t5.txt](prompts/t5.txt) | 五项测试的任务原文（工作区探索 / 建计算器并跑测试 / 失败后自主修复 / 多工具组合 / 中断恢复） | 原文照抄任务书，不改写，否则「Agent 是否真被这句话驱动」就失去可比性 |
| [prompts/probe_shell.txt](prompts/probe_shell.txt) | 只读探针：跑 `python -m unittest -v` 并汇报，明令不许改文件 | 用来在改权限前后各跑一次，隔离出「阻塞来自沙箱置备」而不是来自模型能力 |

## 与上下层的关系

- 上游依赖：`../deepseek-harness`（已构建）、仓库根 `.env`、`../harness-smoke-workspace`（默认工作区）。
- 产出：`../_logs/<stem>.jsonl`、`.err`、`.meta`。
- 消费者：`../harness-validation-reports/agent-loop-test-report.md` 的每一张调用表。
- 恢复会话：`bash run_headless.sh t5 prompts/t5.txt --session-id <../_logs 首行里的 sessionId>`。

## 已知的坑与纪律

1. **必须设 `TSX_TSCONFIG_PATH`**。`node --import tsx/esm …` 依赖当前目录发现 tsconfig `paths`；在仓库外裸跑会解析不到 `tsx/esm`，改用 `file://` 绝对路径又会报 `@deepseek-ai/cordis does not provide an export named 'FiberState'`。
2. **prompt 变量必须在 `cd` 到工作区之前读**（曾有 bug 是先 `cd` 导致 `prompts/t1.txt` 找不到，三次空跑）。改脚本时保留这个顺序。
3. 额外参数（如 `--session-id`）要放在 prompt 之前传入 `$@`，官方 CLI 才认。
4. **不许在这里代 Agent 做题**。任何「先把测试修好再让它跑」都会让测试 3 的验收失效；基线还原动作只允许发生在两次运行之间，并留痕在报告里。
5. 不要在脚本或 prompt 里回显 key；日志里出现的本地 UI token 属同类，落盘即脱敏。
