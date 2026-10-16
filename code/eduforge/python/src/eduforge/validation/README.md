# validation — 验证与发布门禁

**职责**：validating 阶段的检查项构建与发布裁决。把「上游接受修改 / 基础版本未被暗改 / 视图已登记 / 测量非退化 / 薄透镜独立对照 / 像面位置匹配 / 是否真聚焦」等检查汇总为 `ValidationReport`，由 `verdict`（passed / failed / inconclusive）决定任务能否走到 packaging。**科学纪律：对照公式必须与上游仿真互不共用代码**——同一实现算两遍不构成验证。

## 内容（逐文件）

| 文件 | 行数 | 职责 | 关键符号 |
|---|---|---|---|
| `reports.py` | 47 | 报告结构与裁决：`finalize()` 计算 verdict（**无检查项 → inconclusive，不默认 passed**） | `Check`, `ValidationReport`, `Verdict` |
| `policies.py` | 188 | **门禁检查构建**：`build_report` 汇总全部检查项；像面判据常量与选屏逻辑 | `build_report`, `nearest_screen`, `SCREENS_CM`, `SHARP_RMS_MAX`, `POWER_FLOOR` |
| [`scientific/`](scientific/README.md) | — | 独立科学参考式（薄透镜解析公式等） | 见子 README |

## 与上下层的关系

- 依赖：[`../domain/contracts.py`](../domain/contracts.py)、[`../validation/reports.py`](reports.py)、[`scientific/optics.py`](scientific/optics.py)。
- 被谁用：[`../worker/steps.py`](../worker/steps.py)（validating 阶段调 `build_report`）；[`../application/publication.py`](../application/publication.py)（`record_report` 落库 + `publish` 的 `NotPublishable` 门禁）。
- 测试：[`../../../../tests/python/test_publish_chain.py`](../../../../tests/python/test_publish_chain.py)（门禁全链路）、[`test_gate2_protocol.py`](../../../../tests/python/test_gate2_protocol.py)（薄透镜参考）。

## 已知的坑与纪律

- **verdict 保守语义**：没有检查项录得通过时是 `inconclusive` 而非 `passed`——这是防止"空报告放行"的刻意设计。
- 门禁参数（`SCREENS_CM`/`SHARP_RMS_MAX`/`POWER_FLOOR`）改动 = 改变物理判据，改前先跑 gate4/gate8 相关测试看斜率。
- `agent/services.py` 里有一个对 `ValidationReport` 的 import 但基本未使用——别被误导，报告的真正写入方是 `application/publication.py`。
- 新增检查项要同步三处：`build_report`、`reports.finalize` 的裁决输入、以及 `test_publish_chain.py` 的预期。
