# artifacts — 运行期产物区

**职责**：EduForge 运行期的中间产物落盘位置。当前实现：worker 的 **building 阶段**把候选场景写入 `revisions/{candidate_revision_id}/native.json`（id 由 `derived_id(job_id, kind)` 派生，保证重跑幂等、不产生孤儿文件）。

**不入库**：整个目录在根 `.gitignore` 中（`output/eduforge/artifacts/`）——运行数据、可重跑再生；本 README 是目录内唯一被 git 跟踪的文件。

## 内容（运行期结构）

```
artifacts/
└── revisions/
    └── <candidate_revision_id>/     # 由 job_id 派生的稳定 id
        └── native.json              # 候选场景（上游原生格式，字节即交付物）
```

（具体 uuid 子目录随本地跑批出现/消失，本 README 不固定列举。）

## 与上下层的关系

- 生产者：[`code/eduforge/python/src/eduforge/worker/`](../../../code/eduforge/python/src/eduforge/worker/README.md) 的 `artifact_path`；根路径由 `ARTIFACT_DIR` 环境变量给定，默认指向本目录。
- 消费方：API 下载链路按登记的 `storage_key` 取字节并**重算 sha256** 校验（[`code/eduforge/python/src/eduforge/api/`](../../../code/eduforge/python/src/eduforge/api/README.md)）。
- 交付形态的候选（离线包）在 sibling 的 `candidates/`，见 [`../README.md`](../README.md)。

## 已知的坑与纪律

- 目录内容随本地运行变化——**不要把这里当证据**，证据在 [`../reports/`](../reports/README.md)。
- 下载安全（path 越界 403 + sha256 重算）在 `api/main.py` 实现——改本目录结构会直接破坏下载链路，改前先跑 `test_gate5_api_chain.py`。
- 曾长期标注"预留、当前为空"——该措辞已失效（building 阶段实际在此落盘），别再按"空目录"理解。
