# gateway（测试）— 网关路由归属与安全

**职责**：验证浏览器网关的分流规则与安全边界——哪类请求去静态、哪类去 `/api` 反代、哪类去预览，以及越界与回环限制。

## 内容

| 文件 | 行数 | 覆盖 |
|---|---|---|
| `gateway.test.ts` | 147 | 静态 / `/api` 反代（保留方法/路径/体/幂等头）/ 预览分流；越界不读出；API 不可达回 502；未配置回 501；**只放行回环地址** |

## 与上下层的关系

- 被测：[`../../src/gateway/server.ts`](../../src/gateway/README.md)（`assertLoopback`/`createGateway`）、[`../../src/preview/server.ts`](../../src/preview/README.md)。
- 向上汇总在父层 [`../README.md`](../README.md)。

## 已知的坑与纪律

- 回环限制（`assertLoopback`）与幂等头透传是安全/一致性断言——改动反代逻辑必须跑本测试。
- 「API 不可达回 502 / 未配置回 501」区分了两种失败语义，别合并。
