# tests — engine-host 测试套件（vitest + 真实 Chromium）

**职责**：engine-host 的验收面。四个子目录各有分工：适配器单测（`adapters/`）、浏览器端到端（`e2e/`）、引擎级验收（`engines/`）、网关路由（`gateway/`）。e2e 用真实 Chromium，以「双信号稳定渲染」作为截图判定前提。

## 内容（按子目录）

| 子目录 | 文件数 | 覆盖 | 细节 |
|---|---|---|---|
| [`adapters/`](adapters/README.md) → [`adapters/ray-optics/`](adapters/ray-optics/README.md) | 1 | 改参语义单测（不加载上游 bundle，与 `engines/` 分界） | `patch.test.ts` |
| [`e2e/`](e2e/README.md) | 5 | GATE-3 桥接/交互、GATE-8 离线、预览可判性 | 含共享夹具 `render_harness.ts` |
| [`engines/`](engines/README.md) | 3 | GATE-3 宿主验收、GATE-4 科学对照、像面判据回归 | 真跑仿真断言读数 |
| [`gateway/`](gateway/README.md) | 1 | 网关路由归属与安全 | `gateway.test.ts` |
| [`security/`](security/README.md) | 1 | Gate C.0 内部路径沙箱、manifest 越权防逃逸与 Body 限额负向测试 | `sandbox.test.ts` |

## 跑法

```bash
cd code/eduforge && pnpm -r test        # workspace 全量（vitest 54）
```

## 与上下层的关系

- 被测源码：[`../src/`](../src/README.md)。
- 断言上游事实：真实加载 `dist-node/rayOptics.js`（[`source/upstream/`](../../../../../source/upstream/README.md)）。

## 已知的坑与纪律

- **「控制组逐位一致」是贯穿全部 e2e 的不变量**：控制组画面必须与模板原样渲染逐位一致——防"顺手改了别的东西"。
- e2e 依赖本机 Chromium；「双信号稳定」（`waitForStableRender`）是防截图竞态的关键，不要改成单信号。
- 测试规模计数**不在本目录记**：唯一计数处是 [`../../../catalog/engines/ray-optics.yaml`](../../../catalog/engines/README.md) 的 `test_totals`。
