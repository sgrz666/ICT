// 绳波的无头验收：驱动上游 myPhysicsLab 自己的 StringSim（PDE 绳模型），
// 把波速、反射反相、驻波共振与 CFL 稳定性这四件事对着解析式量出来。
//
// 为什么用上游的 StringSim 而不是自己写格子：波动这条在简报里是 P1，
// 「引擎能跑」与「改参后读数跟着变」是两件事，所以每个场景都只改上游的参数
// （tension / density / damping / timeStep），再用与实现无关的解析式判对错：
// v = √(T/μ)、固定端反射反相、f_n = n·v/(2L)、稳定性 v·Δt/Δx ≤ 1。
//
// 跑法：node source/library/wave_lab.mjs [--json]
import fs from "node:fs";
import path from "node:path";
import { fileURLToPath } from "node:url";

const here = path.dirname(fileURLToPath(import.meta.url));
const build = path.join(here, "..", "upstream", "myphysicslab", "build");
const mod = (rel) => "file://" + path.join(build, rel).replace(/\\/g, "/");
const OUT = path.join(here, "wave-lab-evidence.json");

// tsc 产物需要最近的 package.json 声明 ESM；上游 makefile 用 esbuild 注入的两个编译期全局要补
if (!fs.existsSync(build)) {
  console.log("build/ 不存在：先跑 cd source/upstream/myphysicslab && npm install --no-save typescript && npx tsc");
  process.exit(1);
}
fs.writeFileSync(path.join(build, "package.json"), '{\n  "type": "module"\n}\n');
globalThis.MPL_BUILD_TIME = "headless-lab";
globalThis.MPL_LOCALE = "en";

const { StringSim } = await import(mod("sims/pde/StringSim.js"));
const { FlatShape } = await import(mod("sims/pde/StringShapes.js"));
const { Vector } = await import(mod("lab/util/Vector.js"));

// 上游 getPoint(idx, point) 要求传一个带 setTo(x,y) 的可变点；这个版本的 Vector 是不可变的
// （全仓 grep 只有调用侧、没有 setTo 实现），所以自建最小 shim，读数仍由引擎写进来
const makePoint = () => ({ x: NaN, y: NaN, setTo(x, y) { this.x = x; this.y = y; return this; } });

const LENGTH = 13.5; // m，绳长（与上游 StringApp 一致）
const NPTS = 1001; // 网格点数 ⇒ Δx = 13.5/1000 = 0.0135 m
const DT = 0.0025; // s，上游默认步长
const AMP = 0.05; // m，驱动振幅

/** 跑一个受驱动的绳子：drive(t) 给出左端位移，同时记录中点探针与「全绳最大位移」 */
function runString({ tension, density, damping = 0, dt = DT, seconds, drive, probeIdx, sampleEvery = 25 }) {
  const sim = new StringSim(new FlatShape(LENGTH));
  sim.setNumPoints(NPTS);
  sim.setTimeStep(dt); // 会触发 reset()，所以顺序是点数→步长→(下面)张力/密度
  sim.setTension(tension);
  sim.setDensity(density);
  sim.setDamping(damping);
  sim.reset();
  const block = sim.getSimList().getPointMass("block");
  const dx = LENGTH / (NPTS - 1);
  const steps = Math.round(seconds / dt);
  const series = [];
  const probe = makePoint();
  const scan = makePoint();
  const scanIdx = [];
  for (let i = 1; i < NPTS - 1; i += sampleEvery) scanIdx.push(i);
  for (let s = 0; s < steps; s++) {
    const t = s * dt;
    const y = drive ? drive(t) : 0;
    block.setPosition(new Vector(-0.35, y)); // 左端驱动块（宽 0.7 ⇒ 起点 −0.35），advance() 只读它的 Y
    sim.advance();
    sim.getPoint(probeIdx ?? 0, probe); // x 由引擎给出（idx·length/numPoints），别自己算免得差 0.1%
    let mx = 0;
    for (const i of scanIdx) {
      sim.getPoint(i, scan);
      mx = Math.max(mx, Math.abs(scan.y));
    }
    series.push({ t: (s + 1) * dt, y: probe.y, x: probe.x, maxAbs: mx });
  }
  return { sim, series, dx, dt, tension, density, damping, steps };
}

