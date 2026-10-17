import { describe, expect, it } from "vitest";

import {
  beamGeometry, buildProbeScene, lensAxisXcm, probeReadings, sharpestProbe,
} from "../../src/adapters/ray-optics/upstream";
import type { Probe } from "../../src/adapters/ray-optics/upstream";
import { loadTemplateScene, rayOpticsAdapter } from "../../src/adapters/ray-optics/adapter";

// Gate C §C.2：虚像与无穷远不能凭公式判通过，必须有来自光线本身独立几何证据。
// 这里同时钉两件事：
//   1) 纯函数 beamGeometry 在合成读数上的分类行为（含拟合不成立时明确不可判）；
//   2) 接真上游仿真时，三种工况（f=15 实像 / f=40 虚像 / f=30 准直）确实各归各位。
// 物距 u = 30cm 由模板固定（object_1 在 x=-300，units_per_unit=10）。

const SCREENS_CM = [8, 12, 16, 20, 25, 30, 40];

function probe(x: number, width: number, powerFraction = 1): Probe {
  return {
    name: `screen_${x}`,
    x_cm: x,
    power: 100,
    peak_share: 0.1,
    peak_offset_units: 0,
    rms_units: width,
    centroid_units: 0,
    x_units: x * 10,
    power_fraction: powerFraction,
    extent_units: null,
  };
}

async function geometryFor(focalCm: number) {
  const candidate = rayOpticsAdapter.apply(loadTemplateScene(), {
    op: "set_parameter",
    entity_id: "lens_1",
    parameter: "focal_length_cm",
    value: focalCm,
  });
  expect(candidate.validation.ok).toBe(true);
  const m = await rayOpticsAdapter.sample(candidate);
  return { m, g: m.geometry };
}

