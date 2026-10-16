# agent — 规划智能体（LangGraph 四节点 + DeepSeek）

**职责**：把「教师自然语言需求 + 模板上下文」转成一份受服务端授权的 `WorkOrder`（要改哪些对象、改成什么值、导出哪些视图），并保证任何未经模板登记的修改在服务端被拒绝。规划是"提议"，授权是"裁决"——两者分属 `planners.py`（提议）与 `policy.py`（裁决），Worker 在 planning 阶段还会**重跑一次授权**（纵深防御）。

## 内容（逐文件）

| 文件 | 行数 | 职责 | 关键符号 |
|---|---|---|---|
| `__init__.py` | 8 | 模块统一导出入口 | `build_planner`, `ExperimentToolAgent` |
| `bootstrap.py` | 30 | 组装规划器：本地与 AgentArts 共用 `build_planner()`；`default_template_of` 解析模板 id | `build_planner`, `default_template_of` |
| `graph.py` | 46 | LangGraph 四节点规划图：load_context → retrieve → draft → authorize | `build_planning_graph` |
| `model.py` | 77 | DeepSeek 模型接入封装（关闭思考/重试，优先 langchain-deepseek，回退 langchain-openai）。**仅测试引用，运行时实际走 `planners.deepseek_model`** | `create_model` |
| `planners.py` | 133 | 规划端口实现：提示词构造、JSON 剥离解析、DeepSeek HTTP 调用、`GraphPlanner`；无 key 抛 `MissingApiKey`。key 解析统一走 [`../infrastructure/settings.py`](../infrastructure/README.md) 的 `get_deepseek_api_key()`（多变量名优先级 + Windows 注册表兜底） | `MissingApiKey`, `chat_prompt`, `parse_proposal_json`, `deepseek_model`, `GraphPlanner`, `planner_from_env` |
| `policy.py` | 86 | **服务端授权防线**：七步顺序校验（模板同源、route、参数登记、量程、视图、code 任务长度、补服务端身份字段） | `authorize`, `load_template`, `Rejected` |
| `retrieval.py` | 83 | 实验依据检索器（读 `manifest.yaml`，注入受控参数/视图/教学规则）。**仅测试引用，运行时规划图用 `services.retrieve`** | `EvidenceRetriever` |
| `services.py` | 57 | 规划图节点实现：`PlanningServices` 具体类（load_context/retrieve/draft/authorize） | `PlanningServices`（类）, `ModelFn` |
| `state.py` | 48 | 规划状态机类型：`PlanningState`（TypedDict）+ `PlanningServices`（Protocol） | `PlanningState`, `PlanningServices`（协议） |
| `tool_agent.py` | 448 | **自主工具调用循环智能体**：驱动 [`../experiment_tools/`](../experiment_tools/README.md) 的 8 项原子工具完成任务，记录调用历史 Trace | `ToolTraceRecord`, `ToolAgentState`, `ExperimentToolAgent` |

> `__init__.py` 再导出 `build_planner` 与 `ExperimentToolAgent`——两个对外入口（规划器 / 工具智能体）。
| `tool_agent.py` | 449 | 自主工具调用循环智能体：基于 LangGraph StateGraph 构建显式状态机（parse_and_open -> execute_phase1 -> validate_phase1 -> [repair_phase1] -> publish_r2 -> execute_phase2 -> validate_phase2 -> [repair_phase2] -> publish_r3 -> build_package），支持 8 项原子工具执行、细粒度调用 Trace 追踪、自愈验证与连续版本演进 | `ExperimentToolAgent`, `ToolTraceRecord` |


## 四节点图（`graph.py` 的真实行为）

1. `load_context` → 经 `policy.load_template` 读模板清单；
2. `retrieve` → `services.retrieve` 注入受控参数/视图/教学规则（受控检索，不是向量检索）；
3. `draft` → `services.draft` → `planners.deepseek_model` 真正 HTTP 调 DeepSeek，产出 `EditProposal`；
4. `authorize` → `policy.authorize` 七步校验后补服务端身份字段，产出 `WorkOrder`。

## 与上下层的关系

- 被谁用：[`../entrypoints/agent_local.py`](../entrypoints/agent_local.py) 与 [`../entrypoints/agentarts.py`](../entrypoints/agentarts.py) 都经 `bootstrap.build_planner` 组装；[`../worker/run.py`](../worker/run.py) 经 `planners.planner_from_env` 选择规划器（`--planner-static-focal` 时退化为 `StablePlanner` 桩，仅用于链路验证）；[`../worker/steps.py`](../worker/steps.py) 在 planning 阶段再次调用 `policy.authorize`。
- 依赖：[`../domain/contracts.py`](../domain/contracts.py)（全部出入参模型）、[`../infrastructure/catalog.py`](../infrastructure/catalog.py)（policy 读模板）。
- 测试：[`../../../../tests/python/test_gate6_planning.py`](../../../../tests/python/test_gate6_planning.py)、[`test_planner_port.py`](../../../../tests/python/test_planner_port.py)、[`test_plan_architecture_alignment.py`](../../../../tests/python/test_plan_architecture_alignment.py)、[`test_entrypoints.py`](../../../../tests/python/test_entrypoints.py)。

## 已知的坑与纪律

- `state.py` 与 `services.py` 各有一个 `PlanningServices` 名字——前者是 Protocol、后者是具体类，靠模块路径区分（import 时别混）。
- `model.py` 与 `retrieval.py` 是早期实现，**运行时未接入**；改动规划行为请动 `planners.py` 与 `services.py`。
- 缺 DeepSeek key 时 `planner_from_env` 抛 `MissingApiKey` 拒绝启动——key 解析在 [`../infrastructure/settings.py`](../infrastructure/README.md) `get_deepseek_api_key()`（依次查 `deepseek` / `DEEPSEEK` / `DEEPSEEK_API_KEY` / `deepseek_api_key`，Windows 下带注册表兜底）。这是纪律不是缺陷：不允许静默退化为桩模型冒充规划。
- 授权是**顺序七步**校验，调整顺序会改变拒绝语义，动 `policy.authorize` 前先读 `test_gate6_planning.py`。