/** 方脉冲驱动：宽度 width 秒、幅值 A，只在开头打一次 */
const pulseDrive = (width, A) => (t) => (t < width ? A : 0);

/** 在序列里找 |y| 的极值（返回 {t, y}）；from/to 为秒 */
function extremum(series, from, to) {
  let best = null;
  for (const p of series) {
    if (p.t < from || p.t > to) continue;
    if (!best || Math.abs(p.y) > Math.abs(best.y)) best = p;
  }
  return best;
}
function envelope(series, from, to, key = "y") {
  let m = 0;
  for (const p of series) if (p.t >= from && p.t <= to) m = Math.max(m, Math.abs(p[key]) || m);
  return Number.isFinite(m) ? m : m;
}

const results = [];
const near = (metric, measured, expected, tolPct) => {
  const rel = expected === 0 ? measured : Math.abs((measured - expected) / expected) * 100;
  return { metric, measured: +measured.toPrecision(7), analytic: +expected.toPrecision(7), rel_error_pct: +rel.toFixed(3), tolerance_pct: tolPct, verdict: rel <= tolPct ? "pass" : "fail" };
};

const probeIdx = Math.round(NPTS / 2);
const probeX = (probeIdx * LENGTH) / NPTS; // 与上游 getPoint 的 x 定义一致（idx·length/numPoints）

// ① 波速律 v = √(T/μ)：方脉冲从左端出发，测中点处脉冲峰到达时刻
{
  const T = 10, mu = 1;
  const width = 0.1; // s ⇒ 脉冲空间宽约 v·width = 0.316 m ≈ 23 格，足够窄又不至于被格子色散拖偏
  const r = runString({ tension: T, density: mu, seconds: 3.2, drive: pulseDrive(width, AMP), probeIdx });
  const peak = extremum(r.series, 0.5, 2.9);
  const v_measured = peak.x / (peak.t - width / 2); // 峰在中点，Launch 取脉冲中心时刻
  const v_analytic = Math.sqrt(T / mu);
  // 步长减半重跑：若两次测得的 v 差在 0.3% 内，说明读的是物理而不是格子离散化
  const r2 = runString({ tension: T, density: mu, dt: DT / 2, seconds: 3.2, drive: pulseDrive(width, AMP), probeIdx });
  const peak2 = extremum(r2.series, 0.5, 2.9);
  const v2 = peak2.x / (peak2.t - width / 2);
  results.push({
    id: "waves-string-speed",
    title: "绳波波速 v = √(T/μ)：脉冲渡越时间实测 + 步长减半复现",
    engine: { engine: "myPhysicsLab StringSim（上游 PDE 绳模型， leapfrog）", T, mu, L: LENGTH, dx: +r.dx.toFixed(6), dt: DT, probe_x: +probeX.toFixed(4), peak_t: +peak.t.toFixed(5), peak_y: +peak.y.toFixed(5), stability: +r.sim.getStability().toFixed(4), v_measured: +v_measured.toFixed(6), v_half_dt: +v2.toFixed(6) },
    formula: "v = √(T/μ)；渡越时间 = 峰值到达时刻 − 脉冲中心发射时刻",
    checks: [
      near(`v (m/s) @ T=${T} N, μ=${mu} kg/m`, v_measured, v_analytic, 2),
      near("步长减半后 v 的复现（差异应远小于物理误差）", v2 / v_measured, 1, 0.3),
    ],
  });
}

// ② 改参跟着变：μ×4 ⇒ v 减半 ⇒ 渡越时间翻倍（Agent 改 density 的硬证据）
{
  const T = 10;
  const mk = (mu) => {
    const width = 0.1;
    const r = runString({ tension: T, density: mu, seconds: 6.6, drive: pulseDrive(width, AMP), probeIdx });
    const peak = extremum(r.series, 0.5, 6.2);
    return { v: peak.x / (peak.t - width / 2), t: peak.t - width / 2 };
  };
  const a = mk(1), b = mk(4);
  results.push({
    id: "waves-string-density-law",
    title: "线密度翻倍四次 ⇒ 波速减半、渡越时间翻倍（v ∝ 1/√μ）",
    engine: { mu_1: { v: +a.v.toFixed(6), transit_s: +a.t.toFixed(5) }, mu_4: { v: +b.v.toFixed(6), transit_s: +b.t.toFixed(5) } },
    formula: "v = √(T/μ) ⇒ v(μ=4)/v(μ=1) = 1/2；渡越时间之比 = 2",
    checks: [
      near("v(μ=4)/v(μ=1)", b.v / a.v, 0.5, 2),
      near("渡越时间之比 t(μ=4)/t(μ=1)", b.t / a.t, 2, 2),
    ],
  });
}

