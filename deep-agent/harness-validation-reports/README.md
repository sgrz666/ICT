# harness-validation-reports/ — 五份交付报告

## 职责

本轮验证的**结论层**。阶段 A–F 的所有判定只在这里成文；`_logs/` 是原始证据，`_tools/` 是复现方法，本目录是「所以到底行不行」。写完后本轮即停止，不含任何 EduForge 改造实现。

## 内容

| 文件 | 覆盖阶段 | 里面实际写了什么 |
|---|---|---|
| [installation-report.md](installation-report.md) | A + B + C | 环境实测表（Node v24.14.1、pnpm 11.28.5 由仓库 `packageManager` 决定、pwsh 7.6.4、无 submodule）；克隆锚点 `687f282e…` / `dsh-v0.2.1-rc.2` / 22,395 commits；三条命令的退出码与耗时（install 2m1.7s、build 360.27s 九门全过、typecheck 16.12s 五门全过）；Web UI 启动日志与健康状态；阶段 C 各界面核验到哪一层的分层表；六条实际问题 |
| [api-connectivity-report.md](api-connectivity-report.md) | D | 真实 DeepSeek 接入：凭据解析顺序、`baseURL=https://api.deepseek.com/anthropic`（Messages 协议、`x-api-key`）、线上模型目录实测（`deepseek-flash` / `deepseek-v4-pro`）、协议级工具调用预检（`stop_reason: tool_use`）、六次框架内运行的 token 表、五条检查项逐条结论、以及明确标出「成本未测得」 |
| [agent-loop-test-report.md](agent-loop-test-report.md) | E | 五项测试逐条证据：调用顺序表、每次 `tool_result` 的原文摘录、失败与重试计数、耗时；第 6 节权限与审批观察；第 7 节汇总表；第 8 节验收判定；**第 9 节是修复后复跑**（根因 `WRITE_OWNER` 缺失、官方脚本修法、测试 2/3/4 在默认 `workspace-write` 下重跑通过） |
| [architecture-notes.md](architecture-notes.md) | 源码阅读 | 按实际源码总结：Cordis「一切皆插件」、profile/bundle 分层与 `--dump-config`、一次 turn 的事件序列、会话日志即模型可见面（Model-visible ⟺ logged）、capability seam 三角色、工具目录（win32 用 `pwsh` 而非 `bash`）、沙箱与三档权限预置、`llm-deepseek` 错误码族、`DSH_HOME` 路径解析、值得学的工程门 |
| [next-integration-assessment.md](next-integration-assessment.md) | F | 只评估不实现：值得重点复用的模块按性价比排序（agent-loop/tools/session、执行世界 provider 组、llm-deepseek、session 持久化与查询、subagent/goal、plan/todo、skill、sandbox、MCP、Python SDK），不建议动的部分，接入前置条件，以及「官方已有但本轮未验证」清单 |
| [rebrand-qizhi-report.md](rebrand-qizhi-report.md) | G（前端品牌重构） | 启智AGENT 第一版改造：9 处品牌注入点清单（含 `conversation.hero.brand.mark` 这个首屏槽位）、新增 `ui-brand-qizhi` 包占三个槽位的做法、设计与粒子实现说明、构建与浏览器实测（标题/标志/首屏/ favicon 已换，`/DeepSeek/` 匹配为 false，33 项前端单测全过）、前后对比表、5 条后续建议 |
| [rebrand-qizhi-v2-glass-report.md](rebrand-qizhi-v2-glass-report.md) | G（第二版毛玻璃） | v2 全记录：为什么「token 生效但页面仍不透明」逼出逐元素反查（不透明责任集中在 `bg-base`/`specific-sidebar-fill`/`specific-input-major` 三个变量）、改走 `ctx.theme.overrideTokens()` 官方通道而删掉选择器权重对抗、三条被当作硬约束的上游规矩（模态不模糊、菜单材质不重定义、描边不与抬升阴影叠用）、能力降级只能在注册前决定的原因、实测数字（不透明面板 6→0、6 个模糊表面、20 个行内 token）、849+4 测试与两次运行的差异、5 条诚实限制 |
| [rebrand-qizhi.patch](rebrand-qizhi.patch) | G + G(v2) | 上述改动的可重放补丁，**已随第二版重生成**：29 个文件、+1,083 行、65,920 字节（v1 版是 24 个文件 / 49,436 字节）。上游克隆目录被 ICT 的 `.gitignore` 排除，改动只以补丁形式留档 |

## 与上下层的关系

- 上游：本目录引用的每一条数字都应能在 [../_logs/README.md](../_logs/README.md) 指到的具体文件里复核。
- 同级：`_probe/` 证明测试 3 的缺陷是预先存在的；`patches/` 与 `_tools/` 解释工作区是怎么被钉住的。
- 外部：上游事实的权威是 `deepseek-harness` 那个 commit 与 `https://deepseek-harness.github.io/deepseek-harness/`，本目录只描述、不复制。

## 已知的坑与纪律

1. **报告只追加不覆盖**。失败现场（测试 2 首轮、3a、4 首轮）保留在正文里，修复结果写在第 9 节并链接回去；把「未通过」改写成「通过」就是伪造证据。
2. 未跑过的一律写 `pending` / 「本轮未验证」，不许用「框架启动成功」替代「Agent 能力验证成功」。
3. 相对链接以本目录为基准（如 `../_logs/README.md`）；移动文件必须同轮改链接。
4. 任何新增报告都要在这张表里登记一行，并说明它覆盖哪个阶段。
5. 模式差异必须标注：`danger-full-access` 下取得的结论不能写成默认权限下的结论。
