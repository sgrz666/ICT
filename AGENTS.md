# AGENTS.md — 仓库级 Agent 纪律：README 与代码同变

本文件对所有在本工作区执行任务的 Agent 生效，人也要遵守。核心一条：

> **改完代码，必须同轮更新受影响目录的 README。README 与代码同变，是任务完成定义的一部分——没同步 README，等于任务没做完。**

本仓库有一套人工撰写的目录 README 体系（入口：[`README.md`](README.md)），作用是「读 README 即知这个文件夹的层级与内容关系」。代码在演进，README 不跟着变就会从资产变成谎言——比没有更糟。本文件规定：什么时候必须更新、更新哪一份、按什么风格更新、怎么验证。

## 1. 什么时候必须更新

任务涉及以下任一类改动，收尾前必须同步 README：

- 新增 / 删除 / 重命名 / 移动文件或目录；
- 空目录被首次使用（原「预留，当前为空」的措辞必须改），或反向清空；
- 数量、版本、指标、状态发生变化（测试数、文件数、版本号、pending → 实测通过）；
- 新工具脚本、新测试、新模板、新引擎、新报告、新候选产物落地；
- 行为或边界变化：修掉了某个已知坑、限制放宽或收紧、能力项从 pending 变为已实测。

只读的探查、分析、问答不触发本纪律；但凡落盘了改动，就触发。

## 2. 改什么 → 更新哪份（映射表）

| 改动类型 | 必须更新的 README |
|---|---|
| 顶层目录增删 | `README.md`（目录地图） |
| `code/` 下新增工程 | `code/README.md` + 新工程自己的 README |
| eduforge 工程级配置（`pyproject.toml` / `pnpm-workspace.yaml` / 依赖） | `code/eduforge/README.md` |
| 新增 app，或其组件 / 依赖变化 | `code/eduforge/apps/README.md` + `apps/teacher-web/README.md` |
| 新增引擎描述，或能力状态变化 | `code/eduforge/catalog/engines/README.md` |
| 新增模板 | `code/eduforge/catalog/templates/README.md` + 模板目录自己的短 README |
| OpenAPI 再生成 / 契约变化 | `code/eduforge/packages/contracts/README.md` |
| Python 模块增删或职责变化 | `code/eduforge/python/src/README.md`（模块地图） |
| engine-host 源码 / 测试 / 端口变化 | `code/eduforge/services/engine-host/README.md` |
| 新增 pytest 文件 | `code/eduforge/tests/python/README.md`（文件地图） |
| 新增 `tools/` 脚本 | `code/eduforge/tools/README.md` |
| 新 REA 分析输入 | `input/README.md` |
| 新产出（reports / candidates / artifacts / research） | `output/eduforge/README.md` 及对应子目录 README |
| 新计划文档 | `plan/README.md`（只加行，不改旧文档，`plan/` 只追加不回改） |
| 上游变更（`upstream.lock.json` 更新） | `source/upstream/README.md`（引擎表 + 体积列）|
| 新增/替换上游引擎克隆、改克隆方式（浅克隆↔稀疏检出） | `source/upstream/upstream.lock.json` + `source/upstream/README.md` + 重跑 `source/upstream/inspect_upstreams.py` |
| 新增 npm 组件或改钉版本 | `source/components/README.md`（含 `probe_components.mjs` 的可加载性结论） |
| 新增/修改实验目录条目 | `source/library/README.md` + `source/library/experiments.json`，并跑 `python source/library/check_catalog.py`（missing 必须为 0） |
| 测试规模变化 | 只改 `code/eduforge/catalog/engines/ray-optics.yaml` 的 `test_totals`（全仓库唯一计数处），各 README 只引用、不重复记数 |

新增目录时，按同一风格为它写一份新 README（见第 3 节），并在父层 README 里登记。

## 3. 写法规范（与现有 74 份一致）

1. **结构四段式**：职责 → 内容（真实文件名、实测数字）→ 与上下层的关系 → 已知的坑与纪律。
2. 简体中文，具体到文件名；不写「专门功能模块或产物」这类空话模板。
3. **只记实测**：没跑过的一律标 `pending`，不写成已完成；数字与磁盘实测冲突时以实测为准，并把冲突留痕在 README 里。
4. 相对链接，且必须可解析（用第 5 节命令验证）。
5. 改已有 README：先 Read 再 Edit，保留原结构与措辞，只更新变化的部分——不整篇重写，不冲掉别人写的内容。
6. 状态词要保守：失败现场、未闭环项、已知未做，如实写，不粉饰。

## 4. 不要写 README 的地方

