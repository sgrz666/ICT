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

## 注意

- `gate3-interaction.log` 是**失败现场**，对应的交互用例后来已通过（见推进计划实况节）；读它时按历史现场理解。
- 删改任何文件前，先确认 `code/eduforge/catalog/engines/ray-optics.yaml` 的 `verification_baseline` 没有引用它。
