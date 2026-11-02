# labkit — 实验构建核心库（抛体 / 单摆 / 直流电路）

**职责**：把「一个设计 → 物理对账 → 单文件 HTML → 浏览器实测」做成可独立运行的纯 JS 库。它不依赖 dsh、不依赖 engine-host、不依赖数据库；dsh 插件 [`../../../deep-agent/local-tools/dsh-labkit/`](../../../../deep-agent/local-tools/dsh-labkit/README.md) 只是这层能力的一层薄封装。

当前三条实验线：

| 模板 | 引擎 | 配方 | 产物 |
|---|---|---|---|
| `mechanics.projectile` | matter-js 0.20.0 | 平抛 / 斜抛 45° / 互补角 | 约 118 KB 单文件 |
| `mechanics.pendulum` | matter-js 0.20.0 | 摆长-周期 / 振幅修正 | 约 108 KB 单文件 |
| `circuits.ohms_law` | 自包含 MNA | 欧姆定律 / 串联 / 并联 | 约 27 KB 单文件 |

## 1. 内容

### 共享层

行数按 2026-10-20 `wc -l` 实测。这一层当天正被并行会话改动（`lib/check.mjs`、`lib/render-single-file.mjs`、`lib/verify-single-file.mjs`、`lib/template.mjs`、`selftest.mjs` 都在工作树里是 modified，`dispatcher.mjs`、`circuit/`、`pendulum/` 尚未 `git add`），数字会漂；引用前行数请重新 `wc -l`。

| 文件 | 行数 | 职责 |
|---|---|---|
| [`dispatcher.mjs`](dispatcher.mjs) | 106 | 按 `template_id` 分派 check / simulate / render / verify；插件只认这层 |
| [`lib/template.mjs`](lib/template.mjs) | 73 | 按 `template_id` 找模板目录、读 `recipes.json`、`listTemplates()` |
| [`lib/hash.mjs`](lib/hash.mjs) | 27 | canonical JSON + sha256；`design_hash` 绑定设计与证据 |
| [`lib/artifact.mjs`](lib/artifact.mjs) | — | 渲染清单写入/核验：绑定规范化设计、HTML 字节与 canonical JSON L2 证据 |
| [`lib/fs-safe.mjs`](lib/fs-safe.mjs) | 13 | 输出路径白名单 |
| [`lib/verify-single-file.mjs`](lib/verify-single-file.mjs) | 205 | L3：Playwright `file://`，六项判据；探针参数与指标键可配置 |
| [`vendor/matter.min.js`](vendor/matter.min.js) | — | 内联引擎 0.20.0（MIT，83,476 字节，sha256 `72d30be0…88e24ae`） |
| [`selftest.mjs`](selftest.mjs) | 125 | 7 个配方各跑 L1→L2→渲染→L3；退出码 0/1 |
| [`drag-control-probe.mjs`](drag-control-probe.mjs) | 144 | 抛体阻力控件的浏览器回归，**15 条判据**（vendor 哈希逐字节、默认无阻力、写 0.01 后射程显著变小、`ratio_vs_clean ≥ 5`、射程比 ≈2.30、读数表出现无阻力/阻力两行、写回 0 可逆、拖滑块生效、滑块数 3→4、全程零外部请求）；跑法见第 3 节 |

### 抛体

| 文件 | 行数 | 职责 |
|---|---|---|
| [`lib/projectile-core.mjs`](lib/projectile-core.mjs) | 144 | `createProjectileCore(Matter)` → `calibrate / fly / analytic` |
| [`lib/check.mjs`](lib/check.mjs) | 362 | L1 参数/配方/画面/理由校验 + `feasible_hint` |
| [`lib/simulate.mjs`](lib/simulate.mjs) | 165 | L2 matter-js vs 解析式 + 阻力对照组 |
| [`lib/render-single-file.mjs`](lib/render-single-file.mjs) | 162 | 单文件渲染（内联 matter + core） |

### 单摆

