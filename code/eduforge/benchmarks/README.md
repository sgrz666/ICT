# benchmarks — 12 题基准评测（数据集 + 运行器 + 档位）

**职责**：用一个 12 题的小型评测集度量「教师需求 → 受控修改」链路的质量：三类任务（改参 / 视图控制 / 越界拒绝）各 4 题，同时覆盖**接受与拒绝**两条路径。三件套各司其职：题集（`tasks.jsonl`）、档位（`profiles.yaml`）、运行器（`runner.py`）。

## 内容（逐文件）

| 文件 | 行数 | 职责 | 关键内容 |
|---|---|---|---|
| `tasks.jsonl` | 12 | 评测题集，每行一题 JSON | `id` / `category` / `prompt` / `template_id` / `expected_action` / `route` / `check`（op 与目标字段） |
| `runner.py` | 354 | 运行器：按档位逐题走**规划端口**（`screening` 调规则模拟器 `mock_semantic_draft`；`deepseek_direct` 直连 HTTP；`agent_graph` 调 `build_planner`），接受侧只核对**提案 op 的字段**，输出 JSON 报告 + stdout 摘要。**注意**：它不建实验、不提交任务、不轮询、不下载产物——「逐题走真实链路核对产物」这句旧描述与代码不符，已于 2026-10-16 按实况纠正 | `main()` |
| `profiles.yaml` | 21 | 评测档位（模型提供方、超时、重复次数） | 三档（见下） |

## 三类题型（各 4 题）

| category | 数量 | expected_action | 例子 |
|---|---|---|---|
| `parameter_modification` | 4 | accept | "将焦距改成 15 厘米" → `set_parameter` `lens_1` `focal_length_cm=15` |
| `view_control` | 4 | accept | 视图显示/隐藏类指令 |
| `out_of_scope_rejection` | 4 | reject | 越界请求必须被拒（安全侧的负样本） |

## 三个档位（`profiles.yaml`）

| 档位 | 提供方 | 依赖 | 状态 |
|---|---|---|---|
| `screening` | `mock_policy`（离线模拟器） | 无 key | **已实测：12/12 通过** |
| `deepseek_direct` | 真实 DeepSeek 无约束基线 | `DEEPSEEK_API_KEY` | pending（缺 key，未实测） |
| `agent_graph` | LangGraph 规划图 + 授权链闭环 | `DEEPSEEK_API_KEY` | pending（缺 key，未实测） |

## 跑法

```bash
cd code/eduforge && uv run python benchmarks/runner.py            # 直跑
../scripts/eduforge.ps1 benchmark -Profile screening              # 封装入口（工作区根）
```

## 与上下层的关系

- 消费：catalog 模板（[`../catalog/templates/`](../catalog/templates/README.md)）与 `agent/` 的规划端口（`policy.authorize`、`build_planner`、DeepSeek HTTP）；**不经过 API/Worker/Engine Host**；由 [`../../../scripts/README.md`](../../../scripts/README.md) 的 `benchmark` 命令封装。
- 测试：[`../tests/python/test_benchmarks.py`](../tests/python/README.md)。
- 报告产物：运行器输出的 JSON 报告（脚手架在 `output/eduforge/reports/` 侧，见 [`../../../output/eduforge/`](../../../output/eduforge/README.md)）。

## 已知的坑与纪律

- **只有 `screening` 是实测绿**；两个需 key 的档位是能力存在、未闭环——报告里不得写成"已通过"。
- **12/12 不代表「教师拿到了对的实验」**：接受侧判据只核对提案里的 op 字段（`runner.py:129-132`），从不核对引擎观测、交付字节或下载文件；`runner.py:205-209` 甚至把模型返回解析崩溃记为 `model_refused` 从而判通过。把评测对象从「提案是否合法」升级到「交付物是否正确」是未完成项。
- `profiles.yaml` 写了 `repeats: 3`，但 `runner.py` 从不读它——**没有重复运行**，所以本套报告目前无法支撑「成功率」这类统计口径。
- 报告输出用相对路径 `output/eduforge/reports`，从 `code/eduforge` 直跑会在 `code/eduforge/output/` 落一份副本（仓库里已存在那份重复），跑之前先确认工作目录。
- 运行器要求本地服务已起（api / worker / engine-host）——先 `scripts/eduforge.ps1 up` 或按 `doctor` 提示准备环境。
- 改题集要同步三类配比与 `expected_action` 的接受/拒绝平衡——只加正样本会劣化评测信号。
- Deep Agents 这条新路径**尚未纳入基准档位**（本轮只加了 `test_deepagents_real_model.py` 的单任务实测），新增档位前先想清楚判据落在哪一层。
