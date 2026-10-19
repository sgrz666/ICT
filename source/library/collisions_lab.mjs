// 碰撞、动量守恒与牛顿摆的无头验收：同一套解析式，分别拿 matter-js 与 Rapier 去跑。
//
// 为什么要两个引擎对照：这条 P1 实验的解析式很硬（等质量弹性正碰交换速度、弹性斜碰出射成 90°、
// 牛顿摆 n 进 n 出），但结果几乎完全取决于「接触怎么解」。实测结论写在 evidence 里：
// 哪一边不达标就如实记 fail，不把「页面上看起来在弹」当成「动量守恒可验收」。
//
// 跑法：node source/library/collisions_lab.mjs [--json]
import fs from "node:fs";
import path from "node:path";
import { createRequire } from "node:module";
import { fileURLToPath } from "node:url";

const here = path.dirname(fileURLToPath(import.meta.url));
const require = createRequire(path.join(here, "..", "components", "probe_components.mjs"));
const OUT = path.join(here, "collisions-lab-evidence.json");
const M = require("matter-js");
const R = (require("@dimforge/rapier3d-compat").default) ?? require("@dimforge/rapier3d-compat");
await R.init();

const DT_S = 1 / 240;
const DT_MS = DT_S * 1000;
const BASE = M.Common._baseDelta; // 16.666… ms

// 实测定律：matter-js 的 body.velocity 是「每 baseDelta 的位移」⇒ v_phys = velocity × 1000/baseDelta = ×60。
// (position − positionPrev)/dt 只在自由飞行时与之相等；接触期间 positionPrev 不跟着解算器的位置修正走，
// 那个差值会被 slop 修正污染（实测两球「分离量恒 0.9395 < 2r」却读出两个不同的差值速度）。
const mVel = (b) => ({ x: (b.velocity.x * 1000) / BASE, y: (b.velocity.y * 1000) / BASE });
const mSetVel = (b, vx, vy) => M.Body.setVelocity(b, { x: (vx * BASE) / 1000, y: (vy * BASE) / 1000 });

const mEngine = () => {
  const e = M.Engine.create();
  e.gravity.x = 0;
  e.gravity.y = 0;
  return e;
};
const mBall = (x, vx, o = {}) => {
  const b = M.Bodies.circle(x, 0, 0.5, { frictionAir: 0, restitution: o.restitution ?? 1, friction: 0 });
  M.Body.setMass(b, o.mass ?? 1);
  mSetVel(b, vx, 0);
  return b;
};
const mMom = (bs) => bs.reduce((a, b) => ({ x: a.x + b.mass * mVel(b).x, y: a.y + b.mass * mVel(b).y }), { x: 0, y: 0 });
const mKe = (bs) => bs.reduce((a, b) => a + 0.5 * b.mass * (mVel(b).x ** 2 + mVel(b).y ** 2), 0);

function near(label, measured, expected, tolPct) {
  const err = Math.abs(measured - expected);
  const rel = expected === 0 ? err : (err / Math.abs(expected)) * 100;
  return { metric: label, measured: +measured.toFixed(5), analytic: +expected.toFixed(5), rel_error_pct: +rel.toFixed(3), tolerance_pct: tolPct, verdict: rel <= tolPct ? "pass" : "fail" };
}
const conserved = (label, before, after, tolRel = 1e-4) => ({
  metric: label,
  before: +before.toFixed(6),
  after: +after.toFixed(6),
  rel_drift_pct: +((Math.abs(after - before) / (Math.abs(before) || 1)) * 100).toFixed(6),
  tolerance_rel: tolRel,
  verdict: Math.abs(after - before) <= tolRel * (Math.abs(before) || 1) ? "pass" : "fail",
});

/* ─────────────────────────── matter-js 侧 ─────────────────────────── */
const matter = [];

{
  // ⓪ 读数定律
  const e = mEngine();
  const b = mBall(0, 6);
  M.Composite.add(e.world, b);
  M.Engine.update(e, DT_MS);
  const viaField = mVel(b).x;
  const viaDelta = (b.position.x - b.positionPrev.x) / DT_S;
  matter.push({
    id: "matter-velocity-law",
    title: "Matter 速度读数定律：v_phys = body.velocity × 60",
    engine: { body_velocity_x: b.velocity.x, per_step_displacement: b.position.x - b.positionPrev.x, via_field_x60: +viaField.toFixed(5), via_position_delta: +viaDelta.toFixed(5) },
    checks: [near("body.velocity×60 (m/s)", viaField, 6, 0.5), near("自由飞行时位移差/dt (m/s)", viaDelta, 6, 0.5)],
  });
}

