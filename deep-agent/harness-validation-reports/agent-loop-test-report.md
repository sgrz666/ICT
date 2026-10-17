# agent-loop-test-report.md

阶段 E/F：Codex 式自主工具循环验证。所有任务都由 **DeepSeek Harness 官方 Agent** 执行（`dsh --profile headless --json`，源码启动，真实 DeepSeek API），我未代替它完成任何一步；我只负责搭建工作区、保存日志、事后独立复跑测试核对。

## 0. 测试环境

- 一次性工作区：`D:\codeplus\ICT\deep-agent\harness-smoke-workspace`（独立 git 仓库，基线提交 `b6e600c`，与 EduForge 生产代码、密钥文件、数据库完全隔离；EduForge 目录不在 Agent 的 workspace 内）。
- 启动方式：`node --import tsx/esm apps/cli/src/bin.ts --profile headless --json "<task>"`，cwd = 工作区 → 会话 `cwd` 与沙箱可写根都落到工作区（`--json` 首行 `{"type":"session","cwd":…}` 已逐条核对）。
- 权限模式：默认 `workspace-write`（沙箱 + ask 审批）；测试 3、5 另在官方文档化的 `DSH_PERMISSION_MODE=danger-full-access` 下复跑，用于越过本机 NTFS 阻塞（差异见第 6 节，两处均已如实标注）。
- 证据文件：`_logs/<stem>.jsonl`（事件流）、`.err`、`.meta`（起止/退出码/耗时）；复跑脚本 `_tools/run_headless.sh` + `_tools/summarize_events.mjs`。

## 1. 测试 1 —— 工作区探索：**通过**

Prompt：`请自主检查当前工作区的目录结构，读取 README 和主要源文件，概括项目职责，并列出你实际调用了哪些工具。`
会话 `session-d6952efb-a37c-47dc-95e1-b923abe378e7`，exit 0，20s，1 turn / 4 steps，7 次工具调用，1 次工具失败。

| # | 工具 | 输入（截断） | 结果 |
|---|---|---|---|
| 1 | `pwsh` | `Get-ChildItem -Force …` | **error**：`SetNamedSecurityInfoW failed (Win32 5): grantWrite(…)` |
| 2 | `glob` | `**/*` | `README.md cart.py test_cart.py notes.md` |
| 3–6 | `read` ×4 | 四个文件各一次 | 全部 `completed`，返回带行号正文 |
| 7 | `skill` | `diagnose-windows-sandbox-acl` | 载入官方排障 skill 正文 |

最终回答准确给出目录、职责（整数分计的购物车计价 + unittest 约定）、逐函数行为表，并如实列出自己调用过的工具。**真实的文件读取工具调用与工具结果成立。**
关键行为：第 1 步 shell 失败后，模型没有重试同一命令，而是改用 `glob` + `read` 完成任务，并主动加载官方排障 skill —— 属于观察到的自适应，而非我干预。

## 2. 测试 2 —— 自主创建并运行程序：**失败（环境阻塞，模型如实上报）**

Prompt：`请在当前测试工作区编写一个简单的 Python 计算器，支持加减乘除，并编写测试，然后自行执行测试。根据工具返回结果判断是否成功。`
会话 `session-6074ad2f-d123-4fb1-9053-eaa8e2a68d7b`，exit 0，18s，4 次调用（`glob`→`pwsh`→`skill`→`pwsh`），2 次 error。工作区未产生任何新文件。

- 两次 `pwsh` 分别失败于本地沙箱置备（Win32 5）与 `sandbox escalation to "danger-full-access" requires approval, but no approval channel is available`。
- 模型结语（原文摘录）：「任务未完成：当前工作区被 Windows 文件权限问题挡住了 … 由于 `python`/`pytest` 命令同样无法启动，计算器代码既不能写入，也不能执行测试，**所以我没有虚报测试结果**」，并建议用户临时切到「完全权限」。
- 判定：验收未达成（既未建文件也未执行测试）。**注意一处模型自身的不严谨**：它声称「代码既不能写入」，但本轮从未调用过 `write`；测试 4 证明同环境下 `write` 是可用的。即它把 shell 失败外推成了写入失败。诚实上报值得肯定，结论准确性有偏差 —— 两者都记录在案。

## 3. 测试 3 —— 失败后自主修复：**通过（核心验收项）**

