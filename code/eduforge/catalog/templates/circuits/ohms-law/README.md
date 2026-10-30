# ohms-law — 直流电路：欧姆定律与串并联（LabKit 路径）

**职责**：把「欧姆定律」「串联」「并联」三个配方做成可被 Agent 选择、可物理对账、可渲染成**单文件 HTML** 的模板。走 LabKit 文件级链路，不经过 engine-host 适配器，也不在教师端模板库中出现。

## 1. 状态

| 项 | 实测 |
|---|---|
| L1 参数校验 | 三个配方默认参数全过 |
| L2 物理对账 | 3/3 pass；MNA 与解析式在双精度下偏差 0（容差 1e-6 仅用于显示舍入） |
| CircuitJS1 交叉验证 | 8/8 pass；同一组 V/R 下 MNA 与 CircuitJS1（2026-10-19 证据）读数一致（相对误差 ≤1e-6） |
| L3 单文件实测 | 3/3 pass；零网络、canvas 1.96–3.22%、改参有效、console error 0、读数误差 0 |
| 产物体积 | 26.5–26.8 KB（无外部引擎，MNA 内核约 5 KB） |
| 复现命令 | `node code/eduforge/tools/labkit/selftest.mjs`（7 个配方全跑，含本模板 3 个） |
| 教师端 / engine-host | **未接入** |

## 2. 文件

| 文件 | 作用 |
|---|---|
| [`manifest.yaml`](manifest.yaml) | catalog 兼容扁平清单：`template_id: circuits.ohms_law`、`engine_id: circuit_mna`、三个 control（voltage_v / resistance_ohm / r2_ohm）、`status: verified` |
| [`recipes.json`](recipes.json) | 三个配方、量程、验收容差、渲染配置 |
| [`native.json`](native.json) | 场景骨架：电压源 5 V + R1 100 Ω + R2 220 Ω |
| [`lesson.md`](lesson.md) | 三个配方的实验目的 / 步骤 / 观察要点 / 误区 |
| [`render/`](render/README.md) | 单文件骨架、运行时、样式 |

## 3. 配方

| id | 默认参数 | 验收指标 | 教学意图 |
|---|---|---|---|
| `ohms-law` | V=5 V，R=100 Ω | I、U | I=U/R；电压不变时电流与电阻成反比 |
| `series` | V=5 V，R1=100 Ω，R2=220 Ω | I、U1、U2 | 串联电流处处相同，电压按阻值分配 |
| `parallel` | V=5 V，R1=100 Ω，R2=220 Ω | I1、I2、I、Req | 并联电压相同，电流按电阻反比分配，1/Req=1/R1+1/R2 |

决策量程：`U 1–12 V`、`R 10–1000 Ω`、总电流 ≤2 A。

## 4. 为什么是 MNA，不是 CircuitJS1

这是本轮最重要的取舍，必须写清楚：

- 用户要求**单文件 HTML**。CircuitJS1 的 GWT 产物是 15 MB 多文件站点（`site/`），运行时需要同源加载与动态 GWT 分片，**无法可靠地压成一个 HTML**；强行内联会得到一个脆弱且巨大的页面。
- 因此本模板的运行时用**改进节点法（MNA）**求解线性 DC 网络：约 100 行，精确解，单文件 27 KB，GPL-free。
- 为了不丢掉「上游引擎」这层证据，L2 读取 `source/library/circuit-lab-evidence.json`（CircuitJS1 在 2026-10-19 的实测值），对欧姆定律 3 个阻值、串联 3 个量、并联 2 个量做交叉验证：**MNA 与 CircuitJS1 读数在双精度下一致**。
- 若以后必须交付 CircuitJS1 的完整 UI，应走「离线包 + 同源静态服务」形态，而不是单文件；GPL-2.0 分发义务也会被触发。

## 5. 关系

- 核心库：[`../../../../tools/labkit/circuit/`](../../../../tools/labkit/circuit/README.md)（core / check / simulate / render）。
- dsh 工具：`experiment_recipes` 无参调用会列出本模板；`experiment_build` 传 `template_id: circuits.ohms_law`。
- 上游证据：[`../../../../../../source/library/circuit-lab-evidence.json`](../../../../../../source/library/circuit-lab-evidence.json)（CircuitJS1，4 个场景、4/0 pass）。
- 上级分组：[`../README.md`](../README.md)；模式说明：[`../../README.md`](../../README.md)。

## 6. 已知的坑与纪律

1. **只覆盖线性 DC 电阻网络**；RC 充放电、交流、二极管等非线性元件不在本轮范围。
2. **MNA 是精确解，不要用 1% 容差掩盖问题**；若 MNA 与解析式不一致，先查拓扑/节点编号，不要放宽容差。
3. **CircuitJS1 证据是外部对照，不是运行时**；页面上不会出现 CircuitJS1 的 UI 或 GWT 资源。
4. **串联/并联的 `R` 字段**在 CircuitJS1 证据里是电压差（`getVoltageDiff()` 的历史命名），交叉验证时按 `i`/`v` 字段取电流与电压，不要按字段名猜。
5. **catalog.py 仍是手写逐行解析器**：`recipes.json` 是旁路，字段顺序固定为 `controls → views → exports → routes`。
