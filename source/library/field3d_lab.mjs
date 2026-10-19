// 带电粒子在磁场中运动的无头验收：Rapier 只做刚体积分，洛伦兹力由脚本逐步施加，
// 再用与引擎无关的解析式 + 自写圆拟合判对错。
//
// 为什么要这个脚本：调研里这条写明「Rapier 是刚体引擎，不做洛伦兹力」，所以不能当成现成能力。
// 这里要回答的是两个问题：① 用它的力/速度接口手写 F = qv×B，追出来的轨迹到底是不是解析解说的圆；
// ② 引擎自报的质量与真实惯性不一致时（实测 setAdditionalMass 之后 rb.mass() 仍报 0），
// 该怎么标定。容差、步长敏感度和对照组（q=0）都在下面。
//
// 跑法：node source/library/field3d_lab.mjs [--json]（--json 才写 evidence 文件）
import fs from "node:fs";
import path from "node:path";
import { createRequire } from "node:module";
import { fileURLToPath } from "node:url";

const here = path.dirname(fileURLToPath(import.meta.url));
const OUT = path.join(here, "field3d-lab-evidence.json");
// 走 components 那边的 require 链，才能解析到 @dimforge/…（wasm 只随 npm 发布，见 source/components/README.md）
const require = createRequire(path.join(here, "..", "components", "probe_components.mjs"));
const mod = require("@dimforge/rapier3d-compat");
const R = mod.default ?? mod;
await R.init();

const DT = 1 / 240; // s，逐步积分的步长
const V0 = 4; // m/s，垂直于 B 的初速度
const Q = 1; // C（教学单位，量纲自洽即可，重点是比值）
const M_REQ = 0.5; // kg，想要的质量
const BZ = 0.6; // T，磁场沿 +z

function cross(a, b) {
  return { x: a.y * b.z - a.z * b.y, y: a.z * b.x - a.x * b.z, z: a.x * b.y - a.y * b.x };
}

function makeWorld() {
  const w = new R.World({ x: 0, y: 0, z: 0 });
  w.timestep = DT;
  return w;
}

function makeParticle(world, v0) {
  const desc = R.RigidBodyDesc.dynamic()
    .setTranslation(0, 0, 0)
    .setLinvel(v0.x, v0.y, v0.z)
    .setLinearDamping(0)
    .setGravityScale(0);
  desc.setAdditionalMass(M_REQ, true);
  const rb = world.createRigidBody(desc);
  return rb;
}

// 跑一段：lorentz=false 时不施加力（对照组），否则每步用「本步开始时的速度」算 qv×B。
function run({ q, B, v0, seconds, dt = DT, lorentz = true }) {
  const world = makeWorld();
  world.timestep = dt;
  const rb = makeParticle(world, v0);
  const pts = [{ t: 0, p: { ...rb.translation() }, v: { ...rb.linvel() } }];
  const nSteps = Math.max(1, Math.round(seconds / dt));
  let turned = 0;
  let speedMax = 0;
  let speedMin = Infinity;
  let prevV = { ...v0 };
  for (let i = 0; i < nSteps; i++) {
    if (lorentz && q !== 0) {
      const v = rb.linvel();
      const f = cross(v, B);
      rb.resetForces(true);
      rb.addForce({ x: q * f.x, y: q * f.y, z: q * f.z }, true);
    }
    world.step();
    const v = rb.linvel();
    const p = rb.translation();
    const sp = Math.hypot(v.x, v.y, v.z);
    speedMax = Math.max(speedMax, sp);
    speedMin = Math.min(speedMin, sp);
    // 绕 +z 累积转角（用于独立量出周期，不靠解析式反推）
    const dot = prevV.x * v.x + prevV.y * v.y;
    const crs = prevV.x * v.y - prevV.y * v.x;
    turned += Math.atan2(crs, dot);
    prevV = { ...v };
    pts.push({ t: (i + 1) * dt, p: { x: p.x, y: p.y, z: p.z }, v: { x: v.x, y: v.y, z: v.z } });
  }
  const out = { pts, turned, speedMax, speedMin, nSteps, tEnd: nSteps * dt, dt };
  world.free();
  return out;
}

