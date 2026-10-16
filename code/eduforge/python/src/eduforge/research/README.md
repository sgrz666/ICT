# research — 逆向研究（REA 运行器，开发期工具）

**职责**：把 REA（Reverse Engineer Anything）逆向分析能力封装为可编程运行器：对本机仿真引擎样本做静态结构分析，产出 Evidence JSON，供架构决策与引擎评估使用。**这是开发期工具，不进入教师在线业务链路**，当前仅测试可达。

## 内容（逐文件）

| 文件 | 行数 | 职责 | 关键符号 |
|---|---|---|---|
| `rea_runner.py` | 85 | 调用本机 REA CLI 对指定样本目录做分析，收集并落盘 Evidence JSON | `REARunner` |

## 与上下层的关系

- 配套资产在仓库其它层：REA 工具本体是根目录 npm 包 `rea-agents@6.5.0`（见根 [`package.json`](../../../../../../package.json)）；输入样本在 [`../../../../../../input/rea-smoke-test/`](../../../../../../input/rea-smoke-test/README.md)；分析产物在 [`../../../../../../output/rea-smoke-test.json`](../../../../../../output/README.md)。
- 被谁用：**无运行时消费方**（刻意如此）——它是"研究仪器"，可以由人/脚本手动调用，测试见 [`../../../../tests/python/test_plan_architecture_alignment.py`](../../../../tests/python/test_plan_architecture_alignment.py)。
- 部署记录：根目录计划文档 [`../../../../../../plan/26.10.15-REA部署.md`](../../../../../../plan/26.10.15-REA部署.md)。

## 已知的坑与纪律

- REA 的外部引擎（Hopper/Ghidra/IDA/JADX/JEB）本机**未安装**，`rea doctor` 报告为缺——分析能力当前受限于纯静态部分，别把"跑通"当"全能力"。
- 本模块依赖本机 REA CLI 存在；在 CI/他人机器上默认不可用，因此不进主链路是正确的设计，不要"顺手"把它接进 Worker。
- 产物（Evidence JSON）只作参考证据，不参与发布门禁判定——发布门禁唯一在 [`../validation/`](../validation/README.md)。
