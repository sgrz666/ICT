# tools — 六个 experiment_* 工具

**职责**：每个文件注册一个 dsh 原生工具，只做「参数 → 核心库调用 → 结果投影」，不重复物理或渲染逻辑。

| 文件 | 工具 | 超时 | 说明 |
|---|---|---|---|
| [`recipes.mjs`](recipes.mjs) | `experiment_recipes` | 15 s | 读 `recipes.json`，返回配方、默认参数、量程、容差 |
| [`validate.mjs`](validate.mjs) | `experiment_validate` | 15 s | L1 校验 + 解析预测 + `feasible_hint` |
| [`simulate.mjs`](simulate.mjs) | `experiment_simulate` | 60 s | L2 物理对账，写 `evidence.json` |
| [`render.mjs`](render.mjs) | `experiment_render` | 60 s | 先跑 L1/L2 再渲染单文件，不做 L3 |
| [`verify.mjs`](verify.mjs) | `experiment_verify` | 120 s | L3 Playwright `file://` 六项判据 |
| [`build.mjs`](build.mjs) | `experiment_build` | 240 s | 一次完成 L1→L2→渲染→L3，标准请求入口 |

## 统一约定

- 领域失败**返回** `{ok:false, stage, code, summary, hints}`，不抛异常；只有未预期异常才冒泡。
- `summary` 是模型看到的主文本：只放结论、关键读数、路径与建议；完整数据放 `data`，不倾倒 evidence。
- 所有写操作经 [`../lib/paths.mjs`](../lib/paths.mjs) 的 `outPaths()`，输出根固定在 `output/eduforge/candidates/labkit/`。
- `execute(args, exec)` 在进入 L3 前检查 `exec.signal.aborted`；Playwright 在 `finally` 里关闭。

## 与上下层的关系

- 注册入口：[`../index.mjs`](../index.mjs)（`apply(ctx)` 依次调用六个 `registerX`）。
- 能力来源：[`../lib/labkit.mjs`](../lib/labkit.mjs) → [`../../../../code/eduforge/tools/labkit/`](../../../../code/eduforge/tools/labkit/README.md)。
