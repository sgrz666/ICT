# ray-optics-customization — Ray Optics 定制技能（已启用，唯一被代码读取的技能）

**职责**：向负责**代码级**实验定制的智能体说明 Ray Optics 引擎的架构约束、数据边界与交付标准。它是「领域纪律」，与 [`../../python/src/eduforge/agent/prompts/`](../../python/src/eduforge/agent/prompts/README.md) 的「判定纪律」分属两份文件、各司其职。

## 内容（逐文件）

| 文件 | 行数 | 结构 |
|---|---|---|
| `SKILL.md` | 27 | frontmatter（`name: ray-optics-customization`、`description`）+ 三节：**1 交付文件边界**（每次定制只允许交付 `src/lesson.ts`（教学步骤/引导文本/观察记录表）与 `src/controls.ts`（受控滑块、开关、回调），其余修改不予采纳）；**2 仿真数据与对象绑定纪律**（对象身份必须绑 `name`，禁止 `objs[0]` 这类下标寻址；禁止注入未登记 key 如 `eduforge_id`，否则上游加载器置 `scene.error` 拒绝渲染；单位换算严格按模板 `manifest.yaml` 的 `units_per_unit`，凸透镜为 10 像素 = 1 cm）；**3 验证与发布**（改动注入全新沙箱重跑无头仿真与公式核验；焦距必须 > 0；像距物距遵循高斯公式 1/u + 1/v = 1/f；严禁篡改验证用例或门禁规则） |

本目录只含这一份 `SKILL.md`，无附件、无脚本、无资源文件。

## 与上下层的关系

- **读取方（三条技能里唯一有代码读取路径的）**：[`../../python/src/eduforge/agent/deepagents_runtime.py`](../../python/src/eduforge/agent/README.md) 的 `SKILL_PATH`（第 27 行，按 `parents[4]` 相对定位到本仓库 `skills/ray-optics-customization/SKILL.md`）与 `load_skill_text()`，由 `build_system_prompt()` 拼在行为规范之后，小标题显式注明来源路径。
- 断言方：[`../../tests/python/test_deepagents_runtime.py`](../../tests/python/README.md) 断言 `SKILL_PATH.is_file()` 且领域纪律确实进了系统提示词。
- 上游依据：模板事实来自 [`../../catalog/templates/optics/convex-lens/manifest.yaml`](../../catalog/templates/optics/convex-lens/README.md)（`units_per_unit`、量程、允许的路由），引擎能力来自 [`../../catalog/engines/ray-optics.yaml`](../../catalog/engines/README.md)。
- 落地方：`src/lesson.ts` / `src/controls.ts` 这两份交付物的执行者是 [`../../services/engine-host/src/adapters/`](../../services/engine-host/src/adapters/README.md) 与代码定制沙箱侧。

## 已知的坑与纪律

- **相对定位靠层数**：`SKILL_PATH` 用 `parents[4]` 从 `deepagents_runtime.py` 往上爬。移动本目录、改名、或调整 `python/src/eduforge/agent/` 的层级，都会让它指空——而 `load_skill_text()` 捕获 `OSError` 后**返回空串**，表现为提示词少一段而流程照跑。改动后必须跑上面那条断言确认。
- 这份文件此前**零代码读取**（纯文档状态），2026-10-16 才接进 `build_system_prompt()`。旧 README 曾声称由 `coding/deep_agent.py` 与 `agent/retrieval.py` 注入沙箱，那条路径在代码里并不存在；`coding/deep_agent.py` 至今仍未接入。引用消费方时以 `deepagents_runtime.py` 为准。
- 与科学验证参考必须物理自洽：改本文件的公式或判据，要和 [`../../python/src/eduforge/validation/scientific/`](../../python/src/eduforge/validation/README.md) 的独立参考式同轮核对，不能单侧改。
- 不放密钥、不放运行期状态、不放宽许交付的文件清单——交付边界收紧是本仓库的默认方向。
