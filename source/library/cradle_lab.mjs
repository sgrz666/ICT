// 牛顿摆的无头验收：这次不自己造碰撞，直接用上游 myPhysicsLab 自带的摆模型
// （NewtonsCradleApp.make 造 5 个 Scrim 摆 + ContactSim + CollisionAdvance 事件式碰撞）。
//
// 为什么要换引擎：collisions_lab 已经证明 Matter 与 Rapier 两条线都复现不了「n 进 n 出」
// （Matter 自由-自由弹性正碰把 10 J 吃到 1.21 J；Rapier 5 球一列被撞后 4 球同动）。
// myPhysicsLab 的 2D 引擎是「先找碰撞时刻、再按冲量解」的事件驱动式，
// 这才是牛顿摆教学模型该有的解法，所以这条线值得单独验，而不是接着硬调前两个引擎。
//
// 跑法：node source/library/cradle_lab.mjs [--json]
import fs from "node:fs";
import path from "node:path";
import { fileURLToPath } from "node:url";

const here = path.dirname(fileURLToPath(import.meta.url));
const build = path.join(here, "..", "upstream", "myphysicslab", "build");
const mod = (rel) => "file://" + path.join(build, rel).replace(/\\/g, "/");
const OUT = path.join(here, "cradle-lab-evidence.json");

if (!fs.existsSync(build)) {
  console.log('build/ 不存在：先跑 cd source/upstream/myphysicslab && npm install --no-save typescript && npx tsc');
  process.exit(1);
}
fs.writeFileSync(path.join(build, "package.json"), '{\n  "type": "module"\n}\n');
globalThis.MPL_BUILD_TIME = "headless-lab";
globalThis.MPL_LOCALE = "en";

const { ContactSim } = await import(mod("lab/engine2D/ContactSim.js"));
const { CollisionAdvance } = await import(mod("lab/model/CollisionAdvance.js"));
const { DampingLaw } = await import(mod("lab/model/DampingLaw.js"));
const { GravityLaw } = await import(mod("lab/model/GravityLaw.js"));
const { JointUtil } = await import(mod("lab/engine2D/JointUtil.js"));
const { Scrim } = await import(mod("lab/engine2D/Scrim.js"));
const { Shapes } = await import(mod("lab/engine2D/Shapes.js"));
const { Vector } = await import(mod("lab/util/Vector.js"));

// 上游的摆阵列工厂是静态方法，不碰 DOM；万一 App 模块在 Node 里 import 不动，
// 就用下面这份逐行等价的复制（来源：build/sims/engine2D/NewtonsCradleApp.js 的 static make）
let makeCradle, cradleSource;
try {
  const { NewtonsCradleApp } = await import(mod("sims/engine2D/NewtonsCradleApp.js"));
  makeCradle = (sim, opts) => NewtonsCradleApp.make(sim, opts);
  cradleSource = "上游 NewtonsCradleApp.make（原函数）";
} catch (err) {
  makeCradle = (sim, options) => {
    const n = options.numBods;
    const between = sim.getDistanceTol() / 2 + options.gapDistance;
    let x = -(n * 2 * options.radius + (n - 1) * between) / 2 + options.radius;
    for (let i = 0; i < n; i++) {
      const body = Shapes.makePendulum(0.05, options.stickLength, options.radius, "pendulum" + (i + 1));
      body.setAngle(0);
      sim.addBody(body);
      JointUtil.attachRigidBody(sim, Scrim.getScrim(), new Vector(x, 2), body, new Vector(0, options.stickLength), 1);
      body.setZeroEnergyLevel();
      sim.alignConnectors();
      x += body.getWidth() + between;
    }
    sim.getBody("pendulum1").setAngle(options.startAngle);
    sim.alignConnectors();
  };
  cradleSource = "上游 make 的等价复制（App 模块 import 失败：" + String(err.message).slice(0, 60) + "）";
}

const G = 32; // 上游 NewtonsCradleApp 用的重力（ft/s²）
const START = -Math.PI / 4;

