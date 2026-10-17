# architecture-notes.md

按本次下载的官方源码（`master` @ `687f282e8625c6b8d11ff58211a90524be2e4317`，`dsh-v0.2.1-rc.2`）实读总结，来源文件均在括号内标注。只写读到的事实，不写推测。

## 1. 底座：Cordis，「一切皆插件」

`docs/architecture.md` + `AGENTS.md`：dsh 跑在 Cordis（vendored 于 `vendor/cordis`，通过 `pnpm-workspace.yaml` 的 `overrides: '@deepseek-ai/cosmokit': link:vendor/cosmokit` 等锁定）之上。模型适配器、工具注册表、会话日志、甚至 agent loop 本身都是插件，因此**每一项都可以从配置里替换**；注册是 effect，插件卸载即回卷。没有「特权核心」可打补丁，扩展方式是「在旁边挂一个插件」。

## 2. Profile / Bundle 分层组合

- 运行中的 dsh = 启动时按顺序叠层组合出的插件树。**profile** 是 home 下的一份命名组合（`web`/`headless`/`sdk`/`sdk-minimal`/`acp` 为出厂模板）；**bundle** 是 Cordis 配置行 + 其挂载代码的分发单元。二者都各自在 `package.json` 的 `dsh` 字段声明（`dsh.profile` / `dsh.bundle`）。
- 层序：profile 的有序 bundles → 其 `cordis.patch.yml` → home patch → `--patch` 覆盖层。patch 按 `id` 命中某一行并**整段替换其 config**（不是合并），或 `insert` 新行。`--patch` 可重复。
- `dsh-base`（`packages/bundle/base/cordis.patch.yml`）是 web/headless/sdk/acp 的共同底层：模型适配器、工具、持久化、沙箱与审批策略、settings、credentials、遥测。`dsh-headless` 只加一次性 runner；`dsh-web-app` 加浏览器应用；`sdk-minimal` 是刻意的例外，自带完整显式树、不叠 base。
- 自省命令（实测可用）：`dsh --profile headless --dump-config` 打印组合后的真实配置树；还有 `--dump-default-config`、`--dump-config-schema`。
- 启动面被脚本强制：**只有 `dsh` profile 能启动 Node 应用**，包 bin、demo、SDK argv 逃逸都被 `scripts/verify-application-entrypoints.ts` 拒绝。

## 3. 运行时与一次 turn 的真实流程

`docs/architecture.md`「Turn flow」+ `packages/core/agent-loop/src/index.ts`：

```
turn/start → 认领 next-step 输入 + 一条排队消息 → 组装 prompt 分节 + 工具 schema
 → agent/pre-step（可改写/拒绝输入）→ step/start → agent/request → prepareCall()
 → 落 user/message、按需 request/header/context → 从日志冻结模型历史
 → llm/stream → agent/assistant-stream(chunk*) → assistant/message | assistant/attempt
 → tool/call* → tools/pre-execute → tools/execute → tools/post-execute → tool/result*
 → step/end →（工具欠一次请求 或 新输入到达 → 下一步）→ agent/turn-stopping → turn/end
```

- step = 一次模型请求 + 它调用的工具；turn = 0..n 个 step。
- `agent/pre-step`、`agent/request`、`llm/stream`、三个 `tools/*` 是 **waterfall**（监听器必须调用 `next()` 才继续）；`agent/turn-stopping` 是串行无 `next()`。
- 重试不重复组装、不重复 `agent/pre-step`；取消发生在 `agent/request`/`prepareCall()` 阶段时，系统提示与用户消息都**不落盘**。
- Agent 是配置出来的：`agent-loop` 行的 `config.agents[]` 支持 `id / sessionId / provider / model / reasoningEffort / maxTokens / cwd / resumeSessionId`，并校验 `sessionId` 与 `resumeSessionId` 互斥、精确会话身份不得重复。`maxParallelToolCalls` 控制单 step 内并行安全调用数。

## 4. 上下文管理：会话日志就是模型的可见面

