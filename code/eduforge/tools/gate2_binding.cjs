// GATE-2 验证：适配器修改协议在分层物距下是否真的可判真假。
// 三条纪律：控制组（改回原值必须逐位一致）、阈值落点（清晰/弥散/灰区三条线用实测撑开）、
// 分层（u<f / u=f / f<u<2f / u=2f / u>2f 五档都要过，不能只测最顺的一档）。
// 观测只取上游仿真的 Detector 读数；薄透镜公式在这里只用于选探针位置，不参与判定"是否清晰"。
const fs = require('node:fs');
const path = require('node:path');

const UPSTREAM =
  process.env.EDUFORGE_RAYOPTICS ||
  path.resolve(__dirname, '../../../source/upstream/ray-optics');
const ro = require(path.join(UPSTREAM, 'dist-node', 'rayOptics.js'));

const U = 10;          // 1cm = 10 场景单位（模板约定，lengthScale 锁 1）
const HALF_SPAN = 120; // 探测器半宽（场景单位）
const BIN = 2;

function scene(fCm, uCm, probesCm, density = 0.1) {
  return {
    version: 5,
    lengthScale: 1,
    objs: [
      { type: 'IdealLens', name: 'lens_1', p1: { x: 0, y: -250 }, p2: { x: 0, y: 250 }, focalLength: fCm * U },
      { type: 'PointSource', name: 'object_1', x: -uCm * U, y: 0, brightness: 0.5 },
      ...probesCm.map((x, i) => ({
        type: 'Detector',
        name: 'probe_' + i,
        p1: { x: x * U, y: -HALF_SPAN },
        p2: { x: x * U, y: HALF_SPAN },
        twoSided: true, irradMap: true, binSize: BIN,
      })),
    ],
    origin: { x: 400, y: 0 }, scale: 1, width: 1500, height: 900,
    mode: 'rays', rayModeDensity: density,
  };
}

function load(json) {
  return new Promise((resolve, reject) => {
    const s = new ro.Scene();
    s.loadJSON(JSON.stringify(json), (a, completed) => {
      if (s.error) return reject(Object.assign(new Error('loadJSON: ' + s.error), { scene_error: s.error }));
      if (completed) resolve(s);
    });
  });
}

function readout(scene) {
  return new Promise((resolve, reject) => {
    const sim = new ro.Simulator(scene, null, null, null, null, null, false, Infinity, null, null, null);
    sim.on('simulationComplete', () => {
      const probes = scene.objs.filter(o => o.constructor.type === 'Detector').map(obj => {
        const bins = Array.from(obj.binData || []);
        const total = bins.reduce((a, b) => a + b, 0);
        const max = bins.length ? Math.max(...bins) : 0;
        return {
          name: obj.name,
          x_cm: obj.p1.x / U,
          power: obj.power,
          peak_share: total > 0 ? max / total : 0,
        };
      });
      resolve({ probes, rays: sim.processedRayCount, error: sim.error || null });
    });
    sim.on('error', e => reject(new Error('sim: ' + e)));
    sim.updateSimulation(false, false);
  });
}

// 仅用于决定探针放哪儿，不参与"是否清晰"的判定
function predictVcm(fCm, uCm) {
  if (Math.abs(uCm - fCm) < 1e-9) return null;
  return (fCm * uCm) / (uCm - fCm);
}

const SHARP = 0.8, DIFFUSE = 0.4; // 待实测校准的判据线
const classify = s => (s >= SHARP ? 'sharp' : s <= DIFFUSE ? 'diffuse' : 'inconclusive');

