# services — Node 侧服务

pnpm workspace 的 `services/*` 槽位，放常驻服务进程。**[`engine-host/`](engine-host/README.md)** 是上游引擎宿主，**[`agent-runtime/`](agent-runtime/README.md)** 是原生 dsh 智能体运行时。引擎宿主逐文件说明见 [`engine-host/src/README.md`](engine-host/src/README.md)（适配器 / 导出 / 网关 / 预览四个子模块）与 [`engine-host/tests/README.md`](engine-host/tests/README.md)。

Engine Host 的职责边界：**所有对上游引擎的程序化操作都收敛到这一个进程**——适配器改原生场景、预览 iframe 的渲染与桥接、浏览器同源网关、离线包导出。Python 侧通过 HTTP 与它交互（`infrastructure/clients/engine_client.py`），不直接碰上游。

新增 **[agent-runtime/](agent-runtime/README.md)**：原生 dsh 启智 Web 与教学/开发双预设，提供独立数据目录、权限检查、验证及 Windows 发行入口；与 engine-host、Python Worker 分开运行。程序接入沿用官方 SDK JSON-RPC，尚未替换现有生产 Agent。

约定：新服务放这里；服务间不共享进程，业务接口靠 HTTP + contracts 通信，Agent 运行时的进程控制沿用官方 SDK 协议。