/** 摆的角读数以 6 变量/体 的 VarsList 为准：+4 = θ、+5 = θ̇（与上游 graphSetup 同一口径） */
function readAngles(bodies, sim) {
  const vals = sim.getVarsList().getValues();
  return bodies.map((b) => {
    const idx = b.getVarsIndex();
    return { name: b.getName(), theta: vals[idx + 4], omega: vals[idx + 5] };
  });
}

function run({ n = 5, stickLength = 3, radius = 0.6, gap = 0, elasticity = 1, damping = 0, released = [0], startAngle = START, seconds = 10, dt = 1 / 240 }) {
  const sim = new ContactSim();
  const advance = new CollisionAdvance(sim);
  advance.setJointSmallImpacts(false);
  const simList = sim.getSimList();
  const dampingLaw = new DampingLaw(damping, 0.15, simList);
  const gravityLaw = new GravityLaw(G, simList);
  sim.addForceLaw(dampingLaw);
  dampingLaw.connect(simList);
  sim.addForceLaw(gravityLaw);
  gravityLaw.connect(simList);
  makeCradle(sim, { stickLength, radius, gapDistance: gap, numBods: n, startAngle });
  sim.setElasticity(elasticity); // 上游 config() 的顺序：先摆好体，再设弹性（早设会报 setElasticity: no bodies）
  for (const i of released) sim.getBody("pendulum" + (i + 1)).setAngle(startAngle);
  sim.alignConnectors();
  sim.saveInitialState();
  const bodies = [];
  for (let i = 1; i <= n; i++) bodies.push(sim.getBody("pendulum" + i));
  const steps = Math.round(seconds / dt);
  const series = [];
  for (let s = 0; s < steps; s++) {
    advance.advance(dt); // CollisionAdvance 的步进方法就叫 advance(timeStep)
    series.push({ t: (s + 1) * dt, balls: readAngles(bodies, sim), energy: sim.getEnergyInfo().getTotalEnergy() });
  }
  return { sim, series, dt, seconds, n, elasticity };
}

/** 每颗摆的峰值 |θ|（跳过前 0.5 s 的释放段） */
function peaks(series, n) {
  const out = new Array(n).fill(0);
  const at = new Array(n).fill(null);
  for (const row of series) {
    if (row.t < 0.5) continue;
    for (let i = 0; i < n; i++) {
      const a = Math.abs(row.balls[i].theta);
      if (a > out[i]) { out[i] = a; at[i] = row.t; }
    }
  }
  return { mag: out, time: at };
}

const results = [];
const near = (metric, measured, expected, tolPct) => {
  const rel = expected === 0 ? measured : Math.abs((measured - expected) / expected) * 100;
  return { metric, measured: +measured.toPrecision(6), analytic: +expected.toPrecision(6), rel_error_pct: +rel.toFixed(3), tolerance_pct: tolPct, verdict: rel <= tolPct ? "pass" : "fail" };
};

// ① 先验摆本身对不对：同一条摆，小角与大角的周期比应当是 1 + θ0²/16（不依赖引擎的惯量读数）
{
  const measurePeriod = (startAngle, seconds = 8) => {
    const s = run({ n: 1, released: [], startAngle, seconds, dt: 1 / 480 });
    const cross = [];
    for (let i = 1; i < s.series.length; i++) if (s.series[i - 1].balls[0].theta < 0 && s.series[i].balls[0].theta >= 0) cross.push(s.series[i].t);
    if (cross.length < 2) return { T: NaN, crossings: cross.length };
    return { T: cross[cross.length - 1] - cross[cross.length - 2], crossings: cross.length };
  };
  const small = measurePeriod(-0.05);
  const big = measurePeriod(START);
  const ratio_measured = big.T / small.T;
  const ratio_analytic = 1 + START * START / 16; // 一级大角度修正（与引擎无关的解析式）
  results.push({
    id: "cradle-pendulum-isochrony",
    title: "先验摆：θ0=45° 的周期比小角只长 1 + θ0²/16（碰撞判据的前提）",
    engine: { T_small_angle: +small.T.toFixed(6), T_45deg: +big.T.toFixed(6), crossings: [small.crossings, big.crossings], ratio_measured: +ratio_measured.toFixed(6) },
    formula: "T(θ0)/T(0) ≈ 1 + θ0²/16；θ0 = π/4 ⇒ 1.015421（不读引擎自报的周期或惯量）",
    checks: [near("大角/小角周期比", ratio_measured, ratio_analytic, 3)],
  });
}

