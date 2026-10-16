import type { LensBinding, RayScene, SetParameter } from "../../contracts.js";

// 按 name 定位对象，不用数组下标。依据是本机对上游源码的实测：
//   Scene.reorderObj(from,to) 会重排 objs；
//   Editor 拖动时对 Handle 调 scene.unshiftObj 插到队首；
//   Scene.removeObj(index) 让后续对象整体前移。
// 也不能注入自定义 id：BaseSceneObj 的 knownKeys 白名单外的键会置 scene.error。
export function findEntityIndex(scene: RayScene, entityId: string): number {
  const hits = scene.objs
    .map((o, i) => ({ o, i }))
    .filter(({ o }) => o.name === entityId);

  if (hits.length === 0) throw new Error(`ENTITY_NOT_FOUND: ${entityId}`);
  if (hits.length > 1) throw new Error(`ENTITY_AMBIGUOUS: ${entityId}`);
  return hits[0].i;
}

// 版本闸门不在这里。上游 Scene.loadJSON 自己处理：无 version 迁移、
// 字符串或大于 DATA_VERSION 拒绝并置 scene.error、小于则迁移。
// 适配器写死 `!== 5` 会在上游 bump DATA_VERSION 时误伤合法场景，
// 因此改完数据后由调用方 loadJSON 并读回 scene.error。
export function setRayParameter(
  scene: RayScene,
  edit: SetParameter,
  bindings: readonly LensBinding[]
): RayScene {
  const binding = bindings.find(
    item => item.entity_id === edit.entity_id && item.parameter === edit.parameter
  );

  if (!binding) throw new Error("PARAMETER_NOT_SUPPORTED");

  if (!Number.isFinite(edit.value)) throw new Error("VALUE_NOT_FINITE");

  if (edit.value < binding.min || edit.value > binding.max) {
    throw new Error("VALUE_OUT_OF_RANGE");
  }

  if (!Number.isFinite(binding.units_per_unit) || binding.units_per_unit <= 0) {
    throw new Error("INVALID_UNIT_MAPPING");
  }

  // 凹透镜不属本模板；IdealLens 用符号区分会聚/发散
  if (binding.parameter === "focal_length_cm" && binding.min > 0 && edit.value <= 0) {
    throw new Error("VALUE_OUT_OF_RANGE");
  }

  const result = structuredClone(scene);
  const target = result.objs[findEntityIndex(result, binding.entity_id)];

  if (!target || target.type !== binding.native_type) {
    throw new Error("ENTITY_TYPE_MISMATCH");
  }

  if (binding.parameter === "focal_length_cm") {
    target.focalLength = edit.value * binding.units_per_unit;
  } else if (binding.parameter === "object_distance_cm") {
    const lensObj = result.objs.find(o => o.type === "IdealLens");
    let lensX = 0;
    if (lensObj && typeof lensObj.p1 === "object" && typeof lensObj.p2 === "object") {
      const p1 = lensObj.p1 as { x: number };
      const p2 = lensObj.p2 as { x: number };
      lensX = (p1.x + p2.x) / 2;
    }
    target.x = lensX - edit.value * binding.units_per_unit;
  }

  return result;
}

export function setRayParameters(
  scene: RayScene,
  edits: readonly SetParameter[],
  bindings: readonly LensBinding[]
): RayScene {
  let current = scene;
  for (const edit of edits) {
    current = setRayParameter(current, edit, bindings);
  }
  return current;
}
