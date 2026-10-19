// myPhysicsLab 无头可控性实测：用上游自己的 PendulumSim 跑单摆，测周期，与独立解析式对照。
//
// 前置（构建产物不入库，重跑要先执行）：
//   cd source/upstream/myphysicslab && npm install --no-save typescript && npx tsc
//
// 跑法：node source/upstream/probe_myphysicslab.mjs
import fs from "node:fs";
import util from "node:util";
import path from "node:path";
import { fileURLToPath } from "node:url";

const here = path.dirname(fileURLToPath(import.meta.url));
const build = path.join(here, "myphysicslab", "build");
const mod = (rel) => "file://" + path.join(build, rel).replace(/\\/g, "/");

const L = 1.0;          // 摆长 m
const G = 9.8;          // 重力加速度 m/s²
const THETA0 = 0.1;     // 初始角 rad（5.7°，小角度近似误差约 0.06%）
const DT = 0.001;       // 步长 s

function die(stage, e) {
  const msg = util.inspect(e, { depth: 1 }).slice(0, 600);
  const stack = String(e && e.stack ? e.stack : "").split("\n").slice(0, 5).join(" | ");
  console.log(JSON.stringify({ engine: "myphysicslab / PendulumSim", result: "fail", stage, error: msg, stack: stack.slice(0, 400) }, null, 2));
  process.exit(0);
}

var at = "imports";
try {
  if (!fs.existsSync(build)) die("build-missing", "build/ 不存在：先跑 npm install --no-save typescript && npx tsc");
  // tsc 只输出 ESM，Node 需要最近处有 {"type":"module"} 才把 .js 当模块解析；build/ 是生成目录，不是上游源码
  fs.writeFileSync(path.join(build, "package.json"), '{\n  "type": "module"\n}\n');
  // 上游 makefile 用 esbuild --define 注入两个编译期全局，裸 tsc 产物没有；Util.js 模块顶层就引用它们
  globalThis.MPL_BUILD_TIME = "headless-probe";
  globalThis.MPL_LOCALE = "en";

  const { PendulumSim } = await import(mod("sims/pendulum/PendulumSim.js"));
  const { SimpleAdvance } = await import(mod("lab/model/SimpleAdvance.js"));
  const en = PendulumSim.en;

  const sim = new PendulumSim(); at = "constructed";
  if (process.env.MPL_DIAG) {
    console.error("PARAM_NAMES=" + JSON.stringify(sim.getParamsList().getParams().map((q) => q.getName())));
    console.error("EN_KEYS=" + JSON.stringify(Object.keys(en)));
    console.error("EN_VALUES=" + JSON.stringify(en));
  }
  const set = (name, value) => {
    if (!(name in en)) throw new Error(`PendulumSim.en 没有参数 ${name}；可用：${Object.keys(en).join(",")}`);
    sim.getParameterNumber(en[name]).setValue(value);
  };
  // 上游默认 damping=0.5、且有周期驱动；做「单摆周期」实验必须显式关掉，否则测到的是受驱阻尼摆
  const optional = (name, value) => { if (name in en) sim.getParameterNumber(en[name]).setValue(value); };
  set("LENGTH", L);
  set("GRAVITY", G);
  optional("MASS", 1.0);
  optional("DAMPING", 0.0);
  optional("DRIVE_AMPLITUDE", 0.0);
  sim.getVarsList().getVariable(en.ANGLE).setValue(THETA0);
  // 上游枚举里是 ANGULAR_VELOCITY（没有 ANGLE_VELOCITY）：取错键会得到 undefined，
  // 而 getVariable(undefined) 抛出来的是空串异常，排查时极易误判成「引擎跑不起来」
  const velKey = en.ANGULAR_VELOCITY !== undefined ? en.ANGULAR_VELOCITY : en.ANGLE_VELOCITY;
  sim.getVarsList().getVariable(velKey).setValue(0);
  sim.modifyObjects(); at = "configured";

  const advance = new SimpleAdvance(sim);
  const vars = sim.getVarsList();
  const read = () => ({ t: vars.getTime(), th: vars.getVariable(en.ANGLE).getValue() });

  const crossings = [];
  let prev = read();
  for (let i = 0; i < Math.round(30 / DT); i++) {
    advance.advance(DT); at = "stepped:" + i;
    const cur = read();
    if (prev.th > 0 && cur.th <= 0) crossings.push(prev.t + (prev.th / (prev.th - cur.th)) * DT);
    prev = cur;
  }
  const periods = [];
  for (let i = 1; i < crossings.length; i++) periods.push(crossings[i] - crossings[i - 1]);
  const measured = periods.length ? periods.reduce((a, b) => a + b, 0) / periods.length : null;
  const theoretical = 2 * Math.PI * Math.sqrt(L / G);                       // 小角度近似
  const largeAngle = theoretical * (1 + (THETA0 * THETA0) / 16);  // 一级大角度修正

  console.log(JSON.stringify({
    engine: "myphysicslab / PendulumSim（上游自己的 ODE 积分，不是我们的公式）",
    result: measured === null ? "fail" : "pass",
    params: { length_m: L, gravity: G, theta0_rad: THETA0, dt_s: DT },
    en_keys_available: Object.keys(en).join(","),
    zero_crossings: crossings.length,
    measured_period_s: measured === null ? null : Number(measured.toFixed(5)),
    theoretical_period_small_angle_s: Number(theoretical.toFixed(5)),
    theoretical_period_large_angle_s: Number(largeAngle.toFixed(5)),
    rel_error_vs_small_angle_pct: measured === null ? null : Number((((measured - theoretical) / theoretical) * 100).toFixed(4)),
    rel_error_vs_large_angle_pct: measured === null ? null : Number((((measured - largeAngle) / largeAngle) * 100).toFixed(4)),
    note: "同向过零间隔即一个完整周期（上一版误乘 2，得到 2T）",
    period_series: periods.slice(0, 4).map((p) => Number(p.toFixed(5))),
    sim_time_end: prev.t,
  }, null, 2));
} catch (e) {
  die(at, e);
}
