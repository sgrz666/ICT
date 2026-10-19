/** 整批 EJSS 包的「轨迹自洽」检查：不写解析式，也判得出引擎跑的是不是它自己声明的物理。
 *
 * 思路：取主角状态量 p(t)（步内变化最大的那个），对 40 步做二次多项式最小二乘拟合。
 * 若模型是匀加速运动，p 对 t 恰是二次函数，残差应到机器精度；而且拟合出来的二次项系数×2
 * 必须等于引擎自己在 serialize() 里报的那个恒定加速度变量——两条都要对上才算自洽。
 * 对不上就分类成「非匀加速（本判据不适用）」，而不是判 fail：弹簧、分段运动、碰撞类模型
 * 本来就不该过这条判据，把它们写成失败是假陈述。
 *
 * 用法：node source/library/ejss_kinematics_selfcheck.mjs [--steps 40] [--json <out>]
 */

import fs from "node:fs";
import path from "node:path";
import { createRequire } from "node:module";
import { assemble, entryPage, findChromium, probePackage } from "./ejss_headless_lab.mjs";

const require = createRequire(path.join(process.cwd(), "noop.js"));
const ROOT = process.cwd();

function arg(name, def) {
  const i = process.argv.indexOf(`--${name}`);
  return i >= 0 && process.argv[i + 1] && !process.argv[i + 1].startsWith("--") ? process.argv[i + 1] : def;
}

/** 二次最小二乘（正规方程 3×3，手写避免引依赖）。 */
function fitQuadratic(ts, ys) {
  const S = [0, 0, 0, 0, 0, 0], rhs = [0, 0, 0];
  for (let i = 0; i < ts.length; i++) {
    const t = ts[i], y = ys[i], t2 = t * t;
    S[0] += 1; S[1] += t; S[2] += t2; S[3] += t2 * t; S[4] += t2 * t2;
    rhs[0] += y; rhs[1] += y * t; rhs[2] += y * t2;
  }
  // [S0 S1 S2; S1 S2 S3; S2 S3 S4] · [c0 c1 c2] = rhs
  const A = [[S[0], S[1], S[2]], [S[1], S[2], S[3]], [S[2], S[3], S[4]]];
  const M = A.map((r, i) => [...r, rhs[i]]);
  for (let c = 0; c < 3; c++) {
    let piv = c;
    for (let r = c + 1; r < 3; r++) if (Math.abs(M[r][c]) > Math.abs(M[piv][c])) piv = r;
    if (Math.abs(M[piv][c]) < 1e-14) return null;
    [M[c], M[piv]] = [M[piv], M[c]];
    for (let r = 0; r < 3; r++) {
      if (r === c) continue;
      const f = M[r][c] / M[c][c];
      for (let k = c; k < 4; k++) M[r][k] -= f * M[c][k];
    }
  }
  return [M[0][3] / M[0][0], M[1][3] / M[1][1], M[2][3] / M[2][2]];
}

const survey = JSON.parse(fs.readFileSync(path.join(ROOT, "source/upstream/ejss-survey.json"), "utf-8"));
const seen = new Set();
const packages = [];
for (const m of survey.models) {
  if ((m.deliverability || {}).family !== "ejs6") continue;
  const zip = path.join(ROOT, "source/upstream", m.zip);
  if (!fs.existsSync(zip) || seen.has(zip)) continue;
  seen.add(zip);
  packages.push({ zip, title: m.title || path.basename(zip) });
}

const steps = Number(arg("steps", 40));
const relTol = Number(arg("rel-tol", 1e-6));
const { chromium } = require("playwright-core");
const report = {
  measured_at: new Date().toISOString(),
  tool: "source/library/ejss_kinematics_selfcheck.mjs",
  steps,
  criterion: "p(t) 二次拟合的最大残差 / p 的取值范围 ≤ 1e-6，且拟合二次项×2 与引擎自报的某个恒定变量对得上（绝对容差 1e-9 兜底，所以 a=0 的匀速模型也算——上一版要求 |a|>0，把 14 个残差 1e-15 的包误判成不自洽）",
  packages: [],
};
console.log(`跑 ${packages.length} 个包（每包 ${steps} 步）`);