describe("beamGeometry 在合成读数上的分类", () => {
  it("两侧宽度收敛 → 实像，交点即实测像面", () => {
    // 宽度在 20cm 处收为零：|x-20| 的 V 形
    const probes = SCREENS_CM.map(x => probe(x, Math.abs(x - 20) * 2 + 0.5));
    const g = beamGeometry(probes, 0);
    expect(g.kind).toBe("real");
    expect(g.apex_x_cm).toBeCloseTo(20, 1);
    expect(g.image_distance_cm).toBeCloseTo(20, 1);
    expect(g.fit_r2).not.toBeNull();
    expect(g.fit_r2!).toBeGreaterThan(0.9);
    // 容差来自屏间距，不是挑的常数
    expect(g.resolution_cm).toBe(2);
  });

  it("宽度单调发散且反向延长交于入射侧 → 虚像（像距为负）", () => {
    const probes = SCREENS_CM.map(x => probe(x, (x + 20) * 0.6));
    const g = beamGeometry(probes, 0);
    expect(g.kind).toBe("virtual");
    expect(g.apex_x_cm!).toBeLessThan(0);
    expect(g.image_distance_cm!).toBeCloseTo(-20, 1);
  });

  it("宽度全程不变 → 准直，像面无定义", () => {
    const probes = SCREENS_CM.map(x => probe(x, 5));
    const g = beamGeometry(probes, 0);
    expect(g.kind).toBe("collimated");
    expect(g.apex_x_cm).toBeNull();
    expect(g.width_slope_units_per_cm).not.toBeNull();
  });

  it("可用屏不足 → inconclusive，并说明原因（不得当作通过）", () => {
    const probes = [probe(8, 3), probe(12, 2)].map(p => p);
    const g = beamGeometry(probes, 0);
    expect(g.kind).toBe("inconclusive");
    expect(g.reason).toContain("可用屏不足");
  });

  it("最窄屏压在最外侧（像面在阵列之外）→ 整段线性外推给实像，并报告外推标准误", () => {
    const probes = SCREENS_CM.map(x => probe(x, (45 - x) * 1.2));
    const g = beamGeometry(probes, 0);
    // 宽度单调收窄到阵列末端仍未为零：交点在 45cm，量具能把它外推出来
    expect(g.kind).toBe("real");
    expect(g.apex_x_cm!).toBeCloseTo(45, 1);
    expect(g.vertex_stderr_cm).not.toBeNull();
    expect(g.vertex_stderr_cm!).toBeLessThan(1);
    expect(g.reason).toContain("外推");
  });

  it("读数贴到探测器满幅的屏被剔除；全部截断时判不可判", () => {
    // 半高 120 的探测器均匀照亮时 rms 上限 = 240/√12 ≈ 69；> 0.9×69 即视为截断
    const withExtent = (x: number, w: number): Probe => ({ ...probe(x, w), extent_units: 240 });
    const partly = beamGeometry(SCREENS_CM.map(x => withExtent(x, Math.abs(x - 20) * 2 + 0.5)), 0);
    expect(partly.kind).toBe("real");
    const allClipped = beamGeometry(SCREENS_CM.map(x => withExtent(x, 68)), 0);
    expect(allClipped.kind).toBe("inconclusive");
    expect(allClipped.reason).toContain("孔径截断");
  });

  it("退化读数（几乎全漏检）被功率下限剔除后不足以拟合 → 不可判", () => {
    const probes = SCREENS_CM.map((x, i) => probe(x, 1 + i, i > 1 ? 0.01 : 1));
    const g = beamGeometry(probes, 0);
    expect(g.kind).toBe("inconclusive");
    expect(g.usable).toBeLessThan(3);
  });

  it("lensAxisXcm 从场景取透镜中点，非理想透镜时给 null", () => {
    const scene = { objs: [{ type: "IdealLens", p1: { x: -5 }, p2: { x: 5 } }] };
    expect(lensAxisXcm(scene)).toBe(0);
    expect(lensAxisXcm({ objs: [{ type: "SphericalLens" }] })).toBeNull();
  });

  it("观测副本只改量具：屏加宽但 binSize 不变，且在透镜面加一块与口径同宽的光阑", () => {
    const scene = loadTemplateScene();
    const before = JSON.stringify(scene);
    type Pt = { x: number; y: number };
    type ProbeObj = { type: string; name?: string; binSize?: number; p1?: Pt; p2?: Pt; p3?: Pt; p4?: Pt };
    const probeScene = buildProbeScene(scene) as { objs: ProbeObj[] };
    // 交付场景一个字节都不改（探针仿真是量具，不是产物）
    expect(JSON.stringify(scene)).toBe(before);
    const detectors = probeScene.objs.filter(o => o.type === "Detector");
    expect(detectors.length).toBe(7);
    // binSize 必须原样保留：放大 binSize 会把像面附近的读数量化掉（实测把 f=15 的实像判成准直）
    expect(detectors.every(d => d.binSize === 2)).toBe(true);
    expect(detectors.every(d => Math.abs(d.p1!.y) >= 1000)).toBe(true);
    const stop = probeScene.objs.find(o => o.type === "Aperture");
    expect(stop).toBeDefined();
    // 透光孔与透镜口径一致：挡住的是「根本没经过透镜」的直光扇
    const lens = scene.objs.find(o => o.type === "IdealLens") as unknown as { p1: Pt };
    expect(Math.abs(stop!.p3!.y)).toBe(Math.abs(lens.p1.y));
    expect(Math.abs(stop!.p4!.y)).toBe(Math.abs(lens.p1.y));
  });

  it("不加光阑时宽屏读数是废的：直光扇把外推交点带偏到 -227cm", async () => {
    // 这条钉住「为什么要加光阑」。上游点光源发的光里那些没碰到透镜的部分直接铺满宽屏，
    // 二矩被这条直光扇主导：实测（f=50、u=30，独立参考虚像在 -75cm）
    //   有光阑 → 交点 -75.0cm、R²=1.000、斜率 1.786±0.002
    //   没光阑 → 交点 -227.3cm、R²=0.933、斜率 1.995±0.238
    // 两种都"看起来判出了虚像"，但只有加光阑那份的量具和读数是自洽的 —— 所以不能只断言 kind。
    const candidate = rayOpticsAdapter.apply(loadTemplateScene(), {
      op: "set_parameter",
      entity_id: "lens_1",
      parameter: "focal_length_cm",
      value: 50,
    });
    const noStop = buildProbeScene(candidate.native) as { objs: Record<string, unknown>[] };
    noStop.objs = noStop.objs.filter(o => o.type !== "Aperture");
    const g = beamGeometry(await probeReadings(noStop), lensAxisXcm(candidate.native));
    expect(g.usable).toBeGreaterThanOrEqual(3);
    // 偏差远超它自己报出的外推不确定度 ⇒ 这个数不可信，不能当证据发布
    expect(Math.abs(g.image_distance_cm! + 75)).toBeGreaterThan(10 * (g.vertex_stderr_cm ?? 0));
  });
});