{
  // ① 等质量弹性正碰
  const e = mEngine();
  const a = mBall(-1.5, 4);
  const b = mBall(1.5, -2);
  M.Composite.add(e.world, [a, b]);
  M.Engine.update(e, DT_MS);
  const p0 = mMom([a, b]), k0 = mKe([a, b]);
  for (let i = 0; i < 1200; i++) M.Engine.update(e, DT_MS);
  const p1 = mMom([a, b]), k1 = mKe([a, b]);
  matter.push({
    id: "matter-head-on-equal-elastic",
    title: "Matter：等质量弹性正碰（解析式：4/−2 → −2/4 交换速度）",
    engine: { vA: +mVel(a).x.toFixed(5), vB: +mVel(b).x.toFixed(5), separation: +(b.position.x - a.position.x).toFixed(5), ke_before: +k0.toFixed(4), ke_after: +k1.toFixed(4) },
    checks: [near("碰后 vA (m/s)", mVel(a).x, -2, 2), near("碰后 vB (m/s)", mVel(b).x, 4, 2), conserved("动量守恒", p0.x, p1.x), conserved("动能守恒", k0, k1, 1e-3)],
  });
}

{
  // ② 完全非弹性
  const e = mEngine();
  const m1 = 1.5, m2 = 1, u1 = 4;
  const a = mBall(-2.5, u1, { mass: m1, restitution: 0 });
  const b = mBall(2.5, 0, { mass: m2, restitution: 0 });
  M.Composite.add(e.world, [a, b]);
  M.Engine.update(e, DT_MS);
  const p0 = mMom([a, b]);
  for (let i = 0; i < 900; i++) M.Engine.update(e, DT_MS);
  matter.push({
    id: "matter-perfectly-inelastic",
    title: "Matter：restitution=0 的完全非弹性碰撞（共速 = m1u1/(m1+m2)）",
    engine: { vA: +mVel(a).x.toFixed(5), vB: +mVel(b).x.toFixed(5) },
    checks: [near("共速 (m/s)", (mVel(a).x + mVel(b).x) / 2, (m1 * u1) / (m1 + m2), 2), conserved("动量守恒", p0.x, mMom([a, b]).x)],
  });
}

{
  // ③ 牛顿摆
  const e = mEngine();
  const RR = 0.5, L = 2;
  const balls = [];
  for (let i = 0; i < 5; i++) {
    const x = (i - 2) * 2 * RR;
    const b = mBall(x, 0);
    M.Composite.add(e.world, b);
    M.Composite.add(e.world, M.Constraint.create({ pointA: { x, y: -L }, bodyB: b, length: L, stiffness: 1, damping: 0 }));
    balls.push(b);
  }
  const inn = mBall(-6.5, 0);
  M.Composite.add(e.world, inn);
  M.Composite.add(e.world, M.Constraint.create({ pointA: { x: -5.6, y: -L }, bodyB: inn, length: L, stiffness: 1, damping: 0 }));
  mSetVel(inn, 3, 0);
  for (let i = 0; i < 1200; i++) M.Engine.update(e, DT_MS);
  const vs = balls.map((b) => +mVel(b).x.toFixed(5));
  const movers = vs.filter((v) => Math.abs(v) > 0.1).length;
  matter.push({
    id: "matter-newtons-cradle",
    title: "Matter：牛顿摆「一进一出」",
    engine: { per_ball_vx: vs, last_ball: vs[4], moving_balls: movers, in_speed: 3 },
    checks: [near("末端球出射速度 (m/s)", vs[4], 3, 10), { metric: "只有末端 1 球在动", moving_balls: movers, expected: 1, verdict: movers === 1 ? "pass" : "fail" }],
    note: "解析式：动量与动能同时守恒的唯一解就是 n 进 n 出、其余静止",
  });
}