// 自写的最小二乘圆拟合，完全不读引擎自报的任何量：给一串平面点，返圆心、半径与残差。
// 模型 x² + y² + Dx + Ey + F = 0 ⇒ 对每个点是线性方程，正规方程解 D/E,F。
function fitCircle(pts) {
  const n = pts.length;
  const AtA = [[0, 0, 0], [0, 0, 0], [0, 0, 0]];
  const Atb = [0, 0, 0];
  for (let i = 0; i < n; i++) {
    const x = pts[i].p.x;
    const y = pts[i].p.y;
    const row = [x, y, 1];
    const rhs = -(x * x + y * y);
    for (let a = 0; a < 3; a++) {
      Atb[a] += row[a] * rhs;
      for (let b = 0; b < 3; b++) AtA[a][b] += row[a] * row[b];
    }
  }
  const [D, E, F] = solve3(AtA, Atb);
  const cx = -D / 2;
  const cy = -E / 2;
  const radius = Math.sqrt(Math.max(cx * cx + cy * cy - F, 0));
  let sse = 0;
  for (let i = 0; i < n; i++) sse += (Math.hypot(pts[i].p.x - cx, pts[i].p.y - cy) - radius) ** 2;
  return { cx, cy, radius, rms: Math.sqrt(sse / n), n };
}

function solve3(A, b) {
  const m = [
    [A[0][0], A[0][1], A[0][2], b[0]],
    [A[1][0], A[1][1], A[1][2], b[1]],
    [A[2][0], A[2][1], A[2][2], b[2]],
  ];
  for (let i = 0; i < 3; i++) {
    let p = i;
    for (let j = i + 1; j < 3; j++) if (Math.abs(m[j][i]) > Math.abs(m[p][i])) p = j;
    [m[i], m[p]] = [m[p], m[i]];
    const d = m[i][i] || 1e-30;
    for (let j = 0; j < 4; j++) m[i][j] /= d;
    for (let k = 0; k < 3; k++) {
      if (k === i) continue;
      const f = m[k][i];
      for (let j = 0; j < 4; j++) m[k][j] -= f * m[i][j];
    }
  }
  return [m[0][3], m[1][3], m[2][3]];
}

// 标定惯性质量：给一个已知恒力跑一步，用实测 Δv 反算 m_eff = F·dt/Δv。
// 这一条是「引擎自报质量不可信」的实测答案，后面所有解析式都用 m_eff。
function calibrateMass() {
  const world = makeWorld();
  const rb = makeParticle(world, { x: 0, y: 0, z: 0 });
  const reported = rb.mass();
  rb.addForce({ x: 0, y: 1, z: 0 }, true);
  world.step();
  const dv = rb.linvel().y;
  const m_eff = 1 * DT / dv;
  world.free();
  return { reported, dv, m_eff, requested: M_REQ };
}

function near(label, measured, expected, tolPct) {
  const err = Math.abs(measured - expected);
  const rel = expected === 0 ? err : (err / Math.abs(expected)) * 100;
  return {
    metric: label,
    measured: Number(measured.toFixed(6)),
    analytic: Number(expected.toFixed(6)),
    rel_error_pct: Number(rel.toFixed(3)),
    tolerance_pct: tolPct,
    verdict: rel <= tolPct ? "pass" : "fail",
  };
}

const results = [];
const cal = calibrateMass();
const mEff = cal.m_eff;

results.push({
  id: "mass-calibration",
  title: "惯性质量标定：setAdditionalMass 之后引擎自报多少、实际多少",
  formula: "m_eff = F·dt/Δv（单步恒力实测反算）",
  engine: { rb_mass_reported: cal.reported, one_step_dv: +cal.dv.toFixed(8), requested_additional_mass: cal.requested },
  checks: [near("有效质量 (kg)", mEff, M_REQ, 2)],
  lesson: "rb.mass() 报 0（没挂碰撞体时不重算质量属性），但动力学用的是 additionalMass——所以必须以实测为准",
});

