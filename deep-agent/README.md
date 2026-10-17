# deep-agent — DeepSeek Harness 官方源码部署与原生 Agent 能力验证

本轮任务：把 DeepSeek 官方开源的 **DeepSeek Harness（`dsh`）** 完整克隆到本地，装依赖、从源码构建、接入真实 DeepSeek API，并用它**原生**的 Agent 工作流验证自主工具调用、执行反馈与多轮修复能力。**本轮不含任何 EduForge 专属改造。**

- 上游仓库：https://github.com/deepseek-ai/deepseek-harness （MIT，`Everything is a Plugin`）
- 官方文档：https://deepseek-harness.github.io/deepseek-harness/
- 本次实测锚点：`master` @ `687f282e8625c6b8d11ff58211a90524be2e4317`，tag `dsh-v0.2.1-rc.2`，版本 `0.2.1-rc.2`，无 submodule
- 环境：Windows 10.0.26200 / Node v24.14.1 / pnpm 11.28.5（由仓库 `packageManager` 决定）/ Git 2.33.1 / Python 3.13.13 / pwsh 7.6.4，**全程未使用 WSL**

## 结论（一句话版）

官方源码在 Windows 原生可构建可运行，真实 DeepSeek API 可调用，**自主「执行失败 → 读错误 → 改代码 → 再执行」的多轮工具循环真实发生且可审计**；五项测试全部通过，但其中三项是在排掉一个宿主 NTFS 权限坑之后才通过的。细节见 [harness-validation-reports/](harness-validation-reports/README.md)。

## 目录地图

| 目录 | 是什么 | 入库 |
|---|---|---|
| [harness-validation-reports/](harness-validation-reports/README.md) | 五份交付报告（安装、API 联调、Agent 循环实测、架构笔记、集成评估） | ✅ |
| [_tools/](_tools/README.md) | 复现驱动：`run_headless.sh` 跑一次官方 headless 会话，`summarize_events.mjs` 把事件流压成工具调用表，`prompts/` 是五项测试的原文 | ✅ |
| [_logs/](_logs/README.md) | 原始证据：每次运行的 JSONL 事件流、stderr、退出码与耗时；环境与配置快照 | ✅（token 已脱敏） |
| [_probe/](_probe/README.md) | 故意带缺陷的基线副本（`cart.py` + 暴露它的 `test_cart.py`），用来证明测试 3 不是提前修好的 | ✅ |
| [patches/](patches/README.md) | 官方 `--patch` 覆盖层，把 Agent 的工作区钉在一次性目录上 | ✅ |
| [harness-ui-workspace/](harness-ui-workspace/README.md) | Web UI 界面核验用的沙盒目录，里面有审批放行后真实写入的 `note.txt` | ✅ |
| `harness-smoke-workspace/` | 五项测试的真实工作区（自带嵌套 `.git`，基线提交 `b6e600c`） | ❌ 嵌套仓库 |
| `deepseek-harness/` | 官方源码克隆（工作树 2.7 GB 含 node_modules） | ❌ 第三方资产，按上游 commit 随时可重取 |
| `_corepack/`、`.dsh-home/` | pnpm 缓存与隔离的 `DSH_HOME` | ❌ 可再生 |

## 快速上手

前提：`deepseek-harness/` 已按 [installation-report.md](harness-validation-reports/installation-report.md) 的三条命令构建完（`pnpm install` → `pnpm run build` → `pnpm run typecheck`，实测退出码全 0）。

**Web UI**

```powershell
$env:COREPACK_HOME='D:\codeplus\ICT\deep-agent\_corepack'
cd D:\codeplus\ICT\deep-agent\deepseek-harness
corepack pnpm dsh web --port 3081
```

API key 不用配：仓库根的 `.env`（被上游 `.gitignore` 覆盖，不入库）会被自动读到，Settings → 模型 页会显示「已检测到环境变量（DEEPSEEK_API_KEY）」。想自动化目录选择器，加 `--patch apps/web/tests/pin-browse-picker.overlay.yml`（注意它是启动器选项，得写在 `--profile web` 之前，见坑 2）。

**一次命令行任务（最接近 Codex CLI 的用法）**

```powershell
cd D:\codeplus\ICT\deep-agent\deepseek-harness
corepack pnpm dsh --profile headless "列出这个仓库的顶层目录并说明各自职责"
```

**复跑本轮五项测试**

```sh
cd _tools
bash run_headless.sh t3 prompts/t3.txt          # 事件流写进 _logs/t3.jsonl 并打印调用表
WORKSPACE_DIR='D:/别的工作区' bash run_headless.sh t1 prompts/t1.txt
```

恢复某个已结束的会话继续聊（本轮测试 5 用的就是这个机制）：

```sh
bash run_headless.sh t5 prompts/t5.txt --session-id session-18a2e93f-6892-4fc3-b1e8-b0572ddc96d1
```

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
