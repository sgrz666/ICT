import { afterAll, beforeAll, describe, expect, it } from "vitest";

import { createEngineHost } from "../../src/main";
import { loadTemplateScene } from "../../src/adapters/ray-optics/adapter";

// GATE-3：修改后的原生场景必须能被上游真实解释并跑出读数。
let server: ReturnType<typeof createEngineHost>;
let base = "";

beforeAll(async () => {
  server = createEngineHost();
  await new Promise<void>(r => server.listen(0, "127.0.0.1", r));
  const addr = server.address();
  base = `http://127.0.0.1:${typeof addr === "object" && addr ? addr.port : 0}`;
});

afterAll(async () => {
  await new Promise<void>(r => server.close(() => r()));
});

async function apply(value: number) {
  const res = await fetch(`${base}/adapters/ray_optics/apply`, {
    method: "POST",
    headers: { "content-type": "application/json" },
    body: JSON.stringify({
      native: loadTemplateScene(),
      edit: {
        op: "set_parameter",
        entity_id: "lens_1",
        parameter: "focal_length_cm",
        value,
      },
    }),
  });
  return { status: res.status, body: await res.json() };
}

describe("GATE-3 修改后的场景能被上游解释并仿真", () => {
  it("healthz 可达", async () => {
    const res = await fetch(`${base}/healthz`);
    expect((await res.json()).ok).toBe(true);
  });

  it("控制组：焦距改成初始值 10cm，读数与不改动时一致", async () => {
    const before = await apply(10);
    expect(before.status).toBe(200);
    expect(before.body.validation.ok).toBe(true);
    const baseline = JSON.stringify(before.body.measurement.probes);

    const again = await apply(10);
    expect(JSON.stringify(again.body.measurement.probes)).toBe(baseline);
  });

  it("改成 15cm 后上游接受，且像面锐度发生可判定的迁移", async () => {
    const r = await apply(15);
    expect(r.status).toBe(200);
    expect(r.body.validation.ok).toBe(true);
    expect(r.body.validation.version).toBe(5);
    expect(r.body.base_untouched).toBe(true);

    const lens = r.body.native.objs.find((o: { name: string }) => o.name === "lens_1");
    expect(lens.focalLength).toBe(150);

    const probes = r.body.measurement.probes as {
      name: string;
      rms_units: number;
      power_fraction: number;
    }[];
    // u=30cm、f=15cm 时像应成在 30cm 屏。判据用 rms + 功率下限，
    // 不用 peak_share（远屏因几乎全漏检会假清晰，已被实测否证）。
    const usable = probes.filter(p => p.power_fraction >= 0.2);
    const sharpest = usable.reduce((b, p) => (p.rms_units < b.rms_units ? p : b));
    expect(sharpest.name).toBe("screen_30");
    expect(sharpest.rms_units).toBeLessThan(5);
  });

  it("越界值被拒，不产生候选", async () => {
    const r = await apply(999);
    expect(r.status).toBe(400);
    expect(r.body.code).toBe("BAD_REQUEST");
  });

  it("未知对象被拒，不静默改错对象", async () => {
    const res = await fetch(`${base}/adapters/ray_optics/apply`, {
      method: "POST",
      headers: { "content-type": "application/json" },
      body: JSON.stringify({
        native: loadTemplateScene(),
        edit: {
          op: "set_parameter",
          entity_id: "does_not_exist",
          parameter: "focal_length_cm",
          value: 15,
        },
      }),
    });
    expect(res.status).toBe(400);
  });

  it("仿真确实在跑（处理了光线且探测器有读数）", async () => {
    const r = await apply(12);
    expect(r.body.measurement.processedRayCount).toBeGreaterThan(0);
    expect(r.body.measurement.probes.length).toBe(7);
    expect(r.body.measurement.error).toBeNull();
  });
});
