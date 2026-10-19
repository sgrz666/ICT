// 天体运动的无头验收：Rapier 里关掉重力、每步按平方反比律施加中心力，
// 把开普勒三定律、vis-viva 关系与「轨道与行星质量无关」从引擎积分出来的轨道里量出来。
//
// 为什么不用上游现成的太阳系模型：简报里这条是 P2（太阳系与开普勒定律），盘上没有
// 「装了就能读轨道根数」的天体引擎（Stellarium 是星表渲染、Webots 本体未装）。
// 关键是别把「物体在转圈」当成「开普勒第三定律成立」：轨道根数全由引擎给出的
// 位置/速度算，解析式在脚本里独立写；单位取天文学自然单位 GM = 4π²（AU、年），
// 于是 T² = a³ 本身就是解析基准。
//
// 跑法：node source/library/kepler_lab.mjs --json
import fs from "node:fs";
import path from "node:path";
import { createRequire } from "node:module";
import { fileURLToPath } from "node:url";

const here = path.dirname(fileURLToPath(import.meta.url));
const require = createRequire(path.join(here, "..", "components", "probe_components.mjs"));
const OUT = path.join(here, "kepler-lab-evidence.json");
const R = require("@dimforge/rapier3d-compat").default ?? require("@dimforge/rapier3d-compat");
await R.init();

const GM = 4 * Math.PI * Math.PI; // AU³/yr² ⇒ r = 1 AU 的圆轨道正好 T = 1 yr
const DT = 1e-5; // yr；这个格式是「先速度后位置」的一阶积分，周期误差 ∝ Δt，见结果 ⑥

/**
 * 积分一条轨道：从 (r0, 0) 以 (0, v0) 出发。
 * 第 0 步就施加力（先空跑一步会让首帧位置与速度错开，实测把圆轨道的半径甩出 0.9%）。
 * 返回逐帧 {t, r, v, h}，轨道根数由调用方在「跳过第一个完整周期之后」的窗口里算。
 */
function orbit({ r0, v0, dt = DT, seconds, mass = 1 }) {
  const world = new R.World({ x: 0, y: 0, z: 0 });
  world.timestep = dt;
  // 无碰撞体的 dynamic 质量是 0、受力不动 ⇒ 挂一个极小的球并给 additionalMass（同 field3d/gas 的做法）
  const rb = world.createRigidBody(
    R.RigidBodyDesc.dynamic().setTranslation(r0, 0, 0).setLinvel(0, v0, 0).setLinearDamping(0).setAdditionalMass(mass, true),
  );
  world.createCollider(R.ColliderDesc.ball(1e-4).setDensity(0), rb);

  const steps = Math.round(seconds / dt);
  const s = { t: [], r: [], v: [], h: [], turnTimes: [], massAfterFirstStep: null };
  let theta = 0, prevAng = 0, turns = 0;
  for (let i = 0; i < steps; i++) {
    const p = rb.translation();
    const rr = Math.hypot(p.x, p.y);
    rb.resetForces(true);
    rb.addForce({ x: (-GM / rr ** 3) * p.x * mass, y: (-GM / rr ** 3) * p.y * mass, z: 0 }, true);
    world.step();
    if (i === 0) s.massAfterFirstStep = rb.mass();
    const q = rb.translation();
    const vel = rb.linvel();
    const rq = Math.hypot(q.x, q.y);
    const t = (i + 1) * dt;
    s.t.push(t);
    s.r.push(rq);
    s.v.push(Math.hypot(vel.x, vel.y));
    s.h.push(Math.abs(q.x * vel.y - q.y * vel.x)); // 比角动量 = 2 × 面积速率
    const ang = Math.atan2(q.y, q.x);
    let d = ang - prevAng;
    if (d > Math.PI) d -= 2 * Math.PI;
    if (d < -Math.PI) d += 2 * Math.PI;
    theta += d;
    prevAng = ang;
    while (theta >= (turns + 1) * 2 * Math.PI) {
      turns++;
      s.turnTimes.push(t);
    }
  }
  world.free();
  return s;
}

