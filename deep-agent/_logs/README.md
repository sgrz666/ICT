# _logs/ — 原始证据（46 个文件）

## 职责

阶段 B–F 的**一手证据**。报告里任何「通过 / 失败 / 多少调用 / 多少 token」都必须能在这里找到出处文件。本目录是证据链的底部，不是结论的副本。

## 内容

### 环境与构建（阶段 A/B/C）

| 文件 | 内容 |
|---|---|
| `00_environment.txt` | 真实 PATH 下的 node / npm / git / python / corepack / pnpm 版本，以及 Windows `cmd` 侧核对（Qoder 托管 shell 的 PATH 混有第三方 shim，首轮曾报出虚高版本） |
| `01_pnpm_install.log` | `pnpm install`：366 workspace、供应链门 `✓ … (1725 entries in 16.4s)`、postinstall lefthook、`Done in 2m 1.7s`、`INSTALL_EXIT=0` |
| `02_pnpm_build.log` | `pnpm run build`：九门逐条耗时（native addon 1.44s / host compiler 172.37s / Host bundle 26.06s / Desktop 2.73s / client compiler 82.41s / Client bundle 30.24s / Web build 12.37s / host check 166.58s / client check 75.21s）、`9 passed, 0 failed`、`BUILD_EXIT=0` |
| `03_typecheck.log` | `pnpm run typecheck`：`5 passed, 0 failed in 16.12s`、`TYPECHECK_EXIT=0` |
| `04_web_server.log` | 首次 `dsh web --no-open` 启动行与 URL（token 已脱敏） |
| `05_dump_config_headless.txt` | `dsh --profile headless --dump-config` 全量组合树（`sandbox-policy` 的 `mode`/`workspaceRoot`、`approval.policy`、`agent-loop.agents`、win32 下 `tool-bash` 被禁用等真实出厂值都取自这里） |
| `09_web_picker.log`、`10_web_picker.log` | 带官方 `--patch …/pin-browse-picker.overlay.yml` 的启动尝试：`09` 记录 `error: unknown option '--patch'`（参数位置坑），`10` 是成功形态与 URL |
| `06_smoke_ok.json` / `.err`、`07_smoke_cwdtest.json` / `.err` | 两条最小 API 冒烟：`06` 从仓库根启动（暴露 `cwd` 会落到仓库根），`07` 加 `TSX_TSCONFIG_PATH` 从工作区启动（`cwd` 正确、4s、cacheRead 5,760） |

### Agent 循环运行（阶段 E，`<stem>.jsonl` + `.err` + `.meta`）

`.jsonl` 是官方 `--json` 事件流（`session`/`status`/`thinking`/`text`/`tool_call`/`tool_result`/`final`），`.meta` 是 `exit` 与 `elapsed_seconds`。

| stem | 权限模式 | 结果 | 关键看点 |
|---|---|---|---|
| `t1` | workspace-write | exit 0 / 20s / 7 调用 / 1 工具失败 | 首次 pwsh 被 ACL 挡 → 改走 `glob`+`read`×4 → 自发 `skill(diagnose-windows-sandbox-acl)` |
| `t2` | workspace-write | exit 0 / 18s / 4 调用 / 2 失败 | **首轮未通过**：`FINAL` 原文「任务未完成…我没有虚报测试结果」 |
| `t2_fixed` | workspace-write | exit 0 / 18s / 11 调用 / 0 失败 | 修权限后复跑：`write`×2 真建 `calculator.py`+`test_calculator.py`，`pwsh`×2 真执行 |
| `t3` | workspace-write | exit 0 / 43s / 17 调用 / 5 失败 | 改了码但跑不了测试；含 `subagent`/`job_list`/`list_agents` 的绕行尝试与「无审批通道」拒绝 |
| `t3_fullaccess` | danger-full-access | exit 0 / 24s / 14 调用 / 0 失败 | 首个完整闭环：FAIL 输出 → `edit` → 复跑全绿 → 自写边界脚本被 `AssertionError` 打回再改正 |
| `t3_wsw` | **workspace-write** | exit 0 / 23s / 15 调用 / 0 失败 | **验收项的正式形态**：step 4 真失败 → step 5 跑算式取证 `exact 52.5 / current 998 / half-up 997` → step 6 `edit` → step 7 全绿 → step 8 八组边界 → step 9 `git diff` |
| `t4` | workspace-write | exit 0 / 58s / 18 调用 / 4 失败 | 部分通过：`todo_write` 计划 + `write`×3 产物，`FINAL` 明写「实际测试结果：未能执行（不是通过）」 |
| `t4_fixed` | workspace-write | exit 0 / 56s / 23 调用 / 0 失败 | 复跑：13 CLI 测试 `OK`、CLI 实测 `10.50 / 9.98 / exit=2`、全量 23 里 2 个失败被正确归给基线提交 |
| `t5_resume` | danger-full-access | exit 0 / 32s / 4 调用 / 0 失败 | `--session-id session-18a2e93f-…` 采纳旧会话，事件流显示 **turn 2** 且能复述上轮细节（含指出我基线提交信息写「2 failing」实为 3） |
| `probe_shell` | workspace-write（工作区在 `D:\dsh-smoke`） | exit 0 / 47s / 8 调用 / 2 失败 | 换路径复现同一 `Win32 5` → 证明与路径无关，是宿主权限 |
| `probe_after` | workspace-write | exit 0 / 8s / 1 调用 / 0 失败 | 官方脚本置备权限后，confined `pwsh` 立刻真跑出 2 个 FAIL |
| `t3_agent_fixed_cart.py` | — | — | `t3` 那一轮模型改出的 `cart.py` 快照，留存于我还原基线**之前** |

## 与上下层的关系

- 生成者：[../_tools/run_headless.sh](../_tools/run_headless.sh)（Agent 运行类）与手工命令重定向（构建类）。
- 摘要工具：[../_tools/summarize_events.mjs](../_tools/summarize_events.mjs)。
- 消费者：[../harness-validation-reports/agent-loop-test-report.md](../harness-validation-reports/agent-loop-test-report.md)。
- 会话持久化不在这里，在工作区的 `.sessions/`；恢复用的 `sessionId` 取本目录各 `.jsonl` 首行。

## 已知的坑与纪律

1. **落盘即脱敏**：`dsh web` 启动行带本地 UI token（等价于本机免登录访问凭据）。提交前必须跑 `grep -rlE 'token=[A-Za-z0-9_.-]{20,}' _logs` 并确认无输出（本目录已处理）。
2. 永不写入明文 API key；`sk-` 扫描必须为空。
3. `.err` 里 stderr 的 `dsh: reasoning:` 段可能很长，属正常，不要截断成「看起来干净」的版本。
4. 只追加不改写：一次运行一个 stem，重跑就换新 stem（`_fixed`、`_wsw` 这种后缀承载「同 prompt、不同环境」的含义）。
5. `08_*` 不存在（该次尝试未成功启动，日志留在 `09` 里），不是缺失。