- 「**Model-visible ⟺ logged**」是硬纪律：任何进入模型请求的内容都必须能从会话日志重建；新的模型可见输入要求新的 session event。
- `deriveMessages()` 从日志投影模型历史；`assistant/message` 内嵌产生它的那段紧凑流，`assistant/attempt` 保留失败/重试/取消/流错误的历史但不进模型历史。fork、resume、转录、遥测、持久化都从这些 durable 结算派生，实时 UI 增量则来自 `agent/assistant-stream`。
- 投影缝隙 `dsh-session-projection` 提供 `ctx.sessionProjections`：插件注册 fold 单元，宿主用 `stateOf()` 读一份类型化状态，carrier 用 `snapshot()` 批量裁剪视图。agent loop 注册共享的 `turnBoundary` 状态。
- 压缩是分插件的：`compaction-basic`（主动压缩，要求 `contextWindow` > `maxTokens` + `headroomTokens`）、`compaction-image-offload`（超预算时发 `image/offload` 事件并重试 `IMAGE_OFFLOAD_REQUIRED`）、`compaction-tool-result-pruner`。
- 系统提示是「surface node」：`system/message` 逐条落历史；声明 `systemPromptUpdate: in-history` 的路由把变更后的提示追加在缓存历史之后（保住 KV 前缀复用），未声明的路由在首个 system 节点合并。
- 持久化格式：JSONL v0 为 `session.jsonl[.zstd]`，v1+ 为小写 `session.vN.jsonl[.zstd]`；已提交的文件永不重命名/覆盖/删除，相邻迁移只做一次 `vN → vN+1`。默认写在会话 cwd 的 `./.sessions`（实测工作区里出现该目录）。

## 5. 插件系统与扩展点

`docs/architecture.md`「Capability seams」「Where new behavior goes」：一个**缝隙**由三种角色构成 —— Service Definition / Service Provider / Consumer（通常是面向模型的工具），缺一不算缝隙。加能力=设计全三角色。换 provider 能整片改变产品：fs 与 subprocess provider 共享同一个「执行世界」，指向远端沙箱时 Bash/PTY/LSP 一起走。

| 目标 | 机制 |
|---|---|
| 加模型 provider | 在 `ctx.llm` 注册适配器 |
| 加模型可见能力 | 注册 `ctx.tools`（schema 自动进 prompt 组装） |
| 给某会话换能力集 | 组一个 agent preset（service 行需 `isolate` realm） |
| 加 shell 执行 / 持久终端 | 注册 `ctx.shell` backend / `ctx.terminals` backend + `dsh-tool-terminal` |
| 加人工命令（不过模型） | 注册 `ctx.commands` |
| 后台任务 | 注册 `ctx.jobs`，`job_*` 工具读写 |
| 文件访问或策略 | 注册 `ctx.fs` provider 或监听 `fs/*` |
| 约束被 spawn 的进程 | `ctx.sandbox` backend，消费者在 spawn 前包装 argv |
| 拦截请求/工具/turn | 对应 `agent/*`、`tools/*` 事件 |
| 加模型上下文 | `agent.inject()`，下一次被 admission 的 request 生效 |
| fork 会话 | `ctx.agents.create({ sessionId, seed, meta:{ parentSession, seedLength } })` |
| 换会话存储后端 | 实现 `SessionPersistence`（create/open/stat/list/export） |

事件分三域：Session（durable 事实，`session/event`）、Agent（活体 `agent/*`：inbox/step/status/request/validation/continuation）、Capability（`fs/*`、`tools/*`、`telemetry/*` 挂策略不进 loop）。

## 6. 工具机制

`docs/tool-catalog.md`（由 `scripts/gen-tool-catalog.ts` **真启动每个工具插件**后读 `ctx.tools.schemas()` 生成，并有 completeness guard 防止新工具漏文档）：

- 文件类：`read/write/edit/str_replace_editor`（`dsh-tool-fs`），`glob/grep`（`dsh-tool-fs-search`，自带 `@vscode/ripgrep` 二进制经 `ctx.subprocess` 调用，永不后台化）。
- 执行类：`bash`（**win32 上被禁用**）与 `pwsh`（Windows 对位，`disabled: process.platform !== 'win32'`）、`bash-persistent`/`pwsh-persistent`（PTY 后端 + `node-pty`/ConPTY）、`terminal_open/read/send/signal/list/close`、`job_*`。
- 规划与自治：`todo_write`、`exit_plan_mode`（plan 模式下把计划经 user-questions 缝隙交人审批）、`create_goal/get_goal/update_goal`（goal 有 blocked 下限 = 三个被 admission 的 round）、`schedule_*`、`skill`、`ralph`（固定前台 workflow，每轮起一个新的结构化子代）。
- 委派：`dsh-tool-subagent` / `subagent-spawn-in-process`，实验性 **Agent Teams**（`ctx.agentTeams`，durable roster + 直接 inbox 消息）。
- 交付与交互：`present`（deliverables）、`ask_user_question`（可 timed）、`plugin_manager`、`plugin_market`、`lsp`、`mcp_*`、`session_search/session_event_read/…`。
- `run_code` / PTC 模式：`tools` 行的 `config.mode` 取自 `DSH_TOOLS_MODE`；`ptc` 下 `run_code` 是唯一的 wire 工具，其余能力以生成 SDK 段落声明、由程序经绑定回灌完整受守卫的工具管线。本轮未启用（保持出厂默认=逐个工具）。
- 写前必读策略由 `dsh-fs-observation-policy`（`fs/*` 事件门插件）施加，不改 schema。

