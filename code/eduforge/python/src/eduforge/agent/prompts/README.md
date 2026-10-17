# prompts — 智能体系统行为规范资源包

**职责**：把「模型被要求遵守什么」从代码里拿出来，按 Markdown 文件存放，便于逐字核对与 diff。本包只做一件事：读出那份行为规范文本，交给运行时拼进系统提示词。

## 内容（逐文件）

| 文件 | 行数 | 职责 | 关键符号 |
|---|---|---|---|
| `__init__.py` | 18 | 包入口：常量 `EXPERIMENT_AGENT_PROMPT` 指向本目录的 md 文件，`load_experiment_prompt()` 以 UTF-8 读出全文。模块 docstring 说明了为什么不写成 `.py` 字符串 | `EXPERIMENT_AGENT_PROMPT`, `load_experiment_prompt` |
| `experiment_agent.md` | 27 | 行为规范正文，三节：**能力边界**（只能检索/打开/探查/改参数/配视图/跑验证，**不能构建交付包、不能发布版本**——那两件事由后端在验证结论、租约、取消状态、基础版本四道闸门后完成）；**判定纪律 6 条**（先 `inspect_scene` 再改；改过内容则此前验证结论作废、必须重跑 `run_validation`；见到 `isError`/`code`/`verdict: failed` 是真实观察、不许重复同一失败动作并宣称成功；教师指定的数值是需求本身、超量程如实报告不得换值蒙混；不得伪造或修饰结果、不得改验证判据；超出能力范围明确报告）；**交付前收口**（说明版本链、场景里的真实值、验证观察到的量、未解决问题） | — |

## 与上下层的关系

- 唯一读取方：[`../deepagents_runtime.py`](../README.md) 第 21 行 `from eduforge.agent.prompts import load_experiment_prompt`，在 `build_system_prompt()` 里作为第一段。
- 拼接顺序（`deepagents_runtime.py:38`）：本目录的行为规范 → 小标题「## 实验清单纪律（来自 skills/ray-optics-customization/SKILL.md）」 → [`../../../../skills/ray-optics-customization/SKILL.md`](../../../../../skills/ray-optics-customization/README.md) 的领域规范 → 可选的「本次任务的已知事实」。两份文件分工不同：**这里管判定纪律，SKILL.md 管领域与数据结构约束**。
- 断言方：[`../../../../tests/python/test_deepagents_runtime.py`](../../../../../tests/python/README.md) 有「行为规范与 SKILL.md 必须真的进到系统提示词里」的用例——此前 SKILL.md 是零代码读取的纯文档，这条断言就是为了防它再次变成文档装饰。

## 已知的坑与纪律

- `load_skill_text()` 用 `except OSError: return ""` 兜底：**技能文件路径错或读不到时静默降级成空串**，提示词少一段而流程照跑。改 `SKILL_PATH` 或移动 skills 目录后，必须靠上面那条测试确认没静默丢内容，不能只看用例是否通过。
- 提示词与授权是两回事：这里写「不得把 60cm 换成别的值」只是**约束模型意图**；真正的拒绝发生在服务端 [`../policy.py`](../README.md)（七步顺序校验）。删掉一条纪律不会让防线消失，但也不会让防线补上——两者要一起改。
- 行为规范里提到的工具名（`inspect_scene` / `apply_scene_patch` / `configure_teaching_views` / `run_validation`）必须与 [`../tool_registry.py`](../README.md) 的模型可见工具集一致；改工具名不同步这里，模型就会照着不存在的工具名行动。
- 本目录不放密钥、不放运行期状态；提示词内容进 Git，任何改动可追溯（这是把它做成文件的理由）。
