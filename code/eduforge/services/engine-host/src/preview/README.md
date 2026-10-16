# preview — §5.3 预览桥接（postMessage 改参换图）

**职责**：预览系统的服务端半边——注册场景、生成包装页/宿主页、同源改参接口、上游 dist 静态资源。渲染完全由上游模拟器在 iframe 里产生；桥接协议让父页把「滑块改参」发进来，改完重新加载并回报。

## 内容（逐文件）

| 文件 | 行数 | 职责 | 关键符号 |
|---|---|---|---|
| `messages.ts` | 122 | §5.3 协议类型与脚本：`PreviewMessage`、内联 `BRIDGE_SCRIPT`（同源校验、改参走 `/param`）、最小宿主页 `hostPage()` | `PreviewMessage`, `BRIDGE_SCRIPT`, `hostPage()` |
| `server.ts` | 180 | 预览 HTTP 路由：`/scene` 注册、`/param` 同源改参（复用 `rayOpticsAdapter`）、`/p/<id>` 包装页、`/host/<id>` 宿主页、**上游模拟器静态托管（`/simulator/…`，供教师端 SimulatorView 内嵌仿真用）**，静态资源全程防越界 | `MIME`, `PreviewServer`, `createPreviewRoutes()`, `PreviewHandler` |

## 桥接时序（一条改参消息的往返）

1. 父页（前端 `PreviewFrame` / 网关 `/host/<id>`）`postMessage` 发 `eduforge.set_parameter`；
2. 包装页转发到 `POST /param`（服务端复用适配器与上游解释）；
3. 换 src 重新加载 → 回报 `eduforge.ready` / `eduforge.parameter_changed`；
4. 每次 `ready` 带当前 `revision_id`；同源校验不过一律忽略。

## 与上下层的关系

- 被谁用：[`../main.ts`](../README.md)（起预览路由）、[`../gateway/server.ts`](../gateway/README.md)（复用 `MIME`/`PreviewHandler`）。
- e2e 测试：[`../../tests/e2e/`](../../tests/README.md)（`gate3_bridge` / `gate3_interaction` / `preview_render`）。
- 上游 dist 静态资源路径来自 [`../upstream_paths.ts`](../README.md) 的 `UPSTREAM_DIST`。

## 已知的坑与纪律

- **`PreviewMessage` 有两份定义**：本目录 `messages.ts` 与 `packages/contracts/src/preview.ts`，需**手动保持同步**（合约包注释已声明）——改协议两边同改。
- `ready` 只报一次、改参后必须重报（测试断言）；不要为"少发消息"省略重报。
- 越界路径拒绝出现在三处（`/p`、`/host`、静态资源）——审安全时三处都要看。
