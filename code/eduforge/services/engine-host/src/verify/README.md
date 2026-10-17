# verify — 交付前的浏览器实测

**职责**：把「这份离线包到底能不能跑起来」变成一次可复核的测量，而不是一个推断。
上游是个纯前端仿真器，交付形态是「随包静态服务 + `www/index.html`」，所以
"文件都在盘上"和"教师打开后能看见光路"之间隔着一整个运行时：locale 取词、模块加载、
canvas 初始化、光迹渲染。本目录只干一件事——用真 Chromium 打开这份包，回报逐项判据。

## 内容（逐文件）

| 文件 | 行数 | 职责 | 关键符号 |
|---|---|---|---|
| `offline-runner.ts` | 214 | `verifyOfflinePackage(pkgDir)`：读包内 `manifest.json` 的 `entry` → 起一个**只绑回环地址**的随包静态服务 → 真 Chromium 打开 → 逐项判据 → 关浏览器与服务器。判据共 7 条：入口声明/入口在盘/场景载入/画出光斑/零出网/无页面错误/截图成功，任一不过即 `ok=false` | `verifyOfflinePackage()`, `PackageVerification`, `VerifyCheck` |

## 与上下层的关系

- 被谁用：[`../main.ts`](../main.ts) 的 `POST /verify/offline_package`（422 也带判据回去，不压成传输错误）。
- 上游调用方是 Python 侧的 [`../../../../python/src/eduforge/application/package_builder.py`](../../../../python/src/eduforge/application/package_builder.py)：
  离线包建好后立刻实测，不通过就抛 `DeliveryIntegrityError(code="OFFLINE_NOT_RENDERED")`，
  候选因此拿不到包，也就发布不出去（Gate C §C.5 的发布门禁）。
- 静态服务与 `../../tests/e2e/gate8_offline.test.ts` 用的是同一套 MIME 表——上游对
  `text/javascript` 严格检查，MIME 错了脚本就不执行，页面会"安静地什么都不画"。
- 测试：`../../tests/e2e/package_verify.test.ts`（4 项，含"删掉模拟器运行时脚本必须判不过"这条控制组）。

## 已知的坑与纪律

- **`frameLocator(...).isHidden()` 是假绿灯**：元素不存在时它也返回 true。所以这里不用它，
  而是遍历 frame 树找 `#welcome`——找不到就明确判不过（"iframe 文档没 load 出来" ≠ "场景已载入"）。
  `gate8_offline.test.ts` 仍留着这个旧写法，它是本轮发现但尚未修的已知弱点。
- **路径解析别用 `resolve(rel, "index.html")`**：那会拿 `process.cwd()` 去解析相对路径，
  得出一个包外的绝对地址，被越权守卫判成 403，实测表现为"页面开了但一个 canvas 都没有"。
  正确写法是 `join(rel, "index.html")` 再 `resolve(root, ...)`。
- 一次实测约 9–11 秒（Chromium 冷启动 + 场景稳定），不是免费的；只在**交付前**跑一次，
  不要放进每次改参的循环里。
- 静态服务只监听 `127.0.0.1`、端口 0 随机、用完即关；`pkgDir` 来自调用方，
  与 `/export/offline_package` 同一个信任边界（本机单用户进程，Engine Host 不对外监听）。
