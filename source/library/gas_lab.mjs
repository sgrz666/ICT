// 理想气体的无头验收：Rapier 里让一箱弹性小球自己撞墙，把压强从「引擎算出来的碰撞冲量」里量出来，
// 再对照分子动理论 pV = (1/3)·N·m·⟨v²⟩ 与玻意耳/查理/阿伏伽德罗三条状态律。
//
// 为什么要这个脚本：热学这条在简报里是 P1，但仓库里没有任何「装了就能测压强」的引擎。
// 关键是别把「小球在动」当成「气体有压强」：这里压强只由引擎自己给出的速度反转算
// （冲量 = m·Δv，Δv 取引擎碰撞前后的读数），小球之间用碰撞分组关掉，才是真·理想气体；
// 另开一个「重力打开」的对照组——如果各壁受力仍然对称，说明读数在骗人。
//
// 跑法：node source/library/gas_lab.mjs [--json]
import fs from "node:fs";
import path from "node:path";
import { createRequire } from "node:module";
import { fileURLToPath } from "node:url";

const here = path.dirname(fileURLToPath(import.meta.url));
const require = createRequire(path.join(here, "..", "components", "probe_components.mjs"));
const OUT = path.join(here, "gas-lab-evidence.json");
const R = require("@dimforge/rapier3d-compat").default ?? require("@dimforge/rapier3d-compat");
await R.init();

const DT = 2e-4; // s，一步
const T_RUN = 12; // s，一个场景跑多久（分子撞墙次数要够多，否则压强是统计噪声：0.6 s 时每个分子只撞 ~3 次，实测偏 31%）
const R_BALL = 0.03; // m
const MASS = 1e-3; // kg

// 一个可复现的伪随机源（不用 Math.random，否则证据不可复现）
function rng(seed) {
  let s = seed >>> 0;
  return () => ((s = (s * 1664525 + 1013904223) >>> 0) / 4294967296) * 2 - 1;
}

// 碰撞分组：walls=0x0001、balls=0x0002；小球只与墙碰撞（关掉球间碰撞才是理想气体）
const GROUP_WALL = (0x0001 << 16) | 0x0002;
const GROUP_BALL = (0x0002 << 16) | 0x0001;

