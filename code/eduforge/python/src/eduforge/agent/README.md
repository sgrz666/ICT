# agent — 执行核心与授权防线（Deep Agents 主循环 + 服务端授权）

**职责**：两件事，界限分明。一是**决定**——`deepagents_runtime.py` 让真实模型自己在实验上多轮调工具、读观察、决定要不要修，`deepagents_runner.py` 把这一轮的结果收成**候选完成记录**；二是**裁决**——`policy.py` 保证任何未经模板登记的修改在服务端被拒。2026-10-16 起，`graph.py` 的四节点图降级为单轮对照基线，不再是「Agent 的全部」；同日 Gate A 起，生产链从「Planner 出清单、Worker 重放」换成「Runner 直接改持久候选」。

规划是「提议」，授权是「裁决」，提交是「候选行」：模型改的那一份场景就是被验证、被构建、被发布的那一份（`application/candidate_service.py`），`operations_from_trace` 折算清单再交 Worker 重放的老路已从生产链删除。

## 内容（逐文件）

| 文件 | 行数 | 职责 | 关键符号 |
|---|---|---|---|
| `__init__.py` | 11 | 只再导出 `build_planner`。**刻意不在包导入时拉起运行时依赖**——`agent ↔ experiment_tools` 曾因包级再导出形成循环导入，`tool_agent.py` 就是那条环上的一环 | `build_planner` |
| `deepagents_runtime.py` | 145 | Deep Agents 装配：`create_deep_agent(model, tools, backend=StateBackend(), checkpointer, system_prompt)`、把 `skills/ray-optics-customization/SKILL.md` 注入系统提示词、把消息轨迹摊成可核对的 `trace` | `build_experiment_agent`, `run_experiment_agent`, `extract_trace`, `summarise` |
| `deepagents_planner.py` | 113 | **对照基线（不再是生产路径）**：模型跑完循环后把成功的工具调用折算成 `EditProposal`。`operations_from_trace` 保留给 benchmark 与旧 graph 对照，生产链已改走 Runner | `DeepAgentPlanner`, `operations_from_trace` |
| `deepagents_runner.py` | 162 | **Gate A 起的执行端口**：模型通过受控工具直接改持久候选，跑完从**候选行与验证报告**算出 `AgentRunRecord`（candidate_id、content_hash、state_version、validation_id、terminal_state、trace_ref）。一次有效写入都没有就抛 `NO_EFFECTIVE_OPERATIONS`。`finish_run`/`open_candidate_for` 是两个端口共用的判定 | `DeepAgentRunner`, `finish_run`, `open_candidate_for` |
| `proposal_runner.py` | 102 | 把旧的 `PlannerPort`（固定提案、单轮图）**适配到同一条候选写入路径**：先过 `policy.authorize` 再逐条调 `apply_scene_patch`/`configure_teaching_views`。留着是为了对照，不给流水线留「不用模型也能绿」的出口 | `ProposalRunner`, `ProposalPort` |
| `tool_registry.py` | 65 | 模型可见工具集（6 项：search/open/inspect/patch/views/validate）+ 把领域异常转成 `isError` 观察。`build_package` / `publish_revision` **不在这里** | `AGENT_VISIBLE_TOOLS`, `BACKEND_ONLY_TOOLS`, `agent_tools` |
| `fake_model.py` | 172 | 脚本化工具调用模型：不解析自然语言、按观察推进，用于在无 key、不花钱的前提下验证循环/门禁/修复。与真模型走同一条装配路径 | `ScriptedToolModel` |
| `model.py` | 67 | DeepSeek 接入工厂。**本轮转正**（此前零运行时引用）：`base_url`/`model` 全配置化，默认 `deepseek-flash`；`planners.py` 也从这里取端点与模型名，避免两处各写一份 | `create_model`, `resolve_model_name`, `resolve_base_url`, `DEFAULT_MODEL` |
| [`prompts/`](prompts/README.md)：`__init__.py` + `experiment_agent.md` | 18 + 27 | 系统行为规范（先查再改、验过之后改内容即作废、拒绝不得换值蒙混）。提示词按文件存放便于逐字核对；分组层细节（与 SKILL.md 的分工、拼接顺序、静默降级坑）见 [`prompts/README.md`](prompts/README.md) | `load_experiment_prompt` |
| `bootstrap.py` | 30 | 组装单轮规划器：本地与 AgentArts 共用 `build_planner()`；`default_template_of` 解析模板 id | `build_planner`, `default_template_of` |
| `graph.py` | 46 | LangGraph 四节点图（load_context → retrieve → draft → authorize），线性、无环、不调工具。**现在是 `--planner model` 的单轮基线**，不再是默认智能体 | `build_planning_graph` |
| `planners.py` | 137 | 单轮端口实现：提示词构造、JSON 剥离解析、DeepSeek HTTP 调用、`GraphPlanner`；无 key 抛 `MissingApiKey`。端点/模型名改由 `model.py` 供给 | `MissingApiKey`, `api_key`, `chat_prompt`, `parse_proposal_json`, `GraphPlanner`, `planner_from_env`, `MODEL_URL`, `MODEL_NAME` |
| `policy.py` | 96 | **服务端授权防线**：七步顺序校验；本轮抽出 `authorize_operation`，让**工具层用同一套判据**（此前 8 项工具完全不经过策略层） | `authorize`, `authorize_operation`, `load_template`, `Rejected` |
| `retrieval.py` | 83 | 实验依据检索器（读 `manifest.yaml`）。**仅测试引用**，运行时规划图用 `services.retrieve` | `EvidenceRetriever` |
| `services.py` | 57 | 规划图节点实现：`PlanningServices` 具体类 | `PlanningServices`（类）, `ModelFn` |
| `state.py` | 48 | 规划状态机类型：`PlanningState`（TypedDict）+ `PlanningServices`（Protocol） | `PlanningState`, `PlanningServices`（协议） |

