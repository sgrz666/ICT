# tools — 验证探针与代码生成工具

EduForge 的工程自带工具：**验证探针**（切片推进时证明「这件事真的成立」的一次性脚本，产出落在 `output/eduforge/reports/`）和**代码生成**（契约导出）。都不属于产品运行时路径。

## 内容

| 文件 | 语言 | 行数 | 用途 |
|---|---|---|---|
| `rayoptics_probe.cjs` | Node | 212 | 第一切片探针：证明上游接受我们手写的场景、场景可往返保存、对象能被稳定定位并改焦距、改完的仿真与独立薄透镜公式吻合。观测端只用上游仿真，参考公式独立算，不参与观测 |
| `gate2_binding.cjs` | Node | 170 | GATE-2 验证：适配器修改协议在分层物距（u<f / u=f / f<u<2f / u=2f / u>2f 五档）下是否可判真假；三条纪律——控制组、阈值落点、分层 |
| `browser_gate1.py` | Python | 144 | GATE-1 的人工那一半：Playwright 起真实 Chromium，经官方分享 URL 载入种子场景，在 UI 代码页签改焦距再读回序列化结果（内置浏览器视口不可用，这条路不是可选装饰） |
| `browser_gate1_edit.py` | Python | 163 | 上一项的续跑：UI 内改焦距 → 应用同步 → 复制分享链接导出 → 解回校验 |
| `export_contracts.py` | Python | 107 | 从 FastAPI OpenAPI 生成 TS 类型到 `packages/contracts/src/generated/api.ts`（§6.2：不手写第二套业务 DTO）。改了 API 必跑 |
| `run_db.py` | Python | 71 | 启动本地 PostgreSQL 服务（基于 pgserver），包含安全异常保护（杜绝暴力 kill 其它 Postgres 实例与破坏性删库），供一键启动与本地开发使用 |
| `pack_static_html.mjs` | Node | 306 | 把已下载的实验页打包成「每实验一个静态 HTML」：清外链、注入 CSP、Playwright `file://` 实测、生成 `manifest.json` 与实验覆盖索引；当前适配 PhET published 13 个 |

### `pack_static_html.mjs` — 静态 HTML 打包器

```bash
node code/eduforge/tools/pack_static_html.mjs                  # 13 个 PhET 全跑
node code/eduforge/tools/pack_static_html.mjs --only ohms-law # 单个试跑
node code/eduforge/tools/pack_static_html.mjs --no-verify     # 只清洗+出索引
```

- 输入：`source/upstream/phet-published.json` 与 `source/upstream/phet/published/*.html`。
- 清洗：删 Cloudflare/canonical 外链；注入 CSP（`connect-src 'none'`，外部 script/img 全锁死）；写来源与 sha256 元信息。
- 实测：真 Chromium `file://` 打开，确认 SVG/canvas 渲染、`network_responses=0`、模拟器无 console error；统计脚本的 CSP 拦截单独计数，不算模拟器错误。
- 输出：`output/eduforge/candidates/static-html/phet/<sim>.html` + `index.html` + `manifest.json`（含 18 个登记实验的覆盖表）。


### [`labkit/`](labkit/README.md) — 实验构建核心库（抛体 / 单摆 / 直流电路）

纯 JS，不依赖 dsh / engine-host / 数据库：`dispatcher.mjs` 按 `template_id` 分派；三条实验线各自的 `core / check / simulate / render` 在 `lib/`、`pendulum/`、`circuit/`；`selftest.mjs` 一次跑 7 个配方。dsh 原生工具插件 [`../../../deep-agent/local-tools/dsh-labkit/`](../../../deep-agent/local-tools/dsh-labkit/README.md) 只是它的一层薄封装。

```bash
node code/eduforge/tools/labkit/selftest.mjs   # 期望 7/7 pass
```


## 环境约定

- Node 探针默认从工作区根定位上游（`EDUFORGE_RAYOPTICS` 环境变量可覆盖），需要 `source/upstream/ray-optics/dist-node/rayOptics.js` 已构建。
- Python 工具用工程环境跑：`uv run python tools/export_contracts.py`；Playwright 探针需要本机 Chromium。

## 与其他层的关系

探针的输入是 [`../catalog/templates/`](../catalog/templates/README.md) 的模板场景；输出是 [`../../../output/eduforge/reports/`](../../../output/eduforge/reports/README.md) 的 JSON/截图证据；引擎侧事实基准是 [`../catalog/engines/ray-optics.yaml`](../catalog/engines/README.md) 的 `verification_baseline`。