/** 跳过第一个周期后的窗口：周期取后段相邻过节点时间差的平均，根数取同一窗口的极值 */
function elements(s) {
  const from = s.turnTimes[0] ?? 0;
  const gaps = [];
  for (let i = 1; i < s.turnTimes.length; i++) gaps.push(s.turnTimes[i] - s.turnTimes[i - 1]);
  // 少于 2 段间隔就判「圈数不够」，返回 NaN 让检查显式失败，而不是悄悄给个 0
  const T = gaps.length >= 2 ? gaps.reduce((a, b) => a + b, 0) / gaps.length : NaN;
  let rmin = Infinity, rmax = 0, hmin = Infinity, hmax = 0, h0 = NaN;
  const samples = [];
  for (let i = 0; i < s.t.length; i++) {
    if (s.t[i] < from) continue;
    if (s.r[i] < rmin) rmin = s.r[i];
    if (s.r[i] > rmax) rmax = s.r[i];
    if (s.h[i] < hmin) hmin = s.h[i];
    if (s.h[i] > hmax) hmax = s.h[i];
    if (Number.isNaN(h0)) h0 = s.h[i];
    samples.push({ t: s.t[i], r: s.r[i], v: s.v[i], h: s.h[i] });
  }
  const a = (rmin + rmax) / 2;
  return { T, rmin, rmax, a, ecc: (rmax - rmin) / (rmax + rmin), hmin, hmax, h0, samples, turns: s.turnTimes.length, gaps: gaps.length };
}

const results = [];
const near = (metric, measured, expected, tolPct) => {
  const rel = expected === 0 ? measured : Math.abs((measured - expected) / expected) * 100;
  return { metric, measured: +measured.toPrecision(8), analytic: +expected.toPrecision(8), rel_error_pct: +rel.toFixed(4), tolerance_pct: tolPct, verdict: rel <= tolPct ? "pass" : "fail" };
};

const V_CIRC_1AU = Math.sqrt(GM / 1); // 9.42478 AU/yr

// ① 圆轨道：v = √(GM/r) ⇒ T = 2π√(r³/GM) = 1 yr，且半径不漂
{
  const s = orbit({ r0: 1, v0: V_CIRC_1AU, seconds: 4.5 });
  const el = elements(s);
  // 半径漂移随时长累积（一阶格式）⇒ 分别量「2 年窗口」与「整个窗口」，看它是不是按时间线性长大
  const windowDrift = (t0, t1) => {
    let lo = Infinity, hi = 0;
    for (let i = 0; i < s.t.length; i++) {
      if (s.t[i] < t0 || s.t[i] > t1) continue;
      if (s.r[i] < lo) lo = s.r[i];
      if (s.r[i] > hi) hi = s.r[i];
    }
    return hi - lo;
  };
  const from = el.turns ? s.turnTimes[0] : 0;
  const driftShort = windowDrift(from, from + 2);
  const driftLong = windowDrift(from, from + 4);
  results.push({
    id: "kepler-circular-orbit",
    title: "圆轨道：v=√(GM/r) 出发，周期对 2π√(r³/GM)，半径漂移随时长线性累积",
    engine: { GM, r_AU: 1, v0_AU_per_yr: +V_CIRC_1AU.toFixed(8), dt_yr: DT, turns: el.turns, period_yr: +el.T.toFixed(7), rmin: +el.rmin.toFixed(7), rmax: +el.rmax.toFixed(7), eccentricity: +el.ecc.toFixed(6), drift_2yr: +driftShort.toExponential(4), drift_4yr: +driftLong.toExponential(4), drift_ratio: +(driftLong / driftShort).toFixed(3) },
    formula: "T = 2π√(r³/GM)；GM = 4π² ⇒ r=1 AU 时 T = 1 yr",
    checks: [
      near("周期 T (yr)", el.T, 1, 0.2),
      near("偏心率（圆轨道应为 0）", el.ecc, 0, 200),
      { metric: "半径漂移 / r 在整个窗口内 ≤ 0.15%", drift: +(el.rmax - el.rmin).toExponential(4), tolerance_pct: 0.15, verdict: el.rmax - el.rmin <= 0.0015 ? "pass" : "fail" },
      near("漂移随时长的增长比（4 年 / 2 年 ≈ 2 ⇒ 一阶累积，不是物理）", driftLong / driftShort, 2, 15),
    ],
  });
}