describe("接真上游仿真：虚像与无穷远也要有实测证据", () => {
  // 容差来自量具本身：像点在两屏之间由屏分辨率说话，外推工况由交点标准误说话。
  // 独立参考 = 薄透镜公式，只用来「对照」，从来不是判据的来源。
  const toleranceCm = (g: ReturnType<typeof beamGeometry>) =>
    Math.max(2 * (g.resolution_cm ?? 2), 3 * (g.vertex_stderr_cm ?? 0));

  it("f=15、u=30 → 实像：两侧宽度收敛，交点即独立观测到的像面", async () => {
    const { g, m } = await geometryFor(15);
    expect(g.kind).toBe("real");
    expect(g.measured_on).toBe("wide_aperture_probe");
    // 独立参考 v = f·u/(u−f) = 30cm
    expect(g.resolution_cm).not.toBeNull();
    expect(Math.abs(g.image_distance_cm! - 30)).toBeLessThanOrEqual(toleranceCm(g));
    expect(g.usable).toBeGreaterThanOrEqual(3);
    expect(g.fit_r2).toBeGreaterThan(0.9);
    expect(m.probes.some(p => Number.isFinite(p.centroid_units))).toBe(true);
  });

  it("f=40、u=30（虚像在 -120cm）→ 实测发散锥反向延长，交点落在入射侧", async () => {
    const { g } = await geometryFor(40);
    // 旧实现在这里凭 `u < f` 报通过；加宽屏 + 透镜面光阑之后，
    // 光束发散是量出来的：宽度沿阵列单调展宽，外推交点在入射侧。
    expect(g.kind).toBe("virtual");
    expect(g.image_distance_cm!).toBeLessThan(0);
    expect(Math.abs(g.image_distance_cm! + 120)).toBeLessThanOrEqual(toleranceCm(g));
    expect(g.vertex_stderr_cm).not.toBeNull();
  });

  it("f=50、u=30（虚像在 -75cm）→ 虚像，且与独立参考的偏差在量具不确定度内", async () => {
    const { g } = await geometryFor(50);
    expect(g.kind).toBe("virtual");
    expect(g.apex_x_cm!).toBeLessThan(g.lens_x_cm ?? 0);
    expect(Math.abs(g.image_distance_cm! + 75)).toBeLessThanOrEqual(toleranceCm(g));
  });

  it("f=30、u=30（u=f）→ 高平行度：斜率与零不可区分，而不是「看不出变化」", async () => {
    const { g } = await geometryFor(30);
    expect(g.kind).toBe("collimated");
    expect(g.apex_x_cm).toBeNull();
    expect(g.width_slope_units_per_cm).not.toBeNull();
    expect(g.slope_stderr_units_per_cm).not.toBeNull();
    // 判据本身就是这条实测不等式
    expect(Math.abs(g.width_slope_units_per_cm!)).toBeLessThanOrEqual(2 * g.slope_stderr_units_per_cm!);
    expect(g.reason).toContain("不可区分");
  });

  it("f=20、u=30（像面在 60cm，超出屏阵列）→ 整段外推给出实像位置", async () => {
    const { g } = await geometryFor(20);
    expect(g.kind).toBe("real");
    expect(g.image_distance_cm!).toBeGreaterThan(g.array_span_cm!);
    expect(Math.abs(g.image_distance_cm! - 60)).toBeLessThanOrEqual(toleranceCm(g));
  });

  it("最窄屏与几何交点一致（实像工况）", async () => {
    const { g, m } = await geometryFor(15);
    const sharp = sharpestProbe(m.probes);
    expect(sharp).not.toBeNull();
    expect(Math.abs(Number(sharp!.name?.replace("screen_", "")) - g.apex_x_cm!)).toBeLessThanOrEqual(g.resolution_cm!);
  });
});
