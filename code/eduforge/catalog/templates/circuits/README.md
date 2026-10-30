# circuits — 电路学科模板分组

**职责**：`templates/` 下的电路分组层。当前 `ohms-law/` 走 **LabKit 文件级链路**（单文件 HTML，MNA 求解），不是 EduForge 主链路；CircuitJS1 只作为外部交叉验证证据，不进入运行时。

## 内容

| 条目 | 类型 | 状态 |
|---|---|---|
| [`ohms-law/`](ohms-law/README.md) | 模板实例目录 | 直流电路：欧姆定律与串并联（`template_id: circuits.ohms_law`，`engine_id: circuit_mna`）。`manifest.yaml` + `recipes.json` + `native.json` + `lesson.md` + `render/` 齐全；三配方 3/3 pass（MNA 与解析式偏差 0，CircuitJS1 交叉验证 8/8，L3 零网络），产物约 27 KB。**EduForge 主链路未接** |

本目录自身不放数据文件。

## 与上下层的关系

- 上一级：[`../README.md`](../README.md) 的三件套模式；`ohms-law/` 齐备，并额外带 `recipes.json` 与 `render/`。
- 引擎侧：[`../../engines/`](../../engines/README.md) 的 `circuitjs.yaml` 仍是 EduForge 主链路的引擎描述；LabKit 运行时用 MNA，CircuitJS1 证据在 [`../../../../source/library/circuit-lab-evidence.json`](../../../../../source/library/circuit-lab-evidence.json)。
- 参考式桩：[`../../../python/src/eduforge/validation/scientific/`](../../../python/src/eduforge/validation/README.md) 的 `circuits.py`（欧姆定律，未接入运行时）。
- 领域规范：[`../../../skills/circuit-customization/SKILL.md`](../../../skills/circuit-customization/README.md)（注意技能目录名是单数 `circuit-`）。

## 已知的坑与纪律

- **目录在位 ≠ 学科可用**：EduForge 主链路仍未接通 CircuitJS1；LabKit 是另一条文件级链路，不能拿来证明主链路已通。
- **单文件与 CircuitJS1 不可兼得**：GWT 站点 15 MB、需同源加载，无法可靠压成单 HTML；因此 LabKit 用 MNA，CircuitJS1 只做交叉验证。若必须交付 CircuitJS1 UI，应走「离线包 + 同源静态服务」，并处理 GPL-2.0 义务。
- 本模板只覆盖线性 DC 电阻网络；RC/交流/非线性元件不在本轮范围。
- 电路参数（Ω / V）与电表读数视图是上游元件语义，与光学的「对象 name 绑定 + 场景像素」不同构；接入主链路时不要复用光学适配器的判据。
- 技能目录名单数、本目录名复数（`circuits`）不一致是历史命名差异，引用路径时以磁盘目录名为准。
