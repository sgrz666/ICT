// 抛体实验的种子场景 + 独立科学验收：用 Matter.js 真实步进，对照解析式。
//
// 为什么要这个脚本：Matter.js 活在「像素 + 毫秒」世界里，而教学单位是米和秒；
// 更麻烦的是它默认 frictionAir = 0.01（逐步衰减），不显式置 0 的抛体根本不是抛物线。
// 所以这里做三件事：① 把单位标定成一条实测定律（不猜配置）；② 用与引擎无关的解析式
// 判射程/最高点/飞行时间；③ 带一个开阻力的对照组，证明这套容差真能区分
// 「无阻力理想抛体」和「其实一直在衰减」。
//
// 跑法：node source/library/projectile_lab.mjs [--json]（--json 才写 evidence 文件）
import fs from "node:fs";
import path from "node:path";
import { createRequire } from "node:module";
import { fileURLToPath } from "node:url";
import { createProjectileCore } from "../../code/eduforge/tools/labkit/lib/projectile-core.mjs";

const here = path.dirname(fileURLToPath(import.meta.url));
const require = createRequire(path.join(here, "..", "components", "probe_components.mjs"));
const OUT = path.join(here, "projectile-lab-evidence.json");
const M = require("matter-js");

const G = 9.8; // m/s²，教学单位下想要的重力加速度

// 物理内核抽到 code/eduforge/tools/labkit/lib/projectile-core.mjs：
// Node（本文件）与单文件页面共用同一份实现，避免「验收读数」与「页面读数」漂移。
const core = createProjectileCore(M);
const fly = core.fly;
const calibrate = core.calibrate;

function near(label, measured, expected, tolPct) {
  const err = Math.abs(measured - expected);
  const rel = expected === 0 ? err : (err / Math.abs(expected)) * 100;
  return {
    metric: label,
    measured: Number(measured.toFixed(4)),
    analytic: Number(expected.toFixed(4)),
    abs_error: Number(err.toFixed(5)),
    rel_error_pct: Number(rel.toFixed(3)),
    tolerance_pct: tolPct,
    verdict: rel <= tolPct ? "pass" : "fail",
  };
}

const results = [];
const cal = calibrate();
const aEff = cal.a_measured; // 之后所有解析对照都用标定值，不拿配置值糊人

results.push({
  id: "unit-calibration",
  title: "单位标定：这个配置下 Matter 到底掉多快",
  config: cal.config,
  formula: "a[单位/s²] = gravity.y × gravity.scale × 1e6（由源码 force=m·g·scale 与 velocity+=(F/m)·dt² 合并推出，再用自由落体实测复核）",
  engine: { drop_from: 0, to: cal.y, steps: cal.n, seconds: +cal.t.toFixed(5) },
  checks: [near("有效加速度 (m/s²)", aEff, G, 1)],
});

// ① 平抛：h = 20 m，水平 15 m/s
{
  const h0 = 20, v0 = 15, angleDeg = 0;
  const r = fly({ h0, v0, angleDeg });
  const T = Math.sqrt((2 * h0) / aEff);
  results.push({
    id: "projectile-horizontal",
    title: "平抛：h=20 m、v₀=15 m/s 水平",
    engine: {
      landing: r.landed && { t: +r.landed.t.toFixed(4), x: +r.landed.x.toFixed(4) },
      apex: { t: +r.apex.t.toFixed(4), y: +r.apex.y.toFixed(4) },
    },
    formula: "T = √(2h/g)，R = v₀·T，最高点即抛出点",
    checks: [
      near("飞行时间 (s)", r.landed.t, T, 1),
      near("射程 (m)", r.landed.x, v0 * T, 1),
      near("最高点高度 (m)", r.apex.y, h0, 0.5),
    ],
  });
}

