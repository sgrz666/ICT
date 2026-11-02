# patches/ — 官方 `--patch` 覆盖层

## 职责

记录我用官方配置层（`dsh --patch <file>`，应用顺序在 profile 层之后）尝试钉住 Agent 工作区的做法，并留下它**不够用**的实测结论。Harness 的分层组合本来就是「用 YAML 换插件/换配置」，这个目录是那条路径的最小样本。

## 内容

| 文件 | 是什么 | 实测结论 |
|---|---|---|
| [smoke-workspace.patch.yml](smoke-workspace.patch.yml) | 两行覆盖：`working-directory.config.defaultDirectory` 与 `sandbox-policy.config`（`mode: workspace-write` + `workspaceRoot`）指向 `harness-smoke-workspace` | **不足以移动会话 `cwd`**。`--json` 首行仍是 `cwd=D:\…\deepseek-harness`（见 `../_logs/06_smoke_ok.json`），因为 headless 用 `fs.resolve('.')`（即进程 cwd）创建会话。真正生效的做法是**以工作区为当前目录启动**，见 `../_tools/run_headless.sh` |
| [ict-agent-pruned.patch.yml](ict-agent-pruned.patch.yml) | 原生 Cordis 剪枝覆盖层（Headless/CLI 基座）：通过 `disabled: true` 精确关闭官方 OTel 遥测、会话日志外发（`api.deepseeksvc.com`）、DeepSeek 商业账号 OAuth/PKCE 登录、插件清单上报与命令反馈，保持其余原配置，能力仍需实际运行验证 | **实测通过**：`node apps/cli/lib/bin.js --patch deep-agent/patches/ict-agent-pruned.patch.yml --profile headless --dump-config` 退出码 0，目标插件在合成配置中标为禁用；dump-config 不启动插件，不能据此判定全链路能力 |
| [ict-web-pruned.patch.yml](ict-web-pruned.patch.yml) | 原生 Cordis 剪枝覆盖层（Web 工作台基座）：在 `ict-agent-pruned.patch.yml` 基础上进一步关闭 Web 端产品分析（`desktop-product-telemetry`、`product-analytics`）、消息点赞反馈与云端账号/日志设置面板，保留「启智AGENT」品牌、预设注册表与全部教学实验工具 | **实测通过**：`node apps/cli/lib/bin.js --patch deep-agent/patches/ict-web-pruned.patch.yml --profile web --dump-config` 退出码 0 |

patch 语法要点（读自 `../deepseek-harness/packages/bundle/*/cordis.patch.yml` 与 `docs/architecture.md`）：按 `id` 命中一行并**整段替换**其 `config`（不是合并），或 `insert` 新行；`!!js …` 允许表达式但只在 config/entry 内。

## 与上下层的关系

- 上游依赖：`dsh-base` 的 `working-directory` / `sandbox-policy` 两行（真实出厂值见 `../_logs/05_dump_config_headless.txt`）。
- 使用方式：`corepack pnpm dsh --patch ../patches/smoke-workspace.patch.yml --profile headless …`（`--patch` 要写在 profile 之前）。
- 被引用：`../harness-validation-reports/installation-report.md` 关于工作区与 `cwd` 的段落。

## 已知的坑与纪律

1. **`sandbox-policy.workspaceRoot` 只是兜底**：普通 Agent 调用用 session `header.cwd`（源码 `resolveWorkspaceRoot(session?.header.cwd ?? this.workspaceRoot)`）。想让沙箱可写根真的落在别处，必须改变会话 `cwd`，也就是改变启动目录。
2. patch 整段替换 config：只写部分字段会丢掉出厂字段，改前先 `--dump-config` 看清楚那一行原本有什么。
3. 这个文件保留**不是**因为它有效，而是因为它记录了「试过了、为什么不够」——删掉它会让后来人重复踩。新增覆盖层请同轮在本表加一行并写实测结论。

2026-10-31 正式运行入口迁至 [agent-runtime](../../code/eduforge/services/agent-runtime/README.md)。统一裁剪来源为其 `src/snapshot.mjs`，同时生成 Web/SDK 完整配置；本目录两份隐私补丁保留用于旧启动方式与基准对照，不再作为新运行时的双份配置来源。
