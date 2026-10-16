# services — Node 侧服务

pnpm workspace 的 `services/*` 槽位，放常驻服务进程。目前只有一个：**[`engine-host/`](engine-host/README.md)**（Engine Host——上游引擎的宿主）。

Engine Host 的职责边界：**所有对上游引擎的程序化操作都收敛到这一个进程**——适配器改原生场景、预览 iframe 的渲染与桥接、浏览器同源网关、离线包导出。Python 侧通过 HTTP 与它交互（`infrastructure/clients/engine_client.py`），不直接碰上游。

约定：新服务放这里；服务间不共享进程，靠 HTTP + contracts 通信。
