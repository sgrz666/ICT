import { describe, expect, it } from "vitest";

import { beamGeometry, lensAxisXcm, sharpestProbe } from "../../src/adapters/ray-optics/upstream";
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

  it("最窄屏压在最外侧 → 像面在阵列之外，判不可观测", () => {
    const probes = SCREENS_CM.map(x => probe(x, (45 - x) * 1.2));
    const g = beamGeometry(probes, 0);
    expect(g.kind).toBe("inconclusive");
    expect(g.reason).toContain("阵列");
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
});

describe("接真上游仿真：可测的才判，测不到的必须不可判", () => {
  it("f=15、u=30 → 实像：两侧宽度收敛，交点即独立观测到的像面", async () => {
    const { g, m } = await geometryFor(15);
    expect(g.kind).toBe("real");
    // 独立参考 v = f·u/(u−f) = 30cm；容差由屏间距推出来，不是挑的常数
    // 容差依据是屏阵列的分辨率（最小间距的一半），不是挑的常数：
    // 实测交点 30.86cm 对上独立参考 30cm，偏差必须落在分辨率内
    expect(g.resolution_cm).not.toBeNull();
    expect(Math.abs(g.image_distance_cm! - 30)).toBeLessThanOrEqual(g.resolution_cm!);
    expect(g.usable).toBeGreaterThanOrEqual(3);
    expect(g.fit_r2).toBeGreaterThan(0.9);
    expect(m.probes.some(p => Number.isFinite(p.centroid_units))).toBe(true);
  });

  it("f=40、u=30（虚像在 -120cm）→ 本阵列分辨不出来，必须不判虚像通过", async () => {
    const { g } = await geometryFor(40);
    // 旧实现在这里凭 `u < f` 报通过。屏阵列上宽度变化不到 15%，
    // 远处虚像与准直在测量上不可区分 —— 诚实的答案是「不可判/平行度受限」。
    expect(g.kind).not.toBe("real");
    expect(g.reason.length).toBeGreaterThan(0);
    expect(["collimated", "inconclusive"]).toContain(g.kind);
  });

  it("f=50、u=30（虚像在 -75cm）→ 至多给出虚像或不可判，绝不给实像", async () => {
    const { g } = await geometryFor(50);
    expect(["virtual", "collimated", "inconclusive"]).toContain(g.kind);
    if (g.kind === "virtual") {
      expect(g.image_distance_cm!).toBeLessThan(0);
      expect(g.apex_x_cm!).toBeLessThan(g.lens_x_cm ?? 0);
      // 与独立参考 v = -75cm 的偏差要落在外推分辨率内，超了就该判不可判
      expect(Math.abs(g.image_distance_cm! + 75)).toBeLessThanOrEqual(g.resolution_cm! * 10);
    }
  });

  it("f=30、u=30（u=f）→ 高平行度或不可判，不能判成实像", async () => {
    const { g } = await geometryFor(30);
    expect(g.kind).not.toBe("real");
    expect(["collimated", "inconclusive"]).toContain(g.kind);
    if (g.width_slope_units_per_cm !== null) {
      // 平行度：斜率乘上跨度要远小于平均宽度（这正是 collimated 的判据本身）
      expect(Math.abs(g.width_slope_units_per_cm) * (g.array_span_cm ?? 1)).toBeLessThan(10);
    }
  });

  it("f=20、u=30（像面在 60cm，超出屏阵列）→ 判不可判而不是硬给一个屏位", async () => {
    const { g } = await geometryFor(20);
    expect(["inconclusive", "real"]).toContain(g.kind);
    if (g.kind === "inconclusive") expect(g.reason).toContain("阵列");
  });

  it("最窄屏与几何交点一致（实像工况）", async () => {
    const { g, m } = await geometryFor(15);
    const sharp = sharpestProbe(m.probes);
    expect(sharp).not.toBeNull();
    expect(Math.abs(Number(sharp!.name?.replace("screen_", "")) - g.apex_x_cm!)).toBeLessThanOrEqual(g.resolution_cm!);
  });
});
