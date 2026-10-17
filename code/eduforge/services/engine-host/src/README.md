# src — Engine Host 源码头

**职责**：Node 侧「引擎宿主」服务的全部源码。对外是一个进程（`main.ts`）；内部四块：仿真适配（[`adapters/`](adapters/README.md) → [`adapters/ray-optics/`](adapters/ray-optics/README.md)）、离线导出（[`export/`](export/README.md)）、浏览器网关（[`gateway/`](gateway/README.md)）、预览桥接（[`preview/`](preview/README.md)）。

## 内容（根层逐文件）

| 文件 | 行数 | 职责 | 关键符号 |
|---|---|---|---|
| `main.ts` | 108 | 进程入口与 GATE-3 验收面（healthz / template / validate / apply）；非测试环境同时起 engine-host（8010）与网关（4174） | `createEngineHost()` |
| `contracts.ts` | 42 | 本服务**自有**的本地类型（与 `@eduforge/contracts` 是两套并行定义，互不相引） | `SetParameter`, `SetView`, `Operation`, `EditProposal`, `LensBinding`, `RayScene` |
| `upstream_paths.ts` | 42 | 定位上游 Ray Optics 与 catalog 的工作区根；复用上游 `json-url` 编解码器 | `WORKSPACE_ROOT`, `UPSTREAM_DIR`, `UPSTREAM_DIST`, `UPSTREAM_NODE_BUNDLE`, `CATALOG_DIR`, `OUTPUT_DIR`, `lzmaCodec()`, `decodeShareUrl()` |

## 子目录

| 子目录 | 职责 | 细节 |
|---|---|---|
| [`adapters/`](adapters/README.md) → [`adapters/ray-optics/`](adapters/ray-optics/README.md) | 按引擎分组的适配器层（当前只有 ray-optics）：改参 / 校验 / 真实仿真 / 导出 | `upstream.ts` 是真实仿真入口 |
| [`export/`](export/README.md) | 离线网页包组装（i18n 预注入 + manifest 锁） | html / manifest / offline-package |
| [`gateway/`](gateway/README.md) | 浏览器网关：静态 + `/api` 反代 + 预览合成单一源 | 反代只放行回环 |
| [`preview/`](preview/README.md) | §5.3 预览桥接（postMessage 改参换图） | /scene /param /p/ /host/ |
| [`security/`](security/README.md) | 路径沙箱白名单校验器（防越权穿越与软链逃逸） | assertWithinSandbox / getAllowedRoots |

## 与上下层的关系

- 上游依赖：无头 core bundle `dist-node/rayOptics.js`（经 `createRequire` 加载；本体在 `source/upstream/ray-optics/`，身份锁在 `source/upstream/upstream.lock.json`）。
- 消费方：教师前端（经网关同源访问预览与仿真）；Python 侧经 HTTP 调 `/adapters/ray_optics/apply`（客户端在 [`../../../python/src/eduforge/infrastructure/`](../../../python/src/eduforge/infrastructure/README.md)）。
- 测试：[`../tests/`](../tests/README.md)（vitest；e2e 用真实 Chromium）。
- 端口：本地无容器路径为 engine-host `8010` + 网关 `4174`（由 `scripts/eduforge.ps1 up` 使用）；Docker 路径端口不同，见 [`../../../infra/README.md`](../../../infra/README.md)。

## 已知的坑与纪律

- **两套契约并存**：`contracts.ts`（本服务内部用）与 `packages/contracts/src/generated/api.ts`（前端用）是不同来源——本服务不经 `@eduforge/contracts` 取类型，改动要意识到没有自动同步。
- `export/html.ts` 与 [`export/offline-package.ts`](export/offline-package.ts) 各自硬编码算出上游 `dist` 路径，**未复用** `upstream_paths.ts`——改目录结构要三处同看。
- `main.ts` 在 `NODE_ENV=test` 时不监听端口（测试直接拿 `createEngineHost()` 应用面）——本地调试端口问题先看该环境变量。
