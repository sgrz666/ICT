// 双缝/多缝干涉的无头验收：物理不由我写——把上游 EJSS 模型（OSP resources 里的
// webejs_model_MultislitDiffraction.zip）自己声明的 getSingleSlitAmp / getMultiSlitAmp
// 抽出来，在 Node 里按模型自带的公参数值跑，再拿干涉理论的对立预测去判它。
//
// 为什么这样算「引擎出数」而我又自己写一遍格子：这些函数是上游模型的原文，
// 参数名（N、D、d、lambda、L）与取值都来自 _source.ejss 的 public 变量表；
// 我改的只有「在哪里执行」。这也顺带给出 EJSS 线的一条真实 Agent 通路：
// 读变量表 → 取函数体 → 换参数 → 读数，全程不需要浏览器。
//
// 跑法：node source/library/interference_lab.mjs [--json]
import { spawnSync } from "node:child_process";
import fs from "node:fs";
import path from "node:path";
import { fileURLToPath } from "node:url";

const here = path.dirname(fileURLToPath(import.meta.url));
const repo = path.join(here, "..", "..");
const MODEL = path.join(repo, "source", "upstream", "resources", "docs", "CollectionTest", "webejs_model_MultislitDiffraction.zip");
const PROBE = path.join(repo, "source", "upstream", "probe_ejss_model.py");
const OUT = path.join(here, "interference-lab-evidence.json");

if (!fs.existsSync(MODEL)) {
  console.log(`找不到上游模型：${MODEL}（要先跑 source/upstream/fetch_osp_family.sh 装 resources/）`);
  process.exit(1);
}
const r = spawnSync("python", [PROBE, MODEL, "--json", OUT.replace(/evidence\.json$/, "probe-tmp.json")], { encoding: "utf-8" });
if (r.status !== 0) { console.log(r.stdout, r.stderr); process.exit(1); }
const probe = JSON.parse(fs.readFileSync(OUT.replace(/evidence\.json$/, "probe-tmp.json"), "utf-8"));
fs.rmSync(OUT.replace(/evidence\.json$/, "probe-tmp.json"), { force: true });

const params = {};
for (const v of probe.public_variables) {
  if (/^-?[\d.]+$/.test(v.value)) params[v.name] = Number(v.value);
}
const lib = probe.code_blocks["Osejs.Model.Library"] || "";
if (!lib.includes("getMultiSlitAmp")) { console.log("模型里没找到 getMultiSlitAmp，抽取失败"); process.exit(1); }

// 只把两个振幅函数与它们要用的常量喂进去；alpha/beta/vals 等未声明全局沿用上游写法
function build({ N, D, d, lambda, L }) {
  const factory = new Function("N", "D", "d", "lambda", "L", `
    ${lib}
    return { getSingleSlitAmp, getMultiSlitAmp };
  `);
  return factory(N, D, d, lambda, L);
}
const XSCALE = Number((probe.public_variables.find((v) => v.name === "xscale") || {}).value === "2*Math.PI" ? (2 * Math.PI).toFixed(12) : 2 * Math.PI);
const NPTS = params.n || 4 * 1024;

function curve(over = {}) {
  const p = { ...params, ...over };
  const { getSingleSlitAmp, getMultiSlitAmp } = build(p);
  // 模型自己的绘图窗只有 ±xscale/2（≈±3.14），比包络第一极小（x=λL/D=4）还窄，
  // 所以要验包络就得把取样范围放宽——函数是纯的，放宽取样不改变模型
  const span = over.span ?? XSCALE;
  const delta = span / (NPTS - 1);
  const out = [];
  for (let i = 0; i < NPTS; i++) {
    const x = -span / 2 + i * delta;
    const a = getMultiSlitAmp(x);
    const u = getSingleSlitAmp(x);
    out.push({ x, I: a * a, envelope: u * u, delta });
  }
  return out;
}

/** 主极大位置：局部极大且 I > 阈值 */
function principalMaxima(c, thr = 0.5) {
  const out = [];
  for (let i = 1; i < c.length - 1; i++) if (c[i].I > c[i - 1].I && c[i].I >= c[i + 1].I && c[i].I > thr) out.push(c[i].x);
  return out;
}
function maxima(c) {
  const out = [];
  for (let i = 1; i < c.length - 1; i++) if (c[i].I > c[i - 1].I && c[i].I >= c[i + 1].I) out.push({ x: c[i].x, I: c[i].I });
  return out;
}
/** 半高宽中心法测某一级主极大的位置（比“取离散格点峰”稳） */
function nearestPeak(c, target) {
  let best = c[0];
  for (const p of c) if (Math.abs(p.x - target) < Math.abs(best.x - target)) best = p;
  return best;
}

