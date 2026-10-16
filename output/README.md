# output — 运行产物与验证证据

所有「跑出来的东西」放这一层：验证证据（JSON / 日志 / 截图）、候选交付物、以及尚未启用的产物目录。原则：**证据带时间与来源，可复跑**；这一层的内容由程序生成，不手写。

## 内容

| 路径 | 说明 |
|---|---|
| `rea-smoke-test.json` / `rea-smoke-test.err` | REA 对 `../input/rea-smoke-test` 的分析产出（Evidence JSON 154,888 字节）与标准错误流 |
| [`eduforge/`](eduforge/README.md) | EduForge 的全部产物：`reports/`（切片验证证据）、`candidates/`（候选交付物，如 GATE-8 离线网页包）、`artifacts/` 与 `research/`（预留，当前为空） |

## 注意

- `output/eduforge/candidates/` 已列入根 `.gitignore`（离线包装产物体积大且可再生）。
- `reports/` 下的文件是各切片（slice）与闸门（gate）验证时的原始输出，删改前先确认对应测试是否还需要它们做对照，详见 [`eduforge/reports/README.md`](eduforge/reports/README.md)。