- 依赖与缓存目录：`node_modules/`、`.venv/`、`dist/`、`__pycache__/`、`.pytest_cache/`——由所属层 README 统一说明。
- **第三方大仓**：`deep-agent/deepseek-harness/`（2.7 GB 上游源码，验证对象本体）内部 README 是上游资产，保持原样；项目侧说明在 [`deep-agent/README.md`](deep-agent/README.md) 与 [`deep-agent/AGENTS.md`](deep-agent/AGENTS.md) 第 3 节。**任何遍历命令都必须先剪枝**（`os.walk` 就地剪 `subdirs`），包括本文第 5 节的校验脚本——用 `pathlib.rglob` 或 `find -not -path` 会先把整棵上游树走一遍，实测卡几分钟，还会把上游的几百份 README 误计进项目侧数字。
- 上游源码内部：`source/upstream/` 下**每一个引擎克隆**（`ray-optics/`、`myphysicslab/`、`circuitjs1/`、`matter-js/`、`rapier-js/`、`three/`、`stellarium-web-engine/`、`webots/`、`phet/libs/`、`phet/sims/`）的各级 README 都是上游资产，保持原样、不入库；项目侧说明降级写在 [`source/upstream/README.md`](source/upstream/README.md) 的引擎表里，体积与文件数以 [`source/upstream/inventory.json`](source/upstream/inventory.json) 为准。同理：`source/components/node_modules/` 是依赖目录，说明在 [`source/components/README.md`](source/components/README.md)。**遍历时必须先剪掉带 `.git` 的子目录**（这些克隆每个都自带 `.git` 与上万文件，不剪就走不完）。
- 数据叶子：`output/eduforge/candidates/offline-package/www/`（当前实测 2162 个静态资源文件，随构建内容变化）——模式写在父层 README，不逐叶撰写。模板实例目录（如 `catalog/templates/optics/convex-lens/`）**各配一份短 README**（状态、文件、关系），模板模式说明仍以 `catalog/templates/README.md` 为准。

**反向纪律：入库目录 100% 要有 README，包括只做分组的中间层。** 分组层（`catalog/templates/optics/`、`services/engine-host/src/adapters/`、`tests/adapters/` 这类「只装下一层目录」的目录）最容易被跳过——一旦漏掉，下一层 README 就成了没有父亲的孩子，读者无法判断层级关系。当前实测基线：命令 (1) 输出 **`tracked dirs: 100 | missing README: 0`**，磁盘上项目侧 README 共 **108 份**（2026-10-19 资源库安装轮）。与上一基线 101 份（2026-10-18）的差额来源：本轮新增 `source/components/README.md` 与 `source/library/README.md` 两份，其余是并行会话在 `code/eduforge` 一侧同期落盘的 README——本轮没动那些目录，只按实测登记，不改写别人的数字。

不写 README 的目录只有以下 11 类（磁盘实测目录数，截至 2026-10-16，后三类截至 2026-10-18 与 2026-10-19；每类都必须由「谁说明它」那份 README 兜住，兜不住就是文档缺陷）：

| 类别 | 目录数 | 谁说明它 |
|---|---|---|
| `source/upstream/` 各引擎克隆内部（ray-optics 实测 205，其余 8 类见下条口径） | 不实测（每个克隆自带 `.git`，剪枝要求见上） | `source/upstream/README.md` 引擎表 + `source/upstream/inventory.json` |
| `source/components/node_modules/` | 不实测（npm 依赖目录） | `source/components/README.md` |
| `candidates/offline-package/www/` | 89 | `output/eduforge/candidates/README.md` |
| `output/eduforge/pgdata/` | 26 | `output/eduforge/README.md` |
| 各类 `dist/` 构建产物 | 8 | `apps/teacher-web/README.md`、`services/engine-host/README.md` |
| `artifacts/revisions/<uuid>/` | 5 | `output/eduforge/artifacts/README.md` |
| `code/eduforge/output/` | 3 | `code/eduforge/README.md` 目录地图 |
| `.workbuddy/` | 2 | 根 `README.md` 版本控制节 |
| `candidates/offline-package/` | 1 | `output/eduforge/candidates/README.md` |
| `deep-agent/deepseek-harness/` 内部 | 不实测（剪枝要求见上） | `deep-agent/README.md`、`deep-agent/AGENTS.md` 第 3 节 |
| `deep-agent/` 运行时目录（`.dsh-home/`、`_corepack/`、`harness-smoke-workspace/`、`_probe/__pycache__/`） | 4 | `deep-agent/README.md` 目录地图（`.dsh-home/` 含 `.credentials.yaml`，敏感，勿复制外发） |

被 `.gitignore` 整目录挡住的类别（candidates、artifacts），若要给它或它的子目录写 README，`.gitignore` 必须写成 `dir/*` + `!dir/README.md` 两行——只写 `dir/` 会让 README 无法入库，README 体系在克隆出来之后就残缺了。

## 5. 完成定义（收尾前自查）