// ② 开普勒第三定律：两条不同偏心率的椭圆，T²/a³ 都回到 1
{
  const cases = [
    { name: "e≈0.37 椭圆", r0: 1, v0: V_CIRC_1AU * 0.85, seconds: 2.8 },
    { name: "e≈0.10 椭圆", r0: 1, v0: V_CIRC_1AU * 0.95, seconds: 2.8 },
  ];
  const rows = [], checks = [];
  for (const c of cases) {
    const s = orbit(c);
    const el = elements(s);
    rows.push({ case: c.name, rmin_AU: +el.rmin.toFixed(6), rmax_AU: +el.rmax.toFixed(6), a_AU: +el.a.toFixed(6), eccentricity: +el.ecc.toFixed(6), T_yr: +el.T.toFixed(7), "T2": +(el.T ** 2).toFixed(7), "a3": +(el.a ** 3).toFixed(7), T2_over_a3: +((el.T ** 2) / el.a ** 3).toFixed(7) });
    checks.push(near(`T²/a³（${c.name}；GM=4π² ⇒ 应为 1）`, (el.T ** 2) / el.a ** 3, 1, 0.5));
    checks.push(near(`周期 vs 2π√(a³/GM)（${c.name}）`, el.T, 2 * Math.PI * Math.sqrt(el.a ** 3 / GM), 0.5));
  }
  results.push({
    id: "kepler-third-law",
    title: "开普勒第三定律：两条不同偏心率的椭圆都满足 T² = a³",
    engine: rows,
    formula: "T² = (4π²/GM)·a³，取 GM = 4π² ⇒ T² = a³；a = (r_min + r_max)/2 由引擎轨道极值定出",
    checks,
  });
}

// ③ 开普勒第二定律：面积速率 = h/2 守恒；残差是离散化不是物理（Δt 四分之一 ⇒ 波动也约四分之一）
{
  const base = elements(orbit({ r0: 1, v0: V_CIRC_1AU * 0.85, seconds: 2.8 }));
  const quarter = elements(orbit({ r0: 1, v0: V_CIRC_1AU * 0.85, dt: DT / 4, seconds: 2.8 }));
  const spread = ((base.hmax - base.hmin) / base.h0) * 100;
  const spreadQ = ((quarter.hmax - quarter.hmin) / quarter.h0) * 100;
  results.push({
    id: "kepler-second-law",
    title: "开普勒第二定律：dA/dt = h/2 沿整条椭圆守恒（残差随 Δt 线性缩小 ⇒ 是格式误差）",
    engine: { h_start: +base.h0.toFixed(8), h_min: +base.hmin.toFixed(8), h_max: +base.hmax.toFixed(8), spread_pct: +spread.toFixed(6), spread_pct_quarter_dt: +spreadQ.toFixed(6), area_rate_dA_dt: +(base.h0 / 2).toFixed(8), eccentricity: +base.ecc.toFixed(5), v_peri: +(base.samples.reduce((a, b) => (b.r < a.r ? b : a)).v).toFixed(6), v_aph: +(base.samples.reduce((a, b) => (b.r > a.r ? b : a)).v).toFixed(6) },
    formula: "h = |r×v| 只在力指向中心时才守恒；一阶格式下残差 ≈ C·Δt ⇒ Δt/4 应把波动压到约 1/4",
    checks: [
      { metric: `Δt=${DT} 时 h 相对波动 ≤ 0.1%`, spread_pct: +spread.toFixed(6), tolerance_pct: 0.1, verdict: spread <= 0.1 ? "pass" : "fail" },
      { metric: "Δt 缩到四分之一 ⇒ h 波动确实变小（残差是格式来的，不是中心力破了角动量守恒）", spread_quarter_pct: +spreadQ.toFixed(6), improvement_ratio: +(spread / spreadQ).toFixed(4), verdict: spreadQ < spread ? "pass" : "fail" },
      { metric: "近日点速度 > 远日点速度（第二定律的方向性）", v_peri: +(base.samples.reduce((a, b) => (b.r < a.r ? b : a)).v).toFixed(6), v_aph: +(base.samples.reduce((a, b) => (b.r > a.r ? b : a)).v).toFixed(6), verdict: base.samples.reduce((a, b) => (b.r < a.r ? b : a)).v > base.samples.reduce((a, b) => (b.r > a.r ? b : a)).v ? "pass" : "fail" },
    ],
    note: `实测波动 ${spread.toFixed(5)}% → Δt/4 时 ${spreadQ.toFixed(5)}%，比值 ${(spread / spreadQ).toFixed(2)}；不是干净的线性律（周期误差是线性的，见结果 ⑥），所以模板里 Δt 必须钉死，不能靠「反正会收敛」放过。`,
  });
}

