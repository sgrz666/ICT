# lib — LabKit 核心模块

**职责**：抛体样板的核心实现。纯 JS、无第三方运行时依赖（matter-js 由调用方传入），可被 Node 脚本、CLI、dsh 插件共用。

| 文件 | 行数 | 职责 |
|---|---|---|
| [`projectile-core.mjs`](projectile-core.mjs) | 144 | 物理单源：`createProjectileCore(Matter)` → `calibrate / fly / analytic`；另有 `analyticProjectile()` 供 L1 只算公式 |
| [`check.mjs`](check.mjs) | 322 | L1：参数 schema、量程、配方一致性、画面可行性、理由质量；`feasible_hint` |
| [`simulate.mjs`](simulate.mjs) | 165 | L2：matter-js 步进 vs 解析式，逐指标容差 + 阻力对照，写 evidence |
| [`render-single-file.mjs`](render-single-file.mjs) | 117 | 确定性 HTML 组装（模板 + 数据 + 内联引擎/核心） |
| [`verify-single-file.mjs`](verify-single-file.mjs) | 194 | L3：Playwright `file://` 六项判据（canvas 要求不透明 + 非背景 + 多色，透明空白页会被判 fail） |
| [`template.mjs`](template.mjs) | 47 | 按 `template_id` 找目录、读 `recipes.json` |
| [`hash.mjs`](hash.mjs) | 27 | canonical JSON + sha256 + `designHash` |
| [`fs-safe.mjs`](fs-safe.mjs) | 13 | 输出路径白名单 |

## 数据流

`check` → `simulate` → `render` → `verify`，每层都可单独调用；`simulate` 写 `evidence.json`，`render` 用它把 L2 结论嵌进页面，`verify` 用同一份证据对账页面读数。

## 纪律

- 四个阶段共享 `design_hash`；改设计后旧证据必须失配，不允许「新设计配旧证据」。
- 物理只写在 `projectile-core.mjs`；`check.mjs` 只调用 `analyticProjectile()`，`render-single-file.mjs` 只拼接源码，不复制公式。
- 新增引擎时复制的是「core + render + verify」三件，不是把 matter-js 分支塞进同一个文件。

**L1 的「文案承诺 vs 页面控件」检查（2026-10-20 新增，`checkAffordances`）**
`recipes.json` 里每个配方声明一份 `affordances`（`buttons` / `sliders` / `toggles` / `comparison`），
L1 拿 `student_task` 去比：文案里的「点击X」「勾选X」必须真有其事，说要「对比其他角度/对照」而本配方
既无第二场景又无对照开关就报错（`TEXT_AFFORDANCE`）。没声明 `affordances` 的配方只给 warning，不误伤新域。
反例常驻在 [`../l1-text-gate-test.mjs`](../l1-text-gate-test.mjs)（5 例，含"必须放行"的两例，防止门越修越宽）。
来历：dsh 给 oblique45 写的 student_task 让student「点击发射」，而产物只有暂停/重播，
L1 与 L3 都不查这句话能不能兑现，于是一路绿灯进了交付件。
