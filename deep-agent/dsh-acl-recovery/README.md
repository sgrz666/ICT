# dsh-acl-recovery/ — Windows 权限置备的备份与回滚

## 职责

存放**官方** ACL 诊断修复脚本（`diagnose-windows-sandbox-acl.ps1`）为 `harness-ui-workspace` 置备权限时生成的备份、回滚脚本与完整记录。它是「这次系统权限改动可被逐一撤销」的凭据，也是阶段 C 审批闭环的落盘产物。

## 内容

| 文件 | 是什么 |
|---|---|
| `acl-backup-<id>.json` | 改动前该对象的安全描述符备份 |
| `acl-backup-<id>.json.ps1` | 与之配对的**回滚脚本**，按备份还原 |
| `acl-report-<id>.jsonl` | 完整记录（observation / grant / verification / summary）。脚本的标准输出只留尾部，早期记录只在这个文件里存活，所以别只看 stdout |

回滚命令形态（由脚本自己打印，`-Path`/`-AllowRoot` 都限定在工作区根）：

```powershell
pwsh -NoProfile -File 'acl-backup-<id>.json.ps1' -Path 'D:\codeplus\ICT\deep-agent\harness-ui-workspace' `
  -AllowRoot 'D:\codeplus\ICT\deep-agent\harness-ui-workspace' -Restore 'acl-backup-<id>.json'
```

## 与上下层的关系

- 产生者：Web UI 会话「跨工作区文件创建测试」中，Agent 依官方 skill 发起、我在审批面板点「允许一次」后代跑的那一条命令（证据在 `../harness-validation-reports/installation-report.md` 的审批实测表）。
- 被影响对象：[../harness-ui-workspace/](../harness-ui-workspace/README.md)。`harness-smoke-workspace` 的同类备份在 `../harness-smoke-workspace/_acl-out/`（该目录不入库）。
- 背景：不置备权限时，默认 `workspace-write` 下所有命令在启动前就报 `SetNamedSecurityInfoW failed (Win32 5)`（`_logs/probe_shell.*`）。

## 已知的坑与纪律

1. **删之前先确认工作区不再需要**：还原一次就把 `sg` 的 FullControl 撤掉，之后 Agent 在该目录又会回到跑不了命令的状态。
2. 这类目录只由官方脚本写入；**不要手工编辑 ACL、不要提权跑脚本、不要把 `-AllowRoot` 往上级放宽**（官方 skill 的 Never 清单）。
3. 一次改动两份文件（备份 + 回滚脚本），成对存在才算可撤销；出现孤儿文件说明上次运行被中断，按报告里 `restore_pending_then_stop` 的语义处理。
4. 文件里含本机 SID 与绝对路径，属正常环境信息，不含任何 API 凭据。