// ② 斜抛 45°：射程、最高点、飞行时间三件一起对
{
  const v0 = 20, angleDeg = 45;
  const r = fly({ h0: 0, v0, angleDeg });
  const th = (angleDeg * Math.PI) / 180;
  const T = (2 * v0 * Math.sin(th)) / aEff;
  const R = (v0 * v0 * Math.sin(2 * th)) / aEff;
  const H = (v0 * v0 * Math.sin(th) ** 2) / (2 * aEff);
  results.push({
    id: "projectile-oblique-45",
    title: "斜抛：v₀=20 m/s、θ=45°",
    engine: {
      landing: r.landed && { t: +r.landed.t.toFixed(4), x: +r.landed.x.toFixed(4) },
      apex: { t: +r.apex.t.toFixed(4), y: +r.apex.y.toFixed(4) },
    },
    formula: "T = 2v₀sinθ/g，R = v₀²sin2θ/g，H = v₀²sin²θ/(2g)",
    checks: [
      near("飞行时间 (s)", r.landed.t, T, 1),
      near("射程 (m)", r.landed.x, R, 1),
      near("最高点 (m)", r.apex.y, H, 1),
    ],
  });
}

// ③ 互补角等射程：判据里不含 g，连单位标定错了都能暴露
{
  const v0 = 20;
  const a = fly({ h0: 0, v0, angleDeg: 30 });
  const b = fly({ h0: 0, v0, angleDeg: 60 });
  const ratio = a.landed.x / b.landed.x;
  results.push({
    id: "projectile-complementary-angles",
    title: "互补角等射程：30° vs 60°（判据不含 g）",
    engine: { range_30: +a.landed.x.toFixed(4), range_60: +b.landed.x.toFixed(4) },
    formula: "R = v₀²sin2θ/g ⇒ sin60° = sin120°，与 g 和单位标定无关",
    checks: [near("R(30°)/R(60°)", ratio, 1, 1)],
  });
}

// ④ 对照组：开着 Matter 默认阻力时，理想抛体公式必须明显不成立
{
  const v0 = 20, angleDeg = 45;
  const clean = fly({ h0: 0, v0, angleDeg, frictionAir: 0 });
  const draggy = fly({ h0: 0, v0, angleDeg, frictionAir: 0.01 });
  const th = (angleDeg * Math.PI) / 180;
  const R = (v0 * v0 * Math.sin(2 * th)) / aEff;
  const devClean = Math.abs(clean.landed.x - R) / R;
  const devDrag = Math.abs(draggy.landed.x - R) / R;
  results.push({
    id: "projectile-drag-control",
    title: "对照组：frictionAir = 0.01（Matter 默认）vs 0",
    engine: {
      analytic_range: +R.toFixed(4),
      range_no_drag: +clean.landed.x.toFixed(4),
      range_default_drag: +draggy.landed.x.toFixed(4),
    },
    checks: [
      {
        metric: "开阻力后的射程偏离要远大于无阻力那组",
        dev_no_drag_pct: +(devClean * 100).toFixed(3),
        dev_drag_pct: +(devDrag * 100).toFixed(3),
        ratio_required: "> 5×，且开阻力偏离 > 1%",
        verdict: devDrag > 5 * devClean && devDrag > 0.01 ? "pass" : "fail",
      },
    ],
    lesson: "模板若不显式写 frictionAir=0，所谓「抛体」其实在做有阻力运动，解析式对不上却没人报错",
  });
}

for (const r of results) {
  const list = r.checks || (r.check ? [r.check] : []);
  r.verdict = list.every((c) => c.verdict === "pass") ? "pass" : "fail";
}
const pass = results.filter((r) => r.verdict === "pass").length;
const payload = {
  generated_at: new Date().toISOString(),
  engine: `matter-js ${M.version}（无头步进，dt=${core.config.dtS}s，1 单位 = 1 m）`,
  run_command: "node source/library/projectile_lab.mjs --json",
  pass,
  fail: results.length - pass,
  calibrated_acceleration: aEff,
  results,
};

if (process.argv.includes("--json")) fs.writeFileSync(OUT, JSON.stringify(payload, null, 2), "utf-8");
for (const r of results) {
  const list = r.checks || (r.check ? [r.check] : []);
  console.log(`[${r.verdict}] ${r.id}`);
  for (const c of list) console.log(`    ${c.verdict === "pass" ? "✓" : "✗"} ${c.metric}${c.measured !== undefined ? ` · 实测 ${c.measured} vs 解析 ${c.analytic}` : ""}`);
}
console.log(`\n${pass}/${results.length} pass · 标定加速度 ${aEff.toFixed(5)} m/s²（目标 ${G}）`);
process.exit(pass === results.length ? 0 : 1);