// ① 匀强磁场里的圆周运动：半径、周期、旋向、闭合误差
{
  const B = { x: 0, y: 0, z: BZ };
  const TAnalytic = (2 * Math.PI * mEff) / (Math.abs(Q) * BZ);
  const r = run({ q: Q, B, v0: { x: V0, y: 0, z: 0 }, seconds: TAnalytic });
  const fit = fitCircle(r.pts);
  const rAnalytic = (mEff * V0) / (Math.abs(Q) * BZ);
  const omegaMeasured = Math.abs(r.turned) / r.tEnd;
  const tMeasured = (2 * Math.PI / Math.abs(r.turned)) * r.tEnd;
  // 同一物理场景把步长降到 1/4：如果速率漂移是离散施加 qv×B 的产物（而不是物理），它应当同比变小
  const quarter = run({ q: Q, B, v0: { x: V0, y: 0, z: 0 }, seconds: TAnalytic, dt: DT / 4 });
  const driftFine = ((r.speedMax - r.speedMin) / V0) * 100;
  const driftQuarter = ((quarter.speedMax - quarter.speedMin) / V0) * 100;
  results.push({
    id: "bfield-circular-orbit",
    title: "匀强磁场中的圆周运动：qv×B 手写施加，圆拟合与解析式对照",
    engine: {
      steps: r.nSteps,
      seconds: +r.tEnd.toFixed(5),
      turned_rad: +r.turned.toFixed(5),
      fit_center: { x: +fit.cx.toFixed(5), y: +fit.cy.toFixed(5) },
      fit_radius: +fit.radius.toFixed(5),
      fit_rms: +fit.rms.toFixed(6),
      speed_min: +r.speedMin.toFixed(6),
      speed_max: +r.speedMax.toFixed(6),
    },
    formula: "r = mv/(|q|B)，T = 2πm/(|q|B)，|v| 守恒（磁力不做功）",
    checks: [
      near("回旋半径 (m)", fit.radius, rAnalytic, 2),
      near("角速度 ω = |Δφ|/t (rad/s)", omegaMeasured, (Math.abs(Q) * BZ) / mEff, 2),
      near("由累积转角反出的周期 (s)", tMeasured, TAnalytic, 2),
      {
        metric: "轨迹是不是圆（拟合残差 / 半径）",
        rms_over_radius_pct: Number(((fit.rms / fit.radius) * 100).toFixed(3)),
        tolerance_pct: 1,
        verdict: (fit.rms / fit.radius) * 100 <= 1 ? "pass" : "fail",
      },
      {
        metric: "速率漂移：离散施加 qv×B 会让 |v| 微增（磁力本不做功）——要用步长律来判，而不是把容差放大",
        drift_pct_dt: Number(driftFine.toFixed(3)),
        drift_pct_dt_over_4: Number(driftQuarter.toFixed(3)),
        rule: "dt/4 的漂移 ≤ 0.5% 且约为 dt 的 1/4（证明是 O(dt) 离散产物）",
        verdict: driftQuarter <= 0.5 && driftQuarter >= driftFine / 6 && driftQuarter <= driftFine / 2.5 ? "pass" : "fail",
      },
      {
        metric: "旋向：q>0、B 沿 +z 时应为顺时针（turned < 0）",
        turned_rad: Number(r.turned.toFixed(5)),
        verdict: Math.sign(r.turned) === -1 ? "pass" : "fail",
      },
    ],
  });
}

// ② 电荷反号 ⇒ 旋向必须反过来（对符号敏感，不是只看半径）
{
  const B = { x: 0, y: 0, z: BZ };
  const TAnalytic = (2 * Math.PI * mEff) / (Math.abs(Q) * BZ);
  const pos = run({ q: Q, B, v0: { x: V0, y: 0, z: 0 }, seconds: TAnalytic / 2 });
  const neg = run({ q: -Q, B, v0: { x: V0, y: 0, z: 0 }, seconds: TAnalytic / 2 });
  results.push({
    id: "bfield-charge-sign",
    title: "电荷符号 ↔ 旋向：q=+1 vs q=−1",
    engine: { turned_pos_q: +pos.turned.toFixed(5), turned_neg_q: +neg.turned.toFixed(5) },
    checks: [
      {
        metric: "两者符号相反且幅值相当",
        verdict: Math.sign(pos.turned) === -Math.sign(neg.turned) && Math.abs(Math.abs(pos.turned) - Math.abs(neg.turned)) < 0.05 ? "pass" : "fail",
      },
    ],
    formula: "F = qv×B ⇒ 改变 q 的符号就是改变回转方向",
  });
}

// ③ 螺旋：给一个平行于 B 的速度分量，半径只看 v⊥，螺距 = v∥·T
{
  const B = { x: 0, y: 0, z: BZ };
  const vpar = 1.5;
  const TAnalytic = (2 * Math.PI * mEff) / (Math.abs(Q) * BZ);
  const r = run({ q: Q, B, v0: { x: V0, y: 0, z: vpar }, seconds: TAnalytic });
  const fit = fitCircle(r.pts);
  const rAnalytic = (mEff * V0) / (Math.abs(Q) * BZ);
  const dz = r.pts[r.pts.length - 1].p.z - r.pts[0].p.z;
  const tOneTurn = (2 * Math.PI / Math.abs(r.turned)) * r.tEnd;
  results.push({
    id: "bfield-helix-pitch",
    title: "螺旋运动：v⊥ 决定半径、v∥ 决定螺距",
    engine: { dz_one_turn: +dz.toFixed(5), fit_radius: +fit.radius.toFixed(5), turned_rad: +r.turned.toFixed(5) },
    formula: "螺距 = v∥·T（T 用引擎实测的转角周期，不用解析 T），半径仍 = mv⊥/(|q|B)",
    checks: [
      near("半径 (m)", fit.radius, rAnalytic, 2),
      near("一圈沿 B 前进的距离 (m)", dz, vpar * tOneTurn, 2),
    ],
  });
}

