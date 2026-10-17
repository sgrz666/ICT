# plan — 计划、排期与记录

这一层放项目的**决策与进度文档**，按日期命名，只追加、不回改。代码事实以代码和 `source/upstream/upstream.lock.json` 为准；这里的文档解释「为什么这样做」和「现在到哪了」。

## 内容

| 文件 | 性质 | 内容 |
|---|---|---|
| `26.10.14.md` | 早期头脑风暴 | ICT 赛道方向讨论：平台痛点、纯静态交付、教师本地运行、安全与成本等原始想法 |
| `26.10.15-REA部署.md` | 部署记录 | REA（rea-agents 6.5.0）本地 + 全局双安装、MCP 注册、`rea doctor` 现状（缺 Hopper/Ghidra/IDA/JADX/JEB 外部引擎）、用法备忘与一个待办 |
| `26.10.15_EduForge_推进计划.md` | 主排期 | 切片 1–8 与 AgentArts 迁移（第 7–8 周）的排期、闸门、置顶「实况」节、风险登记、逐轮记录（第 1–20 轮） |
| `26.10.15_EduForge_代码级实施方案.md` | 主设计 | 代码级结构（§1 目录与层级、§2 调用关系）、数据协议与数据库（§3）、关键实现代码（§4）、验证/预览/导出（§5）、API 与前端（§6）、实施顺序与测试（§7） |
| [26.10.16_EduForge_原方案审查与Agent重构建议.md](26.10.16_EduForge_原方案审查与Agent重构建议.md) | 代码审查与设计建议 | 原方案对照、真实链路与边界复现、Agent 工具缺口、开源框架候选及分阶段验收；迁移建议尚未实施 |
| [26.10.16_EduForge_DeepAgents落地核查与实况修正.md](26.10.16_EduForge_DeepAgents落地核查与实况修正.md) | 核查 + 本轮实施记录 | 对一份外部重构方案的逐条事实核对（5 处不成立/过期，含 §5 P1 的 `run_db.py` 判断已失效）、本轮另查出的 9 项缺陷与修法、Deep Agents 接入实况、真模型实测结果与 9 项 pending |
| [26.10.17_EduForge_GateC_验证几何与候选绑定.md](26.10.17_EduForge_GateC_验证几何与候选绑定.md) | Gate C 开工（**未闭环**） | C.1 报告绑候选与来源三态化、C.2 虚像/无穷远改判引擎实测光束几何并删掉两条公式恒真判据；逐焦距实测表 + 「孔径截断」量具极限与补齐路径；C.3–C.7 明确未做 |
| [26.10.17_EduForge_GateB_执行权与归属.md](26.10.17_EduForge_GateB_执行权与归属.md) | Gate B 实施与实况 | 心跳接 `renew_and_check`（独立连接）、租约过期不得自续、`attempt`/`next_run_at`/重试上限记账、`job_events` 序号行锁、发布加归属与字节核对、API 与工具层的 owner 过滤与身份边界；含指令 §2 Gate B 八条的逐条落点表，以及本轮实测新抓到的「Runner 回读 lease_token」缺陷 |
| [26.10.17_EduForge_GateA_统一候选执行链.md](26.10.17_EduForge_GateA_统一候选执行链.md) | Gate A 实施与实况 | 按《Deep Agents 实施指令（执行版）》第一轮只做 Gate A：删掉 `operations_from_trace` → `Chain._apply` 的重放语义、候选落 `experiment_candidates`（含迁移与 CAS）、`DeepAgentRunner` 交回候选完成记录；含 §6 模板汇报、对审查文档 P0-1～P0-6 的逐条核对、顺带修掉的 4 项缺陷（含 `eduforge.ps1` 在 PowerShell 5.1 下的 BOM 问题）与 Gate B–F 的 pending 清单 |

## 阅读顺序

新人建议：`26.10.14.md`（背景）→ `26.10.15_EduForge_代码级实施方案.md`（设计）→ `26.10.15_EduForge_推进计划.md`（当前进度，先读置顶的「实况」节）→ `26.10.16_EduForge_原方案审查与Agent重构建议.md`（审查结论与重构方向）→ `26.10.16_EduForge_DeepAgents落地核查与实况修正.md`（那份方向里哪些成立、本轮真正做了什么、还剩什么）。REA 相关单独看 `26.10.15-REA部署.md`。

## 与其他层的关系

- 上游事实（版本、构建、探针实测）不在本层重复，统一记在 [`../source/upstream/upstream.lock.json`](../source/upstream/upstream.lock.json)。
- 测试计数只在 [`../code/eduforge/catalog/engines/ray-optics.yaml`](../code/eduforge/catalog/engines/ray-optics.yaml) 的 `test_totals` 记一处，本层文档引用它。
- 验证证据文件在 [`../output/eduforge/reports/`](../output/eduforge/reports/README.md)。
