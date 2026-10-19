# source/library — 实验资源目录（Agent 可直接消费的那一层）

职责：把「装了哪些上游引擎」和「教师能挑哪些实验」连起来。`source/upstream` 回答的是磁盘上有什么，这里回答的是**每个实验用哪个引擎、种子文件在哪、Agent 能改哪些参数、改完拿什么独立公式验收**。

## 内容

- `experiments.json` — 目录本体。9 个引擎条目 + 18 个实验条目 + 3 条「本轮没装」的记录。实验按 P0/P1/P2 分优先级（实测计数：P0 9 条、P1 7 条、P2 2 条）；状态词只有四种，含义写死在文件开头的 `status_words` 里，避免把「装了源码」说成「接通了」。
- `check_catalog.py` — 校验器。把 `experiments.json` 里引用的每一条 `install_path`/`seed`/`npm_component`/证据路径拿去磁盘上 `os.path.exists`，**missing 必须为 0** 才算这份目录可用。2026-10-19 实测：`paths checked: 49 | missing: 0`。

跑校验（仓库根目录）：

```bash
python source/library/check_catalog.py   # 退出码 0 = 路径全通
```

## 与上下层的关系

- 上游是 [`../upstream/inventory.json`](../upstream/inventory.json)（脚本生成的实测事实）与 [`../upstream/upstream.lock.json`](../upstream/upstream.lock.json)（身份与构建结论）；这里的数字全部从那儿誊来，不另起一套计数。
- 组件类（three / matter-js / rapier3d-compat）落在 [`../components/`](../components/README.md)，可加载性实测证据是 `../components/component-probe.json`。
- 下游是 `code/eduforge/catalog/templates/`：那边放**已经能做参数修改与验证**的模板三件套，这边放**资源已装但还没适配器**的候选。两边状态词不同，不能混用——当前只有 `optics/convex-lens` 在下游是 `template_connected`。

## 已知的坑与纪律

1. **状态词不许拔高**。18 条实验里只有 `mech3d-free-fall-collision` 达到 `component_headless_verified`（Rapier 无头跑出 1s 自由落体 y=15.075，理论 15.095，偏差 0.020 m）。其余一律 `resource_installed`：源码在盘上，但 Agent 还改不动，别对外说成「18 个实验已支持 AI 定制」。
2. **PhET 的 main 分支是空壳**。各仿真仓库 main 只剩 README.md + doc/（实测 3~5 个文件），完整源码在 X.Y 发行分支上；`experiments.json` 里记录的 sim 路径全部指向 `source/upstream/phet/sims/<name>`（发行分支克隆）。`circuit-construction-kit-common` 只有 main，是这批里唯一的空壳。
3. **许可义务要在装的时候就写清楚**，不要等到分发前。GPL-2.0（circuitjs1）、GPL-3.0（PhET 仿真源码）、AGPL-3.0（Stellarium Web Engine）三条各有不同的触发条件，已分别登记在 `experiments.json` 的 `license_obligation` 里。
4. **没权威来源就不装**。OSP@Singapore（EJSS）与 3JCN 记在 `not_installed`：GitHub 上找不到可确认的官方仓库（猜测的 wejen/osp-tools/compadre-io 实测均 404），搜到的都是个人复刻、许可参差。宁可留候选记录，也不把来路不明的代码请进工作区。
5. **改完这个 JSON 必须重跑校验**。路径写错在肉眼 review 时最难发现，而 Agent 取种子时必然踩。
6. 调研阶段那份 44 项候选清单（Markdown + JSON）**在本仓库磁盘上不存在**（2026-10-19 全库搜过），这里落的是其中 18 项 P0/P1/P2 的可核对版本；其余候选要接的时候再补条目，不要凭记忆扩写。
