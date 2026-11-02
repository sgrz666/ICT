# dsh-labkit — dsh 原生实验构建工具

**职责**：把 [`code/eduforge/tools/labkit`](../../../code/eduforge/tools/labkit/README.md) 的能力注册成 **DeepSeek Harness（dsh）原生工具**，让模型在工具表里直接看到 `experiment_*`，用户说一句「做一个抛体 / 单摆 / 欧姆定律实验」就能触发，不需要先读 skill、也不需要拼命令行。自 2026-10-20 起，它还带一个 **`physics-lab` agent preset**（教师端只挂这六个工具）和**交付包**（`experiment_build` 成功后同时写教师手册、学生任务单、包清单）。

**位置刻意放在 `deep-agent/local-tools/` 而不是 `deep-agent/deepseek-harness/packages/`**：上游树是 2.7 GB 的验证对象，不入库、不手改；插件通过 profile patch 的相对路径加载，删除目录即可彻底回滚。

## 1. 工具表

| 工具 | 何时用 | 关键入参 | 超时 |
|---|---|---|---|
| `experiment_recipes` | 任何实验请求的第一步：拿配方、默认参数、量程、容差 | `template_id?` | 15 s |
| `experiment_validate` | 想先确认参数/理由是否合规，或要看解析预测 | `recipe_id, params, why_recipe, student_task, expected_numbers?` | 15 s |
| `experiment_simulate` | 只跑 L2 物理对账，不渲染 | 同上 | 60 s |
| `experiment_render` | 只渲染单文件（内部仍跑 L1/L2 以带证据），不做浏览器实测 | 同上 + `out_name?` | 60 s |
| `experiment_verify` | 对已有 HTML 重跑 L3 离线实测 | `html_path, evidence_path` | 120 s |
| `experiment_build` | **标准请求直接用这个**：L1→L2→渲染→L3→交付包一次完成 | `recipe_id, params, why_recipe, student_task, out_name?` | 240 s |

### 覆盖的实验

| template_id | 配方 | L2 引擎 | 产物 |
|---|---|---|---|
| `mechanics.projectile` | horizontal / oblique45 / complementary | matter-js | ~118 KB 单文件 |
| `mechanics.pendulum` | period-length / angle-correction | matter-js | ~108 KB 单文件 |
| `circuits.ohms_law` | ohms-law / series / parallel | 自包含 MNA（CircuitJS1 交叉验证） | ~27 KB 单文件 |

`experiment_recipes` 不带 `template_id` 时列出全部模板；带参数时返回该模板的配方与量程。三个实验都走 `experiment_build`，无需为每个实验记不同命令。

> 电路为什么不是 CircuitJS1 运行时：GWT 站点 15 MB、多文件、需同源加载，无法做成单文件 HTML。MNA 对线性 DC 是精确解；CircuitJS1 2026-10-19 的实测证据在 L2 里做 8 项交叉验证，读数在双精度下一致。详见 [`../../../code/eduforge/catalog/templates/circuits/ohms-law/README.md`](../../../code/eduforge/catalog/templates/circuits/ohms-law/README.md)。

### 交付包（2026-10-20 起）

`experiment_build` 在 L3 通过后，除了原有的两份文件，还会在同一目录写三份人能直接用的东西：

| 文件 | 内容 | 事实来源 |
|---|---|---|
| `<name>.html` | 单文件实验页（离线双击可开） | LabKit 渲染器 |
| `<name>.html.manifest.json` | 渲染清单：规范化 design、design_hash、HTML sha256、canonical JSON evidence sha256；复验必需 | LabKit 渲染器 |
| `<name>.evidence.json` | 物理证据（design_hash、场景实测/解析、L3 判据） | L2/L3 |
| `<name>.teacher.md` | 教师手册：适用学段、40 分钟 5E 流程、含答案的数据表、常见误区、预设问题、质检结论 | design + evidence + 模板 `lesson.md` |
| `<name>.student.md` | 学生任务单：先预测、步骤、空数据表、分析与结论、迁移题 | 同上 |
| `<name>.package.json` | 包清单：`schema=eduforge.labkit.delivery/v1`、design、design_hash、文件（含渲染清单）、HTML/证据哈希、L2/L3 结果 | 同上 |

三条纪律：

