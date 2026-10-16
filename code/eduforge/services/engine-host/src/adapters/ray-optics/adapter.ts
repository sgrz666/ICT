import { readFileSync } from "node:fs";
import { fileURLToPath } from "node:url";

import { setRayParameter, setRayParameters } from "./patch.js";
import { simulate, validateNative } from "./upstream.js";
import type { LensBinding, RayScene, SetParameter } from "../../contracts.js";

const TEMPLATE_ROOT = fileURLToPath(
  new URL("../../../../../catalog/templates/optics/convex-lens/", import.meta.url)
);

function readManifest(): string {
  return readFileSync(TEMPLATE_ROOT + "manifest.yaml", "utf8");
}

// 绑定表从 catalog 模板清单来，不在代码里另写一份量程。
// units_per_unit 只写在清单顶层（一份数字一个家），这里读顶层再分发到每条控件。
// 清单是 YAML，首版用最小解析取需要的键；等 catalog 有正式加载器后整体替换。
export function loadBindings(): LensBinding[] {
  const manifest = readManifest();
  const topLevelUnits = Number(
    manifest.match(/^units_per_unit:\s*(\S+)/m)?.[1]
  );
  if (!Number.isFinite(topLevelUnits) || topLevelUnits <= 0) {
    throw new Error("INVALID_UNIT_MAPPING: manifest 顶层缺 units_per_unit");
  }

  const controlsBlock = manifest.split("\ncontrols:\n")[1]?.split("\nviews:")[0] ?? "";
  const items = controlsBlock.split("\n  - ").filter(Boolean);
  return items.map(raw => {
    const get = (key: string) => raw.match(new RegExp(`${key}:\\s*(.+)`))?.[1].trim();
    return {
      entity_id: get("entity_id") as string,
      native_type: get("native_type") as string,
      parameter: get("parameter") as string,
      min: Number(get("min")),
      max: Number(get("max")),
      units_per_unit: topLevelUnits,
    };
  });
}

export function loadTemplateScene(): RayScene {
  return JSON.parse(readFileSync(TEMPLATE_ROOT + "native.json", "utf8")) as RayScene;
}

export type Candidate = {
  engine_id: "ray_optics";
  base_native: RayScene;
  native: RayScene;
  validation: ReturnType<typeof validateNative>;
};

export const rayOpticsAdapter = {
  engineId: "ray_optics" as const,

  validateNative(sceneJson: unknown) {
    return validateNative(sceneJson);
  },

  // 只接受已登记的参数修改；WorkOrder 由 Python 侧构造，这里不重新决定归属
  apply(scene: RayScene, edit: SetParameter | readonly SetParameter[], bindings = loadBindings()): Candidate {
    const edits = Array.isArray(edit) ? edit : [edit];
    const next = setRayParameters(scene, edits, bindings);
    // 关键一步：改完立刻交回上游解释，而不是等浏览器
    return {
      engine_id: "ray_optics",
      base_native: scene,
      native: next,
      validation: validateNative(next),
    };
  },

  async sample(candidate: Candidate) {
    return simulate(candidate.native);
  },

  exportNative(candidate: Candidate) {
    return JSON.stringify(candidate.native);
  },
};