function run({ n, L, speed, gravity = 0, seed = 7, radius = R_BALL }) {
  const world = new R.World({ x: 0, y: gravity, z: 0 });
  world.timestep = DT;
  const half = L / 2;
  const t = 0.02; // 壁厚
  const walls = [
    [0, half + t / 2, 0, L, t, L],
    [0, -(half + t / 2), 0, L, t, L],
    [half + t / 2, 0, 0, t, L, L],
    [-(half + t / 2), 0, 0, t, L, L],
    [0, 0, half + t / 2, L, L, t],
    [0, 0, -(half + t / 2), L, L, t],
  ];
  for (const [x, y, z, hx, hy, hz] of walls) {
    const rb = world.createRigidBody(R.RigidBodyDesc.fixed().setTranslation(x, y, z));
    world.createCollider(R.ColliderDesc.cuboid(hx, hy, hz).setRestitution(1).setFriction(0).setCollisionGroups(GROUP_WALL), rb);
  }

  const rand = rng(seed);
  const balls = [];
  for (let i = 0; i < n; i++) {
    // 归一化方向 × speed：所有分子同速率（=单温，玻尔兹曼分布不是本条要验的东西，写清楚就行）
    let dx = rand(), dy = rand(), dz = rand();
    const k = Math.hypot(dx, dy, dz) || 1;
    dx /= k; dy /= k; dz /= k;
    // 位置必须与方向无关，否则「速度大的那个轴刚好也离墙近」会把各向同性带偏（实测 px/py 差 9%）
    const px = rand() * (half - radius * 3), py = rand() * (half - radius * 3), pz = rand() * (half - radius * 3);
    const rb = world.createRigidBody(
      R.RigidBodyDesc.dynamic()
        .setTranslation(px, py, pz)
        .setLinvel(dx * speed, dy * speed, dz * speed)
        .setLinearDamping(0)
        .setGravityScale(gravity ? 1 : 0)
        .setAdditionalMass(MASS, true),
    );
    world.createCollider(R.ColliderDesc.ball(radius).setRestitution(1).setFriction(0).setDensity(0).setCollisionGroups(GROUP_BALL), rb);
    balls.push({ rb, prev: { x: dx * speed, y: dy * speed, z: dz * speed }, impulse: { x: 0, y: 0, z: 0 }, bounceSpeed: [], hits: 0 });
  }

  const v2Start = balls.reduce((a, b) => { const v = b.rb.linvel(); return a + v.x * v.x + v.y * v.y + v.z * v.z; }, 0) / n;
  const steps = Math.round(T_RUN / DT);
  for (let s = 0; s < steps; s++) {
    world.step();
    for (const b of balls) {
      const v = b.rb.linvel();
      // 引擎自己给出的速度反转 = 墙给了冲量；逐分量算 |Δv|，记进对应轴的两面墙
      for (const ax of ["x", "y", "z"]) {
        if (Math.sign(v[ax]) !== Math.sign(b.prev[ax]) && v[ax] !== 0 && b.prev[ax] !== 0) {
          b.impulse[ax] += Math.abs(v[ax] - b.prev[ax]);
          b.bounceSpeed.push(Math.abs(v[ax]));
          b.hits += 1;
        }
      }
      b.prev = { x: v.x, y: v.y, z: v.z };
    }
  }
  let v2 = 0;
  let hits = 0;
  let bounceSpeedMean = 0;
  const perAxis = { x: 0, y: 0, z: 0 };
  for (const b of balls) {
    const v = b.rb.linvel();
    v2 += v.x * v.x + v.y * v.y + v.z * v.z;
    hits += b.hits;
    bounceSpeedMean += b.bounceSpeed.reduce((a, c) => a + c, 0);
    perAxis.x += b.impulse.x;
    perAxis.y += b.impulse.y;
    perAxis.z += b.impulse.z;
  }
  const meanV2 = v2 / n;
  // 每面墙平均受力 = 该轴两面的总冲量 / 时间 / 2
  const force = {};
  for (const ax of ["x", "y", "z"]) force[ax] = (perAxis[ax] * MASS) / T_RUN / 2;
  const area = L * L;
  const pAxis = { x: force.x / area, y: force.y / area, z: force.z / area };
  const p = (pAxis.x + pAxis.y + pAxis.z) / 3;
  const out = {
    n, L, V: L ** 3, meanV2, p, pAxis, force, hits, steps, dt: DT, gravity, speed, radius,
    freePath: L - 2 * radius, // 球心能自由活动的棱长：分子有半径时撞墙间隔由它决定，不是 L
    perParticleBounces: hits / n,
    v2Start,
    bounceSpeedMean: bounceSpeedMean / (hits || 1),
  };
  out.energy_drift_pct = ((meanV2 - v2Start) / v2Start) * 100;
  world.free();
  return out;
}

function near(label, measured, expected, tolPct) {
  const rel = expected === 0 ? measured : Math.abs((measured - expected) / expected) * 100;
  return { metric: label, measured: +measured.toPrecision(6), analytic: +expected.toPrecision(6), rel_error_pct: +rel.toFixed(3), tolerance_pct: tolPct, verdict: rel <= tolPct ? "pass" : "fail" };
}

const results = [];
const N = 120, L = 0.6, SPEED = 2;
const base = run({ n: N, L, speed: SPEED });
// 分子动理论（质点版）：p = N m⟨v²⟩/(3V)
const pPoint = (1 / 3) * (N * MASS * base.meanV2) / base.V;
// 有限半径修正：球心在棱长 ℓ = L−2R 的空间里往返，两次撞墙间隔由 ℓ 决定；
// 每面墙平均受力 = N m⟨vx²⟩/ℓ，摊到真实墙面积 L² 上 ⇒ p = N m⟨v²⟩/(3·ℓ·L²)。
// 这就是范德瓦尔斯 b（分子体积不可忽略 ⇒ 压强大于质点公式）的来源，不是引擎误差。
const pHard = (1 / 3) * (N * MASS * base.meanV2) / (base.freePath * L * L);

