# scripts — 工作区统一操作脚本

放跨工程与工作区级别的操作脚本（区别于 [`../code/eduforge/tools/`](../code/eduforge/tools/README.md)——那里面放的是 EduForge 内部的验证探针与契约导出工具）。

## 内容

| 脚本 | 语言 | 行数 | 作用 |
|---|---|---|---|
| `eduforge.ps1` | PowerShell | 405 | 工作区统一操作入口（§7.4）：`doctor` / `bootstrap` / `up` / `test` / `smoke` / `benchmark` / `down` 七个命令（`-Action` 位置参数由 `ValidateSet` 约束；`-Profile` 默认 `screening`） |

## 端口一览（与脚本内检查一致）

| 端口 | 角色 | 谁在用 |
|---|---|---|
| 8000 | API 后端（FastAPI） | `up` 启动（第 2 步），`doctor` 检查 |
| 8010 | Engine Host（仿真宿主/预览） | `up` 启动，`doctor` 检查 |
| 4174 | 浏览器网关（静态 + `/api` 反代 + 预览同源） | `up` 启动 |

> 另有容器路径的端口拓扑（engine-host 4000 / agent 8001，见 [`../code/eduforge/infra/README.md`](../code/eduforge/infra/README.md)）——两套并存：本脚本走"无容器直跑"，compose 走容器。

## 用法

```powershell
Set-Location D:\codeplus\ICT

# 检查环境健康度（Python、Node、上游核心、Docker、端口、目录完整性）
.\scripts\eduforge.ps1 doctor

# 准备依赖与构建产物
.\scripts\eduforge.ps1 bootstrap

# 运行全量测试套件（pytest + vitest 双套）
.\scripts\eduforge.ps1 test

# 运行真实浏览器端到端冒烟测试
.\scripts\eduforge.ps1 smoke

# 运行基准评测集（支持 -Profile screening / deepseek_direct / agent_graph）
.\scripts\eduforge.ps1 benchmark -Profile screening

# 启动本地服务（API :8000 + Engine Host :8010 + 浏览器网关 :4174）
.\scripts\eduforge.ps1 up

# 停止服务（保留数据）
.\scripts\eduforge.ps1 down
```

## 纪律

- 脚本任一步骤失败返回非零退出码；
- 不输出密钥，不自动升级上游依赖；
- 普通启动不重新全量构建上游资源；
- `down` 停止服务绝不删除数据库或实验研究产物。
