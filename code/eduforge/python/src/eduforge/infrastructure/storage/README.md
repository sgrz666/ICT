# storage — 产物存储（本地 / OBS）

**职责**：`ArtifactStoragePort` 的两种实现——本地文件系统与华为云 OBS。**当前运行时产物不经本目录**：[`../../worker/steps.py`](../../worker/steps.py) 直接把产物写进 `artifact_dir`（Path），下载侧由 [`../../api/main.py`](../../api/main.py) 读文件并做哈希校验。本目录目前仅测试可达，属"端口先行、接线未做"状态。

## 内容（逐文件）

| 文件 | 行数 | 职责 | 关键符号 |
|---|---|---|---|
| `local.py` | 34 | 本地文件存储（`ArtifactStoragePort` 实现） | `LocalArtifactStorage` |
| `obs.py` | 47 | 华为云 OBS 存储**桩**（方法未实现；切片 7~8 云存储预留） | `OBSArtifactStorage` |

## 与上下层的关系

- 依赖：[`../../domain/ports.py`](../../domain/README.md)（协议）、[`../../domain/errors.py`](../../domain/errors.py)。
- 消费方：仅测试（见 [`../../../../../tests/python/test_plan_architecture_alignment.py`](../../../../../tests/python/test_plan_architecture_alignment.py)）；运行时写入方是 `worker/steps.py`，读取与校验方是 `api/main.py`。

## 已知的坑与纪律

- **接入本层 = 三处同改**：写入（`application/package_builder.py`，§C.4 起 Worker 与工具层共用它；落盘路径仍由 `worker/steps.py` 的 `artifact_path` 同款规则给出 `revisions/<候选版本>/`）、读取（`api/main.py` 的 download）、校验（两侧的 sha256 计算）——只改一处会造成"存得进、下不动"。
- `obs.py` 是桩：方法签名在了、实现没有；上云前不要假设它可跑。
- 本地开发时 `ARTIFACT_DIR` 由环境变量给定，路径越界校验（403）在 `api/main.py`——换存储后端时这条校验的等价物必须保留。