results.push({
  id: "gas-kinetic-theory",
  title: "理想气体压强来自分子撞墙：p = N·m·⟨v²⟩/(3V)（有限半径修正后）",
  engine: { N, L, speed: SPEED, radius: R_BALL, freePath: +base.freePath.toFixed(4), seconds: T_RUN, perParticleBounces: +base.perParticleBounces.toFixed(1), meanV2: +base.meanV2.toFixed(6), hits: base.hits, p_Pa: +base.p.toExponential(4), pAxis: Object.fromEntries(Object.entries(base.pAxis).map(([k, v]) => [k, +v.toExponential(4)])) },
  formula: "逐分量取引擎碰撞前后速度差算冲量；p_墙 = F_墙/A（A=L²），三轴平均 = p；对照式 p = N m⟨v²⟩/(3·(L−2R)·L²)",
  checks: [
    near("p (Pa) vs 有限半径修正式", base.p, pHard, 5),
    near("三个方向压强各向同性（x/z 与 y 的比）", (base.pAxis.x + base.pAxis.z) / 2 / base.pAxis.y, 1, 5),
    { metric: "弹性撞墙前后 ⟨v²⟩ 不漂（引擎解算没吃能量）", drift_pct: +base.energy_drift_pct.toFixed(4), tolerance_pct: 0.5, verdict: Math.abs(base.energy_drift_pct) <= 0.5 ? "pass" : "fail" },
  ],
});

// 质点极限：半径趋近 0 时，压强必须回到课本式 p = N m⟨v²⟩/(3L³)；
// 同时基准值/质点式应当 ≈ L/(L−2R)，证明上面那点偏差是几何来的，不是解算器吃了能量。
{
  const tiny = run({ n: N, L, speed: SPEED, radius: 0.004 });
  const pTinyPoint = (1 / 3) * (tiny.n * MASS * tiny.meanV2) / tiny.V;
  results.push({
    id: "gas-point-particle-limit",
    title: "质点极限与偏差归因：R→0 回到课本式；R=3 cm 时高出的倍数 = L/(L−2R)",
    engine: { R_tiny: 0.004, p_tiny_Pa: +tiny.p.toExponential(4), p_point_Pa: +pTinyPoint.toExponential(4), p_base_over_p_point: +(base.p / pPoint).toFixed(5), geometric_prediction: +(L / (L - 2 * R_BALL)).toFixed(5) },
    formula: "R→0 ⇒ ℓ→L ⇒ p = N m⟨v²⟩/(3L³)；有限 R ⇒ p/p_质点 = L/ℓ",
    checks: [
      near("小球的 p vs 质点式 (Pa)", tiny.p, pTinyPoint, 5),
      near("基准超出质点式的倍数 = L/(L−2R)", base.p / pPoint, L / base.freePath, 5),
    ],
  });
}

// 玻意耳：同温同 N，体积减半（边长 ÷∛2）⇒ p×2（质点式），有限半径下修正到 2.06
{
  const small = run({ n: N, L: L / Math.cbrt(2), speed: SPEED });
  const pRatioCorrected = (base.freePath * L * L) / (small.freePath * small.L * small.L);
  results.push({
    id: "gas-boyle",
    title: "玻意耳定律：等温压缩到一半体积 ⇒ 压强翻倍",
    engine: { V_ratio: +(small.V / base.V).toFixed(5), p_ratio: +(small.p / base.p).toFixed(5), L_small: +small.L.toFixed(4), freePath_small: +small.freePath.toFixed(4), corrected_expectation: +pRatioCorrected.toFixed(5) },
    formula: "pV = const（N、⟨v²⟩ 不变）；有限半径版 p ∝ 1/((L−2R)·L²)",
    checks: [
      near("p(小箱)/p(大箱) vs 质点式 V 比", small.p / base.p, base.V / small.V, 5),
      near("p(小箱)/p(大箱) vs 有限半径修正式", small.p / base.p, pRatioCorrected, 3),
    ],
  });
}