| 文件 | 行数 | 职责 |
|---|---|---|
| [`pendulum/core.mjs`](pendulum/core.mjs) | 140 | `createPendulumCore(Matter)` → `calibrate / swing`；`pendulumAnalytic()`（AGM 椭圆积分） |
| [`pendulum/check.mjs`](pendulum/check.mjs) | 159 | L1；多场景固定扫描，`params` 忽略并 warning |
| [`pendulum/simulate.mjs`](pendulum/simulate.mjs) | 104 | L2 摆角过零测周期 vs `T0/Texact` |
| [`pendulum/render.mjs`](pendulum/render.mjs) | 94 | 单文件渲染（内联 matter + 单摆 core） |

### 直流电路

| 文件 | 行数 | 职责 |
|---|---|---|
| [`circuit/core.mjs`](circuit/core.mjs) | 184 | MNA 求解器 + `buildOhm/buildSeries/buildParallel` + 解析参考 |
| [`circuit/check.mjs`](circuit/check.mjs) | 123 | L1 拓扑/量程/电流上限/理由 |
| [`circuit/simulate.mjs`](circuit/simulate.mjs) | 148 | L2 MNA vs 解析式 + CircuitJS1 外部交叉验证 |
| [`circuit/render.mjs`](circuit/render.mjs) | 90 | 单文件渲染（内联 MNA core，无外部引擎） |

## 2. 数据流

```
design {template_id, recipe_id, params, why_recipe, student_task}
        │  dispatcher.checkDesign()
        ▼
L1 ── 失败 ──► {ok:false, errors, hints}
        │ ok
        ▼
L2 ── 失败 ──► {ok:false, stage:'L2', code}
        │ ok（写 evidence.json，含 design_hash）
        ▼
renderSingleFile() ──► 单文件 HTML
        │
        ▼
verifySingleFile() ──► {ok, checks, verdict}
```

关键不变量：

- **同一物理内核**：L2 与页面运行时来自同一份 `core.mjs`；渲染时把 `export` 剥掉后内联，逻辑零复制。
- **证据绑定内容**：`evidence.design_hash = sha256(canonical(normalized design))`；设计改了，旧证据立即失配。
- **复验绑定文件（2026-10-31）**：每次渲染同时写 `<htmlPath>.manifest.json`，schema 为 `eduforge.labkit.render/v1`。L3 先核对其中的 design_hash、HTML sha256、canonical JSON evidence sha256，再启动 Chromium；页面实际 design_hash 也须一致。历史 HTML 没有清单时需重渲染。
- **确定性渲染**：同 design + evidence 连渲两次 sha256 相同；HTML 不含 `generated_at`。
- **L3 探针可配置**：抛体 `v0→R`、单摆 `length_m→T`、电路 `resistance_ohm→I`；指标键按模板传。

## 3. 自检

```bash
node code/eduforge/tools/labkit/selftest.mjs
# 期望：7/7 pass
# projectile 2 配方 ~118 KB；pendulum 2 配方 ~108 KB；circuit 3 配方 ~27 KB；network 0
```

自检现使用唯一的系统临时目录并打印位置，不再覆盖 `output/eduforge/candidates/labkit/selftest/` 旧证据。可用 `EDUFORGE_LABKIT_ROOT` 指定保留 ICT 布局的资源根。2026-10-31 本机完整自检 exit 0。

```bash
node --test code/eduforge/tools/labkit/artifact-integrity.test.mjs
```

[`artifact-integrity.test.mjs`](artifact-integrity.test.mjs) 使用临时目录，复现并钉住 HTML 追加注释、证据 design_hash 改动、越界证据路径、必需指标缺失；正例保留真实 Chromium 检查，单摆逐场景改变参数后核对 L2 读数。2026-10-31 本机 exit 0。`ratio` 是 L2 派生场景，不作为页面独立运行，但其原始场景全部核对；清单哈希也覆盖派生证据。

物理回归（抛体历史口径）：

```bash
node source/library/projectile_lab.mjs --json
# 期望：5/5 pass；evidence 除 generated_at 外与重构前逐字段一致
```

### 四支独立探针：为什么 selftest 7/7 还不够

