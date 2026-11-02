# 原生 dsh 精简实施与验收记录

生成时间：2026-10-31T06:00:07.258Z。上游：687f282e8625c6b8d11ff58211a90524be2e4317。

## 交付行为

- 启智 Web 提供 physics-lab / eduforge-dev 双预设；作为正式本地 bundle 加载，配置保存后仍保留组合。
- 教师只注册真实 LabKit 六工具与提问/展示；开发保留原生文件、PowerShell、技能、规划、目标、后台任务与子智能体。
- 去除遥测、账号、反馈、定时提醒、PTC、市场、联网搜索、MCP 默认插件及 Office；保留 API Key、Web 连接鉴权与审批。
- LabKit 使用真实引擎和 Chromium；独立 UUID 输出目录防同名并发混写，设计/HTML/证据哈希互绑。

## 实测

| 样本 | 启动 ms | 空闲 RSS MiB | 加载插件行 |
|---|---:|---:|---:|
| 原 Web + 原隐私补丁 | 3968 | 276.8 | 154 |
| 精简 Web | 5769 | 183.3 | 128 |

单次新进程观测，启动后空闲一秒；不是多轮统计基准。原始模块清单保留在两份 benchmark JSON。

源码验收：partial，失败项：无。
仓库外发行验收：partial，失败项：无。

待验项目：
- live_model：DEEPSEEK_API_KEY is absent in this verification process. Existing credential stores are not copied.

## 独立发行候选

目录：D:\codeplus\ICT\output\eduforge\candidates\agent-runtime\win-x64-20261031。10056 文件，525505678 字节（501.2 MiB），442 个 npm 包实例。
浏览器：chromium-headless-shell 1248、ffmpeg 1013、winldd 1007。保留依赖许可证，Node 许可证随 runtime 提供。
包内 inventory.json 记录逐文件 SHA256；verify 先检查缺失、变化与多余文件。体积含 Node、浏览器及实验验证资源，不能与上游整个开发检出直接比较。

## 使用与回退

```powershell
.\code\eduforge\services\agent-runtime\agent-runtime.ps1 doctor
.\code\eduforge\services\agent-runtime\agent-runtime.ps1 web -Port 3082
.\code\eduforge\services\agent-runtime\agent-runtime.ps1 verify -Live
```

默认数据位于 %LOCALAPPDATA%/EduForge/agent-runtime，旧会话和凭据未迁移。配置 API Key 后可执行真模型验收；无 key 不使用模拟输出代替。关闭新进程即可继续使用原上游启动方式。

本次未替换 Python Worker 或数据库；SDK 保留原生开发工具和 JSON-RPC，教师端业务集成另行接入。

测试规模唯一计数见 code/eduforge/catalog/engines/ray-optics.yaml 的 test_totals。
