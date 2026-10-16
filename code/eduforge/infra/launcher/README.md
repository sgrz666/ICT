# launcher — 离线启动器编译镜像（切片 9 预留）

**职责**：构建「本地轻量离线启动器」的 Windows 可执行文件：用 Go 交叉编译产物放进 scratch 镜像，最终交付一个单文件 `Start-Experiment.exe`（免安装起离线实验包用）。

## 内容

| 文件 | 行数 | 关键步骤 |
|---|---|---|
| `Dockerfile` | 11 | `FROM golang:1.22-alpine` 构建层：`COPY tools/offline-server` → `CGO_ENABLED=0 GOOS=windows GOARCH=amd64 go build -ldflags="-s -w" -o Start-Experiment.exe` → `FROM scratch` 只带该 exe |

## 与上下层的关系

- 构件产物形态与 GATE-8 离线包（[`../../services/engine-host/src/export/`](../../services/engine-host/src/export/README.md)）配套：离线包 + 启动器组成"教师免安装"交付。
- 源码本应来自 `tools/offline-server/`（Go 程序）。

## 已知的坑与纪律

- **`tools/offline-server` 目录当前不存在**：Go 启动器尚未开工，本 Dockerfile 现在**不可构建**——这是切片 9 的预留件，不是失败现场。
- 交付目标是 Windows exe（学校机房常态）：`GOOS=windows` 交叉编译 + `-s -w` 去符号，产物经 scratch 层输出。
- 启用前需要：先落地 Go 源码目录，再补构建脚本与 README 登记。