`selftest.mjs` 跑的是「每条线的默认场景 + 各一次改参」。下面这四支各补一个 selftest 结构上看不见的洞：

| 探针 | 行数 | 补的是哪个洞 | 判据要点 |
|---|---|---|---|
| [`l1-text-gate-test.mjs`](l1-text-gate-test.mjs) | 51 | L1 那道「文案承诺 vs 页面控件」的门**本身**要有反例——没有它，下次改规则时没人知道这本来要拦什么 | **5 例，两类各半**：3 例必须拦（承诺不存在的「发射」按钮 / 要对比其他角度但既无第二场景也无对照开关 / 提到不存在的「自动发射」开关），2 例必须放行（只提暂停与重播 / 要对照且本配方确有对照叠加）。2026-10-20 本机跑 **5/5 符合预期，exit 0**，报错文案里连「只有：暂停 / 重播」都带出来 |
| [`pendulum-product-probe.mjs`](pendulum-product-probe.mjs) | 82 | selftest 的 L3 对单摆报的是 `readout 0.00e+0`——那是**抛体专属**的读数对照，对单摆等于空判据；所以「7/7」并不证明页面读数与 L2 证据是同一件事 | ① 改摆长周期必须跟着动，且动的是引擎值不是公式值；② 页面读数与 evidence 的 measured T **逐场景对上**；③ 拉到 30° 时周期必须比小角度公式 T0 长约 1.7%（`1+θ₀²/16`）——只把公式抄进 JS 的实现给不出这个数 |
| [`range-sweep-probe.mjs`](range-sweep-probe.mjs) | 87 | L3 只测一个点、L2 只测配方那一个场景，而页面把 v₀ 5~40、h₀ 0~30、θ 15~75、`frictionAir` 0~0.03 全交给了学生 | 把**页面自己声明**的量程推满，任一角落出现 NaN / 曲线不落地 / 与解析式对不上都算坏；判据全取页内的 `tolerances_pct`（1%）、`decision` 量程与 `DATA.acceptance`，不引外部常数 |
| [`drag-control-probe.mjs`](drag-control-probe.mjs) | 144 | 空气阻力控件（见坑 4）的浏览器回归 | 15 条，跑法见本节末尾 |

```bash
node code/eduforge/tools/labkit/l1-text-gate-test.mjs
node code/eduforge/tools/labkit/pendulum-product-probe.mjs [index.html 路径]
node code/eduforge/tools/labkit/range-sweep-probe.mjs [html 路径]
```

### `affordances`：文案与控件的一致性契约

起因是一次真实漏网：dsh 生成的 `student_task` 写着「点击发射或重放…对比页面给出的其他角度」，而产物上只有「暂停 / 重播」两个按钮、也没有第二场景或对照开关——一路绿灯进了交付件。修法是把这个约定写成数据，走三步：

1. **配方声明**：`catalog/templates/mechanics/projectile/recipes.json` 里每条配方带一个 `affordances` 块（`buttons` / `sliders` / `toggles` / `comparison`）。抛体三条现状：`horizontal` 是「暂停、重播」+ 三个滑块（初速度 / 初始高度 / 空气阻力）、无开关、无对照；`oblique45` 多一个「发射角」滑块与 `叠加` 开关、`comparison: true`；`complementary` 的开关是 `保持互补`、同样 `comparison: true`。
2. **L1 拦截**：`lib/check.mjs` 拿 `student_task` 里的承诺去比对声明，不符就报具名错误 `TEXT_AFFORDANCE`（提不存在的按钮、要对照但既无第二场景也无对照开关、提不存在的开关，各有独立文案）。
3. **随产物走**：`lib/render-single-file.mjs` 把 `recipe.affordances` 写进页面 `DATA`（没有声明就写 `null`），所以**探针是拿产物里的声明比对真实渲染**，而不是回头读模板文件——交付物自己带着「我该有哪些控件」的声明。

