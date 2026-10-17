# circuit-customization — 电路定制技能（保留位，零代码读取）

**职责**：为第 7～8 周切片 9 接入 CircuitJS1 预留的领域规范占位文件。**当前没有任何代码读取它**。

## 内容（逐文件）

| 文件 | 行数 | 结构 |
|---|---|---|
| `SKILL.md` | 13 | frontmatter（`name: circuit-customization`，description 标注「第 7～8 周预留」）+ 一节**核心约定**：实验体系采用 SI 单位制（V、A、Ω）；交付文件同为 `src/lesson.ts` 与 `src/controls.ts`；以基尔霍夫定律与欧姆定律作为门禁物理验证基准 |

本目录只含这一份 `SKILL.md`。

## 与上下层的关系

- 配套模板：[`../../catalog/templates/circuits/ohms-law/`](../../catalog/templates/circuits/ohms-law/README.md)（`status: pending_slice_9`，只有 manifest；两个受控参数电阻/电压，视图 `voltmeter` / `ammeter`）。
- 配套引擎描述：[`../../catalog/engines/`](../../catalog/engines/README.md) 的 `circuitjs.yaml`（deferred；Java-GWT 工具链与 Docker 前置未就绪的理由记在 `source/upstream/upstream.lock.json`）。
- 参考式桩：[`../../python/src/eduforge/validation/scientific/`](../../python/src/eduforge/validation/README.md) 的 `circuits.py`（欧姆定律，未接入运行时）。
- 分组层说明：[`../README.md`](../README.md)。

## 已知的坑与纪律

- **目录名是单数 `circuit-customization`**，而它服务的模板学科目录是复数 `circuits/`，同级的力学技能目录又是复数 `mechanics-`。frontmatter 的 `name` 与磁盘目录名一致（`circuit-customization`），改名或建软链会让将来按名解析 `SKILL_PATH` 的逻辑踩空——引用前以磁盘实测为准。
- **文件在位 ≠ 已生效**：没有注入路径，也没有测试断言它。不得写成「电路定制已受约束」。
- 电路的对象绑定语义（元件 + 电表读数）与光学的 `name` 绑定不同构：这份规范目前只写了单位制与门禁基准，接入时要补齐「元件身份怎么绑」这一节，并重新评估 `src/lesson.ts` / `src/controls.ts` 两文件边界对 CircuitJS 是否成立。
- 与 [`../../python/src/eduforge/validation/scientific/`](../../python/src/eduforge/validation/README.md) 的参考式必须同轮核对，不单侧改判据。
