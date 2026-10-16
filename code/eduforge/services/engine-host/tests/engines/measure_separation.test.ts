import { describe, expect, it } from "vitest";

import { loadTemplateScene, rayOpticsAdapter } from "../../src/adapters/ray-optics/adapter";
import { sharpestProbe } from "../../src/adapters/ray-optics/upstream";

// 像面定位判据的回归。这条曾经用 peak_share，被实测否证（远屏因几乎全漏检而假清晰，
// f=5 时把 40cm 屏判成最清晰），现改为 rms + 捕获功率下限。
// 物距 u = 30cm 由模板固定（object_1 在 x=-300，units_per_unit=10）。
const U_CM = 30;
const SCREENS_CM = [8, 12, 16, 20, 25, 30, 40];

const predictedScreen = (v: number) =>
  SCREENS_CM.reduce((best, cm) => (Math.abs(cm - v) < Math.abs(best - v) ? cm : best), SCREENS_CM[0]);

async function measure(f: number) {
  const candidate = rayOpticsAdapter.apply(loadTemplateScene(), {
    op: "set_parameter",
    entity_id: "lens_1",
    parameter: "focal_length_cm",
    value: f,
  });
  expect(candidate.validation.ok).toBe(true);
  const m = await rayOpticsAdapter.sample(candidate);
  return { m, sharp: sharpestProbe(m.probes) };
}

describe("实测像面与独立薄透镜预测一致（全量程）", () => {
  const rows: string[] = [];

  // f=30 会成 u=f 准直、f>30 成虚像，屏阵列上无有意义像面，排除在外。
  it.each([5, 6, 8, 10, 12, 15, 20, 25])("f=%i cm", async (f) => {
    const { m, sharp } = await measure(f);
    expect(sharp).not.toBeNull();
    const v = (f * U_CM) / (U_CM - f);
    const got = Number(sharp!.name?.replace("screen_", ""));
    rows.push(
      `f=${f} v=${v.toFixed(1)} argmax=${got} predicted=${predictedScreen(v)} rms=${sharp!.rms_units.toFixed(1)} usable=${m.probes.filter(p => p.power_fraction >= 0.2).length}/${m.probes.length}`
    );
    expect(got).toBe(predictedScreen(v));
  });

  it("像面正好落在屏上时 rms 塌到接近半个 bin", async () => {
    // f=12 -> v=20cm 正好是 screen_20；f=15 -> v=30cm 正好是 screen_30
    const a = await measure(12);
    const b = await measure(15);
    expect(a.sharp!.rms_units).toBeLessThan(5);
    expect(b.sharp!.rms_units).toBeLessThan(5);
  });

  it("退化读数被功率下限剔除，不会被当成最清晰", async () => {
    const { m } = await measure(5); // v=6cm，在屏阵列之外
    // 没有 power_fraction 下限时 peak_share 会把最远的屏判成最清晰
    const byNaiveShare = [...m.probes].sort((a, b) => b.peak_share - a.peak_share)[0];
    expect(Number(byNaiveShare.name?.replace("screen_", ""))).toBeGreaterThan(8);
    const sharp = sharpestProbe(m.probes);
    expect(Number(sharp!.name?.replace("screen_", ""))).toBe(8);
  });

  it("测量表记满 8 档", () => {
    console.log("\n" + rows.join("\n"));
    expect(rows.length).toBe(8);
  });
});
