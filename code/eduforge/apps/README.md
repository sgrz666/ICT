# apps — 前端应用

pnpm workspace 的 `apps/*` 槽位，放面向用户的前端应用。目前只有一个：**[`teacher-web/`](teacher-web/README.md)**（教师端）。

约定：新前端放这里而不是 `services/`；前端只通过 `@eduforge/contracts` 与后端交互，不直连数据库或上游引擎。
