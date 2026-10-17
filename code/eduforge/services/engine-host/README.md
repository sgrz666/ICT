# engine-host — 引擎宿主服务

包名 `@eduforge/engine-host`，TypeScript + Node 原生 `node:http`（无 Web 框架），`node dist/main.js` 启动，默认监听 `127.0.0.1:8010`。它是 EduForge 与上游引擎之间的**唯一通道**：适配器执行修改、预览渲染、浏览器网关、离线包导出四类能力都收敛在这一个进程里。

## 源码结构（src/）

| 文件 | 职责 |
|---|---|
| `main.ts` | 组合根：装配适配器、网关、预览路由，暴露 `/adapters/ray_optics/apply`（支持批量参数修改）与 `/export/offline_package` 导出端点 |
| `contracts.ts` | 操作协议类型（`SetParameter` / `SetView` 等），泛化绑定类型与参数名定义 |
| `adapters/ray-optics/adapter.ts` | Ray Optics 适配器：读模板 manifest + native.json，校验绑定，支持单项及批量参数修改与光线抽样 |
| `adapters/ray-optics/patch.ts` | 纯函数式场景修改：支持焦距（`focal_length_cm`）与物距（`object_distance_cm`）修改，源数据不被就地改写 |

| `adapters/ray-optics/upstream.ts` | 上游仿真封装（load / validate / simulate） |
| `upstream_paths.ts` | 定位工作区根与上游目录——**靠向上查找，不手数 `../`**（本工程在 parents 层数上错过四次，代价高） |
| `preview/server.ts` | 预览服务：把候选场景经上游自己的分享 URL 机制（json-url lzma + `#hash`）塞进上游模拟器 iframe，渲染完全由上游产生；桥接改参数走 `POST /param`，复用同一个适配器，上游不接受就 422 |
| `preview/messages.ts` | 桥接消息类型（宿主页 ↔ iframe，`eduforge.ready` / `parameter_changed` 等） |
| `gateway/server.ts` | 浏览器网关：静态托管教师前端 + `/api` 反代（保留方法/查询/请求体/自定义头）；**代理目标只允许回环地址**，未配置 501、连不上 502 |
| `export/offline-package.ts` | GATE-8 离线网页包导出（复刻上游 dist + 模板场景，manifest 登记 `scene_sha256`） |
| `export/html.ts` | 单文件 HTML 组装器探索：内联语言词条与 fetch/XHR 拦截脚本（当前实测受限于 iframe 内层跨域隔离，交付形式以随包本地静态服务为主） |
| `export/manifest.ts` | 实验发布元数据清单构建器（独立解耦引擎版本、原生场景哈希与许可协议） |

`dist/` 是 `tsc -p tsconfig.build.json` 的构建产物；测试在 `tests/`（vitest）。

> **逐文件细节**（行数、导出符号、依赖关系）与四个子目录的独立说明见 [`src/README.md`](src/README.md)（另含 [`src/adapters/ray-optics/`](src/adapters/ray-optics/README.md)、[`src/export/`](src/export/README.md)、[`src/gateway/`](src/gateway/README.md)、[`src/preview/`](src/preview/README.md)）。注意：`contracts.ts` 是**本服务自有**的本地类型，与 `packages/contracts` 生成的业务 DTO 是两套并行定义，互不相引——改动没有自动同步。

## 测试结构（tests/）

- `adapters/ray-optics/patch.test.ts` — 补丁纯函数（含控制组：改回原值必须逐位一致）。
- `engines/` — `gate3_engine_host.test.ts`（起真 HTTP 服务走完整链路）、`gate4_science_profile.test.ts`（科学剖面）、`measure_separation.test.ts`（像面定位：7 屏 + RMS，八档 argmax 全对）、`beam_geometry.test.ts`（光束几何：实像交点/虚像反向延长/准直/不可判四态）。
- `e2e/` — `gate3_interaction.test.ts`（浏览器交互：复位、新增对象）、`gate3_bridge.test.ts`（§5.3 桥接消息时序）、`gate8_offline.test.ts`（离线包断网检查）、`preview_render.test.ts` + `render_harness.ts`（渲染可复现性：同场景两次 sum/lit/截图哈希全等）。
- `gateway/gateway.test.ts` — 7 条网关用例（静态挂载、反代保真、501/502、回环限制）。

> 逐文件与四个测试子目录的独立说明见 [`tests/README.md`](tests/README.md)。

## 关系与纪律

- 上游资产在 `../../../../source/upstream/ray-optics`（构建产物 `dist-node/rayOptics.js` 是无头仿真入口）；本服务**不改上游一行**，差异全在 adapters 层。
- 观测只用上游仿真；独立参考公式只在 Python 侧 `validation/scientific/optics.py`，两边不共用。
- `json-url` 复用上游自带那份（npm 版未声明 `@babel/runtime` 依赖，自装会运行期挂，见 `upstream.lock.json` 的 known_pits）。