// ④ 对照组：q=0 时不该有弯曲；同时看步长敏感度（模板要给出「步长 ≤ T/几百」的约束）
{
  const B = { x: 0, y: 0, z: BZ };
  const TAnalytic = (2 * Math.PI * mEff) / (Math.abs(Q) * BZ);
  const rAnalytic = (mEff * V0) / (Math.abs(Q) * BZ);
  const free = run({ q: 0, B, v0: { x: V0, y: 0, z: 0 }, seconds: TAnalytic, lorentz: false });
  const lastFree = free.pts[free.pts.length - 1].p;
  const curved = run({ q: Q, B, v0: { x: V0, y: 0, z: 0 }, seconds: TAnalytic });
  const fine = fitCircle(curved.pts).radius;
  const coarse = runCoarse();
  const fineRel = (Math.abs(fine - rAnalytic) / rAnalytic) * 100;
  const coarseRel = (Math.abs(coarse.radius - rAnalytic) / rAnalytic) * 100;
  results.push({
    id: "bfield-control-and-stepsize",
    title: "对照组与步长敏感度",
    engine: {
      q0_lateral_deviation_m: +Math.abs(lastFree.y).toFixed(9),
      q0_straight_run_m: +lastFree.x.toFixed(4),
      fine_radius: +fine.toFixed(5),
      coarse_radius: +coarse.radius.toFixed(5),
      coarse_steps_per_turn: coarse.stepsPerTurn,
    },
    formula: "q=0 ⇒ 直线；半径误差随步长变化 ⇒ 模板必须约束步长",
    checks: [
      {
        metric: "q=0 时侧向偏移≈0",
        measured_m: Number(Math.abs(lastFree.y).toFixed(9)),
        tolerance_m: 1e-9,
        verdict: Math.abs(lastFree.y) < 1e-9 ? "pass" : "fail",
      },
      {
        metric: "细步长在容差内，且粗步长偏差明显更大（说明判据对步长敏感）",
        fine_rel_pct: +fineRel.toFixed(3),
        coarse_rel_pct: +coarseRel.toFixed(3),
        rule: "fine ≤ 2% 且 coarse > 4×fine",
        verdict: fineRel <= 2 && coarseRel > 4 * fineRel ? "pass" : "fail",
      },
    ],
  });
}

function runCoarse() {
  // 与细步长同一物理量，但每步 1/60 s（一圈约 40 步），用来量化「步长不够细会怎样」
  const world = new R.World({ x: 0, y: 0, z: 0 });
  world.timestep = 1 / 60;
  const desc = R.RigidBodyDesc.dynamic().setTranslation(0, 0, 0).setLinvel(V0, 0, 0).setLinearDamping(0).setGravityScale(0);
  desc.setAdditionalMass(M_REQ, true);
  const rb = world.createRigidBody(desc);
  const TAnalytic = (2 * Math.PI * mEff) / (Math.abs(Q) * BZ);
  const n = Math.round(TAnalytic / (1 / 60));
  const pts = [];
  for (let i = 0; i < n; i++) {
    const v = rb.linvel();
    const f = cross(v, { x: 0, y: 0, z: BZ });
    rb.resetForces(true);
    rb.addForce({ x: Q * f.x, y: Q * f.y, z: Q * f.z }, true);
    world.step();
    const p = rb.translation();
    pts.push({ p: { x: p.x, y: p.y, z: p.z } });
  }
  const fit = fitCircle(pts);
  world.free();
  return { radius: fit.radius, stepsPerTurn: n };
}

for (const r of results) r.verdict = r.checks.every((c) => c.verdict === "pass") ? "pass" : "fail";
const pass = results.filter((r) => r.verdict === "pass").length;
const payload = {
  generated_at: new Date().toISOString(),
  engine: `@dimforge/rapier3d-compat ${R.version()}（无头 world.step，dt=${DT}s；洛伦兹力由脚本每步 qv×B 施加）`,
  run_command: "node source/library/field3d_lab.mjs --json",
  pass,
  fail: results.length - pass,
  calibrated_mass: mEff,
  results,
};
if (process.argv.includes("--json")) fs.writeFileSync(OUT, JSON.stringify(payload, null, 2), "utf-8");
for (const r of results) {
  console.log(`[${r.verdict}] ${r.id}`);
  for (const c of r.checks) console.log(`    ${c.verdict === "pass" ? "✓" : "✗"} ${c.metric}${c.measured !== undefined ? ` · 实测 ${c.measured}` : ""}`);
}
console.log(`\n${pass}/${results.length} pass · 标定质量 ${mEff.toFixed(6)} kg（请求 ${M_REQ}）`);
process.exit(pass === results.length ? 0 : 1);
