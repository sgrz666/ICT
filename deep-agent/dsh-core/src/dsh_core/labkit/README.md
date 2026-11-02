# labkit/ — 物理、电路与光学实验原生工具桥接子系统

**职责**：对应 [`../../../../local-tools/dsh-labkit/`](../../../../local-tools/dsh-labkit/README.md) 与 [`../../../../../code/eduforge/tools/labkit/`](../../../../../code/eduforge/tools/labkit/README.md)，将六个 `experiment_*` 物理实验能力（`experiment_recipes`、`experiment_validate`、`experiment_simulate`、`experiment_render`、`experiment_verify`、`experiment_build`）原生集成至 `dsh-core` 中，覆盖抛体运动、单摆运动、欧姆定律直流电路与凸透镜几何光学共 9 个配方，支持一键产出 5 件套离线教学交付包。

## 内容

| 文件 | 状态 | 说明 |
|---|---|---|
| [`__init__.py`](__init__.py) | 已实测 | 导出 `LabKitBridge`、`RECIPES_CATALOG`、`LABKIT_SYSTEM_PROMPT_SECTION` |
| [`bridge.py`](bridge.py) | 已实测 | L1 参数边界与解析式计算、L2 仿真对账、单文件 CSP HTML 渲染、L3 离线校验及五件套（`.html` / `.evidence.json` / `.teacher.md` / `.student.md` / `.package.json`）生成 |

## 与上下层的关系

- **上层消费者**：上游 `tools`（自动注册 6 个 `experiment_*` 工具）与 `loop` 调度器（在 `physics-lab` 预设与 `standard` 预设中挂载）。
- **对标上游实现**：[`../../../../local-tools/dsh-labkit/index.mjs`](../../../../local-tools/dsh-labkit/index.mjs)。

## 已知的坑与纪律

1. **领域错误不抛未捕获异常**：当模型传入越界参数或未知 `recipe_id` 时，`experiment_validate`/`experiment_build` 返回结构化 `{ok: False, stage, code, summary, hints}`，引导模型根据 `hints` 自主修正参数重试。
2. **`design_hash` 确定性**：`design_hash` 严格由排序后的 `design` JSON 计算 SHA-256 前 16 位十六进制，不含时间戳，确保相同实验设计的构建产物可复核。
