import { readFileSync } from "node:fs";
import { fileURLToPath } from "node:url";
import { dirname, resolve } from "node:path";
import { describe, expect, it } from "vitest";

import { findEntityIndex, setRayParameter } from "../../../src/adapters/ray-optics/patch";
import type { LensBinding, RayScene } from "../../../src/contracts";

const here = dirname(fileURLToPath(import.meta.url));
// tests/adapters/ray-optics -> engine-host -> services -> eduforge，catalog 在 eduforge 下
const SCENE_PATH = resolve(
  here,
  "../../../../../catalog/templates/optics/convex-lens/native.json"
);

const BINDINGS: readonly LensBinding[] = [
  {
    entity_id: "lens_1",
    native_type: "IdealLens",
    parameter: "focal_length_cm",
    min: 5,
    max: 50,
    units_per_unit: 10,
  },
];

function loadScene(): RayScene {
  return JSON.parse(readFileSync(SCENE_PATH, "utf8")) as RayScene;
}

const edit = (value: number) => ({
  op: "set_parameter" as const,
  entity_id: "lens_1",
  parameter: "focal_length_cm",
  value,
});

describe("控制组：改成它自己的初始值必须逐位无变化", () => {
  it("patch to initial 10cm leaves the scene identical", () => {
    const base = loadScene();
    const before = base.objs.find(o => o.name === "lens_1")!.focalLength;
    const after = setRayParameter(base, edit(10), BINDINGS).objs.find(
      o => o.name === "lens_1"
    )!.focalLength;
    expect(before).toBe(100);
    expect(after).toBe(100);
    expect(JSON.stringify(setRayParameter(base, edit(10), BINDINGS))).toBe(
      JSON.stringify(base)
    );
  });
});

describe("单位映射", () => {
  it("15cm -> focalLength 150", () => {
    const out = setRayParameter(loadScene(), edit(15), BINDINGS);
    expect(out.objs[findEntityIndex(out, "lens_1")].focalLength).toBe(150);
  });

  it("源对象不被就地改写", () => {
    const base = loadScene();
    setRayParameter(base, edit(15), BINDINGS);
    expect(base.objs[0].focalLength).toBe(100);
  });

  it("其余对象保持不动", () => {
    const base = loadScene();
    const out = setRayParameter(base, edit(15), BINDINGS);
    expect(out.objs.filter(o => o.name !== "lens_1")).toEqual(
      base.objs.filter(o => o.name !== "lens_1")
    );
  });
});

describe("绑定稳定性", () => {
  it("重排 objs 后仍指向同一个透镜", () => {
    const base = loadScene();
    const shuffled = structuredClone(base);
    shuffled.objs = [shuffled.objs[3], ...shuffled.objs.slice(0, 3)];
    const idx = findEntityIndex(shuffled, "lens_1");
    expect(shuffled.objs[idx].type).toBe("IdealLens");
    expect(idx).toBe(1);
    expect(setRayParameter(shuffled, edit(15), BINDINGS).objs[idx].focalLength).toBe(150);
  });

  it("未知 entity_id 被拒", () => {
    const bad = { ...edit(15), entity_id: "nope" };
    expect(() => setRayParameter(loadScene(), bad, BINDINGS)).toThrow(/PARAMETER_NOT_SUPPORTED/);
  });

  it("重名对象被拒", () => {
    const dup = loadScene();
    dup.objs.push({ ...dup.objs[0], focalLength: 100 });
    // 绑定表里的 lens_1 现在有两个同名对象
    expect(() => findEntityIndex(dup, "lens_1")).toThrow(/ENTITY_AMBIGUOUS/);
  });

  it("同名但类型不符被拒", () => {
    const s = loadScene();
    const wrong: LensBinding[] = [
      { ...BINDINGS[0], entity_id: "object_1", native_type: "IdealLens" },
    ];
    const bad = { ...edit(15), entity_id: "object_1" };
    expect(() => setRayParameter(s, bad, wrong)).toThrow(/ENTITY_NOT_SUPPORTED|ENTITY_TYPE_MISMATCH/);
  });
});

describe("量程与数值健壮性", () => {
  it.each([
    [0, "VALUE_OUT_OF_RANGE"],
    [-10, "VALUE_OUT_OF_RANGE"],
    [4, "VALUE_OUT_OF_RANGE"],
    [51, "VALUE_OUT_OF_RANGE"],
    [Number.NaN, "VALUE_NOT_FINITE"],
    [Number.POSITIVE_INFINITY, "VALUE_NOT_FINITE"],
  ])("拒绝 %p", (value, code) => {
    expect(() => setRayParameter(loadScene(), edit(value as number), BINDINGS)).toThrow(code);
  });

  it("边界值 5 与 50 允许", () => {
    expect(setRayParameter(loadScene(), edit(5), BINDINGS).objs[0].focalLength).toBe(50);
    expect(setRayParameter(loadScene(), edit(50), BINDINGS).objs[0].focalLength).toBe(500);
  });
});