> 已删除：`tool_agent.py`（448 行，规则式「工具循环」）。它 docstring 写的「LangGraph 成熟工具调用循环与自愈修复」不成立——意图解析是四条正则（只认 `调整为|设为|为`）、`model_fn` 参数从未被读、分发是 8 分支 `if/elif`、修复靠**伪造**一条 `expected=50.0` 的验证记录再硬编码回填。它的正则原样保留在 [`tests/python/_regex_baseline.py`](../../../../tests/python/_regex_baseline.py) 作对照组。


## 两条执行路径（都在跑，但证据等级与角色不同）

1. **Deep Agents 自主循环 → `DeepAgentRunner`（生产，`--planner deep`）**：`run_experiment_agent()` 让模型自己发起 `open_experiment`/`inspect_scene`/`apply_scene_patch`/`configure_teaching_views`/`run_validation` 的多轮往返；每次成功的写入**直接落在 `experiment_candidates` 那一行**，跑完由 `finish_run()` 从候选行 + `validation_reports` 算出 `AgentRunRecord`。Worker 之后只消费这份候选。
2. **清单 → `ProposalRunner`（对照基线）**：`--planner model` 的四节点单轮图、`--planner-static-focal` 的固定提案产出 `EditProposal`，经 `authorize` 后**同样调本仓库那套受控工具**写候选。以前这里靠 `operations_from_trace` 把模型的成果折算成清单、由 Worker 在基线上重放第二遍——那条路径已从生产链删除，`operations_from_trace` 只留在 `deepagents_planner.py` 供 benchmark `agent_graph` 档位对照。

两条路径产出同一种记录，差别只在**决策来源**（模型自主 vs 代码给定）。这也是「换措辞还能不能做对」这个问题只能由 `test_deepagents_real_model.py` 回答、不能由脚本模型回答的原因。

## 与上下层的关系

