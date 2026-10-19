# source/library — 实验资源目录（Agent 可直接消费的那一层）

职责：把「装了哪些上游引擎」和「教师能挑哪些实验」连起来。`source/upstream` 回答的是磁盘上有什么，这里回答的是**每个实验用哪个引擎、种子文件在哪、Agent 能改哪些参数、改完拿什么独立公式验收**。

## 内容

- `experiments.json` — 目录本体。9 个引擎条目 + 18 个实验条目 + 3 条「本轮没装」的记录。实验按 P0/P1/P2 分优先级（实测计数：P0 9 条、P1 7 条、P2 2 条）；状态词有六种（`template_connected` / `engine_headless_verified` / `component_headless_verified` / `engine_browser_verified` / `resource_installed` / `reference_only`），含义写死在文件开头的 `status_words` 里，避免把「装了源码」说成「接通了」。当前分布（2026-10-19 实测）：`engine_headless_verified` 7 条（平面镜、折射、全反射、凹透镜、三棱镜、单摆、弹簧振子）、`component_headless_verified` 3 条（3D 自由落体、平抛/斜抛、带电粒子在磁场中）、`engine_browser_verified` 3 条（欧姆定律、串并联、RC 充电，浏览器里读引擎自己的电气量）、`resource_installed` 5 条。
- `optics_hall.mjs` + `optics-hall-evidence.json` — 光学实验馆的验收台（`node source/library/optics_hall.mjs --json`）。五个场景（平面镜 / 折射 / 全反射临界角扫描 / 凹透镜焦距反解 / 三棱镜色散）全部用与引擎无关的解析式判对错，2026-10-19 实测 **5/5 pass**。凹透镜那条从两个屏的束宽反解出 |f| = 100.00000000000037（设定 −100），全程不读引擎自报的焦距；三棱镜那条由脚本自写一套矢量斯涅尔追迹（refract + 逐面求交）作对照，两个折射率下屏上落点 −165.5 / −186.5 vs 解析 −165.815 / −186.609，两色差 −21.0 vs −20.793。
- `projectile_lab.mjs` + `projectile-lab-evidence.json` — 抛体验收台（`node source/library/projectile_lab.mjs --json`），引擎是 npm 组件 matter-js。先做**单位标定**（实测律 `a = gravity.y × gravity.scale × 1e6`，自由落体反解 9.80000 m/s²），再拿解析式判平抛（时间 2.0182 s vs 2.0203、射程 30.2733 vs 30.3046）、斜抛 45°（射程 40.7574 vs 40.8163、最高点 10.1746 vs 10.2041）、互补角等射程（30°/60° = 0.9991，**判据里不含 g**，单位标定错了也瞒不过去）。2026-10-19 实测 **5/5 pass**。
- `field3d_lab.mjs` + `field3d-lab-evidence.json` — 3D 电磁验收台（`node source/library/field3d_lab.mjs --json`），引擎是 `@dimforge/rapier3d-compat`。Rapier 不懂洛伦兹力，所以力由脚本每步 `qv×B` 施加，验收用**自写最小二乘圆拟合**（不读引擎自报的任何量）：半径 3.3597 vs `mv/(|q|B)`=3.3333、角速度 1.19999 vs 1.2、由累积转角反出的周期 5.23603 vs 5.23599、拟合残差/半径 0.285%、q 反号则旋向反号、螺旋螺距 7.8566 vs `v∥·T`=7.8540、q=0 时侧向偏移 0。2026-10-19 实测 **5/5 pass**。
- `collisions_lab.mjs` + `collisions-lab-evidence.json` — 碰撞/动量验收台（`node source/library/collisions_lab.mjs --json`），**同一套解析式分别喂给 matter-js 与 Rapier**。结论 6/9 pass，而且败的那三条比赢的更有用：Rapier 的弹性碰撞全中（等质量 4/−2 → −2/4 精确、2 kg 撞 1 kg 得 1.66667/6.66667、弹性斜碰出射夹角 90.000° 且 |vA|²+|vB|² = 25.000、restitution=0.5 时动量守恒而动能掉 37.5%）；Matter 的自由-自由弹性正碰把 10 J 吃到 1.21 J，「n 进 n 出」的牛顿摆两个引擎都不成立（Rapier 5 球排一列被撞后 4 球同动、末端只拿到 1.588 m/s）。⇒ 动量守恒定量交付只能用 Rapier 或专用一维硬球模型，牛顿摆这条**不许**标成已验证。
- `circuit_harness.html` + `serve_circuitjs.py` + `circuit-lab-evidence.json` — 电学验收台（唯一走浏览器的一条，因为 CircuitJS1 的产物是 GWT 编译的 JS）。官方 JavaScript 接口只有 12 个方法且**没有元件参数 setter**，所以「Agent 改参」的路径是 `importCircuit(整份电路文本)`；读数用 `getCurrent()`/`getVoltageDiff()`（double）与 `getInfo()`（渲染串，只有 4 位有效，别当高精度用）。2026-10-19 实测 5/5 pass：欧姆 R=100 ⇒ 50 mA；把 R 改成 470 Ω ⇒ `getCurrent()` = 0.010638297872340425 A，与 5/470 逐位相同（「改参→引擎跟着变」的硬证）；串联 100+220 处处 15.625 mA、分压 1.563+3.438 = 5.001 V；并联两支路 50 / 22.727 mA、Req 68.75 Ω；RC 充电 Vc(0.084 s) = 2.830616 V（解析 2.8418，偏 0.39%，成因是引擎自报时间与状态差约 1~2 步长）。
- `check_catalog.py` — 校验器。除了把 `install_path`/`seed`/`npm_component`/`measured_evidence`/证据路径逐条拿去 `os.path.exists`（**missing 必须为 0），还做三项自检：状态词必须在 `status_words` 里有定义、实验引用的 engine id 必须存在于 `engines`、标 `*verified` 的实验必须带 `measured_evidence`（防「口头已验证」）。2026-10-19 实测：`paths checked: 56 | missing: 0`，三项自检各 0 项问题（「measured_evidence 混进中文括注导致路径不可查」这一条就是它先逮出来的，已拆成 `measured_evidence` + `measured_note`）。

