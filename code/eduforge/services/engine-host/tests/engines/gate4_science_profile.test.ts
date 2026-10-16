import { describe, expect, it } from "vitest";

// GATE-4：独立参考只在理想薄透镜下成立；对真实厚透镜必须显式判"不可对照"，
// 不能靠放宽容差让它过。下面的数字是实测，不是设计意图。
import { sharpestProbe, simulate, validateNative } from "../../src/adapters/ray-optics/upstream";

const U = 10;
const SCREENS_CM = [8, 12, 16, 20, 25, 30, 40];

function sceneWithLens(lensObj: Record<string, unknown>) {
  return {
    version: 5,
    lengthScale: 1,
    objs: [
      { ...lensObj, name: "lens_1" },
      { type: "PointSource", name: "object_1", x: -300, y: 0, brightness: 0.5 },
      ...SCREENS_CM.map(cm => ({
        type: "Detector", name: `screen_${cm}`,
        p1: { x: cm * U, y: -120 }, p2: { x: cm * U, y: 120 },
        twoSided: true, irradMap: true, binSize: 2,
      })),
    ],
    origin: { x: 400, y: 0 }, scale: 1, width: 1500, height: 900,
    mode: "rays", rayModeDensity: 2,
  };
}

const IDEAL = { type: "IdealLens", p1: { x: 0, y: -250 }, p2: { x: 0, y: 250 }, focalLength: 10 * U };
// 厚透镜 n=1.5、d=10、R1=100、R2=-100：近轴焦距约 101.7 场景单位，
// 但含厚度、球差与 Cauchy 色散（cauchyB 0.004），不是薄透镜模型。
const REAL = {
  type: "SphericalLens", defBy: "DR1R2",
  params: { d: 10, r1: 100, r2: -100 },
  refIndex: 1.5, cauchyB: 0.004, partialReflect: false,
};

async function run(lens: Record<string, unknown>) {
  const scene = sceneWithLens(lens);
  const v = validateNative(scene);
  expect(v.ok).toBe(true);
  expect(v.error).toBeNull();
  const m = await simulate(scene);
  const usable = m.probes.filter(p => p.power_fraction >= 0.2).sort((a, b) => a.rms_units - b.rms_units);
  return { v, m, best: usable[0], spread: usable.length > 1 ? usable[1].rms_units - usable[0].rms_units : 0 };
}

describe("GATE-4 科学对照适用条件", () => {
  it("理想薄透镜：像面清晰且落在预测屏上", async () => {
    const { best, m } = await run(IDEAL);
    expect(best.name).toBe("screen_16");        // 预测 v=15cm，阵列里 16 最近
    expect(best.rms_units).toBeLessThan(15);      // 实测 8.9
    expect(m.processedRayCount).toBeGreaterThan(0);
  }, 120000);

  it("真实厚透镜：整条光具座上都成不出像，必须判为不可对照", async () => {
    const ideal = await run(IDEAL);
    const real = await run(REAL);
    // 实测 best_rms：ideal 8.9 vs real 68.1
    expect(real.best.rms_units).toBeGreaterThan(ideal.best.rms_units * 3);
    // 且各屏读数几乎无区分度（实测前三屏 68.1/68.3/68.7），说明不是"差一点点"，
    // 而是这个装置对该透镜根本不成立 —— 放宽容差会把它伪装成数值误差
    expect(real.spread).toBeLessThan(2);
  }, 180000);

  it("两者上游都接受，差异是物理而不是场景被拒", async () => {
    const ideal = await run(IDEAL);
    const real = await run(REAL);
    expect(ideal.v.objs.find(o => o.name === "lens_1")?.type).toBe("IdealLens");
    expect(real.v.objs.find(o => o.name === "lens_1")?.type).toBe("SphericalLens");
    expect(real.m.error).toBeNull();
  }, 180000);
});