Prompt：`请运行现有测试，分析失败原因，修改程序并重新测试，直到确认修复有效；如果无法修复，请如实汇报。`

### 3a. `workspace-write` 下（会话 `session-f…`，stem `t3`）：exit 0，43s，12 steps，17 次调用，5 次工具失败

真实序列（节选）：`working_directory` → `pwsh`(error) → `skill(diagnose-windows-sandbox-acl)` → `pwsh`(跑修复脚本，error：无审批通道) → `pwsh`×2 换 workdir 重试(error) → `glob` → `read`×4 → `subagent`（派子代理去跑测试）→ `pwsh`(error) → `job_list` → `list_agents` → **`edit`（修复 `apply_discount`）** → `read`（复核改后代码）。

- 这一轮里它**确实改了代码**（`git diff` 显示 `apply_discount` 改为整数域半分进位），但因 shell 全灭而**没能亲自重跑测试**。
- 我独立复跑核对：`python -m unittest` → **OK**（其修复有效）。随后我把 `cart.py` 还原到基线（`git checkout HEAD -- cart.py`），确保 3b 不是「提前人工修好」。

### 3b. `danger-full-access` 下（会话 `session-18a2e93f-6892-4fc3-b1e8-b0572ddc96d1`，stem `t3_fullaccess`）：exit 0，24s，8 steps，14 次调用，0 次工具失败

要求的完整闭环逐条可审计：

| step | 事件 | 证据 |
|---|---|---|
| 1 | `pwsh` 列目录 | completed，列出 7 个文件 + `.git` |
| 2 | `read` ×6 | 读全部源码/测试/README |
| 3 | `pwsh` `python -m unittest -v` | **真实失败输出**：`test_cart_total_end_to_end … FAIL`、`test_discount_rounds_half_up … FAIL`（3 失败） |
| 4 | 模型读数并定位 | 输出原文：「失败都指向同一处根因：`apply_discount` 用 `//` 直接向下取整，而项目规则是四舍五入到分、半分进位」 |
| 4 | **`edit` `cart.py`** | `discount_cents = (total*percent + CENTS_PER_UNIT//2) // CENTS_PER_UNIT` |
| 5 | `pwsh` 复跑测试 | **真实通过输出**：三个用例转 `ok` |
| 5 | `pwsh` 自写边界脚本 | **自己抓到自己的错**：`AssertionError: (1, 50, 0, 1)`，exit 1 |
| 6 | `pwsh` 修正脚本后复跑 | `boundary checks OK`，`CLI example total: 9.97` |
| 6 | `pwsh` 跑 CLI | `9.97 exit=0`；非法折扣 → stderr + `exit=2` |
| 7 | `pwsh` `git diff` | 只改 `cart.py` |
| 8 | 最终回答 | 「已修复并验证通过 … 24 个测试全部通过（修复前 3 个失败）」 |

- **执行失败 → 读取错误 → 修改 → 再执行** 出现两次（测试一次、自己的边界脚本一次），且第二次是模型发现自己脚本的断言写错后主动纠正 —— 不是人工干预。
- 事后我独立复核：`python -m unittest` → `Ran 24 tests … OK`。模型结论与磁盘事实一致。
- 无人工接管；无提前修好（基线在 3b 前由我还原，且 3b 首步输出即为 3 个 FAIL）。

## 4. 测试 4 —— 多工具组合：**部分通过（文件与计划成立，执行被环境挡住）**

Prompt：`请阅读当前工作区，制定一个简短实施计划，新增一个带输入校验的命令行功能，运行相关测试，最后汇报修改文件与实际测试结果。`，stem `t4`，exit 0，58s，18 次调用，4 次 error。

工具组合：`working_directory` → `pwsh`×4（全 error）→ `skill` → `glob` → `read`×6 → **`write`×3** → **`todo_write`×2** → `edit` → `subagent` → `list_agents`×4。

- 计划：用 `todo_write` 落了显式计划（模型最终回答里列出 5 步「实施计划（已执行）」）。
- 产物：新增 `cart_cli.py`（`--item QTY:CENTS` 可重复 + `--discount`，数量≥1、单价≥0、折扣 0–100 整数、非法输入 stderr + 退出码 2）、`test_cli.py`（19 个用例）、README 增补用法与校验规则。文件确实在磁盘上，且被测试 3b/5 复用。
- 执行与汇报：**它没有假装跑过测试**。原文：「**实际测试结果：未能执行（不是通过）** —— 所有 shell 调用在进程启动前就失败了，因此没有产生任何真实的 unittest 输出」，并粘贴了原样错误。
- 副产物：排障时留下 `.dsh-write-probe`（6 字节，内容 `probe`），模型自述「当前 shell 不可用，我无法删除」。属真实遗留项，未清理（清理需绕过它的沙箱，不在本轮范围）。

