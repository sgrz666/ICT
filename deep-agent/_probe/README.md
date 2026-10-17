# _probe/ — 前置条件：缺陷基线副本与上游要求原文

## 职责

阶段 E 的**前提证据**。（1）保存「故意带缺陷」的测试对象副本，用来证明测试 3 的失败是被预先制造、而不是提前修好；（2）保存官方仓库几个关键文件的原文快照，作为「按官方要求办事」的可核对出处。

## 内容

| 文件 | 是什么 |
|---|---|
| `cart.py` | 缺陷基线副本：`apply_discount` 用 `total*percent // 100` 向下取整，违反「折扣四舍五入到分、半分进位」规则 |
| `test_cart.py` | 暴露它的测试：`apply_discount(1050, 5)` 期望 `997`（实际 `998`），另有 `cart_total` 端到端同根因用例。两份合起来 = `Ran 5 tests … FAILED (failures=2)`，退出码 1 |
| `gh_README.md`、`gh_AGENTS.md`、`gh_SAFETY.md`、`gh_development.md`、`gh_package.json`、`gh_pnpm-workspace.yaml` | 克隆前从 `raw.githubusercontent.com/deepseek-ai/deepseek-harness/master` 取的官方原文快照：安装三步、`engines.node ^22.19 \|\| >=24`、`packageManager pnpm@11.28.5`、`allowBuilds`/`minimumReleaseAgeExclude`/`patchedDependencies` 供应链策略、Windows/WSL 章节、SAFETY 的「未审计、沙箱不等于隔离」 |
| `__pycache__/` | Python 3.13 跑这两份测试时的字节码缓存，可再生，不入库 |

## 与上下层的关系

- 与真实工作区的关系：`../harness-smoke-workspace`（不入库，自带嵌套 `.git`）是实际跑测试的地方，基线提交 `b6e600c` 的内容就是本目录这两份文件；每次复跑前我用 `git checkout HEAD -- .` 把它还原到这里描述的状态，还原动作与结果都记在报告第 9 节。
- 被引用：[../harness-validation-reports/agent-loop-test-report.md](../harness-validation-reports/agent-loop-test-report.md) 测试 3、以及「不可提前人工修好」这条验收。
- 官方要求的权威是那个 commit 本身，本目录快照只用于核对读到的内容，不替代它。

## 已知的坑与纪律

1. **这两份文件不许被修好**。`cart.py` 一旦被改正，测试 3 的「失败→修复」闭环就失去意义。要留修复成品，另存文件（例：`../_logs/t3_agent_fixed_cart.py`）。
2. 基线状态可随时复核：`python -m unittest -v` 在本目录应报 `FAILED (failures=2)`。若变成 3 个失败，说明有新的测试文件被并入了工作区而不是这里（`t4` 那轮曾加过 CLI 用例）。
3. `gh_*.md` 是克隆时点的快照，上游会变；引用结论时以 `../deepseek-harness` 里的实际文件为准，本目录只证明「我当时读到过什么」。
4. **`gh_*.md` 内的相对链接不检查**：它们是上游仓库的逐字副本，链接指向的是上游仓库内的路径（`docs/…`、`packages/…`），在这里必然解析不到。文档门 [`../_tools/check_docs.py`](../_tools/check_docs.py) 按 `gh_*.md` 豁免，与 ICT 纪律「上游内部 README 保持原样」同理。要核对这些链接，去 `../deepseek-harness` 里看原件。
4. 目录名带下划线前缀表示「支撑材料」，与 `_tools/`、`_logs/` 同层，不属于交付正文。