## 7. 沙箱与审批

- `sandbox` 默认 `@deepseek-ai/dsh-sandbox-local`：按平台自动选 runner（Linux Landlock/bwrap、macOS `sandbox-exec`、**Windows ACL**，见 `packages/sandbox/sandbox-windows-acl`），不可用时抛 `SANDBOX_UNAVAILABLE`，**绝不静默裸跑**；每次执行上报 `full` 或 `partial` 强制等级 + 拒绝/runner 失败签名。
- `sandbox-policy.config`：`mode = process.env.DSH_PERMISSION_MODE ?? 'workspace-write'`，`workspaceRoot = process.cwd()`，但**普通 Agent 调用用 session cwd**（`session?.header.cwd ?? workspaceRoot`）。
- `approval`（`dsh-user-approval`）：`policy = mode === 'danger-full-access' ? 'never' : 'ask'`。预置三档：`read-only` / `workspace-write` / `danger-full-access`。
- Windows 内置排障 skill 的纪律值得复用：诊断脚本必须在非受限环境跑、一次请求一条命令、带备份与可回滚命令、禁止手工改 ACL、失败即停。
- 实测到的本机现象：ACL 置备在该路径链上失败（Win32 5），拒绝形式是「需要审批但 headless 无审批通道」。安全语义正确（不放行），可用性受阻。
- **headless 关闭托管凭据与授权**：`credentials`/`authorization`/`deepseek-account` 三行 `disabled: true`，只用「启动环境 → `<cwd>/.env` → `$DSH_HOME/.env`」；因此一次性任务没有人工审批回路。

## 8. 模型接入层

`packages/llm/llm-deepseek`：`deepseek-official` 路由，默认 `baseURL = https://api.deepseek.com/anthropic`（Messages 协议，`x-api-key`），`models` 缺省即 `deepseek-flash`（text+image，`systemPromptUpdate: in-history`，`toolUpdate: addition-only`）+ `deepseek-v4-pro`；1M 上下文；`reasoningEffort` 支持 `off/low/high/max`（`off` 发 `thinking:{type:disabled}`）；图片走 Files API 并可回退内联 base64；稳定错误码族 `AUTH/QUOTA/RATE_LIMIT/CONTEXT_WINDOW_EXCEEDED/INVALID_REQUEST/SERVER/HTTP_<status>/TRANSPORT/ABORTED/TIMEOUT/STREAM_CLOSED/MALFORMED_RESPONSE/EMPTY_RESPONSE/MISSING_CREDENTIAL/INVALID_CREDENTIAL`。另有 `llm-pi-ai` 多 provider 适配器（Web Models 页写它）、`llm-deepseek-account` 账户路由、`llm-retry`、`token-meter`。请求体外还会默认附带 `dsh_session_log` 与 `dsh_plugin_packages` 上报字段（不进模型输入）。

## 9. 路径与家目录

`packages/util/home-paths`：`DSH_HOME` 环境变量优先，缺省 `~/.dsh`（本轮改指 `D:\…\.dsh-home`）；profile 落在 `$DSH_HOME/profiles/<profile>/`，用户可编辑 `cordis.patch.yml`，托管凭据 `$DSH_HOME/.credentials.yaml`（GUI 只写这份，且**不会**注入进程环境）。会话与附件、spill、storage 各归其位（`session-persistence-jsonl` root 默认 `./.sessions`）。

## 10. 工程质量手法（值得学的部分）

- 366 workspace 包，Host/Client 双聚合工程分离（因为两侧对 cordis `Context` 做同名 declaration merge，合并成一个 program 会冲突）。
- 生成物 + 一致性门：`verify-*`/`gen-*` 成对出现（tool catalog、config catalog、persistence catalog、cli-help、module-graph、cordis-api、third-party notices、dependency catalog、plugin packages…），文档由源码生成并被门禁止手写漂移。
- 供应链治理内建：pnpm `allowBuilds` 默认拒绝、`minimumReleaseAgeExclude` 精确豁免、`patchedDependencies` 显式列补丁、`postinstall` 装 worktree-local lefthook 钩子。
- 构建是 9 个 gate 的并发 DAG（`DSH_GATE_CONCURRENCY`、`DSH_FAIL_FAST`），一次报告所有独立错误。
- 双语文档体系与词数预算（`verify-doc-budgets`）、散文规范（禁隐喻、一段一行）、`Model Experience` 段落强制写明「模型看到什么 / token 与缓存效应」。