/* ─────────────────────────── Rapier 侧 ─────────────────────────── */
const rapierWorld = () => {
  const w = new R.World({ x: 0, y: 0, z: 0 });
  w.timestep = DT_S;
  return w;
};
const rBall = (w, x, y, vx, vy, mass, restitution) => {
  const desc = R.RigidBodyDesc.dynamic().setTranslation(x, y, 0).setLinvel(vx, vy, 0).setLinearDamping(0).setGravityScale(0).setAdditionalMass(mass, true);
  const rb = w.createRigidBody(desc);
  w.createCollider(R.ColliderDesc.ball(0.5).setRestitution(restitution).setFriction(0).setDensity(0), rb);
  return rb;
};
const rMom = (rbs) => rbs.reduce((a, b) => ({ x: a.x + b.mass() * b.linvel().x, y: a.y + b.mass() * b.linvel().y }), { x: 0, y: 0 });
const rKe = (rbs) => rbs.reduce((a, b) => a + 0.5 * b.mass() * (b.linvel().x ** 2 + b.linvel().y ** 2), 0);
const rapier = [];

{
  // ④ 等质量弹性正碰
  const w = rapierWorld();
  const a = rBall(w, -1.5, 0, 4, 0, 1, 1);
  const b = rBall(w, 1.5, 0, -2, 0, 1, 1);
  w.step(); // 实测：createCollider 之后 mass() 仍是 0，必须 step 一次才算出惯性质量
  const p0 = rMom([a, b]), k0 = rKe([a, b]);
  for (let i = 0; i < 1199; i++) w.step();
  rapier.push({
    id: "rapier-head-on-equal-elastic",
    title: "Rapier：等质量弹性正碰（交换速度）",
    engine: { vA: +a.linvel().x.toFixed(5), vB: +b.linvel().x.toFixed(5), ke_before: +k0.toFixed(5), ke_after: +rKe([a, b]).toFixed(5), mass_reported: [a.mass(), b.mass()] },
    checks: [near("碰后 vA (m/s)", a.linvel().x, -2, 2), near("碰后 vB (m/s)", b.linvel().x, 4, 2), conserved("动量守恒", p0.x, rMom([a, b]).x), conserved("动能守恒", k0, rKe([a, b]), 2e-3)],
  });
  w.free();
}

{
  // ⑤ 不等质量弹性正碰
  const w = rapierWorld();
  const m1 = 2, m2 = 1, u1 = 5;
  const a = rBall(w, -2.5, 0, u1, 0, m1, 1);
  const b = rBall(w, 2.5, 0, 0, 0, m2, 1);
  for (let i = 0; i < 1500; i++) w.step();
  rapier.push({
    id: "rapier-head-on-unequal-elastic",
    title: "Rapier：2 kg 撞 1 kg 静止（一维弹性解析解）",
    engine: { v1: +a.linvel().x.toFixed(5), v2: +b.linvel().x.toFixed(5) },
    formula: "v1' = ((m1−m2)u1)/(m1+m2) = 1.6667，v2' = 2m1u1/(m1+m2) = 6.6667",
    checks: [near("碰后 v1 (m/s)", a.linvel().x, ((m1 - m2) * u1) / (m1 + m2), 2), near("碰后 v2 (m/s)", b.linvel().x, (2 * m1 * u1) / (m1 + m2), 2)],
  });
  w.free();
}

{
  // ⑥ 弹性斜碰 90°
  const w = rapierWorld();
  const a = rBall(w, -3, 0.35, 5, 0, 1, 1);
  const b = rBall(w, 1.5, 0, 0, 0, 1, 1);
  for (let i = 0; i < 1500; i++) w.step();
  const va = a.linvel(), vb = b.linvel();
  const angA = (Math.atan2(va.y, va.x) * 180) / Math.PI;
  const angB = (Math.atan2(vb.y, vb.x) * 180) / Math.PI;
  let sep = Math.abs(angA - angB);
  if (sep > 180) sep = 360 - sep;
  rapier.push({
    id: "rapier-oblique-90-degrees",
    title: "Rapier：等质量弹性斜碰出射应成 90°（台球开球）",
    engine: { angA: +angA.toFixed(3), angB: +angB.toFixed(3), separation_deg: +sep.toFixed(3) },
    formula: "等质量 + 弹性 + 一球静止 ⇒ vA'·vB' = 0；且 |vA'|²+|vB'|² = v0²",
    checks: [near("两出射速度夹角 (°)", sep, 90, 6), near("末速率平方和 (m²/s²)", va.x ** 2 + va.y ** 2 + vb.x ** 2 + vb.y ** 2, 25, 2)],
  });
  w.free();
}

