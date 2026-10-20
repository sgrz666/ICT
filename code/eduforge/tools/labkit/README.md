# labkit — 实验构建核心库（抛体样板）

**职责**：把「一个设计 → 物理对账 → 单文件 HTML → 浏览器实测」做成可独立运行的纯 JS 库。它不依赖 dsh、不依赖 engine-host、不依赖数据库；dsh 插件 [`../../../deep-agent/local-tools/dsh-labkit/`](../../../../deep-agent/local-tools/dsh-labkit/README.md) 只是这层能力的一层薄封装。

当前只有抛体（matter-js）一条样板线；单摆/电路的同类实现是后续复制对象，不是本目录的待办。

## 1. 内容

| 文件 | 行数 | 职责 |
|---|---|---|
| [`lib/projectile-core.mjs`](lib/projectile-core.mjs) | 144 | **物理单源**：`createProjectileCore(Matter)` → `calibrate / fly / analytic`。Node 传 `require('matter-js')`，浏览器传 `window.Matter`，同一份代码 |
| [`lib/check.mjs`](lib/check.mjs) | 322 | L1：schema、量程、配方一致性、画面可行性、教学理由质量；用解析式给预测与 `feasible_hint` |
| [`lib/simulate.mjs`](lib/simulate.mjs) | 165 | L2：matter-js 固定步进 vs 解析式，逐指标容差 + 阻力对照组；写 `evidence.json` |
| [`lib/render-single-file.mjs`](lib/render-single-file.mjs) | 117 | 确定性渲染：模板 + 数据 + 内联 matter.min.js 与核心源码；无时间戳/随机数 |
| [`lib/verify-single-file.mjs`](lib/verify-single-file.mjs) | 194 | L3：Playwright `file://`，六项判据（零网络 / canvas 不透明且多色 / 改参 / console / 读数一致 / 体积） |
| [`lib/template.mjs`](lib/template.mjs) | 47 | 按 `template_id` 找模板目录，读 `recipes.json` |
| [`lib/hash.mjs`](lib/hash.mjs) | 27 | canonical JSON + sha256；`design_hash` 绑定设计与证据 |
| [`lib/fs-safe.mjs`](lib/fs-safe.mjs) | 13 | 输出路径白名单 |
| [`vendor/matter.min.js`](vendor/matter.min.js) | — | 内联引擎 0.20.0（MIT，83,476 字节，sha256 `72d30be0…88e24ae`）；附 `LICENSE.matter.txt` |
| [`selftest.mjs`](selftest.mjs) | 87 | 三个配方各跑 L1→L2→渲染→L3，打印一表；退出码 0/1 |

`vendor/` 是上游 npm 包的副本，不在运行时联网；许可证与哈希记录在此，升级引擎必须同步改 `recipes.json` 的 `engine.version` 与本表。

## 2. 数据流

```
catalog/templates/mechanics/projectile/recipes.json
        │  loadTemplate()
        ▼
checkDesign() ── L1 失败 ──► {ok:false, errors, hints}
        │ ok
        ▼
simulateDesign() ── L2 失败 ──► {ok:false, stage:'L2', code}
        │ ok（写 evidence.json，含 design_hash）
        ▼
renderSingleFile() ──► 单文件 HTML（内联 matter + core + data）
        │
        ▼
verifySingleFile() ──► {ok, checks, verdict}
```

关键不变量：

- **同一物理内核**：L2 与页面运行时都来自 `projectile-core.mjs`；页面渲染时把 `export` 关键字剥掉后内联，逻辑零复制。
- **标定优先**：L2 的解析对照用 `calibrate()` 实测的 `a_eff`，不是名义 9.8。
- **证据绑定内容**：`evidence.design_hash = sha256(canonical(normalized design))`；设计改了，旧证据立刻失配（渲染器报 `EVIDENCE_STALE`）。
- **确定性渲染**：同 design + evidence 连渲两次 sha256 相同；HTML 内不含 `generated_at`。

## 3. 自检

```bash
node code/eduforge/tools/labkit/selftest.mjs
# 期望：3/3 pass；每个产物约 113 KB，network 0
```

物理回归（与历史 lab 口径一致）：

```bash
node source/library/projectile_lab.mjs --json
# 期望：5/5 pass；evidence 除 generated_at 外与重构前逐字段一致
```

## 4. 与其他层的关系

- 模板与教学文案：[`../../catalog/templates/mechanics/projectile/`](../../catalog/templates/mechanics/projectile/README.md)（`manifest.yaml` / `recipes.json` / `native.json` / `lesson.md` / `render/`）。
- dsh 原生工具：[`../../../../deep-agent/local-tools/dsh-labkit/`](../../../../deep-agent/local-tools/dsh-labkit/README.md) 注册 `experiment_*` 六个工具，调用本目录的 `check/simulate/render/verify`。
- 历史物理探针：[`../../../../source/library/projectile_lab.mjs`](../../../../source/library/projectile_lab.mjs) 现在从 `lib/projectile-core.mjs` 导入，CLI 与证据格式保持不变。
- **不接** `engine-host` / `experiment_tools`：那条链路的适配器、`EngineId`、`policies.build_report` 都绑定 ray_optics；合流属下一阶段，不在本目录假装已接。

## 5. 已知的坑与纪律

1. **`frictionAir` 不是二次阻力**：它是速度线性衰减。模板强制 0；阻力只作对照组，不得作为交付模式。
2. **离散步长相位**：matter 的轨迹是 `y_n=½a(n²+n)dt²`，与连续式差半步；所以用实测 `a_eff` 反解，1% 容差才成立。
3. **Node 与 Chromium 的浮点差异**：L3 读数一致性用相对误差 1e-6，不要求逐位相等。
4. **Playwright 解析**：从 `code/eduforge/services/engine-host/package.json` 解析（1.64.1），复用已缓存 Chromium；缺失时报 `PW_NOT_AVAILABLE`，不静默跳过 L3。
5. **产物不入库**：默认写 `output/eduforge/candidates/labkit/`，该目录被根 `.gitignore` 挡住；`selftest` 写 `.../selftest/`。
6. **路径白名单**：`assertUnder()` 只允许写 `candidates/labkit`；新增输出位置必须显式传 `outRoot`，不要绕过。
