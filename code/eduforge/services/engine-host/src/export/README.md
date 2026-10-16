# export — 离线网页包组装

**职责**：把"一个通过验证的候选场景"组装成**离线可跑的网页实验包**：上游 `dist` 整体拷贝、场景写进 hash 与文件、`manifest.json` 锁 sha256、i18n 预注入补丁消除 `file://` 取词问题。交付形态是「随包静态服务」（`file://` 直开实测不可用）。

## 内容（逐文件）

| 文件 | 行数 | 职责 | 关键符号 |
|---|---|---|---|
| `html.ts` | 98 | 离线 HTML 组装器 + **i18n 预注入补丁**（拦截 fetch/XHR，把 i18next 的 locales 请求改为内联） | `loadEmbeddedLocales()`, `generateI18nPatchScript()`, `buildIndexHtml()` |
| `manifest.ts` | 33 | 发布元数据 `manifest.json` 生成 | `ManifestOptions`, `buildManifest()` |
| `offline-package.ts` | 71 | 组装离线包：dist 拷贝 + 场景文件 + manifest 锁 | `OfflinePackage`, `buildOfflinePackage()` |

## 数据流

`buildOfflinePackage(scene, outDir)`：校验上游 `dist` 存在 → 拷贝整份 `dist` 到 `www/` → 场景写 `www/scene/native.json` 且压缩进首页 `#hash` → `manifest.json` 锁 sha256；`buildIndexHtml()` 在同一份首页注入 i18n 补丁脚本。

## 与上下层的关系

- 被谁用：GATE-8 测试 [`../../tests/e2e/gate8_offline.test.ts`](../../tests/README.md)；产物形态对应 [`../../../../../../output/eduforge/`](../../../../../../output/eduforge/README.md) 的 candidates 离线包。
- 上游依赖：上游 `dist`（`source/upstream/ray-optics/dist/`，路径在本目录内硬编码计算）。

## 已知的坑与纪律

- **`file://` 直开不成立**（GATE-8 实测结论）——对外交付说明必须写「随包静态服务运行」；i18n 补丁解决的是取词，不改变这个结论。
- `html.ts` 与 `offline-package.ts` 各自硬编码算出上游 `dist` 路径，**未复用** [`../upstream_paths.ts`](../README.md)——改目录结构要三处同看。
- GATE-8 的三个验证点（包结构 / manifest 与 sha256 / 零出网）在测试里逐项断言——改组装逻辑先跑它。
