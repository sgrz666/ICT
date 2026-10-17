# installation-report.md

阶段 A/B：环境与官方源码、依赖安装、源码构建、类型检查。全部命令实测于本机，未使用发行包替代。

## 1. 环境（实测）

| 项 | 值 | 说明 |
|---|---|---|
| OS | Windows 10.0.26200.8246，AMD64，18 逻辑核 | `cmd /c ver` |
| Shell（本 Agent） | Git Bash（Qoder 托管 PATH） | 注意：该 PATH 中混有 Doubao 沙箱 shim，首轮探测报出的 node/git/python 版本与真实 PATH 不一致，已用 `cmd //c` 复核 |
| Node.js（shell PATH） | v24.14.1，`C:\Program Files\nodejs\node.exe` | 满足官方 `engines.node: ^22.19.0 \|\| >=24.0.0` |
| npm | 11.11.0 | |
| Corepack | 0.34.6 | 未执行 `corepack enable`（本机有 EPERM 前科），改用 `COREPACK_HOME` + `corepack pnpm` |
| pnpm | 11.28.5 | 来源：仓库 `package.json` 的 `packageManager: "pnpm@11.28.5"`，以本次下载实际值为准，非文档臆测 |
| Git | 2.33.1.windows.1（`/mingw64/bin/git`） | 满足官方「Git 2.26+」 |
| Python | 3.13.13 | 工作区测试用 |
| PowerShell | 7.6.4（`pwsh`） | 官方 Windows 组合用 `pwsh` 工具，`bash` 工具在 win32 被禁用 |
| WSL | Ubuntu-24.04（Stopped，未使用）、docker-desktop | 官方文档明确 WSL 可选，本次全程 Windows 原生 |
| 磁盘 | D: 约 761 GB 可用 | 克隆 466 MB 工作树 + 676 MB node_modules 无压力 |

官方要求（实际读自克隆文件，非二手文档）：
- `docs/development.md` Prerequisites：Node 22.19+/24+；需开启 Node 的 TypeScript type-stripping（`NODE_OPTIONS` 不得含 `--no-experimental-strip-types`）；Corepack 管理的 pnpm；Git 2.26+；可选 DeepSeek key。
- `README.md` Run from source：`git clone` → `pnpm install` → `pnpm run build` → `pnpm dsh web`。
- `docs/development.md` First-time setup：「Setup is complete when `pnpm run typecheck` exits successfully.」
- `SAFETY.md`：预览版、未做安全审计、可执行模型生成的代码、沙箱不等于隔离保证。
- `.gitmodules`：不存在（HTTP 404），`git submodule status` 空输出，rc=0 → 本仓库无 submodule。

## 2. 落盘位置

- 工作目录：`D:\codeplus\ICT\deep-agent`（用户指定）。
- 官方源码：`D:\codeplus\ICT\deep-agent\deepseek-harness`。
- 为避免污染 EduForge 仓库，在 `D:\codeplus\ICT\.gitignore` 增加一行 `deep-agent/`（带注释，说明理由与 `source/upstream/ray-optics/` 同类）。除这一行外未改动 EduForge 任何代码、依赖或数据库。
- 该 `.gitignore` 行已被并行会话的一次提交带入 `main`（`git log -1 -- .gitignore` → `8f0d5a7 Gate C §C.6：把离线交付物真的装进 zip，并给假验证装上四件缺失的仪器`），不是我提交的；结果是忽略规则现已持久生效。
- README 纪律缺口（登记，不擅自改他人正在编辑的文件）：按仓库 `AGENTS.md`，`.gitignore` 变更应同轮反映到根 `README.md` 的目录地图说明。`deep-agent/` 属被忽略的外部验证工作区、不入库，因此不需要为它写 README；但根 README 是否要提一句「本机另有被忽略的第三方验证目录」留给维护者决定。
- 隔离的 Harness home：`DSH_HOME=D:\codeplus\ICT\deep-agent\.dsh-home`（默认 `~/.dsh` 不存在，本次未写入 C 盘）。

## 3. 克隆（阶段 A 验收）

```
git clone https://github.com/deepseek-ai/deepseek-harness.git      # 完整克隆，未用 --depth、未用 sparse
```

| 项 | 实测值 |
|---|---|
| remote | `https://github.com/deepseek-ai/deepseek-harness.git` |
| 默认分支 | `master`（不是 main） |
| `git rev-parse HEAD` | `687f282e8625c6b8d11ff58211a90524be2e4317` |
| `git describe --tags` | `dsh-v0.2.1-rc.2` |
| 提交总数 | 22,395 |
| `git status --short` | 空（工作树干净） |
| checkout 文件数 | 16,297 |
| 工作树体积 | 466 MB |
| HEAD 提交 | `Merge pull request #6408 … worktree/release-dsh-0.2.1-rc.2`，2026-10-17 15:22:43 +0800 |
| `package.json` 版本 | `@deepseek-ai/dsh-root` 0.2.1-rc.2（与 UI 内「当前版本：0.2.1-rc.2」一致） |

