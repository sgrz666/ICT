# security — Engine Host 安全测试套件

**职责**：针对 Engine Host 内部端点的安全负向测试集合（路径穿越、越权逃逸、非法 manifest entry、超限 Body 防护）。

## 内容

| 文件 | 用例数 | 覆盖项 |
|---|---|---|
| `sandbox.test.ts` | 10 | 路径白名单拦截、`..` 穿越、Windows/Linux 绝对系统路径拒绝、空字节拒绝、HTTP 403 响应、HTTP 413 大包拦截、manifest entry 越权逃逸拦截 |

## 与上下层的关系

- 被测代码：[`../../src/security/path-sandbox.ts`](../../src/security/path-sandbox.ts)、[`../../src/main.ts`](../../src/main.ts)、[`../../src/verify/offline-runner.ts`](../../src/verify/offline-runner.ts)。
- 运行：`vitest run tests/security/sandbox.test.ts`（纳入整体 vitest 套件）。

## 已知的坑与纪律

- 针对文件系统的负向测试若创建临时目录，必须在 `afterAll` 中安全定向清理；
- 断言 HTTP 状态码为真实的 403 / 413，绝不放宽为 200 或通用 500。