## 5. 测试 5 —— 中断与恢复：**通过**

机制：官方 `--session-id <id>` 采纳已持久化 Session（`dsh --profile headless --session-id …`）。恢复的是测试 3b 的 `session-18a2e93f-…`。Prompt：`这个购物车项目现在还有什么没做完的？请先回顾你已经做过的事情，再给出下一步建议。`，stem `t5_resume`，exit 0，32s，4 次调用（`pwsh`×3、`grep`×1），0 失败。

- 事件流首行仍是同一 `sessionId`，且 `turn_start` 为 **turn 2** —— 对话历史续写，而非新会话。
- 上下文保留可证：它准确复述了自己上一轮做过的事（跑测试、3 个失败用例名、根因、只改了 `apply_discount`、复跑 24 通过、CLI 实测 `9.97`/退出码 2）。这些细节在**新 prompt 里没有**，也无法只靠读文件得到（它需要知道「修复前是 3 个失败」）。
- 它还发现了一个真实不一致：基线提交信息写「2 failing tests」而实际 3 个失败，并正确推断出 `test_cli.py`/`cart_cli.py` 是未跟踪的新增文件、README 有未提交改动 —— 说明它同时使用了会话历史和当轮工具取证。
- 不是「文件还在就算恢复」：日志目录 `.sessions/` 内的持久化会话被显式采纳，工具历史由事件流回放得到。
- 未验证项：硬中断（进程被杀）后的恢复语义；本轮是正常结束后再采纳。

## 6. 权限审批与安全限制（观察到的）

| 观察 | 证据 |
|---|---|
| 默认权限即 `workspace-write`（沙箱 + ask），Web UI 明示「访问模式，当前：工作区内修改」，Settings → 通用设置 有「选择新会话的默认权限模式」 | UI 无障碍树快照 |
| Windows 用 ACL 置备工作区可写根；本机在 `D:\codeplus\ICT\…` 链路上稳定失败：`SetNamedSecurityInfoW failed (Win32 5): grantWrite(…)` | 每次 `pwsh` 调用的 `tool_result` 原文 |
| 官方为此内置 skill `diagnose-windows-sandbox-acl`（`packages/sandbox/sandbox-windows-acl/assets/`），Agent 在 t1/t2/t3/t4 **自发加载** | `skill` 工具调用与返回正文 |
| 修复脚本需解除沙箱；headless 无审批通道 → 明确拒绝：`sandbox escalation to "danger-full-access" requires approval, but no approval channel is available`（**不静默放行**） | t2/t3 `tool_result` |
| 官方 skill 同时规定：诊断脚本必须在**非受限**环境下跑（受限跑会把沙箱自身限制误报成缺权限）、禁止手工改 ACL、禁止提权跑、失败即停并回滚。我据此**没有**擅自修改 D 盘 NTFS 权限，改用官方 `DSH_PERMISSION_MODE` 复跑并标注差异 | `SKILL.md` 全文 |
| 沙箱「拒了但拒的是自己的置备步骤」这一形态应视为宿主环境问题，不是框架策略生效的证据 | 分析结论 |
| 遥测默认开：Settings →「在使用官方模型 API 时上传 Session Log」默认 `checked=true`（会向 DeepSeek 上传会话日志以改进模型）。本轮**未关闭**，以保留官方默认行为；冒烟工作区不含业务数据 | UI 快照 |
| Agent 全程未接触 EduForge 生产代码、`.env`、数据库：会话 `cwd` 固定在冒烟工作区，沙箱可写根由 session cwd 推导 | `--json` 首行 + `sandbox-policy` 源码 |

## 7. 汇总表

