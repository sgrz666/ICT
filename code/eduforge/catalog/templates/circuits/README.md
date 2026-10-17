# circuits — 电路学科模板分组（保留位，引擎未接通）

**职责**：`templates/` 下的电路分组层，为第 7～8 周切片 9 接入 CircuitJS1 预留目录结构。当前只有一个模板声明，**没有任何可跑链路**。

## 内容

| 条目 | 类型 | 状态 |
|---|---|---|
| [`ohms-law/`](ohms-law/README.md) | 模板实例目录 | 欧姆定律与电阻伏安特性（`template_id: circuits.ohms_law`，`engine_id: circuitjs`，`status: pending_slice_9`）。只含 `manifest.yaml` 34 行（电阻 1–1000 Ω、电压 1–24 V 绑定 `power_source_1`、视图 `voltmeter` / `ammeter`）；**没有 `native.json`**，也没有 `lesson.md` |

本目录自身不放数据文件。

## 与上下层的关系

- 上一级：[`../README.md`](../README.md) 的三件套模式；本目录同样只有 manifest。
- 引擎侧：[`../../engines/`](../../engines/README.md) 的 `circuitjs.yaml`（deferred）；上游工具链（Java-GWT + Docker 前置）未就绪的理由记在 [`../../../../source/upstream/upstream.lock.json`](../../../../../source/upstream/README.md)。
- 参考式桩：[`../../../python/src/eduforge/validation/scientific/`](../../../python/src/eduforge/validation/README.md) 的 `circuits.py`（欧姆定律，未接入运行时）。
- 领域规范：[`../../../skills/circuit-customization/SKILL.md`](../../../skills/circuit-customization/README.md)（注意技能目录名是单数 `circuit-`）。

## 已知的坑与纪律

- **目录在位 ≠ 学科可用**，与 mechanics 同一条纪律：pending 不许写成已完成。
- 这是首个声明**两个受控参数**的模板，将来授权链要覆盖「多参数组合改参」——切片 9 设计时的已知待办，不是现在的缺陷。
- 电路参数（Ω / V）与电表读数视图是上游元件语义，与光学的「对象 name 绑定 + 场景像素」不同构；接入时不要复用光学适配器里的判据。
- 技能目录名单数、本目录名复数（`circuits`）不一致是历史命名差异，引用路径时别猜——以磁盘目录名为准。
