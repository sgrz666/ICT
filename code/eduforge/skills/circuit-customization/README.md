# circuit-customization — 电路定制技能（保留位，零代码读取）

**职责**：为第 7～8 周切片 9 接入 CircuitJS1 预留的领域规范占位文件。**当前没有任何代码读取它**。

## 内容（逐文件）

| 文件 | 行数 | 结构 |
|---|---|---|
| `SKILL.md` | 13 | frontmatter（`name: circuit-customization`，description 标注「第 7～8 周预留」）+ 一节**核心约定**：实验体系采用 SI 单位制（V、A、Ω）；交付文件同为 `src/lesson.ts` 与 `src/controls.ts`；以基尔霍夫定律与欧姆定律作为门禁物理验证基准 |

本目录只含这一份 `SKILL.md`。

## 与上下层的关系

- 配套模板：[`../../catalog/templates/circuits/ohms-law/`](../../catalog/templates/circuits/ohms-law/README.md)——现在 `status: verified`，走 **LabKit 文件级链路**（自包含 MNA 求解器，欧姆/串联/并联三配方 3/3 通过 L1/L2/L3，与解析式偏差 0，另有 CircuitJS1 外部交叉验证，产物约 27 KB）。**模板可用 ≠ 本技能生效**：`SKILL_PATH` 仍只指向 `ray-optics-customization/SKILL.md`，这份规范依然零代码读取。
- 配套引擎描述：[`../../catalog/engines/`](../../catalog/engines/README.md) 里的 `circuitjs.yaml` 仍是 `status: pending_slice_9`（Java-GWT 工具链与 Docker 前置未就绪的理由记在 `source/upstream/upstream.lock.json`），那是 EduForge 主链路的描述；模板运行时用的 `engine_id: circuit_mna` 在 `catalog/engines/` 下**还没有对应 yaml**，`EngineId` 里也没有它。
- 参考式桩：[`../../python/src/eduforge/validation/scientific/`](../../python/src/eduforge/validation/README.md) 的 `circuits.py`（欧姆定律，未接入运行时）。
- 分组层说明：[`../README.md`](../README.md)。

## 已知的坑与纪律

- **目录名是单数 `circuit-customization`**，而它服务的模板学科目录是复数 `circuits/`，同级的力学技能目录又是复数 `mechanics-`。frontmatter 的 `name` 与磁盘目录名一致（`circuit-customization`），改名或建软链会让将来按名解析 `SKILL_PATH` 的逻辑踩空——引用前以磁盘实测为准。
- **文件在位 ≠ 已生效**：没有注入路径，也没有测试断言它。不得写成「电路定制已受约束」。
- 电路的对象绑定语义（元件 + 电表读数）与光学的 `name` 绑定不同构：这份规范目前只写了单位制与门禁基准，接入时要补齐「元件身份怎么绑」这一节，并重新评估 `src/lesson.ts` / `src/controls.ts` 两文件边界对 CircuitJS 是否成立。
- 与 [`../../python/src/eduforge/validation/scientific/`](../../python/src/eduforge/validation/README.md) 的参考式必须同轮核对，不单侧改判据。
