# engines — 引擎级验收（GATE-3 / GATE-4）

**职责**：直接打 engine-host 应用面与适配器，断言"仿真真的跑了、读数真的对"的引擎级验收。与 e2e 的区别：不经过浏览器，直接以 HTTP/函数调用验证。

## 内容（逐文件）

| 文件 | 行数 | 覆盖 |
|---|---|---|
| `gate3_engine_host.test.ts` | 106 | 验收面 `/healthz` `/apply`：控制组一致、f=15 像面锐度迁移、`999`/`does_not_exist` 被拒、仿真真跑（`processedRayCount>0`、7 个探测器读数） |
| `gate4_science_profile.test.ts` | 72 | 科学对照适用条件：理想薄透镜成像清晰可对照；**真实厚透镜必须判「不可对照」**（不靠放宽容差） |
| `beam_geometry.test.ts` | 155 | **光束几何判据（Gate C §C.2 新增）**：合成读数上钉实像交点/虚像反向延长/准直/拟合不足四类分类行为，并接真上游跑 f=15（实像，交点与独立参考差 ≤ 屏分辨率）、f=20/40/50（阵列外或孔径截断 → 必须不可判，不许判成实像）、f=30（平行度需实测证据） |
| `measure_separation.test.ts` | 63 | 像面判据回归：全量程 f 与薄透镜预测一致、rms 塌到半 bin、功率下限剔除退化读数 |

## 与上下层的关系

- 被测：[`../../src/main.ts`](../../README.md)（`createEngineHost`）、[`../../src/adapters/ray-optics/`](../../src/adapters/ray-optics/README.md)（`simulate`/`validateNative`/`sharpestProbe`）。
- 对照的另一侧（Python 侧公式与门禁）：[`../../../../python/src/eduforge/validation/`](../../../../python/src/eduforge/validation/README.md)。

## 已知的坑与纪律

- 「不可对照」是**设计内结论**（fail-closed），不是测试失败——厚透镜场景判「可对照」才是 bug。
- `processedRayCount > 0` 是"仿真真跑"的最小证据；断言读数前先断言它，避免把"没跑"当"结果对"。
- 判据参数（rms 半 bin、功率下限）与 [`../../src/adapters/ray-optics/upstream.ts`](../../src/adapters/ray-optics/README.md) 常量绑定，改参数两处同看。