实际模块结构（读自 `pnpm-workspace.yaml` + 目录树，共 366 个 workspace 项目）：`vendor/*`、`packages/*/*`（core、api、llm、shell、subprocess、ssh、terminal、ptc-runtime、sandbox、fs、lsp、skill、web、computer-use、browser-use、compaction、context、subagent、jobs、bundle、workflow、todo、plan、goal、schedule、preset、guard、extensions、session、session-query、attachment、spill、storage、workspace、feedback、identity、settings、credentials、acp、interaction、boot、sdk、host、client、mcp、experimental、test-support、util）、`native/system`、`apps/*`（cli、desktop、desktop-host、web、plugin-market-generator）、`benchmarks`、`website`、`python/sdk-runtime`、`docs/`、`scripts/`。

## 4. 安装与构建（阶段 B 验收）

| 命令 | 退出码 | 实测耗时 | 结果 |
|---|---|---|---|
| `corepack pnpm install` | 0 | 2m1.7s | 366 workspace；lockfile 无需重解析；`✓ Lockfile passes supply-chain policies (1725 entries in 16.4s)`；postinstall 装 lefthook 钩子（pre-commit/pre-merge-commit/pre-push）；node_modules 676 MB |
| `corepack pnpm run build` | 0 | 360.27s | `run-gates: 9 passed, 0 failed, 0 skipped`；native addon PASS 1.44s、host compiler 172.37s、Host bundle 26.06s、Desktop bundle 2.73s、client compiler 82.41s、Client bundle 30.24s、Web build 12.37s、host aggregate check 166.58s、client aggregate check 75.21s；`build: recorded 325 client artifact(s)` |
| `corepack pnpm run typecheck` | 0 | 16.12s | `run-gates: 5 passed, 0 failed, 0 skipped` |

- pnpm 安装未绕过任何构建脚本：`pnpm-workspace.yaml` 的 `allowBuilds` 已显式允许 esbuild / node-pty（含 ConPTY）/ koffi / lefthook，本机全部通过，无 `Ignored build scripts` 报错。
- **未使用 WSL**：Windows 原生即可完成安装、构建、类型检查。原生 `native addon` 与 `@ubjs/node-win32-x64-msvc`、`@vscode/ripgrep-win32-x64` 均正常落地。
- 上游源码零改动：`git status --porcelain --untracked-files=no` 输出为空，`modified_count=0`，`git diff --stat HEAD` 为空。`.env` 与所有构建产物（`lib/`、`node_modules/`、`.sessions/`）都被仓库自身 `.gitignore` 覆盖，因此不出现在 untracked 列表里。
- 「npm 发行包可运行」与「源码构建成功」是两条独立结论：本次验收的是后者（源码），`npx @deepseek-ai/dsh` 未使用、未作为结论依据。

## 5. 阶段 C：Web UI 启动与界面核验深度（如实分层）

启动命令：`corepack pnpm dsh web --no-open`（cwd = 仓库根，`DSH_HOME` 指向隔离目录）。

```
$ node --import tsx/esm apps/cli/src/bin.ts web --no-open
dsh web: http://127.0.0.1:3080/?token=…（token 已在报告与聊天中省略）
```

健康状态：`netstat` 显示 `127.0.0.1:3080 LISTENING`（PID 19176），端口 3080 事前空闲（已先 `netstat` 核实占用，未终止任何其它项目服务）。日志存 `_logs/04_web_server.log`。

浏览器为真实浏览器内核（Qoder 内置浏览器，CDP 驱动）。核验深度：

| 界面 | 本轮核验到哪一步 | 证据 |
|---|---|---|
| 模型配置 | **可用**：Settings → 模型 页显示 DeepSeek 卡片「API 密钥已配置」；「编辑 DeepSeek (deepseek-official)」表单展示 API 密钥输入框并标注 `已检测到环境变量（DEEPSEEK_API_KEY）`；另有「添加模型提供商」「自定义设置」「取消/保存」 | 无障碍树快照 |
| 模型选择 | **可用**：composer 模型条显示 `DeepSeek-V4.1-Flash · High`，展开后出现「模型 / 推理等级」菜单 | 快照 |
| 工作区选择 | **已实测通过**：用官方自动化 overlay 启动 `corepack pnpm dsh --patch apps/web/tests/pin-browse-picker.overlay.yml --profile web --no-open`，点「添加工作区」弹出页内目录选择器（逐级列目录、「编辑路径」直接输入路径、「显示隐藏文件」、新建文件夹、取消/打开）；选中 `harness-ui-workspace` 后 composer 的工作区标签即变为该名 | 无障碍树快照 |
| 会话创建 | **已实测通过**：composer 输入任务后「发送消息」由 disabled 变 enabled；发送后自动生成会话标题「跨工作区文件创建测试」、出现「对话 / 轨迹」两个 tab、会话层级导航、时间戳与逐条工具卡片 | 快照 |
| 权限审批界面 | **已实测通过（含允许与拒绝两条路径）**：详见下表 | 快照 |

