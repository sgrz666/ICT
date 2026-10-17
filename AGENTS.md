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
| 上游变更（`upstream.lock.json` 更新） | `source/upstream/README.md` |
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
- 上游源码内部：`source/upstream/ray-optics/` 的各级 README 是上游资产，保持原样；项目侧说明降级写在 [`source/upstream/README.md`](source/upstream/README.md)。
- 数据叶子：`output/eduforge/candidates/offline-package/www/`（当前实测 2162 个静态资源文件，随构建内容变化）——模式写在父层 README，不逐叶撰写。模板实例目录（如 `catalog/templates/optics/convex-lens/`）**各配一份短 README**（状态、文件、关系），模板模式说明仍以 `catalog/templates/README.md` 为准。

**反向纪律：入库目录 100% 要有 README，包括只做分组的中间层。** 分组层（`catalog/templates/optics/`、`services/engine-host/src/adapters/`、`tests/adapters/` 这类「只装下一层目录」的目录）最容易被跳过——一旦漏掉，下一层 README 就成了没有父亲的孩子，读者无法判断层级关系。当前实测基线：项目侧 86 份 README 覆盖 85 个目录 + 仓库根，无缺失（2026-10-16）。

不写 README 的目录只有以下 8 类（磁盘实测目录数，截至 2026-10-16；每类都必须由「谁说明它」那份 README 兜住，兜不住就是文档缺陷）：

| 类别 | 目录数 | 谁说明它 |
|---|---|---|
| `source/upstream/ray-optics/` 内部 | 205 | `source/upstream/README.md` |
| `candidates/offline-package/www/` | 89 | `output/eduforge/candidates/README.md` |
| `output/eduforge/pgdata/` | 26 | `output/eduforge/README.md` |
| 各类 `dist/` 构建产物 | 8 | `apps/teacher-web/README.md`、`services/engine-host/README.md` |
| `artifacts/revisions/<uuid>/` | 5 | `output/eduforge/artifacts/README.md` |
| `code/eduforge/output/` | 3 | `code/eduforge/README.md` 目录地图 |
| `.workbuddy/` | 2 | 根 `README.md` 版本控制节 |
| `candidates/offline-package/` | 1 | `output/eduforge/candidates/README.md` |

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
python -c "
import re, pathlib
root = pathlib.Path('.')
skip = ('node_modules', '.venv', '.pytest_cache', '.git')
readmes = [p for p in root.rglob('README.md') if not any(s in p.parts for s in skip) and 'upstream' not in p.parts]
bad = []
for r in readmes:
    for m in re.finditer(r'\]\(([^)]+)\)', r.read_text(encoding='utf-8')):
        t = m.group(1).strip().split('#')[0]
        if t and not t.startswith(('http', 'mailto:')) and not (r.parent / t).resolve().exists():
            bad.append((str(r), t))
print('READMEs:', len(readmes), '| broken links:', len(bad))
for b in bad: print('BROKEN:', b)
"
```

## 6. 与其他纪律的关系

- **测试计数唯一来源**：`catalog/engines/ray-optics.yaml` 的 `test_totals`。改了测试规模只更新那一处，README 与计划文档只引用。
- **上游事实唯一权威**：`source/upstream/upstream.lock.json`。README 描述它、引用它，不复制它的内容；更新它之后同步 `source/upstream/README.md` 的描述。
- **证据登记**：新文件进 `output/eduforge/reports/` 时，在 `reports/README.md` 的清单里加一行（文件名、来源、内容）；历史失败现场保留并注明「按历史现场理解」。
- **`plan/` 只追加**：新文档落表登记，不改旧文档；进度变化写在推进计划的「实况」节（那也是它的纪律）。