const browser = await chromium.launch({
  executablePath: findChromium(), headless: true, args: ["--allow-file-access-from-files", "--no-sandbox"],
});
try {
  for (const pkg of packages) {
    const asm = assemble(pkg.zip, []);
    const page = asm.dir && entryPage(asm.dir);
    if (!page) { report.packages.push({ zip: path.relative(ROOT, pkg.zip).replace(/\\/g, "/"), class: "assemble_failed" }); continue; }
    const probe = await probePackage(browser, page, { steps, fullTrace: true });
    const row = { zip: path.relative(ROOT, pkg.zip).replace(/\\/g, "/"), title: pkg.title, primary: probe.primary_var };
    if (!probe.trace_primary || probe.trace_primary.length < 4) {
      row.class = "no_trace";
      report.packages.push(row);
      console.log(`SKIP ${pkg.title.slice(0, 36)} :: 没有可用轨迹`);
      continue;
    }
    const ts = probe.trace_ts, ys = probe.trace_primary;
    const coef = fitQuadratic(ts, ys);
    const span = Math.max(...ys) - Math.min(...ys);
    row.primary_span = span;
    if (!coef) { row.class = "fit_degenerate"; report.packages.push(row); continue; }
    const resid = Math.max(...ys.map((y, i) => Math.abs(y - (coef[0] + coef[1] * ts[i] + coef[2] * ts[i] * ts[i]))));
    const fittedAccel = 2 * coef[2];
    // 候选加速度量：标量恒定值 + 数组里的恒定分量。
    // 判据用「绝对容差兜底」：a=0 的匀速模型（这批题里占一半）之前被 |value|>0 直接否掉，
    // 于是 14 个残差 1e-15 的包被写成「不自洽」——那是判据写错，不是模型不对。
    const flat = {};
    for (const [k, series] of Object.entries(probe.trace_accel_candidates || {})) {
      if (/^(t|dt|animation|stepsPerDisplay)/.test(k)) continue;
      if (series.every((v) => typeof v === "number")) flat[k] = series;
      else if (series.every((v) => Array.isArray(v))) {
        for (let i = 0; i < series[0].length; i++) {
          if (series.every((s) => typeof s[i] === "number")) flat[`${k}[${i}]`] = series.map((s) => s[i]);
        }
      }
    }
    // 第二条、也是更强的判据：不看变量叫什么名字，直接用引擎自己的时间戳做差分，
    // 检查状态量之间满足 p'=v、v'=a 这条运动学链，并且链末端那个量在引擎里是恒定的。
    // 之所以要这条：上一版靠「二次拟合 + 找个等于 2c2 的常量」，一旦自动选中的主角是速度量
    // （2.18/2.19 就是这样），拟合出的 2c2=0 就再也对不上 a=−9.8，把明明自洽的模型判成不自洽。
    const names = Object.keys(flat);
    // 用梯形关系判导数，不用「后向差分 = 本格子的值」：EJSS 的 leapfrog 把 v 与 p 错开半步，
    // 直接比 (p_i−p_{i−1})/dt 与 v_i 会差 ½·a·dt（实测 1% 级），于是 2.18/2.19 这类
    // 明明解析正确的模型被判成不自洽。梯形 (v_i+v_{i−1})/2 对匀加速是精确的。
    const trapOk = (ys, vs, tolRel = 1e-6) => {
      for (let i = 1; i < ys.length; i++) {
        const dt = ts[i] - ts[i - 1];
        if (!(dt > 0)) return false;
        const d = (ys[i] - ys[i - 1]) / dt;
        const avg = (vs[i] + vs[i - 1]) / 2;
        if (!(Math.abs(d - avg) <= Math.max(1e-9, tolRel * Math.max(Math.abs(d), Math.abs(avg))))) return false;
      }
      return true;
    };
    const deriv = (ys) => ys.map((y, i) => (i === 0 ? NaN : (y - ys[i - 1]) / (ts[i] - ts[i - 1])));
    const close = (a, b) => Math.abs(a - b) <= Math.max(1e-9, 1e-6 * Math.max(Math.abs(a), Math.abs(b)));
    const chains = [];
    for (const p of names) {
      for (const v of names) {
        if (v === p) continue;
        if (!trapOk(flat[p], flat[v])) continue;
        const d2 = deriv(flat[v]).slice(2);
        for (const acc of names) {
          if (acc === p || acc === v) continue;
          const s = flat[acc].slice(2);
          const constant = Math.max(...s) - Math.min(...s) < 1e-12;
          if (!(constant && d2.every((x, i) => Number.isFinite(x) && close(x, s[i])))) continue;
          // 非退化要求：一串全 0 的量能「满足」任何差分判据，那是空判据不是物理自洽。
          // 实测第一版就靠 r_pos[0]→r_vel[0]→r_vel[1]（后两个恒为 0）蒙过了 Problem 2.4。
          const range = (a) => Math.max(...a) - Math.min(...a);
          const degenerate = range(flat[p]) < 1e-9 || Math.max(...flat[v].map(Math.abs)) < 1e-9
            || (Math.abs(s[0]) > 1e-12 && range(flat[v]) < 1e-9);
          if (!degenerate) chains.push({ p, v, acc, accel: s[0] });
        }
      }
    }
    row.kinematic_chains = chains.slice(0, 6);
    const accelMatches = Object.entries(flat).filter(([k, series]) => {
      const constant = Math.max(...series) - Math.min(...series) < 1e-12;
      const v = series[0];
      return constant && Math.abs(v - fittedAccel) <= Math.max(1e-9, 1e-6 * Math.abs(v));
    }).map(([k, series]) => ({ name: k, value: series[0] }));
    row.residual_rel = resid / span;
    row.fitted_accel = fittedAccel;
    row.accel_vars = accelMatches;
    const parabolic = span > 1e-9 && row.residual_rel <= relTol && accelMatches.length > 0;
    row.motion_mode = Math.abs(fittedAccel) > 1e-12 ? "匀加速" : "匀速（退化的二次，a=0）";
    // 分三档说清楚「为什么没过」，不要一律写成不自洽：主角量在这 40 步里根本没动过
    // （窗口太短/模型在等事件）与「动了但不是匀加速」是两回事，后者本来就不该过这条判据。
    const why = parabolic || chains.length ? null
      : span < 1e-9 ? "no_motion_in_window"
      : row.residual_rel > relTol ? "not_uniformly_accelerated_in_window"
      : "parabolic_but_no_matching_constant_accel_var";
    row.class = why ? why : "kinematics_selfconsistent";
    row.via = parabolic && chains.length ? "二次拟合+运动学链都过" : parabolic ? "二次拟合" : chains.length ? "运动学链" : "—";
    row.chain_example = chains[0] || null;
    report.packages.push(row);
    console.log(`${row.class === "kinematics_selfconsistent" ? "OK  " : "N/A "} ${pkg.title.slice(0, 36).padEnd(36)} ` +
      `primary=${row.primary} resid=${row.residual_rel.toExponential(1)} a_fit=${row.fittedAccel?.toFixed?.(4) ?? row.fitted_accel?.toFixed(4)} ` +
      `a_vars=${accelMatches.map((m) => m.name + "=" + m.value).join(",") || "—"} ` +
      `chain=${chains.length ? row.chain_example.p + "→" + row.chain_example.v + "→" + row.chain_example.acc : "—"}`);
  }
} finally {
  await browser.close();
}

const cnt = (c) => report.packages.filter((r) => r.class === c).length;
report.summary = {
  run: report.packages.length,
  kinematics_selfconsistent: cnt("kinematics_selfconsistent"),
  no_motion_in_window: cnt("no_motion_in_window"),
  not_uniformly_accelerated: cnt("not_uniformly_accelerated_in_window"),
  parabolic_but_accel_not_found: cnt("parabolic_but_no_matching_constant_accel_var"),
  of_which_uniform_velocity: report.packages.filter((r) => r.class === "kinematics_selfconsistent" && /匀速/.test(r.motion_mode || "")).length,
  of_which_accelerated: report.packages.filter((r) => r.class === "kinematics_selfconsistent" && /匀加速/.test(r.motion_mode || "")).length,
  of_which_via_chain_only: report.packages.filter((r) => r.via === "运动学链").length,
  chains_total: report.packages.reduce((n, r) => n + (r.kinematic_chains || []).length, 0),
};
const out = arg("json", "source/library/ejss-kinematics-selfcheck.json");
fs.writeFileSync(path.join(ROOT, out), JSON.stringify(report, null, 2), "utf-8");
console.log("\n汇总:", JSON.stringify(report.summary), "\n写入", out);
