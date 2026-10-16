# code — 自研代码

全部自研代码都放在这一层。目前只有一个工程：**[`eduforge/`](eduforge/README.md)**（EduForge 主工程，pnpm workspace + Python 包）。

分工约定：

- 跨工程的共享脚本放根 `scripts/`（如 [`../scripts/README.md`](../scripts/README.md) 中的 `eduforge.ps1` 统一操作入口）。
- 每个子工程是自己的构建与测试单元，不在本层做统一构建；EduForge 的入口命令见其 README。
- 依赖安装产物（`node_modules/`、`.venv/`）属于各工程本地环境，已列入 `.gitignore`，不作为交付内容。