审批界面实测（同一次 UI 会话内出现两次审批请求）：

| 场景 | 观察到的行为 |
|---|---|
| 工作区内写 | ACL 修好后 `写入 note.txt` 直接成功，无需审批 —— 符合 `workspace-write` 语义 |
| 工作区外写 | 先返回 `失败：写入 Error: [sandbox: file access denied under workspace-write mode]`，模型随后改用 `sandbox_permissions: danger-full-access` 重试，触发第二次审批 |
| 审批文案 | 面板标题「等待审批」，正文用完整白话说明「哪个文件夹、缺什么权限、会为你本人账户补完全控制、移除其他应用遗留访问、不改文件内容与所有者、每处先备份、结束打印恢复命令、备份报告落在哪里」，并附**将要执行的确切命令行**；按钮为「拒绝」「允许一次」 |
| 允许路径 | 点「允许一次」→ 脚本真跑起来，返回 `PRECONDITION / granted FullControl / verified(writeDac=true, writeOwner=true)`，备份与回滚脚本落到 `deep-agent\dsh-acl-recovery\` |
| 拒绝路径 | 第二个审批点「拒绝」→ 提权未发生，`outside.txt` 未被创建（已核对磁盘） |
| 沙箱自修 | 同一次会话里模型遇到与 headless 相同的 `SetNamedSecurityInfoW … (Win32 5)`，自行加载 `diagnose-windows-sandbox-acl` 并请求审批 —— 即「审批通道存在时它能走完官方修复流程」，与 headless「无审批通道 → 明确拒绝」形成对照 |

两点环境限制（非框架缺陷）：
1. 内置浏览器无可见视口（`viewport=0x0, visibilityState=hidden`），因此**截图与像素级点击不可用**（`NATIVE_BROWSER_VIEWPORT_UNAVAILABLE`）；改用 DOM 事件 + 无障碍树快照核验，功能层面等价，但没有图片证据。
2. 核验完成后会停掉自己启动的 3080 进程（仅本会话自启进程）。

CLI 文档与行为的一处差异（值得反馈上游）：仓库 `AGENTS.md` 与 `docs/cli-help.md` 示例写 `dsh web --patch <file>`；实测 `corepack pnpm dsh web --no-open --patch <file>` 报 `error: unknown option '--patch'`，而 `dsh --patch <file> --profile web --no-open` 与 `dsh --profile web --patch <file> -- --no-open` 都可用。即 `--patch` 作为启动器选项，需排在 profile 选择之前，或显式用 `--` 分隔应用参数。

## 6. 实际问题（如实记录）

1. **`TSX_TSCONFIG_PATH` 依赖**：源码启动是 `node --import tsx/esm apps/cli/src/bin.ts`。把该命令的 cwd 换到仓库外（例如测试工作区）时，裸标识符 `tsx/esm` 无法从新 cwd 解析；改用 `file://` 绝对路径可以加载 tsx，但 `@deepseek-ai/cordis` 会解析到缺少 `FiberState` 命名导出的入口并报 `SyntaxError`。根因：tsx 的 tsconfig `paths`（source plane 别名）是按启动目录发现的。解法：显式设 `TSX_TSCONFIG_PATH=<repo>/tsconfig.json`，即可在任意目录以源码方式启动。官方文档未提示该约束。
2. **Windows ACL 沙箱在本机某些路径上无法置备（已定位并修复）**：`workspace-write` 模式下 `pwsh` 工具与部分写操作稳定失败于 `SetNamedSecurityInfoW failed (Win32 5): grantWrite(…)`。根因经官方脚本判定为登录用户在工作区对象上**缺 `WRITE_OWNER`**（`verdict: PRECONDITION`，`before.writeOwner=false → after=true`），且与路径无关（换到 `D:\dsh-smoke` 同样失败）。修复只用了官方 skill 的那一条命令（`-AllowRoot` 严格等于工作区根，带备份与回滚，落在 `harness-smoke-workspace\_acl-out\`），修复后测试 2/3/4 全部在默认 `workspace-write` 下通过 —— 细节见 `agent-loop-test-report.md` 第 9 节。这是宿主权限问题，不是框架缺陷；框架侧行为正确（拒绝而非静默裸跑）。
3. **headless 无审批通道**：Agent 请求提权时被 `sandbox escalation to "danger-full-access" requires approval, but no approval channel is available` 挡下，行为正确（不静默放行），但也意味着一次性任务无法完成需要审批的修复。
4. 首轮环境探测受 Qoder 托管 PATH 中第三方 shim 干扰，报出虚高版本；已复核并在本报告采用真实 PATH 值。
5. Corepack 在全局目录会 EPERM（本机既有经验）；本次以 `COREPACK_HOME=D:\…\_corepack` 规避，未触碰 `C:\Program Files`。
