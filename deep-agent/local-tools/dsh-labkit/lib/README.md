# lib — 插件的共享适配层

**职责**：把「上游 dsh 工具 API」「EduForge LabKit 分派器」「路径与输出命名」「工具结果文本」收敛成几个小模块，供 `tools/` 下的六个工具复用。

| 文件 | 作用 |
|---|---|
| [`dsh.mjs`](dsh.mjs) | 优先从 `EDUFORGE_DSH_INSTALL_ANCHOR` 解析官方 `defineTool`；未设置时兼容原上游相对布局 |
| [`labkit.mjs`](labkit.mjs) | 核心库单一入口：按配置资源根动态导入 `dispatcher.mjs` 与模板/哈希函数，通过 `file://` URL 支持含空格路径 |
| [`paths.mjs`](paths.mjs) | `repoRoot` 读 `EDUFORGE_LABKIT_ROOT`，默认由插件位置反推；`outRoot` 读 `EDUFORGE_LABKIT_OUTPUT_ROOT`；`outPaths()` 每次分配 `<recipe>/<uuid>/`，防止同名并发混写 |
| [`package.mjs`](package.mjs) | 交付包生成：教师手册、学生任务单、包清单；只读 design / evidence / 模板 `lesson.md`，清单登记渲染清单及实际 L3 哈希，不复制物理实现 |
| [`tool-schema.mjs`](tool-schema.mjs) | 六个工具共用的输出 schema、`designParams()` 参数 schema、`renderResult()` 文本投影 |
| [`format.mjs`](format.mjs) | 抛体场景读数表、错误块、建议块 |
| [`summary.mjs`](summary.mjs) | 按 `template_id` 把 L2 结果投影成摘要表（抛体/单摆/电路） |

## 与上下层的关系

- 上层：[`../index.mjs`](../index.mjs) 与 [`../tools/`](../tools/README.md)。
- 下层：[`../../../../code/eduforge/tools/labkit/`](../../../../code/eduforge/tools/labkit/README.md)（从 `lib/` 起算 5 层到仓库根，再进 `code/`）。
- 上游：[`../../../deepseek-harness/packages/core/tools/`](../../../deepseek-harness/packages/core/tools/)（**只读**，不修改）。

## 纪律

- `dsh.mjs` 的路径与 dsh 版本耦合；升级 dsh 后先跑 `--dump-config` 与一次 headless 会话。
- 新增输出位置必须走 `paths.mjs` 的 `outRoot` 与 `assertUnder()`，不要在工具里硬编码绝对路径。
- 环境变量在模块加载时读取，变更后重启宿主；资源根保留 ICT 相对布局。验证见父层的 `portable.test.mjs` 与真实 `selftest.mjs`。
