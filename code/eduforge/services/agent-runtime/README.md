# agent-runtime — 启智原生 dsh 运行时

## 职责

使用固定版本官方 TypeScript/Cordis 内核运行启智 Web；教学与开发使用隔离的工具预设。Python 业务可通过官方 SDK 协议调用独立进程，本目录不替换 EduForge 数据库、Worker 或发布门禁。

## 内容与使用

| 文件 / 目录 | 职责 |
|---|---|
| `agent-runtime.ps1` | 统一 doctor / web / sdk / verify / package 入口 |
| `package.json` | Node 内置测试与启动命令，不安装第二套 Agent 框架 |
| [config/](config/README.md) | 固定上游、完整组合配置和现有品牌补丁 |
| [src/](src/README.md) | 启动、验证、依赖收集与发行代码 |
| [tests/](tests/README.md) | 工具隔离和可迁移依赖图回归 |

从仓库根执行：

```powershell
.\code\eduforge\services\agent-runtime\agent-runtime.ps1 doctor
.\code\eduforge\services\agent-runtime\agent-runtime.ps1 web -Port 3082
.\code\eduforge\services\agent-runtime\agent-runtime.ps1 verify
.\code\eduforge\services\agent-runtime\agent-runtime.ps1 package -Out D:\EduForge-release
```

`web` 输出本机访问地址；其中 token 是凭据，不应分享或写进报告。网页中新建会话可选「教学实验」或「开发助手」。教学提供六个 `experiment_*` 工具与提问、展示；开发提供文件、PowerShell、技能、Todo/Plan/Goal、后台任务和子智能体。预设选择不是不同用户之间的权限隔离。

配置作为正式本地 bundle 注册；Web 保存设置、配置重载和重启会重新装配该 bundle，用户设置保留在独立 patch 层。`verify` 包含真实 Chromium 的预设切换、保存设置后重载和拒绝审批按钮检查，以及 SDK 握手、缺失会话恢复拒绝和退出检查。发行包的 `verify` 在运行前后按 `inventory.json` 复核全部文件，篡改、缺失或多余文件均拒绝。Chromium 日志写用户数据目录，不写发行目录；首次使用的引导弹窗在浏览器验收的动作阶段处理，避免异步弹窗拦截点击。

默认数据目录为 `%LOCALAPPDATA%\EduForge\agent-runtime`，内有 `home/`、`workspace/` 与 `labkit/`。用 `-Data <目录>` 和 `-Workspace <目录>` 指定其他位置；不自动复制旧凭据或会话。在模型配置页配置 API Key，或在启动进程提供 `DEEPSEEK_API_KEY`。SDK 启动通过 `sdk` 子命令，stdout 保留 JSON-RPC。

`verify -Live` 在当前进程存在 `DEEPSEEK_API_KEY` 时执行真实模型修复、子智能体、原生压缩和恢复；没有 key 时标 `pending`。可用 `EDUFORGE_LIVE_MODEL` 指定实际服务支持的模型。SDK 保留原生开发工具核心，当前不提供 Web 的教学预设选择；完整教师端集成留在后续业务接入。

开发模式读取原有 `deep-agent/deepseek-harness` 构建产物；发行模式只读包内 `runtime/` 与 `assets/`。这些生成目录不纳入源码与逐目录 README 覆盖。

`package` 在开发工作区使用，目标必须为不存在的目录；生成包的 `runtime/` 是实体 npm 多版本依赖树、Windows x64 Node 与 Chromium Headless Shell，不含完整 Chrome 的重复二进制。源码工作区的包依赖由 `pnpm-lock.yaml` 的空 importer 登记；上游包始终从固定构建或发行包解析。

## 与上下层的关系

父层为 [services](../README.md)。真实实验能力来自 [LabKit](../../tools/labkit/README.md) 和 [dsh 插件](../../../../deep-agent/local-tools/dsh-labkit/README.md)，不使用 Python dsh-core 的公式模拟。现有上游检出保持只读；回退可停止新服务并继续使用原启动方式。

## 已知边界与纪律

- 默认 `workspace-write` + `ask`，不自动提权、不修改系统 ACL。官方策略允许读文件，并允许写工作区和平台临时目录；不能把它误述为只允许访问工作区。
- `verify` 分开记录 pass/fail/pending，缺少模型或原生隔离前提不降级为模拟通过。`partial` 表示仍有 pending，不能作为完整发布验收。
- 官方 SDK 当前没有完整交互审批或单轮取消协议；没有审批通道时不放行需要审批的操作。
- 新生成 HTML 需要一起保存 `.html.manifest.json` 和证据文件，旧产物重新构建后才能用新完整性校验复验。
- 初版目标 Windows x64。体积由实际依赖集合决定，不以整个上游开发仓库体积作为缩减基准。