// ② 1 进 1 出：交接完成后，首球与中间球都得停在原位，末球摆到释放角
{
  const s = run({ n: 5, released: [0], seconds: 10 });
  const p = peaks(s.series, 5);
  const thr = 0.5 * Math.abs(START);
  const tTransfer = s.series.find((r) => r.t > 0.5 && Math.abs(r.balls[4].theta) > thr)?.t ?? NaN;
  const win = s.series.filter((r) => r.t >= tTransfer && r.t <= tTransfer + 0.35);
  const rest = (i) => Math.max(...win.map((r) => Math.abs(r.balls[i].theta)));
  const e0 = s.series[0].energy, eMax = Math.max(...s.series.map((r) => r.energy));
  results.push({
    id: "cradle-one-in-one-out",
    title: "牛顿摆「一进一出」：末球峰值角回到释放角，交接后首球与中间球停在原位",
    engine: { startAngle: +START.toFixed(5), peaks: p.mag.map((v) => +v.toFixed(5)), transfer_at_s: +tTransfer.toFixed(4), residual_after_transfer: { ball1: +rest(0).toFixed(5), mids: [1, 2, 3].map((i) => +rest(i).toFixed(5)) }, energy_start: +e0.toFixed(5), energy_max: +eMax.toFixed(5) },
    formula: "等质量弹性碰撞链 ⇒ 末球带走全部动量与动能 ⇒ 峰值角 = 释放角，其余球碰撞后速度归零",
    checks: [
      near("末球峰值角 / 释放角", p.mag[4] / Math.abs(START), 1, 8),
      { metric: "交接后 0.35 s 内首球几乎不动（<5% 释放角）", ball1: +rest(0).toFixed(5), verdict: rest(0) < 0.05 * Math.abs(START) ? "pass" : "fail" },
      { metric: "交接后中间三球几乎不动（<5% 释放角）", mids: [1, 2, 3].map((i) => +rest(i).toFixed(5)), verdict: Math.max(...[1, 2, 3].map(rest)) < 0.05 * Math.abs(START) ? "pass" : "fail" },
      { metric: "总能量不增（elasticity=1 也不能凭空长能量）", max_over_start: +(eMax / e0).toFixed(6), verdict: eMax <= e0 * 1.02 ? "pass" : "fail" },
    ],
  });
}

// ③ 传递时刻的角速度交接：末球出射 |ω| 与首球入射 |ω| 相当（动量守恒在等质量链上的表现）
{
  const s = run({ n: 5, released: [0], seconds: 10 });
  let incident = 0, tHit = 0;
  for (let i = 1; i < s.series.length; i++) {
    const w = s.series[i].balls[0].omega;
    if (Math.abs(w) > Math.abs(incident)) { incident = w; tHit = s.series[i].t; }
    if (w * incident < 0 && Math.abs(incident) > 1e-6) break; // 首球反向 ⇒ 刚撞完
  }
  const window = s.series.filter((r) => r.t > tHit && r.t < tHit + 0.25);
  const out = window.reduce((a, r) => (Math.abs(r.balls[4].omega) > Math.abs(a) ? r.balls[4].omega : a), 0);
  results.push({
    id: "cradle-velocity-transfer",
    title: "碰撞交接：首球最大入射角速度与末球出射角速度相当",
    engine: { incident_omega: +incident.toFixed(6), at_s: +tHit.toFixed(4), outgoing_omega: +out.toFixed(6) },
    formula: "等质量弹性正碰交换速度 ⇒ |ω_out| ≈ |ω_in|（摆长相同 ⇒ 线速度同量纲）",
    checks: [near("|ω_末球| / |ω_首球|", Math.abs(out) / Math.abs(incident), 1, 6)],
  });
}

