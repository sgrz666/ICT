# sandbox — 沙箱隔离与受控执行子系统 (Sandbox Subsystem)

> 2026-10-31 状态修正：本模块是进程执行原型：命令文本和 cwd 检查不构成操作系统隔离，不能用于运行不可信学生代码。历史“沙箱”命名与下文能力说明按原型理解。

**职责**：提供 Windows 兼容的原生命令受控执行环境。替代官方 `sandbox-windows-acl` 因无管理员特权而在 NTFS DACL 上报 Win32 5 拒绝错误的脆弱机制，采用**工作区路径门禁 + Windows 原生子进程超时清理（`taskkill /F /T`）+ 三档安全策略**的架构，并提供脱网确定性执行的 `MockSandboxProvider`。

## 内容

| 文件 | 状态 | 说明 |
|---|---|---|
| [`policy.py`](policy.py) | 已实测 | 三档权限策略（`read-only`, `workspace-write`, `danger-full-access`）与命令/工作目录安全校验器 |
| [`windows_compat.py`](windows_compat.py) | 已实测 | Windows 原生 Shell 检测（PowerShell 7, Windows PowerShell, Cmd, Git Bash）与 UTF-8 输出编码前导注入 |
| [`process_runner.py`](process_runner.py) | 已实测 | 原生子进程执行器 `ProcessSandbox`，集成超时拦截与 Windows `taskkill /PID <pid> /T /F` 进程树强杀 |
| [`jobs.py`](jobs.py) | 已实测 | 后台驻留任务管理器 `BackgroundJobManager`：对标 `@deepseek-ai/dsh-jobs-local` 与 `dsh-tool-jobs`，支持 `start_job`、`list_jobs`、`get_job_output`、`kill_job` 与会话归属隔离 |
| [`mock_sandbox.py`](mock_sandbox.py) | 已实测 | 内存 Mock 沙箱 `MockSandboxProvider`，支持规则注册、内置常用命令模拟与脱网无副作用测试 |
| [`__init__.py`](__init__.py) | 已实测 | 子系统 API 导出入口 |

## 与上下层的关系

- **上层依赖**：被顶级包 [`../__init__.py`](../__init__.py) 统一导出；在 Agent 智能体循环中作为 `tool-bash`/`tool-pwsh` 或代码执行环境被调用。
- **平级协同**：依赖文件子系统 [`../file/containment.py`](../file/containment.py) 的路径包含算法验证工作目录 `cwd`。
- **外部应用**：供教育智能体运行 Python 学生代码、物理模拟器计算脚本，防止恶意脚本逃逸破坏系统。

## 已知的坑与纪律

1. **进程树杀灭纪律**：Windows 下简单的 `proc.terminate()` 无法杀死子进程拉起的孙进程（如 powershell 启动的 python 进程），超时必须使用 `taskkill /PID <pid> /T /F` 递归清理，防止后台悬挂僵尸进程。
2. **UTF-8 输出前导**：PowerShell 默认输出编码非 UTF-8 会导致中文字符串乱码，执行时已注入 `[Console]::OutputEncoding = UTF-8` 前导指令。
3. **只读策略严格防篡改**：在 `read-only` 策略下，任何写重定向（`>`、`>>`）或删除命令（`rm`, `del`）均立即被拦截并抛出 `PolicyViolationError`。
