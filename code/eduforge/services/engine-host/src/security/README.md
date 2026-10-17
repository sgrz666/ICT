# security — 内部路径沙箱与端点防御

**职责**：Engine Host 内部构建与校验端点的路径沙箱白名单校验器，防止任意路径注入、跨目录穿越（`..`）与符号链接逃逸。

## 内容

| 文件 | 行数 | 职责 | 关键符号 |
|---|---|---|---|
| `path-sandbox.ts` | 60 | 校验输入路径是否落在受控的工件目录、候选目录或临时目录白名单内 | `assertWithinSandbox()`, `getAllowedRoots()`, `PathTraversalError` |

## 与上下层的关系

- 被谁用：
  - [`../main.ts`](../main.ts)：对 `POST /export/offline_package`（`outDir`）与 `POST /verify/offline_package`（`dir`）执行入参沙箱校验，越权直接拒回 HTTP 403 `FORBIDDEN`；
  - [`../verify/offline-runner.ts`](../verify/offline-runner.ts)：在启动随包静态服务前核验离线包根目录安全性。
- 测试：[`../../tests/security/sandbox.test.ts`](../../tests/security/sandbox.test.ts)。

## 已知的坑与纪律

- **不仅判前缀，要查 realpath**：若目标路径已存在，做符号链接解析（`realpathSync`），防止攻击者在沙箱内建软链跳到宿主机敏感目录；
- **测试环境支持**：`tmpdir()` 默认纳入允许根，供自动化测试安全创建临时包，容器化环境可通过 `EDUFORGE_ALLOWED_ROOTS` 显式扩展挂载卷。
