# packages — 跨栈共享包

pnpm workspace 的 `packages/*` 槽位，放被前端与服务端共享的 TypeScript 库。目前只有一个：**[`contracts/`](contracts/README.md)**（源码逐文件说明见 [`contracts/src/README.md`](contracts/src/README.md)，生成物见 [`contracts/src/generated/README.md`](contracts/src/generated/README.md)）。

约定：这里只放「契约与类型」，不放业务逻辑；新包先确认确实跨 `apps/` 与 `services/` 共用再拆出来。