// ④ 2 进 2 出：释放两颗 ⇒ 末两颗摆出去，第三颗留下
{
  const s = run({ n: 5, released: [0, 1], seconds: 12 });
  const p = peaks(s.series, 5);
  results.push({
    id: "cradle-two-in-two-out",
    title: "「二进二出」：释放两颗 ⇒ 只有末两颗摆出去",
    engine: { released: 2, peaks: p.mag.map((v) => +v.toFixed(5)), out_ratio: +((p.mag[4] + p.mag[3]) / (2 * Math.abs(START))).toFixed(4), middle_peak: +p.mag[2].toFixed(5) },
    formula: "动量与动能同时守恒 ⇒ n 进必 n 出（这就是为什么 1 进 5 出不存在）",
    checks: [
      { metric: "末两颗都摆到接近释放角（>75%）", last_two: p.mag.slice(3).map((v) => +v.toFixed(5)), verdict: p.mag[3] > 0.75 * Math.abs(START) && p.mag[4] > 0.75 * Math.abs(START) ? "pass" : "fail" },
      { metric: "中间那颗留在原位（<25%）", middle: +p.mag[2].toFixed(5), verdict: p.mag[2] < 0.25 * Math.abs(START) ? "pass" : "fail" },
    ],
  });
}

// ⑤ 弹性系数对照组：e=0.5 时「n 进 n 出」必须塌掉 —— 否则说明判据对参数不敏感，读数就是假的
{
  const soft = run({ n: 5, released: [0], elasticity: 0.5, seconds: 10 });
  const p = peaks(soft.series, 5);
  const mids = Math.max(...p.mag.slice(1, 4));
  results.push({
    id: "cradle-elasticity-control",
    title: "对照组：elasticity 1→0.5 ⇒ 末球峰值掉到释放角的一小半、中间球不再静止",
    engine: { elasticity: 0.5, peaks: p.mag.map((v) => +v.toFixed(5)), last_peak_ratio_vs_release: +(p.mag[4] / Math.abs(START)).toFixed(4), middle_max_ratio: +(mids / Math.abs(START)).toFixed(4), compare_elastic_1: "同一场景 elasticity=1 时中间球峰值恒为 0（见结果 ②）" },
    formula: "非弹性碰撞动能不守恒 ⇒ 末球拿不满速度、中间球必然跟着动",
    checks: [
      { metric: "末球峰值角 < 80% 释放角", ratio: +(p.mag[4] / Math.abs(START)).toFixed(4), verdict: p.mag[4] < 0.8 * Math.abs(START) ? "pass" : "fail" },
      { metric: "中间球不再静止（>2% 释放角；弹性=1 时实测是 0）", middle_max: +mids.toFixed(5), verdict: mids > 0.02 * Math.abs(START) ? "pass" : "fail" },
    ],
  });
}

for (const r of results) r.verdict = r.checks.every((c) => c.verdict === "pass") ? "pass" : "fail";
const pass = results.filter((r) => r.verdict === "pass").length;
const payload = {
  generated_at: new Date().toISOString(),
  engine: `myPhysicsLab ContactSim + CollisionAdvance（事件式碰撞）+ ${cradleSource}；g=${G}、stickLength=3、radius=0.6、elasticity 默认 1、dt=1/240 s`,
  run_command: "node source/library/cradle_lab.mjs --json",
  pass,
  fail: results.length - pass,
  results,
};
if (process.argv.includes("--json")) fs.writeFileSync(OUT, JSON.stringify(payload, null, 2), "utf-8");
for (const r of results) {
  console.log(`[${r.verdict}] ${r.id}`);
  for (const c of r.checks) console.log(`    ${c.verdict === "pass" ? "✓" : "✗"} ${c.metric}${c.measured !== undefined ? ` · 实测 ${c.measured} vs 理论 ${c.analytic}（${c.rel_error_pct}%）` : ` · ${JSON.stringify(c).replace(/^{"metric":"[^"]+",?/, "")}`}`);
}
console.log(`\n${pass}/${results.length} pass · 摆阵列来源：${cradleSource}`);
process.exit(pass === results.length ? 0 : 1);