(async () => {
  const f = 10;
  const strata = [
    ['u<f (虚像)', 5],
    ['u=f (无穷远)', 10],
    ['f<u<2f (放大实像)', 15],
    ['u=2f (等大实像)', 20],
    ['u>2f (缩小实像)', 60],
  ];

  const DENS = Number(process.env.DENSITY || 0.1);
  const results = [];
  for (const [label, u] of strata) {
    const v = predictVcm(f, u);
    // 实像：探针放在预测像面 + 偏离 40% 处；虚像/无穷：出射侧放两支探针，都不该锐利
    const probes = v !== null && v > 0
      ? [v, v * 1.4]
      : [15, 30];
    const r = await readout(await load(scene(f, u, probes, DENS)));
    results.push({
      stratum: label,
      u_cm: u, f_cm: f,
      predicted_v_cm: v,
      probes: r.probes,
      rays: r.rays,
      classifications: r.probes.map(p => classify(p.peak_share)),
    });
  }

  // 控制组：把焦距"改成"它自己的初始值 10cm，读数必须与不改完全一致
  const baselineScene = scene(f, 30, [15, 21]);
  const r1 = await readout(await load(baselineScene));
  const sameValue = JSON.parse(JSON.stringify(baselineScene));
  sameValue.objs[0].focalLength = 10 * U; // 与 baseline 相同
  const r2 = await readout(await load(sameValue));
  const control = {
    baseline: r1.probes,
    patched_to_initial: r2.probes,
    identical: JSON.stringify(r1.probes) === JSON.stringify(r2.probes),
  };

  // 修改生效性：u=30、f 10→15，预测像面 15→30，锐利探针必须迁移
  const before = await readout(await load(scene(10, 30, [15, 30])));
  const after = await readout(await load(scene(15, 30, [15, 30])));
  const effect = {
    before_sharp: classify(before.probes.find(p => p.x_cm === 15).peak_share),
    after_sharp: classify(after.probes.find(p => p.x_cm === 15).peak_share),
    before: before.probes, after: after.probes,
  };

  // 版本策略：旧版本应由上游迁移，未来版本应被拒绝——我们只读 scene.error
  const versionPolicy = {};
  const oldScene = scene(10, 30, [15]);
  oldScene.version = 4;
  try {
    const s = await load(oldScene);
    versionPolicy.v4 = { accepted: true, version_after: JSON.parse(s.toJSON()).version };
  } catch (e) { versionPolicy.v4 = { accepted: false, error: e.scene_error }; }

  const newScene = scene(10, 30, [15]);
  newScene.version = 99;
  try {
    await load(newScene);
    versionPolicy.v99 = { accepted: true, note: '上游未拒绝，需注意' };
  } catch (e) { versionPolicy.v99 = { accepted: false, error: e.scene_error }; }

  // 未知/重名绑定必须被拒
  const dup = scene(10, 30, [15]);
  dup.objs.push({ type: 'IdealLens', name: 'lens_1', p1: { x: 500, y: -250 }, p2: { x: 500, y: 250 }, focalLength: 100 });
  const bindings = (() => {
    const find = (json, id) => {
      const hits = json.objs.filter(o => o.name === id);
      if (hits.length === 0) return 'ENTITY_NOT_FOUND';
      if (hits.length > 1) return 'ENTITY_AMBIGUOUS';
      return 'ok';
    };
    return {
      unknown: find(dup, 'nope'),
      duplicate: find(dup, 'lens_1'),
      single: find(scene(10, 30, [15]), 'lens_1'),
    };
  })();

  console.log(JSON.stringify({
    thresholds: { sharp_at_least: SHARP, diffuse_at_most: DIFFUSE, between: 'inconclusive' },
    strata: results, control, effect, versionPolicy, bindings,
  }, null, 2));
  fs.mkdirSync(path.resolve(__dirname, '../../../output/eduforge/reports'), { recursive: true });
  fs.writeFileSync(
    path.resolve(__dirname, '../../../output/eduforge/reports/slice2-gate2.json'),
    JSON.stringify({ thresholds: { SHARP, DIFFUSE }, strata: results, control, effect, versionPolicy, bindings }, null, 2)
  );
})().catch(e => { console.error('GATE2 FAILED:', e.message); process.exit(1); });