{
  // ⑦ 牛顿摆
  const w = rapierWorld();
  const RR = 0.5;
  const row = [];
  for (let i = 0; i < 5; i++) row.push(rBall(w, (i - 2) * 2 * RR, 0, 0, 0, 1, 1));
  const inn = rBall(w, -6.5, 0, 3, 0, 1, 1);
  for (let i = 0; i < 2000; i++) w.step();
  const vs = row.map((rb) => +rb.linvel().x.toFixed(5));
  const movers = vs.filter((v) => Math.abs(v) > 0.1).length;
  rapier.push({
    id: "rapier-newtons-cradle",
    title: "Rapier：牛顿摆「一进一出」",
    engine: { per_ball_vx: vs, last_ball: vs[4], moving_balls: movers, in_speed: 3 },
    checks: [near("末端球出射速度 (m/s)", vs[4], 3, 10), { metric: "只有末端 1 球在动", moving_balls: movers, expected: 1, verdict: movers === 1 ? "pass" : "fail" }],
  });
  w.free();
}

{
  // ⑧ 对照组
  const w = rapierWorld();
  const a = rBall(w, -2, 0, 4, 0, 1, 0.5);
  const b = rBall(w, 2, 0, 0, 0, 1, 0.5);
  w.step();
  const k0 = rKe([a, b]), p0 = rMom([a, b]);
  for (let i = 0; i < 1199; i++) w.step();
  const k1 = rKe([a, b]);
  rapier.push({
    id: "rapier-dissipation-control",
    title: "Rapier 对照组：restitution=0.5 时动量守恒、动能必须明显损失",
    engine: { ke_before: +k0.toFixed(5), ke_after: +k1.toFixed(5) },
    checks: [conserved("动量守恒", p0.x, rMom([a, b]).x), { metric: "动能损失 > 10%", ke_lost_pct: +(((k0 - k1) / k0) * 100).toFixed(3), rule: "> 10%", verdict: (k0 - k1) / k0 > 0.1 ? "pass" : "fail" }],
  });
  w.free();
}

const groups = [
  { engine: `matter-js ${M.version}`, results: matter },
  { engine: `@dimforge/rapier3d-compat ${R.version()}`, results: rapier },
];
for (const g of groups) for (const r of g.results) r.verdict = r.checks.every((c) => c.verdict === "pass") ? "pass" : "fail";
const passOf = (rs) => rs.filter((r) => r.verdict === "pass").length;
for (const g of groups) g.summary = `${passOf(g.results)}/${g.results.length} pass`;
const allPass = groups.reduce((a, g) => a + passOf(g.results), 0);
const allN = groups.reduce((a, g) => a + g.results.length, 0);
if (process.argv.includes("--json"))
  fs.writeFileSync(
    OUT,
    JSON.stringify({ generated_at: new Date().toISOString(), run_command: "node source/library/collisions_lab.mjs --json", dt_s: DT_S, pass: allPass, fail: allN - allPass, groups }, null, 2),
    "utf-8",
  );
for (const g of groups) {
  console.log(`\n### ${g.engine} — ${g.summary}`);
  for (const r of g.results) {
    console.log(`[${r.verdict}] ${r.id}`);
    for (const c of r.checks) console.log(`    ${c.verdict === "pass" ? "✓" : "✗"} ${c.metric}${c.measured !== undefined ? ` · 实测 ${c.measured} vs 解析 ${c.analytic}` : ""}${c.before !== undefined ? ` · ${c.before} → ${c.after}` : ""}${c.ke_lost_pct !== undefined ? ` · 损失 ${c.ke_lost_pct}%` : ""}${c.moving_balls !== undefined ? ` · 动的球 ${c.moving_balls}` : ""}`);
  }
}
console.log(`\n合计 ${allPass}/${allN} pass`);
process.exit(allPass === allN ? 0 : 1);
