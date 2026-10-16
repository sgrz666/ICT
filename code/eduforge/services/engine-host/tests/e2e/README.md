# e2e — 真实浏览器端到端（GATE-3 / GATE-8）

**职责**：用真实 Chromium（playwright）验证预览桥接、交互与离线包的端到端行为。共享夹具 `render_harness.ts` 提供「双信号稳定」的截图判定——两次独立信号同时稳定才认为画面可判。

## 内容（逐文件）

| 文件 | 行数 | 覆盖 |
|---|---|---|
| `render_harness.ts` | 85 | 共享夹具：`lightSignals()`、`waitForStableRender()`（双信号同时稳定）、`openPreview()`、`shotHash()`、`startBrowser()`、`startPreview()` |
| `gate3_bridge.test.ts` | 110 | §5.3 桥接：ready 只报一次、改参后重报 + `parameter_changed`、新 revision、旧版本仍可达、越界回 `APPLY_FAILED` |
| `gate3_interaction.test.ts` | 106 | 载入即隐欢迎页、清空复位、侧栏新增对象 |
| `gate8_offline.test.ts` | 154 | 离线包结构 / manifest / sha256 锁定、随包静态服务**零出网**、`file://` 直开不可用（实测结论） |
| `preview_render.test.ts` | 108 | 真实浏览器可判性：控制组逐位一致、f=10 vs f=15 光路不同、拒绝越界路径、`/scene` 回 201 含 iframe、无脚本错误 |

## 与上下层的关系

- 被测：[`../../src/preview/`](../../src/preview/README.md)、[`../../src/export/`](../../src/export/README.md)、[`../../src/adapters/ray-optics/`](../../src/adapters/ray-optics/README.md)。
- 向上汇总在父层 [`../README.md`](../README.md)。

## 已知的坑与纪律

- **双信号稳定是防竞态核心**：不要改成单信号"跑得快"。
- **控制组逐位一致是贯穿不变量**：控制组必须与模板原样渲染逐位相同——它防的是"顺手改了别的东西"。
- `gate8` 的「零出网」断言依赖随包静态服务方式运行；改服务方式先看该测试的监听方式。
