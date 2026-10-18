# deep-agent — DeepSeek Harness 官方源码部署与原生 Agent 能力验证

本轮任务：把 DeepSeek 官方开源的 **DeepSeek Harness（`dsh`）** 完整克隆到本地，装依赖、从源码构建、接入真实 DeepSeek API，并用它**原生**的 Agent 工作流验证自主工具调用、执行反馈与多轮修复能力。**本轮不含任何 EduForge 专属改造。**

- 上游仓库：https://github.com/deepseek-ai/deepseek-harness （MIT，`Everything is a Plugin`）
- 官方文档：https://deepseek-harness.github.io/deepseek-harness/
- 本次实测锚点：`master` @ `687f282e8625c6b8d11ff58211a90524be2e4317`，tag `dsh-v0.2.1-rc.2`，版本 `0.2.1-rc.2`，无 submodule
- 环境：Windows 10.0.26200 / Node v24.14.1 / pnpm 11.28.5（由仓库 `packageManager` 决定）/ Git 2.33.1 / Python 3.13.13 / pwsh 7.6.4，**全程未使用 WSL**

## 目录

- [结论（一句话版）](#结论一句话版)
- [目录地图](#目录地图) — 每个目录是什么、多大、入库与否
- [精细目录索引（逐文件实测）](#精细目录索引逐文件实测) — 整棵树的文件级清单与读法
- [如何启动](#如何启动) — 从裸机到跑通一次 Agent 会话：
  [0 前置条件](#0-前置条件本机实测) ·
  [1 环境变量](#1-三个必须显式设置的环境变量) ·
  [2 克隆与构建](#2-首次准备完整克隆--从源码构建一次性) ·
  [3 启动 Web UI](#3-启动-web-ui有审批通道的形态) ·
  [4 启动命令行任务](#4-启动一次命令行任务最接近-codex-cli-的用法) ·
  [5 复跑五项测试](#5-复跑本轮五项测试推荐用封装脚本) ·
  [6 Windows 权限置备](#6-windows-新建工作区的第一次权限置备不做则命令全跑不起来) ·
  [7 停止与清理](#7-停止与清理) ·
  [8 启动失败对照表](#8-启动失败对照表) ·
  [9 收尾自检](#9-收尾自检改完任何本目录内容都要跑)
- [与上层（ICT / EduForge）的关系](#与上层ict--eduforge的关系)
- [已知的坑与纪律](#已知的坑与纪律)

## 结论（一句话版）

官方源码在 Windows 原生可构建可运行，真实 DeepSeek API 可调用，**自主「执行失败 → 读错误 → 改代码 → 再执行」的多轮工具循环真实发生且可审计**；五项测试全部通过，但其中三项是在排掉一个宿主 NTFS 权限坑之后才通过的。细节见 [harness-validation-reports/](harness-validation-reports/README.md)。

- 后续追加（阶段 G）：把 Web 前端品牌层从 DeepSeek 官方壳改成 **启智AGENT** —— 新增 `packages/client/ui-brand-qizhi` 占掉 `sidebar.brand.mark`、`sidebar.brand.name`、`conversation.hero.brand.mark` 三个槽位（鲸鱼标志与动画鱼由此彻底退出 UI），换掉标题、favicon、PWA manifest 与首屏文案，并加了一层零依赖 Canvas 粒子。后端、Agent Loop、工具与会话链路零改动，改动清单与验证见 [rebrand-qizhi-report.md](harness-validation-reports/rebrand-qizhi-report.md)，可重放补丁是 [rebrand-qizhi.patch](harness-validation-reports/rebrand-qizhi.patch)。改的是被忽略的 `deepseek-harness/` 工作树，所以本目录只留报告与补丁。
- 后续追加（阶段 G 第二版）：页面做成**毛玻璃**——品牌强调色与所有面板材质统一，做法是从 `ui-brand-qizhi` 调 `ctx.theme.overrideTokens()` 把 alias token 覆盖层注册进官方主题服务（呈现器写成 `body` 行内变量，因此不需要和上游样式表比选择器权重），样式表只留氛围底、画布色与 `backdrop-filter`；第一版做到一半被用户实测否掉：右半页糊成一片，根因是给**自身没有填充的透明容器**（右侧面板、composer 座位、header、左栏 `<nav>`）加了 `backdrop-filter`——模糊透明容器等于把它范围内的内容搅成一团。修法是把磨砂只留给唯一自己画半透明填充的大表面（侧栏列），并把所有「盖在内容之上」的表面 α 提到 0.94 以上，只让画布与侧栏透；这条不变量现在有测试钉住。客户端类型检查/打包与 849+5 项前端测试全绿，模态遮罩与菜单材质按上游规矩保持不碰。详见 [rebrand-qizhi-v2-glass-report.md](harness-validation-reports/rebrand-qizhi-v2-glass-report.md)，补丁已重生成。

## 目录地图

| 目录 | 是什么 | 实测规模 | 入库 |
|---|---|---|---|
| [harness-validation-reports/](harness-validation-reports/README.md) | 交付报告（安装、API 联调、Agent 循环实测、架构笔记、集成评估、品牌重构 v1/v2）+ 可重放补丁 | 9 个条目：7 份报告 + `rebrand-qizhi.patch`（29 文件 / +1,083 行 / 65,920 字节）+ README | ✅ |
| [_logs/](_logs/README.md) | 原始证据：环境与构建日志、Web 启动日志、每次 Agent 运行的 `jsonl`/`err`/`meta` 三元组 | 55 个条目 = 54 份证据（19 份编号日志 + 11 组三元组 33 份 + 2 份单文件）+ README | ✅（token 已脱敏） |
| [_tools/](_tools/README.md) | 复现驱动：`run_headless.sh` 跑一次官方 headless 会话，`summarize_events.mjs` 把事件流压成工具调用表，`check_docs.py` 是文档门 | 5 个条目（README + 3 个工具 + `prompts/`） | ✅ |
| [_tools/prompts/](_tools/prompts/README.md) | 五项测试与只读探针的任务原文 | 7 个条目（README + `t1..t5.txt` + `probe_shell.txt`） | ✅ |
| [_probe/](_probe/README.md) | 故意带缺陷的基线副本（`cart.py` + 暴露它的 `test_cart.py`）与官方要求原文快照，证明测试 3 不是提前修好的 | 10 个条目（README + 2 份 py + 6 份 `gh_*` + `__pycache__/`） | ✅（`__pycache__/` ❌） |
| [patches/](patches/README.md) | 官方 `--patch` 覆盖层，把 Agent 的工作区钉在一次性目录上；含「它不够用」的实测结论 | 2 个条目（README + `smoke-workspace.patch.yml`） | ✅ |
| [dsh-acl-recovery/](dsh-acl-recovery/README.md) | **官方 ACL 脚本**为 `harness-ui-workspace` 置备权限时生成的备份、回滚脚本与完整记录——系统权限改动可逐一撤销的凭据 | 4 个条目（README + 备份 json + 回滚 ps1 + 记录 jsonl） | ✅ |
| [harness-ui-workspace/](harness-ui-workspace/README.md) | Web UI 界面核验用的沙盒目录，里面有审批放行后真实写入的 `note.txt` | 4 个条目（README + `hello.txt`、`note.txt`、`notes.txt`） | ✅ |
| `harness-smoke-workspace/` | 五项测试的真实工作区（自带嵌套 `.git`，基线提交 `b6e600c`），另有 `_acl-out/` 权限备份 | 不入库，故不写 README（说明见 AGENTS.md 第 3 节） | ❌ 嵌套仓库 |
| `deepseek-harness/` | 官方源码克隆，本轮验证对象 | 工作树 2.7 GB 含 node_modules；内部 README 是上游资产 | ❌ 第三方资产，按上游 commit 随时可重取 |
| `_corepack/`、`.dsh-home/` | pnpm 缓存与隔离的 `DSH_HOME`（会话、日志、配置都落在这里） | 可再生 | ❌ 可再生 |

> 逐文件清单与「谁生成、读者该拿它干什么」在下面的[精细目录索引](#精细目录索引逐文件实测)一节。

## 精细目录索引（逐文件实测）

计数口径：2026-10-18 用 `ls -A` 就地实测，「条目数」含该目录的 `README.md`。文档门 `python _tools/check_docs.py` 当前输出 `dirs checked: 9 | md files: 20 | README missing: 0 | broken links: 0`。

```
deep-agent/                       13 个条目（2 份本层文档 + 8 个入库目录 + 3 个不入库目录）
├── README.md                     ← 本文件：结论摘要、目录地图、精细索引、启动指南、坑
├── AGENTS.md                     ← 本目录的硬门：每个含文件的目录都要有 README + 安全纪律 + 验证命令
│
├── harness-validation-reports/    9 条  ✅ 结论层（阶段 A–G）
│   ├── README.md                  报告索引：每份报告覆盖哪个阶段、里面实际写了什么
│   ├── installation-report.md     A+B+C：环境实测表、克隆锚点、三条构建命令的退出码与耗时、Web UI 健康状态、界面核验分层表
│   ├── api-connectivity-report.md D：真实 DeepSeek 接入、baseURL 与协议、线上模型目录、token 表、「成本未测得」
│   ├── agent-loop-test-report.md  E：五项测试逐条调用表与原文摘录、第 6 节权限观察、第 8 节验收判定、第 9 节修复后复跑
│   ├── architecture-notes.md      源码阅读：Cordis 插件模型、profile/bundle 分层、事件序列、沙箱三档、DSH_HOME 解析
│   ├── next-integration-assessment.md F：只评估不实现，按性价比列可复用模块 + 「官方已有本轮未验证」清单
│   ├── rebrand-qizhi-report.md    G：启智AGENT 第一版（9 处品牌注入点、新增 ui-brand-qizhi、浏览器实测）
│   ├── rebrand-qizhi-v2-glass-report.md G 第二版：毛玻璃（逐元素反查、overrideTokens 官方通道、不透明面板 6→0）
│   └── rebrand-qizhi.patch        可重放补丁：29 文件 / +1,083 行 / 65,920 字节（v1 版为 24 文件 / 49,436 字节）
│
├── _logs/                        55 条  ✅ 证据层（本 README 不复制其内容，索引在 _logs/README.md）
│   ├── README.md                  证据索引：每个 stem 的权限模式、exit、耗时、调用数与关键看点
│   ├── 00_environment.txt         真实 PATH 下的版本核对（含 Qoder 托管 shell 的 shim 陷阱）
│   ├── 01_pnpm_install.log / 02_pnpm_build.log / 03_typecheck.log   三条构建命令的完整输出与退出码
│   ├── 04_web_server.log / 16_qizhi_web.log / 17_qizhi_v2_web.log   三次 Web 启动行（URL 与端口，token 已脱敏）
│   ├── 05_dump_config_headless.txt  出厂组合树全量（sandbox-policy、approval、agent-loop.agents、win32 禁用 tool-bash）
│   ├── 06_smoke_ok.{json,err} / 07_smoke_cwdtest.{json,err}  两条最小 API 冒烟（对照 cwd 落点与 TSX_TSCONFIG_PATH）
│   ├── 09_web_picker.log / 10_web_picker.log  --patch 位置坑的失败与成功两态（`08_*` 不存在，非缺失）
│   ├── 11..15_rebrand_build*.log  品牌包接入构建的五次现场：未登记聚合 → composite → 38 条严格模式 → 6 条 → 全绿
│   ├── <stem>.{jsonl,err,meta}    11 组 Agent 运行三元组：t1 t2 t2_fixed t3 t3_fullaccess t3_wsw t4 t4_fixed t5_resume probe_shell probe_after
│   ├── t3_agent_fixed_cart.py     t3 那轮模型改出的 cart.py 快照（留存在基线还原之前）
│   └── vitest-v2.log              第二版改动的全量前端测试：56 文件 / 849 测试全绿（RC=0）
│
├── _tools/                        5 条  ✅ 复现层
│   ├── README.md                  工具用法与「不许代 Agent 做题」纪律
│   ├── run_headless.sh            一次 headless 运行的封装（导出 4 个环境变量、读 prompt 后才 cd、落 jsonl/err/meta）
│   ├── summarize_events.mjs       事件流 → 调用表 + turns/steps/失败数/token 合计（报告里的数字都出自它）
│   ├── check_docs.py              文档门：每目录 README + 相对链接，os.walk 就地剪枝
│   └── prompts/                   7 条：t1..t5.txt（五项任务原文）+ probe_shell.txt（只读探针）+ README.md
│
├── _probe/                       10 条  ✅ 前提层
│   ├── README.md                  缺陷基线与快照的出处、以及「这两份文件不许被修好」
│   ├── cart.py / test_cart.py     向下取整缺陷 + 暴露它的 5 个用例（`FAILED (failures=2)`，退出码 1）
│   ├── gh_README.md gh_AGENTS.md gh_SAFETY.md gh_development.md gh_package.json gh_pnpm-workspace.yaml   官方要求逐字快照（链接按 gh_* 豁免检查）
│   └── __pycache__/               ❌ 字节码缓存，可再生
│
├── patches/                       2 条  ✅  README.md + smoke-workspace.patch.yml（实测「不足以移动会话 cwd」的结论留在表里）
├── dsh-acl-recovery/               4 条  ✅  README.md + acl-backup-<id>.json + 同名 .ps1 回滚脚本 + acl-report-<id>.jsonl 完整记录
├── harness-ui-workspace/           4 条  ✅  README.md + hello.txt / note.txt / notes.txt（审批放行后由 Agent 真实写入）
├── harness-smoke-workspace/       ❌ 不入库：嵌套 .git（基线 b6e600c）、_acl-out/ 权限备份、__pycache__/
├── deepseek-harness/              ❌ 不入库：2.7 GB 上游源码 + node_modules，唯一密钥在它的 .env（53 字节，变量名 DEEPSEEK_API_KEY，值不打印）
├── _corepack/                     ❌ 不入库：corepack/pnpm 缓存（COREPACK_HOME 指这里，避开全局安装的 EPERM）
└── .dsh-home/                     ❌ 不入库：隔离的 DSH_HOME（配置、会话索引、startup 日志）
```

读法：**结论**看 reports，**证据**看 _logs，**怎么复现**看 _tools，**前提是否成立**看 _probe 与 patches，**系统改动怎么撤销**看 dsh-acl-recovery。跨目录只引用不复制（AGENTS.md 第 7 节）。

## 如何启动

下面每一步的退出码、耗时、端口与文件路径都取自 `_logs/` 里的实测现场；命令可直接复制，**路径按本机改**。

### 0. 前置条件（本机实测）

| 项 | 实测值 | 备注 |
|---|---|---|
| Node | v24.14.1 | 上游 `engines` 要求 `^22.19 \|\| >=24`（原文快照见 [_probe/gh_package.json](_probe/gh_package.json)） |
| pnpm | 11.28.5，**由仓库 `packageManager` 字段决定** | 用 `corepack pnpm …`，不要用全局 pnpm；本机装全局 pnpm 会 EPERM |
| Git | 2.33.1 | 克隆必须完整历史（22,395 commits） |
| pwsh | 7.6.4 | win32 的工具目录是 `pwsh` 而非 `bash`；中文回显乱码时加 `-NoProfile` |
| Python | 3.13.13 | 只用于 [_probe/](_probe/README.md) 的缺陷基线复核 |
| WSL | **全程未使用** | 官方 Windows 路径原生可构建可运行 |
| 体积 | node_modules 676 MB，`deepseek-harness/` 工作树 2.7 GB | 上游本体不入库，按 commit 随时可重取 |

自检（版本以**真实 PATH** 为准）：

```powershell
node -v; corepack pnpm -v; git --version; pwsh -v; python -V
```

`_logs/00_environment.txt` 记过一次教训：Qoder 托管 shell 的 PATH 混有第三方 shim，首轮报出过虚高版本，所以别只信一个 shell 的输出。

### 1. 三个必须显式设置的环境变量

| 变量 | 指到本目录的位置 | 不设会怎样 |
|---|---|---|
| `COREPACK_HOME` | `_corepack/` | 落到全局 corepack 目录，本机实测触发 EPERM |
| `DSH_HOME` | `.dsh-home/` | 配置、会话、启动日志写进 C 盘用户目录。**该目录里有 `.credentials.yaml`，属敏感目录：不入库、不外发、不贴进聊天** |
| `TSX_TSCONFIG_PATH` | `deepseek-harness/tsconfig.json` | 只有从**仓库外**以源码方式启动才需要；不设会报 `@deepseek-ai/cordis does not provide an export named 'FiberState'`（[_logs/06_smoke_ok.json](_logs/06_smoke_ok.json) 与 [07_smoke_cwdtest.json](_logs/07_smoke_cwdtest.json) 是这条的失败/成功对照） |

密钥不用单独配：`deepseek-harness/.env`（53 字节，变量名 `DEEPSEEK_API_KEY`，值不打印、不入库）会被自动读到；[_tools/run_headless.sh](_tools/run_headless.sh) 用 `set -a; . .env; set +a` 注入且永不回显。

### 2. 首次准备：完整克隆 + 从源码构建（一次性）

```powershell
git clone https://github.com/deepseek-ai/deepseek-harness.git
cd deepseek-harness
$env:COREPACK_HOME='D:\codeplus\ICT\deep-agent\_corepack'; $env:DSH_HOME='D:\codeplus\ICT\deep-agent\.dsh-home'
corepack pnpm install      # 实测 exit 0 / 2m1.7s；366 workspace；供应链门 1725 entries in 16.4s
corepack pnpm run build    # 实测 exit 0 / 360.27s；run-gates 9 passed 0 failed；325 个 client artifact
corepack pnpm run typecheck # 实测 exit 0 / 16.12s；run-gates 5 passed 0 failed
```

不要 shallow / sparse clone：构建与快照测试依赖完整历史。三条命令的逐门耗时在 [_logs/02_pnpm_build.log](_logs/02_pnpm_build.log)，判读口径在 [installation-report.md](harness-validation-reports/installation-report.md)。

### 3. 启动 Web UI（有审批通道的形态）

```powershell
$env:COREPACK_HOME='D:\codeplus\ICT\deep-agent\_corepack'
$env:DSH_HOME='D:\codeplus\ICT\deep-agent\.dsh-home'
cd D:\codeplus\ICT\deep-agent\deepseek-harness
corepack pnpm dsh web --no-open          # 实测 URL：http://127.0.0.1:3080/?token=…
corepack pnpm dsh web --port 3081        # 已有实例占 3080 时换端口
```

- 启动行的 `token=` 是**本机免登录访问凭据**，等价于密钥：不要粘进聊天、报告或提交；`_logs/` 里三份 web 启动日志都已脱敏（`token=REDACTED` / `token=[REDACTED-local-ui-access-credential]`）。
- Settings → 模型 页会显示「已检测到环境变量（DEEPSEEK_API_KEY）」，无需手工填。
- **进真实项目前先在 Settings → 通用设置 关掉「在使用官方模型 API 时上传 Session Log」**（出厂勾选）。
- 想自动化目录选择器：`corepack pnpm dsh --patch apps/web/tests/pin-browse-picker.overlay.yml --profile web --no-open`。`--patch` 是启动器选项，必须排在 `--profile` 之前，或写成 `dsh --profile web --patch X -- --no-open`；`dsh web --patch X` 实测报 `error: unknown option '--patch'`（对照现场 [09_web_picker.log](_logs/09_web_picker.log) → 成功形态 [10_web_picker.log](_logs/10_web_picker.log)）。
- 需要选工作区：点「添加工作区」后用页内目录选择器（可「编辑路径」直接输入），选中 `harness-ui-workspace` 后 composer 的工作区标签即变为该名。
- 只有走 Web UI 才有审批通道；headless 下提权操作会被拒且无处可批（见坑 4）。

### 4. 启动一次命令行任务（最接近 Codex CLI 的用法）

```powershell
cd D:\codeplus\ICT\deep-agent\deepseek-harness
corepack pnpm dsh --profile headless "列出这个仓库的顶层目录并说明各自职责"
```

要机器可读的事件流加 `--json`（`session`/`status`/`thinking`/`text`/`tool_call`/`tool_result`/`final`）；想确认出厂配置：

```powershell
corepack pnpm dsh --profile headless --dump-config   # 全量组合树，实测快照在 _logs/05_dump_config_headless.txt
```

**会话 `cwd` 等于进程 `cwd`**——这一点被专门验证过：`--patch` 改 `working-directory` 与 `sandbox-policy.workspaceRoot` 都不足以移动会话 cwd（[_logs/06_smoke_ok.json](_logs/06_smoke_ok.json) 里首行仍是 `cwd=…\deepseek-harness`）。想让 Agent 落在别的工作区，就**从那个目录启动**，见下一步。

### 5. 复跑本轮五项测试（推荐用封装脚本）

```sh
cd _tools
bash run_headless.sh t3 prompts/t3.txt              # 事件流→ _logs/t3.jsonl，stderr→ .err，退出码与耗时→ .meta
WORKSPACE_DIR='D:/别的工作区' bash run_headless.sh t1 prompts/t1.txt
```

脚本做的事：导出 `COREPACK_HOME` / `DSH_HOME` / `TSX_TSCONFIG_PATH`、读 `.env` 拿 key（不回显）、**先读 prompt 再 `cd` 到工作区**、以 `--profile headless --json` 启动 node、把三份产物落进 `_logs/`，最后调 [summarize_events.mjs](_tools/summarize_events.mjs) 打印调用表（编号、工具名、输入/结果截断、状态，以及 turns/steps/调用数/失败数/token 合计）。五项任务原文在 [_tools/prompts/](_tools/prompts/README.md)，只读探针是 `probe_shell.txt`。

恢复某个已结束的会话继续聊（本轮测试 5 用的就是这个机制）：

```sh
bash run_headless.sh t5 prompts/t5.txt --session-id session-18a2e93f-6892-4fc3-b1e8-b0572ddc96d1
```

`sessionId` 从 `_logs/<stem>.jsonl` 的**首行**取。会话实体落在 `DSH_HOME/sessions/<工作区路径编码>/<sessionId>/`（本机实测：`--D-codeplus-ICT-deep-agent-harness-smoke-workspace--` 桶里 11 个会话），另有项目缓存索引 `DSH_HOME/storages/session_projcache/sessions/*.json`（23 份）。**删 `.dsh-home/` 等于丢掉全部可恢复会话**——清缓存前先确认没有要续跑会话。

换 stem 复跑，不要覆盖旧现场：`_fixed`、`_wsw`、`_fullaccess` 这类后缀承载「同 prompt、不同环境」的含义（[_logs/README.md](_logs/README.md) 有逐 stem 的权限模式与结果对照）。

### 6. Windows 新建工作区的第一次权限置备（不做则命令全跑不起来）

症状是启动前就报 `SetNamedSecurityInfoW failed (Win32 5): grantWrite(…)`；根因是登录用户在工作区目录缺 `WRITE_OWNER`，与路径无关（对照现场：`_logs/probe_shell.*` 在 `D:\dsh-smoke` 复现同一错误 → `_logs/probe_after.*` 置备后同一命令 8s 跑完并真报出 2 个 FAIL）。只用官方脚本，`-AllowRoot` 严格等于工作区根：

```powershell
& 'D:\codeplus\ICT\deep-agent\deepseek-harness\packages\sandbox\sandbox-windows-acl\assets\diagnose-windows-sandbox-acl\scripts\diagnose-windows-sandbox-acl.ps1' `
  -Path 'D:\你的工作区' -AllowRoot 'D:\你的工作区' -Out 'D:\你的工作区\_acl-out'
```

脚本会先备份安全描述符再授权，并在结束时打印回滚命令。`harness-ui-workspace` 那一轮的备份、回滚脚本与完整记录在 [dsh-acl-recovery/](dsh-acl-recovery/README.md)；`harness-smoke-workspace` 的同类备份在它自己的 `_acl-out/`（不入库）。纪律：不手工改 ACL、不提权跑、不往上级放宽 `-AllowRoot`、失败即停并回滚；**这是系统权限改动，动手前要有人确认**。

### 7. 停止与清理

- 前台进程 `Ctrl-C` 即可；查端口占用：`Get-NetTCPConnection -LocalPort 3080 -State Listen`。
- 可再生、可删：`_corepack/`、`_probe/__pycache__/`、`harness-smoke-workspace/_acl-out/`（前提是不再需要回滚）、`harness-ui-workspace/` 里的临时文件。
- **不许删/不许改**：`_logs/` 的现场（只追加）、[_probe/cart.py](_probe/cart.py) 与 [test_cart.py](_probe/test_cart.py)（改正它们等于伪造测试 3 的前提）、`dsh-acl-recovery/` 的成对备份+回滚脚本（孤儿文件说明上次被中断）。
- `.dsh-home/` 删之前看第 5 步的会话警告。

### 8. 启动失败对照表

| 症状 | 根因 | 处置 | 现场 |
|---|---|---|---|
| `SetNamedSecurityInfoW failed (Win32 5)` | 新工作区缺 `WRITE_OWNER` | 按第 6 步置备，再复跑 | `_logs/probe_shell.*` → `_logs/probe_after.*` |
| `error: unknown option '--patch'` | `--patch` 写在了 `web` 之后 | 改成 `dsh --patch X --profile web` 或 `dsh --profile web --patch X -- ` | `_logs/09_web_picker.log`、`10_web_picker.log` |
| `…cordis does not provide an export named 'FiberState'` | 仓库外源码启动没设 `TSX_TSCONFIG_PATH` | 显式指向 `deepseek-harness/tsconfig.json` | `_logs/06_smoke_ok.*` vs `07_smoke_cwdtest.*` |
| 会话 cwd 落在仓库根，Agent 改错目录 | headless 用进程 cwd 建会话 | 从目标工作区目录启动（`run_headless.sh` 已如此） | `patches/README.md` 坑 1 |
| `sandbox escalation to "danger-full-access" requires approval, but no approval channel is available` | headless 没有审批通道 | 行为正确，别为此全局切权限档；要审批闭环就走 Web UI | `_logs/t3.*`（绕行尝试与拒绝都记着） |
| 找不到模型 / 请求被拒 | 模型名以线上目录为准 | `GET https://api.deepseek.com/models` 实测只有 `deepseek-flash`、`deepseek-v4-pro`；仓库 patch 里的 `deepseek-v4-flash` 线上不存在 | `harness-validation-reports/api-connectivity-report.md` |
| 中文输出乱码 | 部分 shell 走 GBK | `pwsh -NoProfile`，或按 [_logs/00_environment.txt](_logs/00_environment.txt) 用真实 PATH 核对 | AGENTS.md 第 8 节 |
| 找不到 prompt 文件、三次空跑 | `run_headless.sh` 里 `cd` 在读 prompt 之前 | 保持「先读 prompt 再 `cd`」的顺序 | `_tools/README.md` 坑 2 |

### 9. 收尾自检（改完任何本目录内容都要跑）

```bash
cd D:/codeplus/ICT/deep-agent
python _tools/check_docs.py                 # 期望：README missing: 0，broken links: 0
python -m unittest -v                       # 在 _probe/ 里跑，期望 FAILED (failures=2)——基线必须仍是坏的
grep -rn "sk-[A-Za-z0-9]\{16,\}" . --exclude-dir=deepseek-harness --exclude-dir=_corepack --exclude-dir=.dsh-home --exclude-dir=harness-smoke-workspace
grep -rlE 'token=[A-Za-z0-9_.-]{20,}' . --exclude-dir=deepseek-harness --exclude-dir=harness-smoke-workspace   # 两条都必须无输出
git -C deepseek-harness status --porcelain --untracked-files=no   # 每一行都要能落在品牌白名单内
```

`check_docs.py` 用 `os.walk` 就地剪枝。**不要**把它或任何遍历命令改写成 `pathlib.rglob` / `find -not -path`——那会先钻进 2.7 GB 的上游树，实测卡几分钟（本轮就踩了一次，命令被超时打断）。

## 与上层（ICT / EduForge）的关系

这是 ICT 仓库里一个**与被验证对象隔离**的验证工作区：EduForge 的生产代码、依赖、数据库都没被碰过，`git status` 里 EduForge 侧的改动全部来自并行会话。上游那份 `deep-agent/` 忽略规则（现已被拆成细粒度规则）早先已被并行会话带入提交。

按 ICT 的 `AGENTS.md` 纪律，本目录的**每一个文件夹都必须有自己的 README**，这条要求在 [deep-agent/AGENTS.md](AGENTS.md) 里对后续 Agent 生效。仓库根的 `README.md` 目录地图是否要登记 `deep-agent/`，因该文件正被并行会话编辑，本轮未改，缺口登记在此。

## 已知的坑与纪律

1. **新建工作区第一次必须做一次 Windows 权限置备**，否则所有命令在启动前就报 `SetNamedSecurityInfoW failed (Win32 5): grantWrite(…)`。根因是登录用户在工作区目录上缺 `WRITE_OWNER`（`sg` 在 `D:\` 各处只有 `Modify`），与路径无关。修法只用官方那条命令，`-AllowRoot` 严格等于工作区根，改动前备份、结束打印回滚命令：

   ```powershell
   & '…\deepseek-harness\packages\sandbox\sandbox-windows-acl\assets\diagnose-windows-sandbox-acl\scripts\diagnose-windows-sandbox-acl.ps1' `
     -Path 'D:\你的工作区' -AllowRoot 'D:\你的工作区' -Out 'D:\你的工作区\_acl-out'
   ```

   纪律：不手工改 ACL、不提权跑、失败即停并回滚（这是官方 skill 的「Never」清单）。排好后 `harness-smoke-workspace` 与 `harness-ui-workspace` 各有一份 `_acl-out`/回滚脚本。
2. **`--patch` 的位置**：`dsh web --no-open --patch X` 实测报 `unknown option '--patch'`；可用形态是 `dsh --patch X --profile web` 或 `dsh --profile web --patch X -- <app-args>`。上游 `AGENTS.md`/`cli-help.md` 的示例与本机行为不一致，值得反馈。
3. **源码启动对工作目录敏感**：`node --import tsx/esm apps/cli/src/bin.ts` 依赖 tsx 从**当前目录**发现 tsconfig `paths`（source plane 别名）。要在仓库外启动，必须显式设 `TSX_TSCONFIG_PATH=<repo>/tsconfig.json`，否则报 `@deepseek-ai/cordis does not provide an export named 'FiberState'`。官方文档未提这一点。
4. **headless 没有审批通道**：需要提权的操作会拿到 `sandbox escalation to "danger-full-access" requires approval, but no approval channel is available`。行为正确（拒绝而非静默放行），但要审批闭环就得用 Web UI。
5. **默认遥测是开的**：Settings → 通用设置 →「在使用官方模型 API 时上传 Session Log」出厂勾选，会把含工作区文件内容的会话日志上传给 DeepSeek。**拿真实项目试之前先关掉。**
6. **模型名以线上目录为准**：`GET https://api.deepseek.com/models` 实际返回 `deepseek-flash`、`deepseek-v4-pro`；仓库测试 patch 里出现的 `deepseek-v4-flash` 线上不存在。
7. **密钥**：唯一副本在 `deepseek-harness/.env`（不入库）。本目录所有日志与报告都已核对无明文 key；`_logs/` 里的本地 UI token 已脱敏。用完请轮换那把 key。
8. **不要 shallow / sparse clone**：本轮按官方要求完整克隆（22,395 commits），构建与快照测试依赖完整历史。
9. **文档与磁盘的计数冲突留痕（以实测为准，本轮不改他人正文）**：
   - [_logs/README.md](_logs/README.md) 标题写「53 个文件」，实测该目录是 **54 份证据 + README = 55 条目**（阶段 G 之后新增 `16_qizhi_web.log`、`17_qizhi_v2_web.log`、`vitest-v2.log` 而标题未跟改）；
   - `_logs/17_qizhi_v2_web.log` **尚未进该目录的登记表**——按 AGENTS.md 第 7 节「每条结论都要能追到具体文件」，这一条是缺口，归 `_logs/README.md` 的持有者补；
   - 本 README 的目录地图此前写「五份交付报告」，实测 `harness-validation-reports/` 是 **7 份报告 + 1 份补丁 + README**，已按实测改正。
10. **会话不在工作区，在 `DSH_HOME`**：本目录 [AGENTS.md](AGENTS.md) 第 8 节与 `_logs/README.md` 都写「会话持久化落在工作区的 `.sessions/`」，但 `dsh-v0.2.1-rc.2` 实测 `harness-smoke-workspace/` 里没有 `.sessions/`；会话实际在 `.dsh-home/sessions/--D-codeplus-ICT-deep-agent-harness-smoke-workspace--/<sessionId>/`（该桶实测 11 个会话目录），另有索引 `.dsh-home/storages/session_projcache/sessions/*.json`（23 份）。这条影响启动的两处：`--session-id` 续跑的前提是 `.dsh-home/` 还在；换 `DSH_HOME` 等于换一批会话。
11. **`.dsh-home/` 是敏感目录**：里面有 `.credentials.yaml` 与 `.anonymous-user-id`。它已被 `.gitignore` 挡住，但**不要复制、打包或外发**该目录，也不要在报告里贴其中任何文件内容。
12. **遍历本目录时不要走到上游树**：`deepseek-harness/` 是 2.7 GB。任何 `rglob` / `find` 全量遍历都会先钻进去（实测卡到超时），文档门 `_tools/check_docs.py` 用 `os.walk` 就地剪枝就是为了这个。
