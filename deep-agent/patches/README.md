# patches/ — 官方 `--patch` 覆盖层

## 职责

记录我用官方配置层（`dsh --patch <file>`，应用顺序在 profile 层之后）尝试钉住 Agent 工作区的做法，并留下它**不够用**的实测结论。Harness 的分层组合本来就是「用 YAML 换插件/换配置」，这个目录是那条路径的最小样本。

## 内容

| 文件 | 是什么 | 实测结论 |
|---|---|---|
| [smoke-workspace.patch.yml](smoke-workspace.patch.yml) | 两行覆盖：`working-directory.config.defaultDirectory` 与 `sandbox-policy.config`（`mode: workspace-write` + `workspaceRoot`）指向 `harness-smoke-workspace` | **不足以移动会话 `cwd`**。`--json` 首行仍是 `cwd=D:\…\deepseek-harness`（见 `../_logs/06_smoke_ok.json`），因为 headless 用 `fs.resolve('.')`（即进程 cwd）创建会话。真正生效的做法是**以工作区为当前目录启动**，见 `../_tools/run_headless.sh` |

patch 语法要点（读自 `../deepseek-harness/packages/bundle/*/cordis.patch.yml` 与 `docs/architecture.md`）：按 `id` 命中一行并**整段替换**其 `config`（不是合并），或 `insert` 新行；`!!js …` 允许表达式但只在 config/entry 内。

## 与上下层的关系

- 上游依赖：`dsh-base` 的 `working-directory` / `sandbox-policy` 两行（真实出厂值见 `../_logs/05_dump_config_headless.txt`）。
- 使用方式：`corepack pnpm dsh --patch ../patches/smoke-workspace.patch.yml --profile headless …`（`--patch` 要写在 profile 之前）。
- 被引用：`../harness-validation-reports/installation-report.md` 关于工作区与 `cwd` 的段落。

## 已知的坑与纪律

1. **`sandbox-policy.workspaceRoot` 只是兜底**：普通 Agent 调用用 session `header.cwd`（源码 `resolveWorkspaceRoot(session?.header.cwd ?? this.workspaceRoot)`）。想让沙箱可写根真的落在别处，必须改变会话 `cwd`，也就是改变启动目录。
2. patch 整段替换 config：只写部分字段会丢掉出厂字段，改前先 `--dump-config` 看清楚那一行原本有什么。
3. 这个文件保留**不是**因为它有效，而是因为它记录了「试过了、为什么不够」——删掉它会让后来人重复踩。新增覆盖层请同轮在本表加一行并写实测结论。