**边界照实说**：配方没声明 `affordances` 时这道门**跳过并给 warning**（新接入的域还没声明，不误伤），所以「L1 过了」在没声明的配方上不代表文案与控件一致；`l1-text-gate-test.mjs` 就是钉住这道门别退化成空判据的那支探针。dsh 插件侧目前没有读 `affordances`（`deep-agent/local-tools/dsh-labkit/` 里没有相关引用）。

空气阻力控件回归（改了 `render/runtime.js` 或 `lib/simulate.mjs` 之后必跑）：

```bash
node code/eduforge/tools/labkit/drag-control-probe.mjs            # 默认测最新产物
node code/eduforge/tools/labkit/drag-control-probe.mjs <html 路径> # 测指定那一份
```

它对着的是浏览器里的真页面：把 `friction_air` 从 0 写到 0.01、拖滑块、再写回 0，并核对页面自己算出的两个比值。数值的出处是 `output/eduforge/candidates/labkit/oblique45/oblique45-range-max.evidence.json` 里的 `drag_control` 段：`deviation_no_drag_pct 0.144 → deviation_with_drag_pct 56.498`、`ratio 391.23`、`range_no_drag 40.7574 / range_with_drag 17.7558`（比值 2.295，即探针里的「射程比 ≈2.30」），`verdict: pass`。

## 4. 与其他层的关系

- 模板与教学文案：`catalog/templates/{mechanics/projectile,mechanics/pendulum,circuits/ohms-law}/`。
- dsh 原生工具：`deep-agent/local-tools/dsh-labkit/` 注册 `experiment_*` 六个工具，调用本目录的 dispatcher。
- 历史物理探针：`source/library/projectile_lab.mjs` 从 `lib/projectile-core.mjs` 导入；`source/library/circuit-lab-evidence.json` 是电路的 CircuitJS1 交叉验证来源。
- **不接** `engine-host` / `experiment_tools`：主链路的适配器、`EngineId`、`policies.build_report` 仍绑定 ray_optics；合流属下一阶段。

## 5. 已知的坑与纪律

1. **物理只写在各 `core.mjs`**；check/simulate/render 不复制公式。新增实验 = 新 core + check + simulate + render + dispatcher 一行。
2. **单摆 30° 必须用椭圆积分精确解**；小角度公式只作教学对照（差约 1.7%）。
3. **电路是 MNA 精确解**；CircuitJS1 是外部交叉验证，不是运行时。若必须交付 CircuitJS1 UI，走离线包 + 同源服务，别硬塞进单文件。
4. **`frictionAir` 不是二次阻力**：matter-js 的 `frictionAir` 是每个步长对速度的**线性衰减**，不是 `½CρAv²`。2026-10-20 起它作为第四个控件开放给教师与 Agent（`manifest.yaml` 的 `friction_air`，页面滑块量程 `0 ~ 0.03`，取自 `recipes.json` 的 `acceptance.drag_control.friction_air = 0.01` 的三倍），**默认仍是 0**。两条理由：① 默认一动，L2/L3 那句「引擎 vs 解析式」的历史证据就作废（解析式只在无阻力时成立）；② 页面上必须按「线性阻尼」解释，不得写成"真实空气阻力"。阻力对照组判据的口径别记错：L2 要的是 `ratio_vs_clean ≥ 5`（实测 391.23，是**偏差放大倍数**），而学生看得懂的「射程比」是 `range_ratio_clean_over_drag ≈ 2.30`（40.7574 / 17.7558）——这两个数不是一回事，按 ≥5 去断言射程比会当场红。
5. **Playwright 解析**：从 `code/eduforge/services/engine-host/package.json` 解析 1.64.1，复用已缓存 Chromium；缺失时报 `PW_NOT_AVAILABLE`。
6. **产物不入库**：默认写 `output/eduforge/candidates/labkit/`，被根 `.gitignore` 挡住。
7. **路径白名单**：`assertUnder()` 只允许写 `candidates/labkit`；新增输出位置必须显式传 `outRoot`。
8. **内容清单不是签名**：能检出单个 HTML/证据的改动与错配；不声称能防止有人同时改写 HTML、证据与清单。缺清单、不完整指标或不匹配的页面设计指纹不能报告通过。
