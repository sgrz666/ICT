// 第一切片验证探针。
// 证明四件事：上游接受我们的场景；场景可往返保存；对象能被稳定定位并修改焦距；
// 改完的仿真结果与独立薄透镜公式吻合。
// 观测端只用上游仿真；参考公式只在这里独立算，不参与观测，避免自我验证。
const fs = require('node:fs');
const path = require('node:path');

const UPSTREAM =
  process.env.EDUFORGE_RAYOPTICS ||
  path.resolve(__dirname, '../../../source/upstream/ray-optics');
const BUNDLE = path.join(UPSTREAM, 'dist-node', 'rayOptics.js');
const SCENE = path.resolve(
  __dirname,
  '../catalog/templates/optics/convex-lens/native.json'
);

const UNITS_PER_CM = 10; // 模板约定：1cm = 10 场景单位（上游无单位系统）

const ro = require(BUNDLE);

function loadScene(sceneJson) {
  return new Promise((resolve, reject) => {
    const scene = new ro.Scene();
    scene.loadJSON(JSON.stringify(sceneJson), (needFullUpdate, completed) => {
      if (scene.error) return reject(new Error('loadJSON error: ' + scene.error));
      if (completed) resolve(scene);
    });
  });
}

function simulate(scene) {
  return new Promise((resolve, reject) => {
    const simulator = new ro.Simulator(
      scene, null, null, null, null, null, false, Infinity, null, null, null
    );
    simulator.on('simulationComplete', () => {
      const raw = [];
      scene.objs.forEach((obj, i) => {
        if (obj.constructor.type !== 'Detector') return;
        const bins = obj.irradMap && obj.binData ? Array.from(obj.binData) : [];
        const total = bins.reduce((a, b) => a + b, 0);
        const max = bins.length ? Math.max(...bins) : 0;
        const idx = bins.length ? bins.indexOf(max) : -1;
        const len = Math.hypot(obj.p2.x - obj.p1.x, obj.p2.y - obj.p1.y);
        const bin = obj.binSize || 1;
        let rms = Number.NaN;
        if (total > 0) {
          const centroid =
            bins.reduce((acc, w, k) => acc + w * ((k + 0.5) * bin - len / 2), 0) / total;
          rms = Math.sqrt(
            bins.reduce(
              (acc, w, k) => acc + w * ((k + 0.5) * bin - len / 2 - centroid) ** 2,
              0
            ) / total
          );
        }
        raw.push({
          index: i,
          name: obj.name,
          x: obj.p1.x,
          power: obj.power ?? 0,
          bins: bins.length,
          peak_share: total > 0 ? max / total : 0,
          peak_offset_units: idx >= 0 ? (idx + 0.5) * bin - len / 2 : Number.NaN,
          rms_units: rms,
        });
      });
      const maxPower = raw.reduce((m, d) => Math.max(m, d.power), 0);
      const detectors = raw.map(d => ({
        ...d,
        power_fraction: maxPower > 0 ? d.power / maxPower : 0,
      }));
      resolve({
        detectors,
        processedRayCount: simulator.processedRayCount,
        totalTruncation: simulator.totalTruncation,
        sim_error: simulator.error || null,
        sim_warning: simulator.warning || null,
      });
    });
    simulator.on('error', e => reject(new Error('simulator: ' + e)));
    // 构造 Simulator 不会自动开跑；漏掉这句的后果是事件永不触发、Node 静默 exit 0
    simulator.updateSimulation(false, false);
  });
}

// 独立参考：理想薄透镜。与上游 IdealLens 的薄透镜模型对应，但不共用代码路径。
function thinLensReference(fCm, uCm) {
  if (!(fCm > 0) || !(uCm > 0)) throw new Error('convex-lens inputs must be positive');
  if (Math.abs(uCm - fCm) < 1e-9) return { vCm: null, m: null, kind: 'at_infinity' };
  const v = (fCm * uCm) / (uCm - fCm);
  return { vCm: v, m: -v / uCm, kind: v > 0 ? 'real' : 'virtual' };
}

// 按 name 定位对象，不用数组下标。
// 依据（本机实测）：Scene.reorderObj 会重排 objs；Editor 拖动时对 Handle 调 unshiftObj
// 插到队首；removeObj 会让后续对象整体前移。⇒ 下标绑定在正常编辑下就会指错对象。
// 上游 BaseSceneObj 的 knownKeys 白名单外的字段会置 scene.error，故不能注入自定义 id；
// name 在白名单内且能往返保留，是可用的唯一稳定标识。
function findEntity(sceneJson, entityId) {
  const hits = sceneJson.objs
    .map((o, i) => ({ o, i }))
    .filter(({ o }) => o.name === entityId);
  if (hits.length === 0) throw new Error('ENTITY_NOT_FOUND: ' + entityId);
  if (hits.length > 1) throw new Error('ENTITY_AMBIGUOUS: ' + entityId);
  return hits[0].i;
}

