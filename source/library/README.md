# source/library — 实验资源目录（Agent 可直接消费的那一层）

职责：把「装了哪些上游引擎」和「教师能挑哪些实验」连起来。`source/upstream` 回答的是磁盘上有什么，这里回答的是**每个实验用哪个引擎、种子文件在哪、Agent 能改哪些参数、改完拿什么独立公式验收**。

## 内容

- `experiments.json` — 目录本体。9 个引擎条目 + 18 个实验条目 + 3 条「本轮没装」的记录。实验按 P0/P1/P2 分优先级（实测计数：P0 9 条、P1 7 条、P2 2 条）；状态词有五种（`template_connected` / `engine_headless_verified` / `component_headless_verified` / `resource_installed` / `reference_only`），含义写死在文件开头的 `status_words` 里，避免把「装了源码」说成「接通了」。当前分布（2026-10-19 实测）：`engine_headless_verified` 6 条（平面镜、折射、全反射、凹透镜、单摆、弹簧振子）、`component_headless_verified` 1 条（3D 自由落体）、`resource_installed` 11 条。
- `optics_hall.mjs` + `optics-hall-evidence.json` — 光学实验馆的验收台（`node source/library/optics_hall.mjs --json`）。四个场景（平面镜 / 折射 / 全反射临界角扫描 / 凹透镜焦距反解）全部用与引擎无关的解析式判对错，2026-10-19 实测 **4/4 pass**。凹透镜那条从两个屏的束宽反解出 |f| = 100.00000000000037（设定 −100），全程不读引擎自报的焦距。
- `check_catalog.py` — 校验器。除了把 `install_path`/`seed`/`npm_component`/`measured_evidence`/证据路径逐条拿去 `os.path.exists`（**missing 必须为 0），还做三项自检：状态词必须在 `status_words` 里有定义、实验引用的 engine id 必须存在于 `engines`、标 `*verified` 的实验必须带 `measured_evidence`（防「口头已验证」）。2026-10-19 实测：`paths checked: 52 | missing: 0`，三项自检各 0 项问题（「measured_evidence 混进中文括注导致路径不可查」这一条就是它先逮出来的，已拆成 `measured_evidence` + `measured_note`）。

跑校验（仓库根目录）：

```bash
python source/library/check_catalog.py   # 退出码 0 = 路径全通
```

## 与上下层的关系

- 上游是 [`../upstream/inventory.json`](../upstream/inventory.json)（脚本生成的实测事实）与 [`../upstream/upstream.lock.json`](../upstream/upstream.lock.json)（身份与构建结论）；这里的数字全部从那儿誊来，不另起一套计数。
- 组件类（three / matter-js / rapier3d-compat）落在 [`../components/`](../components/README.md)，可加载性实测证据是 `../components/component-probe.json`。
- 下游是 `code/eduforge/catalog/templates/`：那边放**已经能做参数修改与验证**的模板三件套，这边放**资源已装但还没适配器**的候选。两边状态词不同，不能混用——当前只有 `optics/convex-lens` 在下游是 `template_connected`。

## 已知的坑与纪律

1. **状态词不许拔高**。18 条实验里 7 条达到了「本机真跑出可对账的物理量」：4 条光学（`optics_hall.mjs`：平面镜 200.5 vs 解析 200、折射 449.5 vs 450、临界角落在 (40°,42°] 对上 asin(1/1.5)=41.81°、凹透镜由束宽反解出 |f|=100.00000000000037）、单摆（2.00835 s vs 2.00834 s）、3D 自由落体（15.075 vs 15.095）。其余 11 条一律 `resource_installed`：源码在盘上，但 Agent 还改不动。注意这 7 条也**还没有模板与适配器**——能无头取数 ≠ 教师能一句话定制并拿到离线包。
2. **光学的两个静默陷阱**（本轮实测踩过）：点必须写成 `{x,y}`，写成 `[x,y]` 时 `loadJSON` 不报错但光线一步就没了；`PlaneGlass` 的玻璃在 `p1→p2` 的**左手侧**，光源放错侧时「全反射」会退化成光在空气里直走而**看起来仍然通过**。所以验收台自带一条 `refIndex=1.0` 的对照跑：先证明几何基线，再谈物理。
3. **PhET 的 main 分支是空壳**。各仿真仓库 main 只剩 README.md + doc/（实测 3~5 个文件），完整源码在 X.Y 发行分支上；`experiments.json` 里记录的 sim 路径全部指向 `source/upstream/phet/sims/<name>`（发行分支克隆）。`circuit-construction-kit-common` 只有 main，是这批里唯一的空壳。
4. **许可义务要在装的时候就写清楚**，不要等到分发前。GPL-2.0（circuitjs1）、GPL-3.0（PhET 仿真源码）、AGPL-3.0（Stellarium Web Engine）三条各有不同的触发条件，已分别登记在 `experiments.json` 的 `license_obligation` 里。
5. **没权威来源就不装**。OSP@Singapore（EJSS）与 3JCN 记在 `not_installed`：GitHub 上找不到可确认的官方仓库（猜测的 wejen/osp-tools/compadre-io 实测均 404），搜到的都是个人复刻、许可参差。宁可留候选记录，也不把来路不明的代码请进工作区。
6. **改完这个 JSON 必须重跑校验**。路径写错在肉眼 review 时最难发现，而 Agent 取种子时必然踩。
7. 调研阶段那份 44 项候选清单（Markdown + JSON）**在本仓库磁盘上不存在**（2026-10-19 全库搜过），这里落的是其中 18 项 P0/P1/P2 的可核对版本；其余候选要接的时候再补条目，不要凭记忆扩写。