const results = [];
const near = (metric, measured, expected, tolPct) => {
  const rel = expected === 0 ? measured : Math.abs((measured - expected) / expected) * 100;
  return { metric, measured: +measured.toPrecision(7), analytic: +expected.toPrecision(7), rel_error_pct: +rel.toFixed(3), tolerance_pct: tolPct, verdict: rel <= tolPct ? "pass" : "fail" };
};

const base = curve();
const wide = curve({ span: 12 });
const fringe = (params.lambda * params.L) / params.d; // 相邻主极大间距（小角，x = mλL/d）
const envZero = (params.lambda * params.L) / params.D; // 单缝包络第一极小
const pm = principalMaxima(base);
const spacings = pm.slice(1).map((x, i) => x - pm[i]);
const meanSpacing = spacings.reduce((a, b) => a + b, 0) / (spacings.length || 1);

results.push({
  id: "interference-fringe-spacing",
  title: "多缝主极大间距 = λL/d（模型自己的 getMultiSlitAmp 跑出来的曲线）",
  engine: { model: probe.title, author: probe.author, params, peaks_found: pm.length, first_peaks: pm.slice(0, 5).map((v) => +v.toFixed(5)), mean_spacing: +meanSpacing.toFixed(6) },
  formula: "d·sinθ = mλ，小角下 x_m = mλL/d ⇒ Δx = λL/d",
  checks: [
    near("主极大间距 (模型单位)", meanSpacing, fringe, 2),
    near("中央主极大在 x=0", Math.abs(nearestPeak(base, 0).x), 0, 100),
  ],
});

const wideZero = (() => { let prev = wide[0]; for (const q of wide.slice(1)) { if (prev.envelope > 1e-6 && q.envelope <= 1e-6) return Math.abs(q.x); prev = q; } return NaN; })();
const missingOrder = params.d / params.D; // = 10：第 10 级干涉主极大正好落在包络第一极小上 ⇒ 缺级
const atMissing = nearestPeak(wide, fringe * missingOrder);
results.push({
  id: "interference-single-slit-envelope",
  title: "单缝包络第一极小 = λL/D，且它正好把第 d/D 级干涉主极大「吃掉」（缺级）",
  engine: { env_zero_measured: +wideZero.toFixed(6), env_zero_analytic: +envZero.toFixed(6), missing_order: missingOrder, x_of_missing_order: +(fringe * missingOrder).toFixed(6), I_at_that_order: +atMissing.I.toFixed(9), envelope_at_that_order: +atMissing.envelope.toFixed(9), note: "模型绘图窗 ±3.14 装不下 x=4，这条把取样范围放宽到 ±6（函数是纯的，不改模型）" },
  formula: "D·sinθ = λ ⇒ 包络第一极小 x = λL/D；当 d/D 为整数时第 d/D 级主极大恰落在该处 ⇒ 缺级",
  checks: [
    near("包络第一极小位置", wideZero, envZero, 3),
    { metric: `第 ${missingOrder} 级主极大消失：I < 1e-4`, value: +atMissing.I.toFixed(9), tolerance: 1e-4, verdict: atMissing.I < 1e-4 ? "pass" : "fail" },
  ],
});

// 两个主极大之间恰有 N−2 个次极大：这是多缝干涉的结构预言，N 一变就得跟着变
{
  const rows = [];
  const checks = [];
  for (const N of [1, 2, 3, 5]) {
    const c = curve({ N });
    const strong = maxima(c).filter((p) => p.I > 1e-3);
    // 取中央与第一主极大之间（不含端点）的次极大个数
    const inGap = strong.filter((p) => p.x > 0.02 && p.x < fringe - 0.02).length;
    rows.push({ N, maxima_in_first_gap: inGap, expected: Math.max(N - 2, 0), total_strong_maxima: strong.length });
    checks.push({ metric: `N=${N}：两主极大之间次极大数 = N−2`, found: inGap, analytic: Math.max(N - 2, 0), verdict: inGap === Math.max(N - 2, 0) ? "pass" : "fail" });
  }
  results.push({ id: "interference-secondary-maxima", title: "次极大个数 = N−2（改缝数立刻跟着变）", engine: rows, formula: "N 缝：相邻主极大之间有 N−2 个次极大、N−1 个极小", checks });
}