- 被谁用：[`../worker/run.py`](../worker/run.py) 的 `select_planner()` 按 `--planner model|deep|static` 选择执行端口（`deep` 构造 `DeepAgentRunner`，`model`/`static` 产出提案由 `ProposalRunner` 适配）；[`../worker/steps.py`](../worker/steps.py) 的 `Chain.planning` 调用端口的 `run()`。[`../entrypoints/agent_local.py`](../entrypoints/agent_local.py) 与 [`../entrypoints/agentarts.py`](../entrypoints/agentarts.py) 仍经 `bootstrap.build_planner` 组装单轮图（它们只出 `WorkOrder`，不是执行入口；AgentArts 侧接入 Runner 属 Gate F）。
- 依赖：[`../domain/contracts.py`](../domain/contracts.py)（全部出入参模型）、[`../infrastructure/catalog.py`](../infrastructure/catalog.py)（policy 读模板）、[`../experiment_tools/`](../experiment_tools/README.md)（deep 路径的真实工具面）、`deepagents` + `langchain-openai`（本轮新增依赖）。
- 测试：[`../../../../tests/python/test_gate6_planning.py`](../../../../tests/python/test_gate6_planning.py)（单轮与授权）、[`test_planner_port.py`](../../../../tests/python/test_planner_port.py)、[`test_plan_architecture_alignment.py`](../../../../tests/python/test_plan_architecture_alignment.py)、[`test_entrypoints.py`](../../../../tests/python/test_entrypoints.py)、[`test_deepagents_runtime.py`](../../../../tests/python/test_deepagents_runtime.py)（循环与门禁，假模型）、[`test_deepagents_real_model.py`](../../../../tests/python/test_deepagents_real_model.py)（真模型，无 key 时 SKIPPED）、[`test_gate_a_candidate.py`](../../../../tests/python/test_gate_a_candidate.py)（Runner → 候选 → 发布哈希一致，含纯视图与 CAS 负向用例）、[`test_single_publish_path.py`](../../../../tests/python/test_single_publish_path.py)（结构守卫）。

## 已知的坑与纪律

- `state.py` 与 `services.py` 各有一个 `PlanningServices` 名字——前者是 Protocol、后者是具体类，靠模块路径区分（import 时别混）。
- `retrieval.py` 仍是早期实现、运行时未接入；`model.py` 本轮已转正（被 `planners.py` 与 `deepagents_planner.py` 共同使用），别再当成死代码删掉。
- **不要在 `agent/__init__.py` 里再导出会 import `experiment_tools` 的模块**：`experiment_tools/service.py` 反向 import `agent.policy`，包级再导出会成环（这轮就靠这条才把 `deepagents_runtime` 导进来）。
- `deepagents` 的 `FilesystemMiddleware` / `SubAgentMiddleware` 是**必需中间件**，模型总会看到 `ls`/`read_file`/`write_file`/`execute`/`task`；`_ToolExclusionMiddleware` 的文档明说排除「不是安全边界」。本仓库的安全来自选 `StateBackend`（非沙箱 backend，`execute` 直接返回错误、文件工具只作用于会话状态），不来自工具屏蔽。
- `langsmith` 随 `deepagents` 一起装进来了。若环境存在 `LANGSMITH_API_KEY` / `LANGCHAIN_TRACING_V2`，提示词与轨迹会被静默上传——本地优先的仓库要在启动前显式 `LANGSMITH_TRACING=false`。
- 缺 DeepSeek key 时 `planner_from_env` / `--planner deep` 抛 `MissingApiKey` 拒绝启动——key 解析在 [`../infrastructure/settings.py`](../infrastructure/README.md) `get_deepseek_api_key()`（依次查 `deepseek` / `DEEPSEEK` / `DEEPSEEK_API_KEY` / `deepseek_api_key`，Windows 下带注册表兜底）。这是纪律不是缺陷：不允许静默退化为桩模型冒充规划。开发机上实测：注册表里既无 `deepseek` 也无可用 DeepSeek key（`LLM_API_KEY` 被服务端判 401），所以默认走 SKIPPED 而不是假通过。
- 授权是**顺序七步**校验，调整顺序会改变拒绝语义，动 `policy.authorize` 前先读 `test_gate6_planning.py`；`authorize_operation` 是它抽出的逐条判据，工具层与这里必须同源。