- 文档**不重新解释物理**：公式取 `recipes.json` 的 `formulas_display` 原文，误区/步骤取 `lesson.md` 的「配方 N」小节，读数取 evidence。
- 文档**不带时间戳**，内容由 design 与证据决定；`design_hash` 只绑 design，不绑 `lesson.md`，改教学文案不会让旧证据失配（改参数才会）。
- 学生表跳过 `ratio` 这类派生场景，只留学生真正要做的场景；教师表保留派生行，便于讲评。

首次实测（2026-10-20，`selftest.mjs`，互补角 30°/60°）：

```text
experiment_build ok · L2 max 0.408181% · L3 network 0 · readout 1.35e-7
teacher/student/manifest 三份落盘，16 项断言全过
selftest-docs：3 模板 × 8 配方全部通过
```

领域失败不抛异常，返回 `{ok:false, stage, code, summary, hints}`；模型可按 `hints` 调整参数或理由后重试（建议最多 3 次）。当前完整证据落盘在配置输出根的 `<recipe>/<uuid>/`，历史产物仍保留原层级。

系统提示里还注入了一段行为约束（`ctx.systemPrompt.section`）：优先 `experiment_build`；不得自行编写物理公式、手写 HTML 或修改验收容差；成功后直接汇报 HTML 与交付包路径，不再读产物。

## 2. 安装（不改上游，可回滚）

插件是普通 ESM 文件；`defineTool` 优先从启动器给定的 `EDUFORGE_DSH_INSTALL_ANCHOR` 解析，未设置时兼容原有上游相对布局，不另装一套框架。

### 2.1 教师端：装成 `physics-lab` preset（推荐）

把 [`preset.patch.yml`](preset.patch.yml) 里的整个 `- insert:` 块追加到 `.dsh-home/profiles/web/cordis.patch.yml`。它注册一个 `physics-lab` preset，子行只挂 `persona / time-context / ask-user / present / eduforge-labkit`，**没有 shell、fs、web**——老师端只能通过工具生成实验，模型没有手写 HTML 的入口。

`eduforge-labkit` 子行的 `name` 必须写**绝对 `file://` URL**：

```yaml
name: 'file:///D:/codeplus/ICT/deep-agent/local-tools/dsh-labkit/index.mjs'
```

原因：preset 子行继承的 `baseUrl` 是 dsh 包目录，不是 profile 目录；写相对路径会解析到 `deepseek-harness/local-tools/…`（不存在）。换仓库位置时改这一行。

重启 dsh web 后，在新会话的模式选择器里应看到「格物 · 物理实验工坊」，描述是「一句话把教学需求变成可离线运行、经过物理对账的实验包…」。**2026-10-20 实测**：临时起一个 `--port 0` 的 web 实例，用 Playwright 打开模式选择器，标准模式、物理实验工坊、PTC、极简、创造五个模式同时可见；preset 无 broken 诊断。临时实例已关闭，没有替换 3081 上的 GUI。

配置层自检（只证明组合里有一行，不证明挂载成功；挂载以上面的选择器实测为准）：

```bash
cd D:/codeplus/ICT/deep-agent/deepseek-harness
DSH_HOME=D:/codeplus/ICT/deep-agent/.dsh-home \
  "C:/Program Files/nodejs/node.exe" apps/cli/lib/bin.js --profile web --dump-config \
  | Select-String -Pattern 'preset-physics-lab|physics-lab|eduforge-labkit'
# 期望：preset-physics-lab / id: physics-lab / - id: eduforge-labkit
```

> `.dsh-home/` 是本地运行配置，不入库。换机器或重置 `DSH_HOME` 后要重新加这一段。

### 2.2 无头/回归：全局挂载

headless profile 仍用全局行（当前 `.dsh-home/profiles/headless/cordis.patch.yml` 就是这样），这样 `dsh --profile headless` 的真实会话仍能直接看到 `experiment_*`：

```yaml
- insert:
    - id: eduforge-labkit
      name: ../../../local-tools/dsh-labkit/index.mjs
```

`name` 相对 profile 根（`.dsh-home/profiles/<profile>/`），loader 会解析成 `file:///D:/codeplus/ICT/deep-agent/local-tools/dsh-labkit/index.mjs`。

**不要和 preset 同时挂**：两边都注册 `experiment_*` 会撞同名工具。教师端用 preset，回归用全局，二选一。

### 2.3 自检

2026-10-31 起，`EDUFORGE_LABKIT_ROOT` 可指定保留 ICT 相对布局的资源根，`EDUFORGE_LABKIT_OUTPUT_ROOT` 可将产物写到独立的用户数据目录；两者均在插件加载时读取。不设置时仍按插件位置反推仓库根，并写入原 `output/eduforge/candidates/labkit/`。改变量后需重启 dsh。资源根与输出根均可含空格，不需要 Python bridge。

