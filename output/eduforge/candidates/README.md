# candidates — 候选交付物

放「准备交出去的东西」。目前只有一个：`offline-package/`——**GATE-8 离线网页包**，已通过断网检查。

## offline-package/

- `manifest.json` — 包清单：`engine_id: ray_optics`、`engine_version: 5.5.0`、`native_format_version: 5`、`scene_sha256`（登记哈希，交付时按它校验）、入口 `www/index.html`、`requires_local_static_server: true`、许可 `Apache-2.0 (Ray Optics)`。
- `www/` — 当前实测 **2162 个文件**（随构建内容变化；含上游模拟器静态产物 + 全量 81 个案例场景与多语言页面 + 模板场景经 json-url lzma 注入）。历史上曾为 477 个文件（未含全量案例库构建），数字以 `find www -type f | wc -l` 实测为准。

## 已知限制

- **必须本地静态服务**：上游运行时 HTTP 取 i18n 词条，`file://` 直开不成立；「单文件 HTML」形态还差一层 i18n 预注入，未做。
- 体积大，已列入根 `.gitignore`；可再生（导出实现见 `code/eduforge/services/engine-host/src/export/offline-package.ts`，测试 `tests/e2e/gate8_offline.test.ts`）。
