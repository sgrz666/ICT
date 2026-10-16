# eduforge — EduForge 产物区

EduForge 跑出来的东西分四类，按性质分目录，不混放：

| 目录 | 性质 | 状态 |
|---|---|---|
| [`reports/`](reports/README.md) | 验证证据（切片/gate 的原始输出：JSON、日志、截图） | 15 个文件，内容最实 |
| `candidates/` | 候选交付物（给用户/评委看的东西） | `offline-package/`：GATE-8 离线网页包；**已列入 `.gitignore`** |
| `artifacts/` | 运行期产物区（worker building 阶段写 `revisions/{candidate}/native.json`） | **运行数据，不入库**（已列入 `.gitignore`） |
| `research/` | 调研材料 | 预留，当前只有 README |

另有两个本地运行状态（不入库，均在 `.gitignore`）：`pgdata/`（pgserver 数据目录）、`eduforge.pids` 与 `pg_uri.txt`（一键启动脚本的运行痕迹）。

## 约定

- 本目录内容全部由程序/命令生成，**不手写、不手改**；要复跑就重跑对应测试或探针（入口见 [`../../code/eduforge/tools/`](../../code/eduforge/tools/README.md)）。
- `candidates/` 已列入根 `.gitignore`（体积大且可再生）；`reports/` 是证据，删除前确认没有测试引用它做对照。

## 与其他层的关系

- 生产者：`../../code/eduforge`（测试与探针）；设计与排期：`../../plan/26.10.15_EduForge_推进计划.md`。
- 根目录另有两个 REA 冒烟分析产出（`../rea-smoke-test.json` / `.err`），不属于 EduForge，见 [`../README.md`](../README.md)。