function setFocalLengthCm(sceneJson, entityId, cm) {
  const next = structuredClone(sceneJson);
  const target = next.objs[findEntity(next, entityId)];
  if (!target || target.type !== 'IdealLens') throw new Error('ENTITY_TYPE_MISMATCH');
  if (!Number.isFinite(cm) || cm <= 0) throw new Error('VALUE_REJECTED');
  target.focalLength = cm * UNITS_PER_CM;
  return next;
}

(async () => {
  const base = JSON.parse(fs.readFileSync(SCENE, 'utf8'));
  const out = { upstream: UPSTREAM, bundle_bytes: fs.statSync(BUNDLE).size };

  // 1) 上游是否接受我们手写的场景
  const scene = await loadScene(base);
  out.load = {
    accepted: true,
    scene_error: scene.error || null,
    scene_warning: scene.warning || null,
    version_after_load: JSON.parse(scene.toJSON()).version,
    objs: scene.objs.map((o, i) => ({ i, type: o.constructor.type, name: o.name })),
  };

  // 2) 保存 → 重载 → 再保存，字符串必须一致
  const saved1 = scene.toJSON();
  const reloaded = await loadScene(JSON.parse(saved1));
  out.roundtrip = {
    identical: saved1 === reloaded.toJSON(),
    bytes: saved1.length,
    name_survives_serialization: JSON.parse(saved1).objs.some(o => o.name === 'lens_1'),
  };

  // 3) 绑定稳定性：重排 objs 之后，按 name 仍指向同一个透镜
  const shuffled = structuredClone(base);
  shuffled.objs = [shuffled.objs[3], ...shuffled.objs.slice(0, 3)];
  out.binding = {
    index_of_lens_1_before: findEntity(base, 'lens_1'),
    index_of_lens_1_after_shuffle: findEntity(shuffled, 'lens_1'),
    still_ideal_lens: shuffled.objs[findEntity(shuffled, 'lens_1')].type === 'IdealLens',
    rejects_unknown_entity: (() => {
      try { findEntity(base, 'nope'); return false; } catch { return true; }
    })(),
  };

  // 4) 纯函数改焦距：15cm → focalLength 150，且源对象不被污染
  const patched = setFocalLengthCm(base, 'lens_1', 15);
  out.patch = {
    baseline_focalLength: base.objs[0].focalLength,
    patched_focalLength: patched.objs[findEntity(patched, 'lens_1')].focalLength,
    expected: 150,
    source_unmutated: base.objs[0].focalLength === 100,
    rejects_nonpositive: (() => {
      try { setFocalLengthCm(base, 'lens_1', 0); return false; } catch { return true; }
    })(),
  };

  // 5) 两个配置各自仿真，看哪块屏上的像更集中
  const runs = {};
  for (const [label, json] of [['f10cm', base], ['f15cm', patched]]) {
    runs[label] = await simulate(await loadScene(json));
  }
  out.simulations = runs;

  // 6) 与独立参考对照：u=30cm，f=10 → v=15；f=15 → v=30
  const uCm = 300 / UNITS_PER_CM;
  out.reference = {
    object_distance_cm: uCm,
    f10: thinLensReference(10, uCm),
    f15: thinLensReference(15, uCm),
  };

  const SHARP_POWER_FLOOR = 0.2;
  const screensCm = [8, 12, 16, 20, 25, 30, 40];
  const nearestScreen = v =>
    screensCm.reduce((b, cm) => (Math.abs(cm - v) < Math.abs(b - v) ? cm : b), screensCm[0]);

  // 判据：先按捕获功率下限剔除"光斑超出屏宽、几乎全漏检"的退化读数，
  // 再取光斑 RMS 最小的屏。不用 max/total —— 远屏会因分母塌掉而假清晰。
  const sharpest = r => {
    const usable = r.detectors.filter(d => (d.power_fraction ?? 0) >= SHARP_POWER_FLOOR);
    if (usable.length === 0) return null;
    return usable.reduce((b, d) => (d.rms_units < b.rms_units ? d : b));
  };

  const s10 = sharpest(runs.f10cm);
  const s15 = sharpest(runs.f15cm);
  out.verdict = {
    criterion: "rms_spot_width_with_power_floor",
    f10cm_sharp_screen: s10 && s10.name,
    f10cm_predicted_screen: "screen_" + nearestScreen(out.reference.f10.vCm),
    f15cm_sharp_screen: s15 && s15.name,
    f15cm_predicted_screen: "screen_" + nearestScreen(out.reference.f15.vCm),
    matches:
      !!s10 &&
      !!s15 &&
      s10.name === "screen_" + nearestScreen(out.reference.f10.vCm) &&
      s15.name === "screen_" + nearestScreen(out.reference.f15.vCm),
  };

  console.log(JSON.stringify(out, null, 2));
})().catch(e => {
  console.error('PROBE FAILED:', e.message);
  process.exit(1);
});
