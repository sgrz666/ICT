# apps — 前端应用

pnpm workspace 的 `apps/*` 槽位，放面向用户的前端应用。目前只有一个：**[`teacher-web/`](teacher-web/README.md)**（教师端）。

- 源码逐文件说明：[`teacher-web/src/README.md`](teacher-web/src/README.md)（含 [`api/`](teacher-web/src/api/README.md)、[`components/`](teacher-web/src/components/README.md)、[`data/`](teacher-web/src/data/README.md)、[`hooks/`](teacher-web/src/hooks/README.md) 子目录）。

约定：新前端放这里而不是 `services/`；前端只通过 `@eduforge/contracts` 与后端交互，不直连数据库或上游引擎。
