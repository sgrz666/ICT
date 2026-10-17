# next-integration-assessment.md

只做未来集成评估，不含任何改造实现（本轮边界）。结论建立在已读源码与本轮实测之上。

## 1. 口径先说清楚

- 赛题对云侧仍有硬要求，本轮验证的是**本地优先**路线的可行性底座；DeepSeek Harness 是本地跑起来的 agent harness（Web/headless/SDK/ACP/Desktop 都能本机运行），但它本身**不等于**满足赛题云侧条款，云侧那一份仍要另做。
- EduForge 现有链路（teacher-web + engine-host + catalog/templates + ray-optics 上游 + 离线包交付）是**确定性**产物链；Harness 是**模型驱动**的 agent 循环。集成的价值点不在让模型去替代确定性构建，而在「非确定性、需要探索与修复」的那几段。
- 成熟环境复用优先：本轮已证明 `pnpm install/build/typecheck` 在 Windows 原生可直接通过，不存在「必须先上 WSL」的隐性成本。

## 2. 值得重点复用的模块（按性价比排序）

| 模块 | 为什么值得复用 | 接法（未来） | 风险 |
|---|---|---|---|
| `packages/core/agent-loop` + `core/tools` + `core/session` | 这就是 Codex 式循环本体：step/turn 语义、waterfall 拦截点、`tools/pre-execute → execute → post-execute` 守卫管道、并行安全调用 | 不动 loop，只在 `ctx.tools` 挂 EduForge 能力 | 预稳定 API，`AGENTS.md` 明说「THERE WILL BE COMPATIBILITY-BREAKING CHANGES」，必须锁 SHA 逐版本跟 |
| **capability seam 三件套**（`ctx.fs` / `ctx.shell` / `ctx.subprocess` / `ctx.sandbox` / `ctx.terminals`） | 「fs 与 subprocess 共享同一执行世界」= 把 provider 指到远端/容器，Bash、PTY、LSP 一起走，不需要 fork 代码。EduForge 若要把 Agent 跑在隔离沙箱里，这是唯一干净入口 | 写一个 `ctx.fs`/`ctx.shell` provider（例如指向 ICT 的某个只读根 + 指定可写子树） | Windows 侧 ACL 置备在本机已实测受阻；跨环境要先解决 |
| `dsh-llm-deepseek`（+ `llm-pi-ai`、`llm-retry`、`token-meter`） | 已实测：Anthropic Messages 兼容、`tool_use` 正确、思考签名回传、`systemPromptUpdate: in-history` 保前缀缓存、cacheRead 命中率极高（本轮 cacheRead 171k vs input 15k）、稳定错误码族可直接拿来做可观测 | 直接用官方 provider，模型选 `deepseek-flash`；需要别的网关时用 `llm-pi-ai` 自定义 provider | `deepseek-v4-flash` 这类**仓库测试里出现过但线上目录不存在**的 id 不能照抄；目录以 `GET /models` 为准 |
| `session-persistence-jsonl` + `session-query`（`session_search`/`session_event_read`） + `session-log-export` | 会话即审计账本：durable、可 grep/导出、vN 迁移不覆盖旧代。EduForge 的交付门（Gate C 那种「测不过就拿不到包」）正好需要这种可重放证据链 | 把 Gate 的 Agent 侧证据落成 Session，报告直接从中投影 | 大 JSONL+zstd 的读取要按官方 `stat/list` 只读头，别自己扫盘 |
| `subagent` + 实验性 **Agent Teams** + `dsh-tool-ralph` + `goal` | 本轮看到模型自发用 `subagent` 去跑测试、用 `list_agents` 轮询；`goal` 有 blocked 三轮下限。这跟我们的 Gate/多阶段推进结构是同构的 | 每阶段一个 goal + 有界 ralph 轮次；把「失败即停并如实上报」写进 prompt 纪律 | Agent Teams 明确属 experimental，不作交付承诺 |
| `plan`/`todo_write`/`exit_plan_mode` + `user-questions` | `exit_plan_mode` 把计划交人审批的回路，恰好对应我们「先明确再自主推进」的协作习惯 | 长任务用 plan 模式起手，审批通过再动手 | headless 无审批通道（本轮实测），要审批就得走 Web/SDK/ACP |
| `skill` 系统（`.agents/skills/` + `dsh-tool-skill`） | 本轮最强证据：Agent 遇到 Windows ACL 失败**自发加载官方 `diagnose-windows-sandbox-acl` skill** 并遵守其「禁止手工改 ACL、失败即停」纪律。这正是我们想要的「把运维手册写成可被检索的技能」 | 把 ICT 的 README 纪律、Gate 检查表、排障手册做成 dsh skill | skill 内容进模型上下文，成本与注入面要控 |
| `sandbox-local` + `sandbox-policy` + `permission-presets` + `user-approval` | 三档预置（read-only / workspace-write / danger-full-access）+ 拒绝时上报 `full`/`partial` 强制等级，不静默裸跑 | 让交付前的 Agent 自动修只在 workspace-write 下跑，且必须有人审批回路 | 平台强制力不等价：Windows ACL 依赖宿主权限，本机已翻车一次 |
| `dsh-mcp-client` / `mcp_*` 工具 | 我们已有的 MCP 资产可以原样喂给 harness，而不是重写一遍 | 作为 Consumer 侧能力接入 | 本轮**未验证**（官方已有、本轮未测） |
| `python/sdk-runtime` + Python SDK | ICT 侧 Python 比重高；官方 Python SDK「投射同一个 loop」，运行时把 `dsh` CLI 打包成平台 wheel | 从 Python 驱动一次离线包验证会话 | 需另行核对本机 Python 3.13 + 打包链路；本轮未验证 |

