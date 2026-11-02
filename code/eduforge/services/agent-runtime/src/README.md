# src — 原生 dsh 启动与发行

职责：用官方运行内核启动项目自有配置，不重写 Agent 循环。

内容：`layout.mjs` 解析目录；`composition.mjs` 读取完整组合；`snapshot.mjs` 固定上游与品牌快照；`runtime.mjs` 经官方 runProfile 启动；`cli.mjs` 为统一入口；`verify.mjs` 验证真实工具与权限；`live.mjs` 提供显式真模型验收；`sdk-smoke.mjs` 检查原生 JSON-RPC；`ui-smoke.mjs` 用 Chromium 检查启智页面；`benchmark.mjs` 在新进程测启动/内存/模块；`package-graph.mjs` 保留 npm 多版本依赖；`package.mjs` 收集运行资源、浏览器并生成逐文件哈希。

关系：读取上层 `config/`；依赖已构建的官方包，实验工具来自原 JS LabKit 插件。

`report.mjs` 从两份实际验收、基准测量和发行清单生成实施报告，不把 pending 转成 pass。

纪律：上游目录只读；生成配置需要显式 `snapshot.mjs --write`。不得将密钥、会话或本机凭据复制进发行包。