// ③ 固定端反射反相：右端 w[N]=0 是固定端，反射脉冲必须倒相
{
  const T = 10, mu = 1;
  const width = 0.1;
  const v = Math.sqrt(T / mu);
  const t_incident = probeX / v; // 峰到中点
  const t_reflected = (2 * LENGTH - probeX) / v; // 撞右端（x=L）后回到中点
  const r = runString({ tension: T, density: mu, seconds: t_reflected + 1.2, drive: pulseDrive(width, AMP), probeIdx });
  const before = extremum(r.series, t_incident - 0.9, t_incident + 0.9);
  const after = extremum(r.series, t_reflected - 0.9, t_reflected + 0.9);
  const ratio = Math.abs(after.y) / Math.abs(before.y);
  results.push({
    id: "waves-string-reflection",
    title: "固定端反射：回到中点的脉冲峰值变号（倒相），幅度不超过入射脉冲",
    engine: { incident_peak: { t: +before.t.toFixed(5), y: +before.y.toFixed(6) }, reflected_peak: { t: +after.t.toFixed(5), y: +after.y.toFixed(6) }, expect_incident_at_s: +t_incident.toFixed(4), expect_reflected_at_s: +t_reflected.toFixed(4), right_end_BC: "上游 advance() 里 wNew[N]=0（固定端）" },
    formula: "固定端反射位移反号（自由端才同号）⇒ 读到同号说明边界条件或读数窗口在骗人",
    checks: [
      { metric: "反射峰与入射峰反号", incident_y: +before.y.toFixed(6), reflected_y: +after.y.toFixed(6), verdict: Math.sign(after.y) !== Math.sign(before.y) ? "pass" : "fail" },
      { metric: "反射峰幅度落在入射峰的 0.4~1.05 倍（格子色散只摊平不放大）", ratio: +ratio.toFixed(4), verdict: ratio >= 0.4 && ratio <= 1.05 ? "pass" : "fail" },
      near("反射峰到达时刻 vs (2L−x_probe)/v", after.t, t_reflected + width / 2, 5),
    ],
  });
}

// ④ 驻波共振：扫驱动频率，峰应落在 f_n = n·v/(2L)；探针取全绳最大位移（中点是二次模态的节点，不能只看中点）
{
  const T = 10, mu = 1;
  const v = Math.sqrt(T / mu);
  const f1 = v / (2 * LENGTH);
  const scan = [0.7, 1.0, 1.3, 2.0, 2.6].map((k) => +(k * f1).toFixed(6));
  const measure = (f) => {
    const periods = 40;
    const seconds = periods / f;
    const r = runString({ tension: T, density: mu, damping: 0.05, seconds, drive: (t) => 0.01 * Math.sin(2 * Math.PI * f * t), probeIdx });
    return envelope(r.series, seconds - 5 / f, seconds, "maxAbs"); // 最后 5 个周期的空间最大振幅
  };
  const amps = scan.map((f) => ({ f, amp: measure(f) }));
  const peak = amps.reduce((a, b) => (b.amp > a.amp ? b : a));
  const [on1, second, off] = [amps[1], amps[3], amps[2]]; // 扫频表按 0.7 / 1.0 / 1.3 / 2.0 / 2.6 × f₁ 固定顺序
  results.push({
    id: "waves-string-resonance",
    title: "驻波共振：扫频峰值落在 f₁ = v/(2L)，二次模态 f₂=2f₁ 也明显高于失谐",
    engine: { v: +v.toFixed(6), L: LENGTH, f1_Hz: +f1.toFixed(6), damping: 0.05, drive_amp: 0.01, periods: 40, sweep: amps.map((a) => ({ f_Hz: a.f, f_over_f1: +(a.f / f1).toFixed(3), amp: +a.amp.toFixed(6) })), measured_peak_f_over_f1: +(peak.f / f1).toFixed(4) },
    formula: "两端（驱动端近似节点、固定端节点）驻波条件 L = n·λ/2 ⇒ f_n = n·v/(2L)",
    checks: [
      near("扫频峰值位置 f_peak / f₁（应为 1）", peak.f / f1, 1, 2),
      { metric: "共振/失谐振幅之比 f₁ vs 1.3f₁ > 3", ratio: +(peak.amp / off.amp).toFixed(3), verdict: peak.amp / off.amp > 3 ? "pass" : "fail" },
      { metric: "二次模态 2f₁ 也共振（>2 倍失谐）", ratio: +((second?.amp ?? 0) / off.amp).toFixed(3), verdict: (second?.amp ?? 0) / off.amp > 2 ? "pass" : "fail" },
    ],
  });
}

