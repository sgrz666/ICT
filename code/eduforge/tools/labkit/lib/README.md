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