搬迁包需保留本插件目录、`code/eduforge/tools/labkit/`、三类实验模板完整目录、`source/library/circuit-lab-evidence.json`；`source/components/package.json` 附近须可解析 `matter-js`，`code/eduforge/services/engine-host/package.json` 附近须可解析 `playwright`/`playwright-core`，并提供对应 Chromium。启动器用安装锚点定位官方工具 API，不依赖原上游源码目录。

```bash
cd D:/codeplus/ICT
node deep-agent/local-tools/dsh-labkit/selftest.mjs
# 期望：所有断言 PASS，末行「交付包自检通过」；开头打印独立临时输出目录
node deep-agent/local-tools/dsh-labkit/selftest-docs.mjs
# 期望：8/8 配方文档生成通过（3 模板 × 8 配方，跑 L1/L2，不跑 L3）
node code/eduforge/tools/labkit/selftest.mjs
# 期望：7/7 pass（抛体 2、单摆 2、电路 3）
node --test deep-agent/local-tools/dsh-labkit/portable.test.mjs code/eduforge/tools/labkit/artifact-integrity.test.mjs
# 期望：路径搬迁、真实浏览器验收及 HTML/证据篡改反例全部通过
```

`selftest.mjs` 走的是真实 `experiment_build` 处理函数（含 L3 Chromium），不是只测文档生成；它同时核对三份文档落盘、包清单 schema、design_hash、HTML/证据哈希与 L2/L3 读数。`selftest-docs.mjs` 补的是覆盖面：新增配方若让某一类文档生成失败（空 metrics、没有 params 场景等），这一支会先红。三支 selftest 均使用唯一临时目录，不覆盖历史证据；插件包自检在设置输出根时，会在该根内再创建唯一子目录。2026-10-31 本机复跑上述命令均 exit 0；完整搬迁运行包另由发布流程验收。

全局挂载的历史实测（2026-10-20，未因本轮改动失效）：

- **交付包真实会话**（headless，全局挂载，2026-10-20 18:23）：一句「互补角 30°/60°」需求 → 2 次工具调用（`experiment_recipes` → `experiment_build`），产出 `complementary-angles.html`（128.9 KB）+ `.evidence.json` + `.teacher.md`（5.2 KB）+ `.student.md`（1.8 KB）+ `.package.json`（1.8 KB），CLI `exit 0`；最终回复直接列了五份路径与 L2/L3 读数，没有再读产物。
- 互补角 prompt → 模型先调 `experiment_recipes`，再调一次 `experiment_build`，产出 `output/eduforge/candidates/labkit/complementary/complementary_angles_30_60.html`（113.8 KB，三层验收全过）。
- 斜抛 45° prompt → 同样 2 次工具调用，产出 `output/eduforge/candidates/labkit/oblique45/oblique45-range-max.html`（113.4 KB）。
- 单摆 prompt → 2 次调用，产出 `output/eduforge/candidates/labkit/period-length/pendulum_period_length.html`（107.9 KB）。
- 欧姆定律 prompt → 2 次调用，产出 `output/eduforge/candidates/labkit/ohms-law/ohms_law_5v.html`（27.0 KB）。
- 早期版本在 `experiment_build` 之后会额外用 `grep/read` 检查 HTML；在工具摘要与系统提示里写明「页面已嵌入教学内容，构建成功后直接汇报」后，复跑稳定为 **2 次调用**，不再读产物。

### 2.4 回退

删掉 profile patch 里的 `preset-physics-lab` 块（或全局 `eduforge-labkit` 行）并重启；插件目录可整体删除。若曾用 `dsh plugin add file:` 安装，再执行
`dsh plugin --profile <p> remove @eduforge/dsh-labkit`。

## 3. 安全边界（重要）

- 工具 handler 运行在 dsh **宿主进程**内，直接用 `node:fs`，**绕过** dsh 对模型 shell 的沙箱。这是可信本地工具的取舍：读取配置资源根内的模板、核心、引擎与交叉验证证据，产物只写配置输出根（默认 `output/eduforge/candidates/labkit/`）。
- `out_name` 经过 `safeName()`，只留字母数字下划线连字符；渲染器再用 `assertUnder()` 做一次根目录校验。
- L3 启动的 Chromium 是 `offline: true` + 请求拦截；页面本身也有 `default-src 'none'` CSP。
- **不要把本插件装到不可信工作区**：它能读资源根内模板与核心库，并向配置输出目录写文件。环境变量由可信启动器设置，不作为模型工具参数。