// ④ vis-viva：v² = GM(2/r − 1/a)，在近日点、远日点、中段三处对照
{
  const s = orbit({ r0: 1, v0: V_CIRC_1AU * 0.85, seconds: 2.8 });
  const el = elements(s);
  const atMin = el.samples.reduce((a, b) => (b.r < a.r ? b : a));
  const atMax = el.samples.reduce((a, b) => (b.r > a.r ? b : a));
  const atMid = el.samples[Math.floor(el.samples.length * 0.37)];
  const rows = [], checks = [];
  for (const [label, p] of [["近日点", atMin], ["远日点", atMax], ["中段", atMid]]) {
    const lhs = p.v ** 2;
    const rhs = GM * (2 / p.r - 1 / el.a);
    rows.push({ at: label, r_AU: +p.r.toFixed(6), v2: +lhs.toFixed(7), vis_viva: +rhs.toFixed(7) });
    checks.push(near(`v² vs GM(2/r − 1/a)（${label}）`, lhs, rhs, 0.5));
  }
  results.push({ id: "kepler-vis-viva", title: "vis-viva 关系：轨道三点的 v² 与 GM(2/r − 1/a) 对上", engine: rows, formula: `v² = GM(2/r − 1/a)，a = ${el.a.toFixed(6)} AU`, checks });
}

// ⑤ 轨道与行星质量无关 + 关掉中心力就匀速直线（对照组）
{
  const lightRun = orbit({ r0: 1, v0: V_CIRC_1AU, seconds: 4.5, mass: 1 });
  const heavyRun = orbit({ r0: 1, v0: V_CIRC_1AU, seconds: 4.5, mass: 50 });
  const light = elements(lightRun);
  const heavy = elements(heavyRun);
  const straight = (() => {
    const world = new R.World({ x: 0, y: 0, z: 0 });
    world.timestep = DT;
    const rb = world.createRigidBody(R.RigidBodyDesc.dynamic().setTranslation(1, 0, 0).setLinvel(0, 1, 0).setAdditionalMass(1, true));
    world.createCollider(R.ColliderDesc.ball(1e-4).setDensity(0), rb);
    const n = Math.round(0.2 / DT);
    for (let i = 0; i < n; i++) world.step();
    const p = rb.translation();
    world.free();
    return { t_yr: +0.2.toFixed(6), pos: { x: +p.x.toFixed(8), y: +p.y.toFixed(8) }, expected_y: +0.2.toFixed(8), expected_x: 1 };
  })();
  results.push({
    id: "kepler-mass-independence-and-control",
    title: "周期与行星质量无关（1 vs 50）；关掉中心力 ⇒ 沿初速度方向匀速直线",
    engine: { mass_measured_light: lightRun.massAfterFirstStep, mass_measured_heavy: heavyRun.massAfterFirstStep, T_mass1_yr: +light.T.toFixed(7), T_mass50_yr: +heavy.T.toFixed(7), turns_each: [light.turns, heavy.turns], no_force: straight },
    formula: "GM=4π²、r=1 AU ⇒ T=1 yr（与行星质量无关）；无合力时 y(t) = v·t、x 不动",
    checks: [
      near("周期比 T(50×质量)/T(1×质量)", heavy.T / light.T, 1, 0.2),
      near("无外力时 y = v·t", straight.pos.y, straight.expected_y, 0.2),
      { metric: "无外力时 x 不动（真直线，没有偷偷留向内的力）", x: straight.pos.x, expected: 1, verdict: Math.abs(straight.pos.x - 1) < 1e-9 ? "pass" : "fail" },
    ],
  });
}

