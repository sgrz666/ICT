# reports — 验证证据

切片（slice）与闸门（gate）推进时的**原始输出**：探针 JSON、测试日志、浏览器截图。原则是保留原始证据而非只留结论——每个数字都能在这里找到出处。文件按「切片_主题」命名。

## 文件清单

| 文件 | 来源 | 内容 |
|---|---|---|
| `slice1-rayoptics-probe.json` | `tools/rayoptics_probe.cjs` | 第一切片核心证据：上游接受手写场景（error/warning 均 null）、toJSON 往返闭合、纯函数改焦距（15cm→150）、绑定方式结论（下标绑定否决，改 `name`）、与薄透镜参考式吻合 |
| `slice1-browser.json` / `slice1-browser-loaded.png` | `tools/browser_gate1.py` | 真实 Chromium 经分享 URL 载入场景：标题、canvas 层数、页面错误、UI 元素清单 |
| `slice1-browser-edit.json` / `slice1-browser-edit-final.png` | `tools/browser_gate1_edit.py` | UI 内改焦距 → 同步 → 复制分享链接 → 解回：`focalLength` 由缺失变 150、四个 `name` 保留 |
| `share-hash.txt` | 上游「复制分享链接」 | lzma 压缩的场景 URL（382 字符），浏览器探针的输入 |
| `slice2-gate2.json` / `slice2-gate2-stdout.json` | `tools/gate2_binding.cjs` | GATE-2：阈值（清晰 ≥0.8 / 弥散 ≤0.4 / 之间不可判）与五档分层物距的判定结果 |
| `engine-host-boot.log` | Engine Host 启动 | 一行：`engine-host listening on 127.0.0.1:8010` |
| `static-server.log` | 上游静态服务器 | 本地 serve 上游编辑器时的访问日志（4 个 URL 全 200） |
| `probe-out.txt` | 交互探针 | 预览 iframe 内 HTTP 响应摘要（200、长度、开头内容） |
| `gate3-interaction.log` | vitest（失败留痕） | GATE-3 交互测试一次失败运行的完整输出——保留它是为了记录排查过程，不是当前状态 |
| `benchmark-screening.json` | `benchmarks/runner.py` | §7.4 基准评测筛查报告：12 题三类任务（参数修改、视图控制、超出能力应拒）全量实跑，通过率与策略拦截率 100% |
| `benchmark-deepseek_direct.json` | `benchmarks/runner.py` | `deepseek_direct` 档位：`status: SKIPPED`——缺 `DEEPSEEK_API_KEY`，显式跳过（不伪充结果） |
| `benchmark-agent_graph.json` | `benchmarks/runner.py` | `agent_graph` 档位：`status: SKIPPED`——同上，缺 key |
| `agent-deepagents-real.json` | `tests/python/test_deepagents_real_model.py` | 2026-10-16 真实模型（`deepseek-flash`）自主完成「焦距 15cm + 物距 30cm + 数据记录表」的完整 Tool Trace：7 次调用（含一次自主换查询词重试的 `search_experiments`）、逐项 `observed`/`expected` 判据、最终场景读数与验证结论。**注意**：`profile` 标注的是这一条任务实测通过，不是 12 题基准的模型档位成绩 |
| `gate-c5b-post-publish-reverification.txt` | `pytest` 全量 / 契约生成 / 金路径含反面 | §C.5b 发布后重验：`verify_package_on_disk` 按清单逐文件重算（`changed`/`missing`/`unexpected` + 整包摘要），`Chain.packaging` 进事务前拦 `PACKAGE_DRIFT`，新出口 `GET /revisions/{id}/offline_verification` 随附发布前的浏览器实测记录；实测含反面——改一个 `www/index.html` 立刻 `verified=false` |
| `gate-c3-teaching-views-and-temp-hygiene.txt` | `pytest` 全量 / `npm run build` / Chromium 金路径 | §C.3 教学视图上屏（后端视图出口 + 契约重生成 + 前端面板，屏上那一行与交付的 `teaching_views.json` 逐值比对）；以及 `%TEMP%` 1018 个测试目录的根因核对与 conftest 会话级清扫、后台心跳与 `check_now()` 共用一条连接导致的 asyncpg `InterfaceError` 竞态修复（含绕开锁复现的控制证明） |
| `gate-c5-browser-verification.txt` | `vitest` 全量 / `pytest` 全量 / 一次真 Chromium 实测记录 | §C.5 发布门禁：离线包由 Engine Host 用真浏览器打开的 7 条判据与实测数字（光强 2.9e8、点亮像素 453202、零出网、9.2–10.2 秒），反面用例（删掉模拟器运行时脚本必须判不过）、`offline_verification.json` 的位置，以及顺手发现的 `gate8_offline.test.ts` 用 `isHidden()` 判"场景已载入"的假绿灯（本轮未修，已登记） |
| `gate-c4-unified-package-builder.txt` | `pytest` 全量 / `vitest` 全量 / 逐文件计数 | §C.4 统一交付包构建器：Worker 原先不建离线包、两处各写一份盘、引擎交付元数据被哈希表覆盖——这三处不一致的修法与实测；含"按文件名排除清单导致 `www/simulator/manifest/manifest.json` 一直被漏在哈希表外（2161 → 2162 条）"这个顺手抓到的真缺陷，以及一次发布产物由 1 份变 2 份的行为改动 |
| `gate-c2-wide-aperture-probe.txt` | `pytest` / `vitest` / 引擎逐工况探针（15 组） | §C.2 补量具的实测：vitest 70、pytest 125 收集 / 124 通过 / 1 SKIPPED；宽孔径观测副本 + 透镜面光阑后 15 个工况全部判出并与薄透镜参考对上（最大偏差 0.8cm），含「有光阑 −75.0cm vs 无光阑 −227.3cm」这条控制组，以及虚像/准直从拒绝发布改回凭实测发布的行为变化 |
| `gate-c-validation-geometry.txt` | `uv run pytest` / `vitest` / 引擎逐焦距探针 | Gate C（C.1+C.2）实测：125 收集 / 124 通过 / 1 SKIPPED、vitest 67、逐焦距光束几何数值表，以及「虚像与准直在当前屏阵列上测不出来 → 一律拒绝发布」这条未闭环缺口（同日第二轮已补，见上一行） |
| `gate-b-execution-rights.txt` | `uv run pytest` / `vitest` / 故障注入 | Gate B 的命令与真实退出码：124 收集 / 123 通过 / 1 SKIPPED（真模型无 key）、vitest 54 全绿、`--timeout` 参数不存在被工具纠正一次、执行权与归属各判据的落点，以及本轮实测新抓到的 `lease_token` 回读缺陷 |
| `gate-a-candidate-run.txt` | `uv run pytest` / `vitest` / `scripts/eduforge.ps1 doctor` | 2026-10-17 Gate A 的命令与真实退出码：基线 103→113 收集（112 通过 / 1 SKIPPED 真模型无 key）、vitest 54 全绿、doctor 通过（含 `eduforge.ps1` 加 UTF-8 BOM 才能在 PowerShell 5.1 解析这一前置修复）、benchmarks 仍无 `deepagents_e2e` 档位，以及并跑导致 `initdb` 内存不足的那 17 项 ERROR 的如实留痕 |

## 注意

- `gate3-interaction.log` 是**失败现场**，对应的交互用例后来已通过（见推进计划实况节）；读它时按历史现场理解。
- 删改任何文件前，先确认 `code/eduforge/catalog/engines/ray-optics.yaml` 的 `verification_baseline` 没有引用它。
