# AGENTS.md — deep-agent 目录的 Agent 纪律：每个文件夹都要有架构级 README

本文件对任何在 `deep-agent/` 下工作的 Agent 生效，人也要遵守。它继承仓库根 [`../AGENTS.md`](../AGENTS.md) 的总纪律（README 与代码同变），并把「目录必须被说明」这条在本目录内**提高到硬门**。

## 核心一条

> **`deep-agent/` 下每一个存在文件的文件夹，都必须有一份 `README.md`，写清这个目录在验证链路里的位置、里面有什么、每个文件为什么存在、以及读它的人会踩的坑。少一份，任务就不算完成。**

理由：这个目录的全部价值是**可复核的证据**。报告说「Agent 真的跑了测试」，读者必须能顺着链接走到 `_logs/*.jsonl` 里亲眼看见那条 `FAIL` 输出，再走到 `_probe/` 确认缺陷是预先存在的，走到 `_tools/` 知道是哪个命令生成的。任何一个没被说明的目录都会让证据链在那里断掉——断掉的证据链比没有证据更糟，因为它看起来像完整的。

## 1. 什么时候必须写或改

- 新建目录：落地同时写它的 `README.md`，并在上一级 README 的目录地图里登记。
- 目录里新增 / 删除 / 重命名 / 移动文件：同轮更新该目录 README；影响的下游结论一并更新。
- 产生新的运行证据（新日志、新会话、新退出码、新耗时、新 token 计数）：登记进 `_logs/README.md`，并在报告里引用。
- 修复或推翻了一个已知坑：改 `_logs`／`README.md` 的「已知的坑」节，**保留旧记录**，追加「修复后复跑」，不要覆盖原文——失败现场本身是结论的一部分。
- 只读探查不触发；只要落盘了改动就触发。

## 2. 每份目录 README 的四段式（必须按这个骨架写）

1. **职责**：这个目录在全链路（阶段 A 环境 → B 构建 → C Web UI → D API 接入 → E Agent 循环 → F 报告）里承担哪一段，一句话说清。
2. **内容**：逐个真实文件说明它是什么、由谁生成、读者该拿它干什么。数字必须是实测值（退出码、耗时、调用次数、token、文件数），不许写「一些脚本」「相关日志」这类空话。
3. **与上下层的关系**：链到它依赖谁、谁消费它（相对链接，且必须可解析）；跨目录的结论只引用、不复制。
4. **已知的坑与纪律**：本目录特有的陷阱（路径、编码、权限、脱敏要求、并行会话冲突点）。

额外两条本目录特有：

- **一份事实只有一个家**。计数、SHA、版本号写死在唯一归属处（SHA 与版本在 `README.md` 顶部，测试计数在各报告里），其余位置只引用。上游事实的权威是 `deepseek-harness` 那个 commit，不复制进本目录。
- **状态词要保守**。没跑过写 `pending`；失败现场如实写「未通过 / 环境阻塞」；修复后另起一节复跑并给新证据。禁止用「框架启动成功」代替「Agent 能力验证成功」这类降级替换。

## 3. 不允许写 README 的地方

| 目录 | 为什么不写 | 谁说明它 |
|---|---|---|
| `deepseek-harness/` | 2.7 GB 第三方源码，内部 README 是上游资产，保持原样 | 本目录 `README.md` + 报告的 architecture-notes |
| `_corepack/`、`.dsh-home/`、各 `node_modules/`、`__pycache__/` | 缓存与可再生产物 | `README.md` 目录地图 + `_logs/README.md` |
| `harness-smoke-workspace/`、`harness-ui-workspace/_acl-out/` | 一次性工作区（含嵌套 `.git`）与权限备份，不入库 | 本 `README.md` 第 8 节坑与 `_tools/README.md` |

被判「不入库 / 不写 README」的目录，必须在某个入库 README 里被点名说明——否则读者无法判断它是缺失还是有意排除。

## 4. 安全纪律（不可协商）

