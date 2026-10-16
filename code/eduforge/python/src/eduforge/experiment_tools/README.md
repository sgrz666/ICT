# experiment_tools — 实验引擎工具服务层

## 1. 职责

将底层仿真引擎（Engine Host）、模板目录（`catalog/templates/`）与数据库存储编排为 8 项标准原子工具，
作为成熟 Agent 执行框架（LangGraph、Deep Agents、MCP Client）的操作端口，
替代脆弱的单轮全量 JSON 提案直接生成，实现自主闭环的物理实验修改、验证与交付。

## 2. 内容（8 项工具与文件清单）

### 8 项原子工具

1. `search_experiments`: 检索实验与模板，支持关键词过滤与参数说明透出；
2. `open_experiment`: 载入已有实验或由模板初始化新工作区会话；
3. `inspect_scene`: 探查场景物理元件、实时物距焦距与薄透镜高斯光学理论指标；
4. `apply_scene_patch`: 增量应用物理参数修改并驱动上游执行真实光线追踪仿真；
5. `configure_teaching_views`: 配置教学视图与实验测量记录表格，自动计算填报数据行；
6. `run_validation`: 运行独立参考公式核验、边界条件检查与光线汇聚度验证；
7. `build_package`: 组装候选版本资产（`native.json`、`teaching_views.json`）与可离线交互运行的网页包；
8. `publish_revision`: 原子提交新版本并推进 `experiments.head_revision_id`，支持后续连续编辑。

### 模块文件清单

- [`__init__.py`](__init__.py): 模块入口导出；
- [`contracts.py`](contracts.py): 8 项工具的 Pydantic 输入输出契约模型；
- [`service.py`](service.py): `ExperimentToolService` 核心实现，支持数据库会话与内存预览双模态；
- [`langchain_tools.py`](langchain_tools.py): LangChain `StructuredTool` 标准封装函数 `get_experiment_tools`；
- [`mcp_server.py`](mcp_server.py): Model Context Protocol (MCP) JSON-RPC 服务实现。

## 3. 与上下层的关系

- **上层使用者**:
  - [`eduforge.agent.tool_agent`](../agent/tool_agent.py): 自主工具调用循环智能体；
  - 外部 MCP 客户端（如 Claude Desktop、Cursor、Deep Agents SDK）；
  - Web API 与自动化验收测试。
- **下层协作者**:
  - [`eduforge.infrastructure.clients.engine_client`](../infrastructure/clients/engine_client.py): HTTP 驱动 Node.js Engine Host 仿真与离线包打包；
  - [`eduforge.validation.policies`](../validation/policies.py): 物理规则与双轨光学校验；
  - [`eduforge.infrastructure.db.repositories`](../infrastructure/db/repositories.py): 数据库版本表与产物记录。

## 4. 已知的坑与纪律

1. **版本连续编辑链**: 第二次修改（如连续将物距从 30cm 改为 20cm）必须以第一次发布的版本作为 `base_revision`，不得死锁或使用初始种子版本覆盖；
2. **教学视图数据累加**: 测量记录表在连续实验过程中应当保留前次测量记录并追加新记录，不可直接覆盖清空；
3. **真实光路验证**: 验证必须核验场景内实际元件参数与成像光斑物理二阶矩，杜绝仅做静态文本比对。