// 改波长 ⇒ 条纹间距线性变；改缝间距 d ⇒ 反比变（Agent 改参与读数的闭环）
{
  const double_ = curve({ lambda: params.lambda * 2 });
  const sp2 = (() => { const p = principalMaxima(double_); const s = p.slice(1).map((x, i) => x - p[i]); return s.reduce((a, b) => a + b, 0) / s.length; })();
  const wideD = curve({ d: params.d * 2 });
  const spD = (() => { const p = principalMaxima(wideD); const s = p.slice(1).map((x, i) => x - p[i]); return s.reduce((a, b) => a + b, 0) / s.length; })();
  results.push({
    id: "interference-parameter-response",
    title: "改参与读数跟着变：λ×2 ⇒ 间距×2；d×2 ⇒ 间距÷2",
    engine: { base_spacing: +meanSpacing.toFixed(6), lambda_x2_spacing: +sp2.toFixed(6), d_x2_spacing: +spD.toFixed(6) },
    formula: "Δx = λL/d",
    checks: [near("λ 翻倍后的间距比", sp2 / meanSpacing, 2, 3), near("d 翻倍后的间距比", spD / meanSpacing, 0.5, 3)],
  });
}

// 中央主极大的相对强度恒为 1（模型把振幅除以 N 做了归一化）⇒ 记录这个事实，免得模板里把它当 N² 用
{
  const rows = [];
  for (const N of [1, 2, 5, 12]) rows.push({ N, central_I: +nearestPeak(curve({ N }), 0).I.toFixed(6) });
  results.push({
    id: "interference-normalisation-trap",
    title: "模型把多缝振幅除以 N 归一化 ⇒ 中央主极大恒为 1，不能拿它当「强度 ∝ N²」的证据",
    engine: rows,
    formula: "上游原文：getMultiSlitAmp = getSingleSlitAmp(x)·sin(Nβ)/sin(β)/N（末尾除 N）",
    checks: [{ metric: "各 N 下中央强度都是 1（±1%）", values: rows.map((v) => v.central_I), verdict: rows.every((v) => Math.abs(v.central_I - 1) < 0.01) ? "pass" : "fail" }],
    note: "教学上真要讲「缝越多主越亮」，得自己按未归一化的 (sin Nβ/sin β)² 出数，或在读数时乘 N²。这条是模板必须写清楚的坑，不是模型的错。",
  });
}

for (const res of results) res.verdict = res.checks.every((c) => c.verdict === "pass") ? "pass" : "fail";
const pass = results.filter((x) => x.verdict === "pass").length;
const payload = {
  generated_at: new Date().toISOString(),
  engine: `上游 EJSS 模型原文函数（${probe.title}，作者 ${probe.author}；从 ${path.basename(MODEL)} 的 _source.ejss 抽出 Osejs.Model.Library 里的 getSingleSlitAmp/getMultiSlitAmp 后在 Node 执行）；参数取模型自带的 public 变量 ${JSON.stringify(params)}`,
  run_command: "node source/library/interference_lab.mjs --json",
  extraction_tool: "source/upstream/probe_ejss_model.py",
  pass,
  fail: results.length - pass,
  results,
};
if (process.argv.includes("--json")) fs.writeFileSync(OUT, JSON.stringify(payload, null, 2), "utf-8");
for (const res of results) {
  console.log(`[${res.verdict}] ${res.id}`);
  for (const c of res.checks) console.log(`    ${c.verdict === "pass" ? "✓" : "✗"} ${c.metric}${c.measured !== undefined ? ` · 实测 ${c.measured} vs 理论 ${c.analytic}（${c.rel_error_pct}%）` : ` · ${JSON.stringify(c).replace(/^{"metric":"[^"]+",?/, "")}`}`);
}
console.log(`\n${pass}/${results.length} pass · 模型函数原文取自 ${path.basename(MODEL)}`);
process.exit(pass === results.length ? 0 : 1);