| 测试 | 模式 | exit | 耗时 | turns/steps | 调用数 | 工具失败 | 结果 | 人工接管 |
|---|---|---|---|---|---|---|---|---|
| 1 探索 | workspace-write | 0 | 20s | 1/4 | 7 | 1 | **通过** | 否 |
| 2 建计算器并测试 | workspace-write | 0 | 18s | 1/4 | 4 | 2 | **失败**（环境阻塞，如实上报，无产物） | 否 |
| 3a 修复 | workspace-write | 0 | 43s | 1/12 | 17 | 5 | 改了代码但**未能亲自重跑**；我独立复跑确认修复有效 | 否（仅事后核对） |
| 3b 修复 | danger-full-access | 0 | 24s | 1/8 | 14 | 0 | **通过**：失败→读取→改→复跑绿，两次自纠 | 否 |
| 4 多工具组合 | workspace-write | 0 | 58s | 1/多 | 18 | 4 | **部分通过**：计划/文件成立，测试未能执行（模型如实说明） | 否 |
| 5 恢复 | danger-full-access | 0 | 32s | turn 2/3 | 4 | 0 | **通过**：续写同一 Session，保留上下文与工具历史 | 否 |

Token 合计（各运行 step 求和，未测得货币成本）：input 14,888 / output 14,319 / cacheRead 171,136 / total 200,343（不含冒烟与 t1/t4 的完整分解，见 `_logs/*.jsonl` 与 `api-connectivity-report.md`）。

## 8. 结论与验收判定

- 「至少出现一次可审计的多轮工具反馈循环，并且有真实测试结果」——**达成**（测试 3b：真实 FAIL 输出 → 读取错误 → `edit` → 真实全绿输出，另有模型自纠一次；事后由我独立复跑核对为 24 tests OK）。
- 官方源码可构建、Web UI 可启动、真实 DeepSeek API 可调用 ——**达成**。
- 测试 2 与测试 4 的「执行并汇报测试结果」子项**首轮在 `workspace-write` 下未通过**，原因是指向宿主 NTFS 权限的沙箱置备失败（登录用户缺 `WRITE_OWNER`），而非模型或 API 缺陷；定位并用官方脚本修复后，两者已在同一默认权限模式下复跑通过（第 9 节）。未改用 Mock、未手工代做。
## 9. 修复后复跑（2026-10-17 21:17–21:22）：**测试 2、3、4 全部在默认 `workspace-write` 下通过**

前面第 2、3a、4 节的失败根因已定位并修好，以下是复跑结果。原始失败记录保留在上文，不覆盖——它记录了「模型在阻塞下如何如实上报」，本身就是有效证据。

### 9.1 根因（实测，非推测）

- 换路径无效：把同一份破损基线放到 `D:\dsh-smoke` 后，confined `pwsh` 仍报 `SetNamedSecurityInfoW failed (Win32 5): grantWrite(D:\dsh-smoke)`；换 `workdir` 到 `C:\Users\sg\AppData\Local\Temp` 也是同一条错误（`_logs/probe_shell.jsonl`）。
- 权限读盘：工作区与 `D:\codeplus`、`D:\codeplus\ICT`、`deep-agent` 各级 ACE 一致 —— `sg` 只有 `Modify`（Administrators/SYSTEM 有 FullControl），无 AppContainer 污染、无显式 deny。
- 官方脚本的判定给出精确结论：`verdict: PRECONDITION`，`before: {writeOwner: false, writeDac: true}` → `after: {writeOwner: true}`。即 **登录用户缺少 `WRITE_OWNER`**，而沙箱置备工作区要写 security descriptor，因此被 Windows 拒绝。属宿主权限问题，非框架缺陷。

### 9.2 修复方式（官方路径，可回滚）

只用了官方 skill 的那一条命令，未手工改 ACL、未提权、未 `runas`：

```powershell
& '…\sandbox-windows-acl\assets\diagnose-windows-sandbox-acl\scripts\diagnose-windows-sandbox-acl.ps1' `
  -Path 'D:\codeplus\ICT\deep-agent\harness-smoke-workspace' `
  -AllowRoot 'D:\codeplus\ICT\deep-agent\harness-smoke-workspace' `
  -Out 'D:\codeplus\ICT\deep-agent\harness-smoke-workspace\_acl-out'