1. **密钥**：唯一允许的位置是 `deepseek-harness/.env`（被上游 `.gitignore` 覆盖）。任何报告、日志、README、提交信息都不得出现明文 key；提交前必须跑第 6 节的扫描。本地 UI token 属同类，落盘即脱敏。
2. **不要给 Agent 真实业务目录**。工作区必须是一次性目录，并把 `sandbox-policy` 的可写根钉在它身上；`workspace-write` 是默认档，**不要**为了让演示通过而全局切 `danger-full-access`——真要用，就在报告里标注哪些结论是在该模式下取得的。
3. **不改上游**：`deepseek-harness/` 里除 `.env` 外不得有任何 tracked 文件被修改，收尾前用第 6 节命令验证。
4. **遥测**：默认「使用官方模型 API 时上传 Session Log」为开启。涉及真实项目时先关。
5. 需要改系统权限（ACL、注册表、全局配置）时，只用官方脚本、范围严格等于工作区根、保留备份与回滚命令，**并向用户确认后再动手**。

## 5. 完成定义（收尾前逐条自查）

- [ ] `deep-agent/` 下每个含文件的目录都有 `README.md`（第 6 节命令的 `missing` 必须为 0，排除第 3 节名单）；
- [ ] 每份都满足四段式，内容段的文件名与磁盘一致、数字为实测；
- [ ] 新增目录已登记进上一级 README 的目录地图；
- [ ] 相对链接全部可解析，无指向已删除文件的残留；
- [ ] 失败与修复并存留痕：同一事实不被覆盖，只追加；
- [ ] 未跑过的能力标 `pending`，未验证与「官方已有本轮未验证」分开写；
- [ ] 密钥扫描干净、上游 tracked 文件零改动。

## 6. 验证命令

```bash
cd D:/codeplus/ICT/deep-agent

# 文档门：每目录 README 覆盖 + 相对链接可解析（缺失或断链即非零退出）
python _tools/check_docs.py
```

脚本用 `os.walk` 就地剪枝，**绝不进入** `deepseek-harness/`、`_corepack/`、各 `node_modules/`。不要把它改写成 `find -not -path` 或 `pathlib.rglob` 那种形式——那两种写法会先把 2.7 GB 的上游树整颗遍历一遍，实测会卡住几分钟（我第一版就踩了）。新增排除项要同时改脚本里的 `SKIP` 和本文件第 3 节的名单。`_probe/gh_*.md` 是上游逐字快照，链接指向上游仓库，按 `gh_*.md` 豁免（理由写在 `_probe/README.md`）。

```bash
# 密钥与 token 扫描（任何输出都要立刻处理，不得提交）
grep -rn "sk-[A-Za-z0-9]\{16,\}" . --exclude-dir=deepseek-harness --exclude-dir=_corepack --exclude-dir=.dsh-home --exclude-dir=harness-smoke-workspace
grep -rlE 'token=[A-Za-z0-9_.-]{20,}' . --exclude-dir=deepseek-harness --exclude-dir=harness-smoke-workspace

# 上游零改动
git -C deepseek-harness status --porcelain --untracked-files=no   # 必须为空

# 提交前只看自己动过的路径：仓库里有并行会话同时在改 EduForge 生产文件，禁止 git add -A
git -C /d/codeplus/ICT status --short -- deep-agent .gitignore
```

## 7. 与报告体系的分工

- `harness-validation-reports/` 五份交付报告是**结论**所在；`_logs/` 是**原始证据**所在；`_tools/` 是**如何复现**所在；`_probe/` 与 `patches/` 是**前提条件**所在。目录 README 负责解释「这里有什么、为什么」，不重复结论正文。
- 报告里每个「通过 / 未通过」都必须能被 `_logs/README.md` 的索引追到具体文件；追不到就写 `pending` 或删除该结论。

## 8. 本目录特有的坑

- `run_headless.sh` 会先读 prompt 文件再 `cd` 到工作区（曾有 bug 是先 `cd` 导致相对路径找不到）。改它时保留这个顺序。
- 会话持久化落在**工作区**的 `.sessions/`，不在本目录；找恢复用的 `sessionId` 去 `_logs/<stem>.jsonl` 首行。
- 中文 PowerShell 输出在部分 shell 下会乱码（GBK），需要英文回显时用 `pwsh -NoProfile`。
- 并行会话可能同时在改 ICT 仓库根的 `README.md` 与 `.gitignore`：只按路径 `git add` 自己动过的文件，父层 README 若被别人改动占着，就把缺口登记在本 `README.md` 里而不是覆盖。