// 查理/阿蒙顿：同体积同 N，温度（=⟨v²⟩）翻倍 ⇒ 压强翻倍。速率 ×√2 使 ⟨v²⟩ ×2
{
  const hot = run({ n: N, L, speed: SPEED * Math.SQRT2 });
  results.push({
    id: "gas-amontons",
    title: "等容升温：⟨v²⟩ 翻倍（速率 ×√2）⇒ 压强翻倍",
    engine: { meanV2_ratio: +(hot.meanV2 / base.meanV2).toFixed(5), p_ratio: +(hot.p / base.p).toFixed(5) },
    formula: "p = N m⟨v²⟩/(3·ℓ·L²)，V、N、R 不变 ⇒ p ∝ ⟨v²⟩ ∝ T",
    checks: [near("p(热)/p(冷)", hot.p / base.p, 2, 5), near("⟨v²⟩ 比", hot.meanV2 / base.meanV2, 2, 3)],
  });
}

// 阿伏伽德罗：同 T 同 V，分子数翻倍 ⇒ 压强翻倍
{
  const more = run({ n: 2 * N, L, speed: SPEED });
  results.push({
    id: "gas-avogadro",
    title: "等温等容加料：分子数翻倍 ⇒ 压强翻倍",
    engine: { N_before: N, N_after: 2 * N, p_ratio: +(more.p / base.p).toFixed(5) },
    formula: "p ∝ N",
    checks: [near("p(2N)/p(N)", more.p / base.p, 2, 5)],
  });
}

// 对照组：打开重力 ⇒ 下壁必须比上壁受力大（读不出这个各向异性，前面的压强就是假的）
{
  const g = run({ n: N, L, speed: SPEED, gravity: 9.8 });
  const ratio = g.force.y / base.force.y;
  results.push({
    id: "gas-gravity-control",
    title: "对照组：开重力后 y 轴总受力必须明显偏离无重力（静压差）",
    engine: { force_y_no_gravity: +(base.force.y).toExponential(4), force_y_with_gravity: +g.force.y.toExponential(4), p_with_gravity_Pa: +g.p.toExponential(4) },
    checks: [{ metric: "开重力后 y 轴受力变化 > 1%", ratio: +ratio.toFixed(4), verdict: Math.abs(ratio - 1) > 0.01 ? "pass" : "fail" }],
    note: "注意：这里只验「读数能感觉到重力」，不做流体静力学定量——那需要按面分别记冲量（本脚本按轴合并了两面墙）",
  });
}

for (const r of results) r.verdict = r.checks.every((c) => c.verdict === "pass") ? "pass" : "fail";
const pass = results.filter((r) => r.verdict === "pass").length;
const payload = {
  generated_at: new Date().toISOString(),
  engine: `@dimforge/rapier3d-compat ${R.version()}（6 面刚性墙 + ${N} 个 restitution=1 小球；球间碰撞用 collisionGroups 关掉 ⇒ 真理想气体；dt=${DT}s，跑 ${T_RUN}s）`,
  run_command: "node source/library/gas_lab.mjs --json",
  pass,
  fail: results.length - pass,
  results,
};
if (process.argv.includes("--json")) fs.writeFileSync(OUT, JSON.stringify(payload, null, 2), "utf-8");
for (const r of results) {
  console.log(`[${r.verdict}] ${r.id}`);
  for (const c of r.checks) console.log(`    ${c.verdict === "pass" ? "✓" : "✗"} ${c.metric}${c.measured !== undefined ? ` · 实测 ${c.measured} vs 理论 ${c.analytic}（${c.rel_error_pct}%）` : ` · ${JSON.stringify(c)}`}`);
}
console.log(`\n${pass}/${results.length} pass · 基准 p = ${base.p.toExponential(3)} Pa（质点式 ${pPoint.toExponential(3)}，有限半径修正式 ${pHard.toExponential(3)}）`);
process.exit(pass === results.length ? 0 : 1);