## 4. 版本耦合与已知风险

1. **上游 API 耦合**：`lib/dsh.mjs` 优先从启动器指定的 `EDUFORGE_DSH_INSTALL_ANCHOR` 解析官方 tools 包；未指定时兼容原有上游相对路径。dsh 升级若改导出，插件启动即报错；当前锚定 `dsh-v0.2.1-rc.2` / commit `687f282e`。
2. **preset 子行必须用绝对 `file://` URL**：preset 子行继承的 `baseUrl` 是 dsh 包目录，不是 profile 目录；写 `../../../local-tools/…` 会解析到 `deepseek-harness/local-tools/…`。全局挂载行仍可写相对 profile 根的路径。
3. **改 profile 必须重启**：profile 是静态组合，没有热重载；当前 GUI 会话不会因为改了 patch 就出现新 preset。
4. **工具结果 token**：`render` 只输出摘要与路径，不倾倒完整 evidence；失败时才带逐项错误。
5. **交付包与模板文案同源**：教师手册/学生任务单的步骤与误区取自模板 `lesson.md`，公式取自 `recipes.json`；改文案会改文档，但 `design_hash` 只绑 design，不会因文案变化而失配。
6. **并发（2026-10-31 修复）**：每次 simulate/render/build 分配独立 UUID 子目录，同一 `out_name` 也不共享文件。调用方必须使用返回路径；历史同名覆盖行为不再保留。`portable.test.mjs` 用两个不同电阻、相同名字并发构建验证互不混写。
7. **复验绑定（2026-10-31）**：L3 先检查 `.html.manifest.json` 中的设计、HTML 与证据哈希，再启动真实 Chromium。HTML 追加无害注释、只改 evidence.design_hash、缺少必要读数均拒绝；单摆逐个重跑 L2 的实际场景。旧产物没有渲染清单时需重新 build/render，不能把历史通过结论当成新复验。清单用于检出错配或单文件改动，不是抵抗同时重写全部文件的数字签名。

## 5. 文件

| 文件 | 作用 |
|---|---|
| [`index.mjs`](index.mjs) | Cordis 插件入口：`name` / `inject` / `apply`，系统提示 + 六个工具注册 |
| [`lib/dsh.mjs`](lib/dsh.mjs) | 从安装锚点解析官方 `defineTool`，未设置时回退原相对布局 |
| [`lib/labkit.mjs`](lib/labkit.mjs) | 核心库单一入口 |
| [`lib/paths.mjs`](lib/paths.mjs) | 仓库根、输出根、`safeName` / `outPaths` |
| [`lib/tool-schema.mjs`](lib/tool-schema.mjs) | 共用输出 schema、参数 schema、文本投影 |
| [`lib/format.mjs`](lib/format.mjs) | 场景表、错误块、建议块 |
| [`lib/summary.mjs`](lib/summary.mjs) | 按 `template_id` 把 L2 结果投影成摘要表（抛体/单摆/电路） |
| [`lib/package.mjs`](lib/package.mjs) | 交付包生成：教师手册、学生任务单、包清单；事实只取 design/evidence/`lesson.md` |
| [`tools/recipes.mjs`](tools/recipes.mjs) | `experiment_recipes` |
| [`tools/validate.mjs`](tools/validate.mjs) | `experiment_validate` |
| [`tools/simulate.mjs`](tools/simulate.mjs) | `experiment_simulate` |
| [`tools/render.mjs`](tools/render.mjs) | `experiment_render` |
| [`tools/verify.mjs`](tools/verify.mjs) | `experiment_verify` |
| [`tools/build.mjs`](tools/build.mjs) | `experiment_build`（一次完成 + 交付包） |
| [`preset.patch.yml`](preset.patch.yml) | `physics-lab` agent preset 的声明块（教师端工具白名单） |
| [`selftest.mjs`](selftest.mjs) | 交付包自检：真实 `experiment_build`（含 L3）、文档与哈希绑定，使用唯一临时目录 |
| [`selftest-docs.mjs`](selftest-docs.mjs) | 8 配方文档生成自检（L1/L2，不跑 L3） |
| [`portable.test.mjs`](portable.test.mjs) | Node 测试：显式资源/输出根、含空格的复制资源树、独立用户数据输出；现场保留在打印的临时目录 |
