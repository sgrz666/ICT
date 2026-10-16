# templates — 教学模板

一个模板 = 一台「可被程序化修改、可被独立验证」的虚拟实验装置。模板是纯数据（YAML + JSON + Markdown），按「学科/实验」分子目录存放。

## 内容

- [`optics/convex-lens/`](optics/convex-lens/README.md) — 凸透镜成像（首批唯一就绪模板）：
  - `manifest.yaml` — 模板清单：场景单位约定（`units_per_unit: 10`、锁 `lengthScale: 1`）、对象布局（`lens_1` IdealLens + `object_1` PointSource + 7 块 Detector 光屏阵列，身份一律用 `name`）、可改参数（焦距 5–50 cm、物距 10–60 cm，非正值拒）、观测判据（光斑二矩半径 RMS + 功率下限，**弃用 peak_share**，理由见文件内 `why_not_peak_share`）、实测基线（f=5/6/8/10/12/15/20/25 八档 argmax 全部与独立薄透镜预测一致）、允许的路由（config / code）。

  - `native.json` — 上游原生场景（version 5），被 engine-host 适配器与探针直接加载。
  - `lesson.md` — 课文草稿（尚未接入教师端）：学生任务三步 + 已实测的「焦距-像距-光屏 rms」数据表。
  - 逐文件说明见 [optics/convex-lens/README.md](optics/convex-lens/README.md)。
- [`mechanics/pendulum/`](mechanics/pendulum/README.md) — 单摆周期与简谐振动（第 7～8 周切片 9 保留位，`manifest.yaml` 声明摆长控制与能量视图，标记 `status: pending_slice_9`）。
- [`circuits/ohms-law/`](circuits/ohms-law/README.md) — 欧姆定律与伏安特性（第 7～8 周切片 9 保留位，`manifest.yaml` 声明电阻/电压控制与电表读数视图，标记 `status: pending_slice_9`）。

## 结构约定

```
templates/<学科>/<实验>/
├── manifest.yaml    # 模板清单（唯一权威）
├── native.json      # 上游原生场景
└── lesson.md        # 教学课文（草稿）
```

## 与其他层的关系

- `manifest.yaml` 的 `engine_id` 指向 [`../engines/`](../engines/README.md) 的引擎描述；能力边界以引擎文件为准。
- 被 `../../services/engine-host/src/adapters/ray-optics/adapter.ts` 与 `../../tools/rayoptics_probe.cjs`、`gate2_binding.cjs` 读取。
- 每个模板实例目录各配一份短 README（该模板的状态、文件与关系）；**模式说明以本文件为准**，新模板照 `optics/convex-lens/` 的结构抄。

## 纪律

- 每个可绑定对象必须显式命名且唯一（上游未命名对象不输出 `name` 键；重名返回 `ENTITY_AMBIGUOUS`）。
- 官方 gallery 场景（如 SphericalLens 版 convex-lens.json）含球差色散，与薄透镜参考式不等价，**不能**当理想透镜模板的种子。
