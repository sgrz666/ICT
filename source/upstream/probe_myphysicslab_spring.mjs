// myPhysicsLab 弹簧振子无头实测：胡克定律 F=-kx（读引擎算出的加速度）+ 周期 T=2π√(m/k)。
// 参数名不硬写：先枚举 SingleSpringSim.en，再按语义匹配设置，避免上游改名就整块崩。
//
// 前置同 probe_myphysicslab.mjs：npm install --no-save typescript && npx tsc
// 跑法：node source/upstream/probe_myphysicslab_spring.mjs
import fs from "node:fs";
import path from "node:path";
import { fileURLToPath } from "node:url";

const build = path.join(path.dirname(fileURLToPath(import.meta.url)), "myphysicslab", "build");
const mod = (rel) => "file://" + path.join(build, rel).replace(/\\/g, "/");
const OUT = path.join(path.dirname(fileURLToPath(import.meta.url)), "probe-myphysicslab-spring.json");

const K = 2.0;      // 劲度系数 N/m
const M = 0.5;      // 质量 kg
const X0 = 0.3;     // 初始拉伸 m
const DT = 0.001;

function die(stage, e) {
  const msg = String(e && e.message ? e.message : e).slice(0, 300);
  console.log(JSON.stringify({ engine: "myphysicslab / SingleSpringSim", result: "fail", stage, error: msg }, null, 2));
  process.exit(0);
}

try {
  if (!fs.existsSync(build)) die("build-missing", "先跑 npm install --no-save typescript && npx tsc");
  fs.writeFileSync(path.join(build, "package.json"), '{\n  "type": "module"\n}\n');
  globalThis.MPL_BUILD_TIME = "headless-probe";
  globalThis.MPL_LOCALE = "en";

  const { SingleSpringSim } = await import(mod("sims/springs/SingleSpringSim.js"));
  const { SimpleAdvance } = await import(mod("lab/model/SimpleAdvance.js"));
  const en = SingleSpringSim.en;
  const names = Object.keys(en);

  const sim = new SingleSpringSim();
  const setBy = (re, val) => {
    const key = names.find((n) => re.test(n));
    if (!key) return null;
    try { sim.getParameterNumber(en[key]).setValue(val); return key; } catch { return null; }
  };
  const kKey = setBy(/^K$|SPRING_CONST|STIFF/i, K);
  const mKey = setBy(/MASS|^M$/i, M);
  const dampKey = setBy(/DAMP/i, 0);          // 无阻尼才满足 T=2π√(m/k)

  sim.getVarsList().getVariable(en.POSITION).setValue(X0);
  sim.getVarsList().getVariable(en.VELOCITY).setValue(0);
  sim.modifyObjects();

  const advance = new SimpleAdvance(sim);
  const vars = sim.getVarsList();
  const read = () => ({
    t: vars.getTime(),
    x: vars.getVariable(en.POSITION).getValue(),
    v: vars.getVariable(en.VELOCITY).getValue(),
    a: vars.getVariable(en.ACCELERATION).getValue(),
  });

  // ① 胡克定律：t=0、x=X0、v=0 时引擎应给出 a = -k·X0/m
  advance.advance(DT);
  const first = read();
  const aExpect = -(K * X0) / M;

  // ② 周期：连续过零（同向）间隔
  const cross = [];
  let prev = first;
  for (let i = 0; i < Math.round(60 / DT); i++) {
    advance.advance(DT);
    const cur = read();
    if (prev.x > 0 && cur.x <= 0) cross.push(prev.t + (prev.x / (prev.x - cur.x)) * DT);
    prev = cur;
  }
  const per = [];
  for (let i = 1; i < cross.length; i++) per.push(cross[i] - cross[i - 1]);
  const T = per.length ? per.reduce((a, b) => a + b, 0) / per.length : null;
  const TExpect = 2 * Math.PI * Math.sqrt(M / K);
  // 能量守恒（无阻尼）：½kx² + ½mv² 应始终等于初始势能
  const eNow = 0.5 * K * prev.x ** 2 + 0.5 * M * prev.v ** 2;
  const e0 = 0.5 * K * X0 ** 2;

  const hookOK = Math.abs(first.a - aExpect) <= Math.abs(aExpect) * 0.02;
  const perOK = T !== null && Math.abs(T - TExpect) / TExpect <= 0.01;
  const res = {
    engine: "myPhysicsLab / SingleSpringSim（上游自己的积分器）",
    result: hookOK && perOK ? "pass" : "fail",
    params_set: { k: kKey, m: mKey, damping: dampKey, k_value: K, mass_value: M, x0: X0, dt: DT },
    en_keys_available: names.join(","),
    hook_law: { measured_accel: first.a, analytic_accel: aExpect, rel_err_pct: Number((((first.a - aExpect) / aExpect) * 100).toFixed(3)) },
    period: { measured: T === null ? null : Number(T.toFixed(5)), analytic_T: Number(TExpect.toFixed(5)), rel_err_pct: T === null ? null : Number((((T - TExpect) / TExpect) * 100).toFixed(3)) },
    energy: { initial: e0, at_end: Number(eNow.toFixed(6)), drift_pct: Number((((eNow - e0) / e0) * 100).toFixed(4)) },
    zero_crossings: cross.length,
    time_end: prev.t,
  };
  fs.writeFileSync(OUT, JSON.stringify(res, null, 2) + "\n");
  console.log(JSON.stringify(res, null, 2));
} catch (e) {
  die("runtime", e);
}
