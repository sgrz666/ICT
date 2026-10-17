# validation — 验证与发布门禁

**职责**：validating 阶段的检查项构建与发布裁决。每条判据必须交代 `source`（证据从哪来）与 `profile`（在什么科学剖面下成立），并且三态化：`pass`（观测支持）/`fail`（观测反驳）/`na`（**没有独立观测**）；`na` 把整份结论压成 `inconclusive`，发布因此被挡住而不是被蒙过去。报告还绑定 `candidate_id`+`content_hash`+`engine_version`+`profile`。把「上游接受修改 / 基础版本未被暗改 / 视图已登记 / 测量非退化 / 薄透镜独立对照 / 像面位置匹配 / 是否真聚焦」等检查汇总为 `ValidationReport`，由 `verdict`（passed / failed / inconclusive）决定任务能否走到 packaging。**科学纪律：对照公式必须与上游仿真互不共用代码**——同一实现算两遍不构成验证。

## 内容（逐文件）

| 文件 | 行数 | 职责 | 关键符号 |
|---|---|---|---|
| `reports.py` | 102 | 报告结构与裁决：`Check` 带 `source`/`profile`/`status`(pass/fail/na)/`tolerance`/`decisive`，`passed` 与 `status` 不一致时构造即报错；`finalize()` 计算 verdict（**无检查项 → inconclusive，决定性 `na` → inconclusive，不默认 passed**）；报告绑定 `candidate_id`+`content_hash`+`engine_version` | `Check`, `ValidationReport`, `Verdict`, `CheckStatus` |
| `policies.py` | 366 | **门禁检查构建**：`build_report` 汇总全部检查项；像面判据常量、选屏逻辑，以及 `_agreement_tolerance_cm()`——容差由量具自己报出的不确定度算（`max(2×屏定位分辨率, 3×外推交点标准误)`），不写死 | `build_report`, `nearest_screen`, `SCREENS_CM`, `SHARP_RMS_MAX`, `POWER_FLOOR`, `SCREEN_RESOLUTION_CM`, `VERTEX_SIGMA_FACTOR`, `_add_geometry_check` |
| [`scientific/`](scientific/README.md) | — | 独立科学参考式（薄透镜解析公式等） | 见子 README |

## 与上下层的关系

- 依赖：[`../domain/contracts.py`](../domain/contracts.py)、[`../validation/reports.py`](reports.py)、[`scientific/optics.py`](scientific/optics.py)。
- 被谁用：[`../experiment_tools/service.py`](../experiment_tools/README.md)（`run_validation` 调 `build_report`，并**当场** `record_report` 落 `validation_reports`，再把 `validation_id` + 候选 `content_hash` 绑回 `experiment_candidates`）；[`../worker/steps.py`](../worker/steps.py) 的 validating 阶段**改为经 `run_validation` 走这一条实现**（2026-10-17 Gate A 起，Worker 不再自己调 `build_report`，两套判据语义收敛为一份）；[`../application/publication.py`](../application/publication.py)（`record_report` 落库 + `publish` 的 `NotPublishable` 门禁）。
- 测试：[`../../../../tests/python/test_publish_chain.py`](../../../../tests/python/test_publish_chain.py)（门禁全链路）、[`test_gate2_protocol.py`](../../../../tests/python/test_gate2_protocol.py)（薄透镜参考）。

## 已知的坑与纪律

- **`base_untouched` 本轮才真的成立**：`worker/steps.py` 过去写 `(base != result) or True`，恒真，于是本文件第 3 行宣称的「基础版本未被暗改」这道闸门实际不存在；`policies.py` 的该判据永远不会红。现在取「引擎返回的 `base_untouched`（`main.ts:60` 比对入参与产出）∧ 库里基线修订逐字节复核」两者之与，它才可能失败。
- **已收紧的判据（2026-10-17 Gate C §C.2）**：旧的 `virtual_image_valid: u < f` 与 `focal_parallel_beams: abs(f-u)<1e-4` 是公式恒真自证，已删除；现在虚像/无穷远必须拿引擎实测的光束几何（`measurement.geometry`，见 [`upstream.ts`](../../../../services/engine-host/src/adapters/ray-optics/README.md)）。
- **Python 不采信引擎给的 `kind`**：`beam_parallelism_observed` 自己复核 `|slope| ≤ 2×slope_stderr`（σ 由各屏读数的拟合残差算出），`beam_geometry_agrees` 自己算与独立参考的偏差是否落在 `_agreement_tolerance_cm()` 内。换引擎、改判据实现都拦得住；旧的 `passed = slope is not None`（只要报了个数就放行）已废除。
- **量具极限已在 2026-10-17 第二轮补上（此前如实记为未闭环）**：交付屏只有 ±12cm 半高，虚像与准直工况下光斑铺满探测器（rms ≈ 均匀照明上限的 98%），一度只能报「孔径截断，测不出来」，f=40/f=50/u=f 一律不发布。现在几何证据取自**观测副本**（屏加宽、`binSize` 不变，透镜面加与口径同宽的光阑挡掉未经透镜的直光扇），实测交点 f=40→−119.6cm（参考 −120）、f=50/u=10→−12.5cm（参考 −12.5）、u=f 各屏宽度完全一致 → 这些工况恢复发布，但凭的是读数不是公式。**留下的坑**：交付给教师的屏仍是 ±12cm，屏上不成像时（f=5）`spot_is_actually_focused` 照样反驳——几何证据来自副本，聚焦证据仍来自交付屏，两条不能互相顶替。
- 实像工况的屏位判据已从 `abs(...) < 1e-9` 的假精确改为「落在屏分辨率 2cm 内」（最小屏间距 4cm 的一半），并与几何交点交叉核对（`beam_geometry_agrees` 在实像下作非决定性证据）。
- **verdict 保守语义**：没有检查项录得通过时是 `inconclusive` 而非 `passed`——这是防止"空报告放行"的刻意设计。
- 门禁参数（`SCREENS_CM`/`SHARP_RMS_MAX`/`POWER_FLOOR`）改动 = 改变物理判据，改前先跑 gate4/gate8 相关测试看斜率。
- `policies.py` 里 `view_edits: list[Any]` 的 `Any` 从未 import，只因 `from __future__ import annotations` 才没炸；一旦有人对这张模块用 `typing.get_type_hints` 就会报错。
- `agent/services.py` 里有一个对 `ValidationReport` 的 import 但基本未使用——别被误导，报告的真正写入方是 `application/publication.py`。
- 新增检查项要同步三处：`build_report`、`reports.finalize` 的裁决输入、以及 `test_publish_chain.py` 的预期。