- [ ] 改动涉及的每个目录，其 README 已同步；新增目录已按同一风格写好新 README；
- [ ] **入库目录 100% 有 README**：`git ls-files` 涉及的每个目录都存在 `README.md`（缺失数必须为 0），新增的分组层目录也算；
- [ ] 被删除 / 重命名的文件，在所有 README 里无残留引用；
- [ ] 相对链接全部可解析（下面命令跑过，`broken = 0`）；
- [ ] 数字与磁盘实测一致（计数、版本、字节数以实测为准）；
- [ ] 状态词准确：未跑过标 `pending`，不拔高；
- [ ] 空目录被使用时，「预留」措辞已更新；反向清空时已改回「预留」。

验证命令（工作区根目录跑，需要 python3）：

```bash
# (1) 入库目录 100% 有 README：missing 必须为 0
python -c "
import subprocess, os
subprocess.run(['git', 'config', 'core.quotePath', 'false'])
tracked = subprocess.run(['git', 'ls-files'], capture_output=True, text=True, encoding='utf-8', errors='replace').stdout.splitlines()
dirs = set()
for f in tracked:
    d = os.path.dirname(f)
    while d:
        dirs.add(d); d = os.path.dirname(d)
missing = [d for d in sorted(dirs) if not os.path.exists(os.path.join(d, 'README.md'))]
print('tracked dirs:', len(dirs), '| missing README:', len(missing), missing)
"

# (2) 相对链接可解析：broken links 必须为 0（就地剪枝，绝不进入第三方大仓）
python -c "
import os, re
PRUNE = {'node_modules', '.venv', '.pytest_cache', '.git', '__pycache__', 'dist',
         'deepseek-harness', '_corepack', '.dsh-home', 'harness-smoke-workspace'}
EXCLUDE_DIRS = ('source/upstream/ray-optics',)   # 上游资产：README 保持原样，不检查其内部链接
readmes = []
for base, sub, files in os.walk('.'):
    # 剪掉固定名单 + 任何「自带 .git 的子目录」：source/upstream 下每个引擎克隆、
    # deep-agent 的上游大仓、一次性工作区都在这一刀里剪掉，不用逐个点名。
    sub[:] = [d for d in sub if d not in PRUNE and not os.path.isdir(os.path.join(base, d, '.git'))]
    rel = os.path.relpath(base, '.').replace(os.sep, '/')
    if any(rel.startswith(p) for p in EXCLUDE_DIRS):
        continue
    if 'README.md' in files:
        readmes.append(os.path.join(base, 'README.md'))
bad = []
for r in readmes:
    for m in re.finditer(r'\]\(([^)]+)\)', open(r, encoding='utf-8').read()):
        t = m.group(1).strip().split('#')[0]
        if t and not t.startswith(('http', 'mailto:')):
            if not os.path.exists(os.path.normpath(os.path.join(os.path.dirname(r), t))):
                bad.append((r, t))
print('READMEs:', len(readmes), '| broken links:', len(bad))
for b in bad: print('BROKEN:', b)
"
```

实测基线（2026-10-18）：命令 (1) 输出 `tracked dirs: 98 | missing README: 0 []`（另有 2 个正在写入、尚未 `git add` 的目录 `code/eduforge/catalog/templates/optics/{camera-principle,concave-lens}`，磁盘上也已各有 README，故入库目录 + 待入库目录 = 100 个且缺失为 0）；命令 (2) 输出 `READMEs: 101 | broken links: 0`。

实测基线（2026-10-19，资源库安装轮）：命令 (1) 输出 `tracked dirs: 100 | missing README: 0 []`；命令 (2) 输出 `READMEs: 108 | broken links: 0`。命令 (2) 的剪枝这一轮加了一条通用规则——**任何自带 `.git` 的子目录直接剪掉**，因此 `source/upstream/` 下新装的 8 类引擎克隆（myphysicslab / circuitjs1 / matter-js / rapier-js / three / stellarium-web-engine / webots / phet 的 30 个仓库）不会把上万个上游 README 计进来；不加这一刀，实测会多扫 1.8 万多个文件并把上游 README 误计入项目侧数字。`deep-agent/` 另有自己的更严的门：`python deep-agent/_tools/check_docs.py`（它同时要求该目录下每个含文件的子目录都有 README，2026-10-18 实测 `dirs checked: 9 | README missing: 0 | broken links: 0`）。

## 6. 与其他纪律的关系

- **测试计数唯一来源**：`catalog/engines/ray-optics.yaml` 的 `test_totals`。改了测试规模只更新那一处，README 与计划文档只引用。
- **上游事实唯一权威**：`source/upstream/upstream.lock.json`。README 描述它、引用它，不复制它的内容；更新它之后同步 `source/upstream/README.md` 的描述。
- **证据登记**：新文件进 `output/eduforge/reports/` 时，在 `reports/README.md` 的清单里加一行（文件名、来源、内容）；历史失败现场保留并注明「按历史现场理解」。
- **`plan/` 只追加**：新文档落表登记，不改旧文档；进度变化写在推进计划的「实况」节（那也是它的纪律）。
