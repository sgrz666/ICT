# templates — 教学模板

一个模板 = 一台「可被程序化修改、可被独立验证」的虚拟实验装置。模板是纯数据（YAML + JSON + Markdown），按「学科/实验」分子目录存放。

## 内容

- [`optics/`](optics/README.md) — 光学分组层（3 个真实模板在位）→ [`optics/convex-lens/`](optics/convex-lens/README.md) 凸透镜成像、[`optics/concave-lens/`](optics/concave-lens/README.md) 凹透镜发散与成像、[`optics/camera-principle/`](optics/camera-principle/README.md) 照相机成像原理：
  - `manifest.yaml` — 模板清单：场景单位约定（`units_per_unit: 10`、锁 `lengthScale: 1`）、对象布局（命名实体、Detector 光屏阵列）、可改参数、观测判据与科学规约。
  - `native.json` — 上游原生场景（version 5），被 engine-host 适配器与探针直接加载。
  - `lesson.md` — 课文草稿（尚未接入教师端）：学生任务三步 + 已实测的「焦距-像距-光屏 rms」数据表。
  - 逐文件说明见 [optics/convex-lens/README.md](optics/convex-lens/README.md)。
- [`mechanics/`](mechanics/README.md) — 力学分组层 →
  [`mechanics/projectile/`](mechanics/projectile/README.md) 抛体运动（`engine_id: matter_js`，**LabKit 文件级链路**：三配方 L1/L2/L3 已实测、产出单文件 HTML；未接入 engine-host / 教师端）、
  [`mechanics/pendulum/`](mechanics/pendulum/README.md) 单摆周期与简谐振动（同为 **LabKit 链路**：两配方 L1/L2/L3 已实测，产物约 108 KB；myPhysicsLab 只保留为历史无头证据）。
- [`circuits/`](circuits/README.md) — 电路分组层 →
  [`circuits/ohms-law/`](circuits/ohms-law/README.md) 直流电路：欧姆定律与串并联（**LabKit 链路**，`engine_id: circuit_mna`；三配方 L1/L2/L3 已实测，CircuitJS1 交叉验证 8/8；产物约 27 KB；未接入 engine-host / 教师端）。

## 结构约定

```
templates/<学科>/<实验>/
├── manifest.yaml    # 模板清单（唯一权威）
├── native.json      # 上游原生场景
└── lesson.md        # 教学课文（草稿）
```

LabKit 模板（[`mechanics/projectile/`](mechanics/projectile/README.md)、[`mechanics/pendulum/`](mechanics/pendulum/README.md)、[`circuits/ohms-law/`](circuits/ohms-law/README.md)）额外带 `recipes.json` 与 `render/`。`recipes.json` 不是重复声明，而是因为 `catalog.py` 是手写逐行解析器：嵌套的 recipes / acceptance / render 放进 `manifest.yaml` 会被当成 control 项解析坏。

## 与其他层的关系

- `manifest.yaml` 的 `engine_id` 指向 [`../engines/`](../engines/README.md) 的引擎描述；能力边界以引擎文件为准。
- 被 `../../services/engine-host/src/adapters/ray-optics/adapter.ts` 与 `../../tools/rayoptics_probe.cjs`、`gate2_binding.cjs` 读取。
- 每个**学科分组目录**（`optics/`、`mechanics/`、`circuits/`）各配一份分组层 README（该学科在位模板与整体状态），每个**模板实例目录**各配一份短 README（该模板的状态、文件与关系）；**模式说明以本文件为准**，新模板照 `optics/convex-lens/` 的结构抄。

## 纪律

- 每个可绑定对象必须显式命名且唯一（上游未命名对象不输出 `name` 键；重名返回 `ENTITY_AMBIGUOUS`）。
- 官方 gallery 场景（如 SphericalLens 版 convex-lens.json）含球差色散，与薄透镜参考式不等价，**不能**当理想透镜模板的种子。