// ⑤ 稳定性护栏：上游自己的 CFL 量 v·Δt/Δx，越过 1 立刻发散 ⇒ 模板必须锁步长
{
  const T = 20, mu = 1; // v = 4.4721，配 Δt=0.0025、Δx=0.0135 ⇒ stability=0.828（合规）
  const ok = runString({ tension: T, density: mu, seconds: 3.2, drive: pulseDrive(0.1, AMP), probeIdx });
  const okStab = ok.sim.getStability();
  const okEnv = envelope(ok.series, 0, 3.2, "maxAbs");
  const bad = runString({ tension: T, density: mu, dt: 0.005, seconds: 3.2, drive: pulseDrive(0.1, AMP), probeIdx });
  const badStab = bad.sim.getStability();
  const badEnv = envelope(bad.series, 0, 3.2, "maxAbs");
  const exploded = !Number.isFinite(badEnv) || badEnv > 20 * okEnv;
  results.push({
    id: "waves-string-stability-guard",
    title: "CFL 护栏：v·Δt/Δx ≤ 1 才可信；把 Δt 翻倍（0.83→1.66）立即数值发散",
    engine: { v_T20: +Math.sqrt(T / mu).toFixed(6), dx: +ok.dx.toFixed(6), stability_ok: +okStab.toFixed(4), stability_bad: +badStab.toFixed(4), envelope_ok: +okEnv.toFixed(6), envelope_bad: Number.isFinite(badEnv) ? +badEnv.toExponential(4) : String(badEnv) },
    formula: "上游 getStability() = √(T/μ)·Δt/Δx；显式格式要求 ≤ 1",
    checks: [
      { metric: "合规配置 stability ≤ 1", stability: +okStab.toFixed(4), verdict: okStab <= 1 ? "pass" : "fail" },
      { metric: "越界配置 stability > 1 且振幅炸掉（≥20× 或 NaN）", stability: +badStab.toFixed(4), verdict: badStab > 1 && exploded ? "pass" : "fail" },
    ],
    note: "这一条不是物理，是给模板用的实现约束：改 tension（=改 v）必须同时改 Δt 或 Δx，否则拿到的是数值爆炸不是实验结果。",
  });
}

for (const r of results) r.verdict = r.checks.every((c) => c.verdict === "pass") ? "pass" : "fail";
const pass = results.filter((r) => r.verdict === "pass").length;
const payload = {
  generated_at: new Date().toISOString(),
  engine: `myPhysicsLab StringSim（上游 PDE 绳模型，leapfrog 格式；L=${LENGTH} m、N=${NPTS}、Δt=${DT} s、驱动端位移、右端固定）`,
  run_command: "node source/library/wave_lab.mjs --json",
  pass,
  fail: results.length - pass,
  results,
};
if (process.argv.includes("--json")) fs.writeFileSync(OUT, JSON.stringify(payload, null, 2), "utf-8");
for (const r of results) {
  console.log(`[${r.verdict}] ${r.id}`);
  for (const c of r.checks) console.log(`    ${c.verdict === "pass" ? "✓" : "✗"} ${c.metric}${c.measured !== undefined ? ` · 实测 ${c.measured} vs 理论 ${c.analytic}（${c.rel_error_pct}%）` : ` · ${JSON.stringify(c).replace(/^{"metric":"[^"]+",?/, "")}`}`);
}
console.log(`\n${pass}/${results.length} pass · 探针位置 x = ${probeX.toFixed(4)} m`);
process.exit(pass === results.length ? 0 : 1);