跑校验（仓库根目录）：

```bash
python source/library/check_catalog.py   # 退出码 0 = 路径全通
```

## 与上下层的关系

- 上游是 [`../upstream/inventory.json`](../upstream/inventory.json)（脚本生成的实测事实）与 [`../upstream/upstream.lock.json`](../upstream/upstream.lock.json)（身份与构建结论）；这里的数字全部从那儿誊来，不另起一套计数。
- 组件类（three / matter-js / rapier3d-compat）落在 [`../components/`](../components/README.md)，可加载性实测证据是 `../components/component-probe.json`。
- 下游是 `code/eduforge/catalog/templates/`：那边放**已经能做参数修改与验证**的模板三件套，这边放**资源已装但还没适配器**的候选。两边状态词不同，不能混用——当前只有 `optics/convex-lens` 在下游是 `template_connected`。

## 已知的坑与纪律

1. **状态词不许拔高**。18 条实验里 10 条达到了「本机真跑出可对账的物理量」（`engine_headless_verified` 7 + `component_headless_verified` 3）：5 条光学（`optics_hall.mjs`：平面镜 200.5 vs 解析 200、折射 449.5 vs 450、临界角落在 (40°,42°] 对上 asin(1/1.5)=41.81°、凹透镜由束宽反解出 |f|=100.00000000000037、三棱镜两 n 落点 −165.5/−186.5 vs 自写矢量斯涅尔 −165.815/−186.609）、单摆（2.00835 s vs 2.00834 s）、弹簧振子（a=−1.1999976 vs −kx/m=−1.2，周期 3.14159 vs 2π√(m/k)）、抛体（射程 30.2733 vs 30.3046、互补角比 0.9991）、3D 自由落体（15.075 vs 15.095）、3D 带电粒子（半径 3.3597 vs 3.3333、周期 5.23603 vs 5.23599）、电学 3 条（CircuitJS1 在浏览器里读自己的电气量：R=470 Ω ⇒ 0.010638297872340425 A 与 5/470 逐位相同；串联 15.625 mA 与分压 1.563+3.438 V；并联 50 / 22.727 mA、Req 68.75 Ω）。其余 5 条一律 `resource_installed`：源码在盘上，但 Agent 还改不动。注意这 13 条也**还没有模板与适配器**——引擎能算出对得上的数 ≠ 教师能一句话定制并拿到离线包。
2. **光学的两个静默陷阱**（本轮实测踩过）：点必须写成 `{x,y}`，写成 `[x,y]` 时 `loadJSON` 不报错但光线一步就没了；`PlaneGlass` 的玻璃在 `p1→p2` 的**左手侧**，光源放错侧时「全反射」会退化成光在空气里直走而**看起来仍然通过**。所以验收台自带一条 `refIndex=1.0` 的对照跑：先证明几何基线，再谈物理。
3. **PhET 的 main 分支是空壳**。各仿真仓库 main 只剩 README.md + doc/（实测 3~5 个文件），完整源码在 X.Y 发行分支上；`experiments.json` 里记录的 sim 路径全部指向 `source/upstream/phet/sims/<name>`（发行分支克隆）。`circuit-construction-kit-common` 只有 main，是这批里唯一的空壳。
4. **许可义务要在装的时候就写清楚**，不要等到分发前。GPL-2.0（circuitjs1）、GPL-3.0（PhET 仿真源码）、AGPL-3.0（Stellarium Web Engine）三条各有不同的触发条件，已分别登记在 `experiments.json` 的 `license_obligation` 里。
5. **没权威来源就不装**。OSP@Singapore（EJSS）与 3JCN 记在 `not_installed`：GitHub 上找不到可确认的官方仓库（猜测的 wejen/osp-tools/compadre-io 实测均 404），搜到的都是个人复刻、许可参差。宁可留候选记录，也不把来路不明的代码请进工作区。
6. **改完这个 JSON 必须重跑校验**。路径写错在肉眼 review 时最难发现，而 Agent 取种子时必然踩。
7. **负结果也要落盘**。collisions_lab 里 Matter 的弹性正碰与两个引擎的牛顿摆都是 fail，证据文件照写不误；把「引擎能跑出画面」写成「这条实验已可交付」是本目录最严重的一类错误。
8. 调研阶段那份 44 项候选清单（Markdown + JSON）**在本仓库磁盘上不存在**（2026-10-19 全库搜过），这里落的是其中 18 项 P0/P1/P2 的可核对版本；其余候选要接的时候再补条目，不要凭记忆扩写。