## 3. 明确不建议动的部分

- **不要**用 Agent 替换确定性构建链（`PackageBuilder`、离线包 ZIP、字节收口那套）。Agent 的价值在探索与修复，不在字节确定性。
- **不要**改 `packages/core/agent-loop`、`core/tools`、沙箱与审批策略去迁就业务。官方纪律是「新行为挂到扩展点，改 loop 要改架构文档」；预稳定 API 上动核心 = 自找升级债务。
- **不要**把 EduForge 生产目录直接当 Agent workspace。本轮的做法（独立一次性工作区 + 独立 `DSH_HOME` + session cwd 即沙箱可写根）应固化为标准姿势。
- **不要**信任默认遥测：「使用官方模型 API 时上传 Session Log」出厂为**开**。业务数据进会话日志后会被上传，接入前必须先关或先做日志脱敏，并把这一条写进项目纪律。

## 4. 下一轮若要真接进来，先决条件

1. ~~解决 Windows 沙箱置备~~ **已解决**：根因是登录用户在工作区目录上缺 `WRITE_OWNER`（`D:\codeplus` 与 `D:\` 下各处 ACE 相同：`sg` 只有 `Modify`），DSH 置备工作区授权要写 security descriptor 因此报 `SetNamedSecurityInfoW … Win32 5`，与路径无关。修法就是官方那条命令（`-Path`/`-AllowRoot` 都严格等于工作区根，带备份与回滚）：新建工作区时需要各跑一次，属**一次性置备步骤**，应写进项目的「新建 Agent 工作区」流程里，而不是每次让模型去排障。跨环境替代方案是 Linux/WSL2 专用工作树（官方明令 checkout、依赖、工具链必须同环境，不可混用 node_modules）。
2. 选一个真实小场景做端到端：候选是「Gate C 的离线包浏览器实测失败时，让 Agent 读日志、定位、修模板、重跑」——它的失败→修复回路本轮已原型验证过。
3. 锁版本：把 `upstream.lock.json` 式的做法复制到 harness（记 SHA + tag + 关键 `packageManager`/`engines`），因为 0.2.x 明确会破坏兼容。
4. 定凭据策略：`.env`（本轮用法，随工作区生灭）还是 GUI 托管 `.credentials.yaml`（跨会话持久、不注入进程环境）。业务环境里我倾向前者 + 用后即换。
5. 成本核算：本轮 harness 只给 token 不给钱。接入前需要一份 DeepSeek 价目 + `token-meter` 的换算，否则 Gate 预算无法定（本轮**成本未测得**）。

## 5. 本轮未验证、但官方已具备的能力（避免下轮误判为不存在）

Desktop（Electron）应用与打包链、ACP、SDK（TS/Python）、MCP client、browser-use/computer-use 全套、LSP、PTC/`run_code` 模式、Agent Teams、图片输入、`deepseek-account` 登录路由、插件市场、schedule/jobs、compaction 三件套的实际压缩效果、会话硬中断恢复、`test:snapshot` 无密钥回放。本轮一律标 pending，未当作结论。