```

结果：`GRANTED … SID=S-1-5-21-…-1001`，`verification: verified`，`nextAction: verify_original_confined_operation`，`visited 19`，`refused 0`，备份与回滚命令落在 `_acl-out\acl-backup-*.json(.ps1)`。`-AllowRoot` 严格等于工作区根本身（遵守 skill「不得放宽到祖先目录」）。

修好后先做了一次最小确认（`_logs/probe_after.jsonl`）：confined `pwsh` 真跑出 `Ran 5 tests … 2 FAIL`，exit 0，8s，1 次调用 —— 沙箱工作正常，随即把测试 2/3/4 全部还原到**默认权限模式**重跑。

### 9.3 复跑逐条证据

复跑前把 `harness-smoke-workspace` 用 `git checkout HEAD -- .` 还原到提交 `b6e600c` 的破损基线（删除 `cart_cli.py`/`test_cli.py`/`.dsh-write-probe`），并核对 `Ran 5 tests … FAILED (failures=2)`，确保不是提前修好。

| 复跑 | 权限模式 | 耗时 | steps | 调用数 | 工具失败 | 结果 |
|---|---|---|---|---|---|---|
| 测试 2 建计算器并跑测试（`t2_fixed`） | workspace-write | 18s | 9 | 11（`pwsh`×2、`glob`、`read`×3、`todo_write`×3、`write`×2） | 0 | **通过**：自主新建 `calculator.py` + `test_calculator.py`（加、减、乘、除、除零 raises），并真的执行了测试 |
| 测试 4 多工具组合（`t4_fixed`） | workspace-write | 56s | 13 | 23（`pwsh`×7、`read`×7、`edit`×4、`write`×2、`todo_write`×2、`glob`） | 0 | **通过**：`todo_write` 落计划 → 写 `cart_cli.py`（`2x499 1x52 --discount 5`，数量≥1、单价≥0、折扣 0–100 整数，非法输入退出码 2）→ 写并 4 次迭代 `test_cart_cli.py` → `Ran 13 tests OK` → CLI 实测 `10.50 / 9.98 / exit=2` → 全量 `Ran 23 FAILED (failures=2)`，**并正确判定这 2 个失败属基线提交 `b6e600c`、不在自己改动范围内**，未粉饰 |
| 测试 3 失败后自主修复（`t3_wsw`） | workspace-write | 23s | 10 | 15（`pwsh`×6、`read`×8、`edit`×1） | 0 | **通过**：见 9.4 |

### 9.4 `t3_wsw` 的完整闭环（这才是验收项该有的样子）

1. step 4：`python -m unittest -v` → 真实失败输出「23 个用例中 2 个失败，`998 != 997`」。
2. step 5：模型没有直接改代码，而是先跑一条算式核对：`exact: 52.5 / current: 998 / half-up: 997` —— 用工具取证确认根因。
3. step 6：`edit cart.py` 改成整数域半分进位。
4. step 7：复跑 → 「23 个测试全部通过」。
5. step 8：自写 8 组边界用例复验（`1050@5%→997`、`999@100%→0`、`1051@5%→998`、`105@50%→52`…）全部 OK。
6. step 9：`git --no-pager diff -- cart.py` 自证只改了那一个函数。
7. 事后我独立复跑：`python -m unittest` → **`Ran 23 tests in 0.003s / OK`**；`git diff --stat` → `README.md +14, cart.py +10/-2`。模型结论与磁盘事实一致。

### 9.5 修正后的结论

- 阶段 E 五项：**测试 1、2、3、4、5 全部通过**，其中 1、2、3、4 均在官方默认 `workspace-write` 权限模式下取得（测试 5 复用 `session-18a2e93f-…` 的 Session 采纳机制，见第 5 节）。
- 第 2、3a、4 节里「失败/部分通过」的原因已被消除，且消除方式是官方文档化的那一条命令，不是关沙箱、不是换 Mock、不是我代做。
- Web UI 的会话创建与权限审批也已实测闭环（允许与拒绝两条路径都走过）：见 `installation-report.md` 第 5 节。关键取证 —— 工作区内 `写入 note.txt` 直接成功且磁盘核对内容为 `ui-ok`；工作区外 `D:\dsh-smoke\outside.txt` 先被 `sandbox: file access denied under workspace-write mode` 拒绝，模型改用 `danger-full-access` 重试触发第二次审批，我点「拒绝」后磁盘上确实没有该文件。审批界面用白话解释了改什么、备份与恢复方式，并展示了将要执行的确切命令。
- 沙箱在修复后仍按预期工作：写操作限在工作区、越界需要审批；本轮工作区内动作无需审批即可完成，符合 `workspace-write` 语义。
- 遗留在工作区的排查产物：`_acl-out/`（权限备份与回滚脚本）；`.dsh-write-probe` 已在复跑前删除。

