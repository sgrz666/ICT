# gateway — 浏览器网关（单源合成）

**职责**：把「教师前端静态站 + `/api` 反代 + 预览路由」合成**单一源**（默认 4174），保证 §5.3 预览桥接的同源校验（`e.origin === location.origin`）不被放宽。反代只放行回环地址，防 SSRF。

## 内容（逐文件）

| 文件 | 行数 | 职责 | 关键符号 |
|---|---|---|---|
| `server.ts` | 123 | 网关路由归属：静态文件（`EDUFORGE_TEACHER_WEB_DIST`）、`/api` 反代（保留方法/路径/体/幂等头）、预览分流；未配置回 501、不可达回 502、越界不读出 | `GatewayOptions`, `assertLoopback()`, `createGateway()` |

## 路由归属（`createGateway` 的分流规则）

| 请求 | 去向 |
|---|---|
| `/api/...` | 反向代理到 Python 业务 API（仅限回环地址） |
| 应用静态文件 | 教师前端构建产物（vite dist） |
| 其余（`/scene` `/param` `/p/...` `/host/...` `/simulator/...`） | 预览路由（[`../preview/server.ts`](../preview/README.md)） |

## 与上下层的关系

- 被谁用：[`../main.ts`](../README.md) 在非测试环境随 engine-host 一起监听；测试 [`../../tests/gateway/gateway.test.ts`](../../tests/README.md)。
- 依赖：[`../preview/server.ts`](../preview/README.md)（复用 `MIME` 与 `PreviewHandler`）。

## 已知的坑与纪律

- **同源是硬前提**：桥接脚本对入站 `postMessage` 强制同源校验；若让前端另开端口访问预览，这条边界就会被放宽——不要这样部署。
- 反代只放行回环地址（`assertLoopback`）：防 SSRF 的刻意设计，别为了"方便"放开。
- 网关路径下 `/api` 的幂等头必须原样透传（工单测试断言了这一点）——透传链路改动先跑 `gateway.test.ts`。
