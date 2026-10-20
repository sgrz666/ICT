# lib — 插件的共享适配层

**职责**：把「上游 dsh 工具 API」「EduForge LabKit 核心」「路径与输出命名」「工具结果文本」四件事收敛成四个小模块，供 `tools/` 下的六个工具复用。

| 文件 | 作用 |
|---|---|
| [`dsh.mjs`](dsh.mjs) | 从上游已构建的 `packages/core/tools/lib/index.js` 相对导入 `defineTool`；插件零 npm 依赖的关键 |
| [`labkit.mjs`](labkit.mjs) | 核心库单一入口：`checkDesign` / `simulateDesign` / `renderSingleFile` / `verifySingleFile` / `loadTemplate` / `designHash` |
| [`paths.mjs`](paths.mjs) | `repoRoot`（由插件位置反推）、`outRoot`、`safeName()`、`outPaths()` |
| [`tool-schema.mjs`](tool-schema.mjs) | 六个工具共用的输出 schema、`designParams()` 参数 schema、`renderResult()` 文本投影 |
| [`format.mjs`](format.mjs) | 场景读数表、错误块、建议块 |

## 与上下层的关系

- 上层：[`../index.mjs`](../index.mjs) 与 [`../tools/`](../tools/README.md)。
- 下层：[`../../../../code/eduforge/tools/labkit/`](../../../../code/eduforge/tools/labkit/README.md)（从 `lib/` 起算 5 层到仓库根，再进 `code/`）。
- 上游：[`../../../deepseek-harness/packages/core/tools/`](../../../deepseek-harness/packages/core/tools/)（**只读**，不修改）。

## 纪律

- `dsh.mjs` 的路径与 dsh 版本耦合；升级 dsh 后先跑 `--dump-config` 与一次 headless 会话。
- 新增输出位置必须走 `paths.mjs` 的 `outRoot` 与 `assertUnder()`，不要在工具里硬编码绝对路径。