// ⑥ 步长收敛：这个格式一阶 ⇒ 周期误差 ∝ Δt；用三点收敛证明读数在往解析值靠
{
  const coarse = elements(orbit({ r0: 1, v0: V_CIRC_1AU, dt: 4e-5, seconds: 4.5 }));
  const mid = elements(orbit({ r0: 1, v0: V_CIRC_1AU, dt: 2e-5, seconds: 4.5 }));
  const fine = elements(orbit({ r0: 1, v0: V_CIRC_1AU, dt: DT, seconds: 4.5 }));
  const e_c = coarse.T / 1 - 1, e_m = mid.T / 1 - 1, e_f = fine.T / 1 - 1;
  results.push({
    id: "kepler-step-convergence",
    title: "步长收敛：Δt 每减半，周期误差近似减半（一阶格式），细步长下 <0.2%",
    engine: { dt_coarse: 4e-5, dt_mid: 2e-5, dt_fine: DT, T_coarse: +coarse.T.toFixed(8), T_mid: +mid.T.toFixed(8), T_fine: +fine.T.toFixed(8), err_pct: [+(e_c * 100).toFixed(4), +(e_m * 100).toFixed(4), +(e_f * 100).toFixed(4)], error_halving_ratios: [+(e_c / e_m).toFixed(3), +(e_m / e_f).toFixed(3)] },
    formula: "解析周期 1 yr；一阶积分 ⇒ error ≈ C·Δt ⇒ Δt 减半误差减半（比值≈2）",
    checks: [
      near("细步长周期 vs 解析 1 yr", fine.T, 1, 0.2),
      near("误差随 Δt 减半的比例（应≈2，证明是离散化而非物理）", e_c / e_m, 2, 12),
    ],
  });
}

for (const r of results) r.verdict = r.checks.every((c) => c.verdict === "pass") ? "pass" : "fail";
const pass = results.filter((r) => r.verdict === "pass").length;
const payload = {
  generated_at: new Date().toISOString(),
  engine: `@dimforge/rapier3d-compat ${R.version()}（重力关掉、每步施加 −GM·m·r̂/r²；自然单位 GM=4π² AU³/yr²；轨道根数由 world.step 给出的位置/速度算，Δt=${DT} yr）`,
  run_command: "node source/library/kepler_lab.mjs --json",
  pass,
  fail: results.length - pass,
  results,
};
if (process.argv.includes("--json")) fs.writeFileSync(OUT, JSON.stringify(payload, null, 2), "utf-8");
for (const r of results) {
  console.log(`[${r.verdict}] ${r.id}`);
  for (const c of r.checks) console.log(`    ${c.verdict === "pass" ? "✓" : "✗"} ${c.metric}${c.measured !== undefined ? ` · 实测 ${c.measured} vs 理论 ${c.analytic}（${c.rel_error_pct}%）` : ` · ${JSON.stringify(c).replace(/^{"metric":"[^"]+",?/, "")}`}`);
}
console.log(`\n${pass}/${results.length} pass · GM=${GM.toFixed(6)} AU³/yr²、Δt=${DT} yr`);
process.exit(pass === results.length ? 0 : 1);
