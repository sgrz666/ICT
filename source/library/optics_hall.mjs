// 光学实验馆的种子场景 + 独立科学验收：用上游真实光线追迹，对照解析式。
//
// 资源库的价值不在「场景能打开」，而在「Agent 改了参数之后，引擎追出来的光路
// 能被一个与引擎无关的公式判对错」。这里就跑这一件事。
//
// 跑法：node source/library/optics_hall.mjs [--json]（--json 才写 evidence 文件）
import fs from "node:fs";
import path from "node:path";
import { createRequire } from "node:module";
import { fileURLToPath } from "node:url";

const here = path.dirname(fileURLToPath(import.meta.url));
const require = createRequire(import.meta.url);
const DIST = path.join(here, "..", "upstream", "ray-optics", "dist-node", "rayOptics.js");
const OUT = path.join(here, "optics-hall-evidence.json");

if (!fs.existsSync(DIST)) {
  console.log(JSON.stringify({ result: "blocked", error: "缺 dist-node/rayOptics.js：cd source/upstream/ray-optics && npm install && npm run build-node" }, null, 2));
  process.exit(0);
}
const ro = require(DIST.replace(/\\/g, "/"));

const P = (x, y) => ({ x, y });
// 上游把点序列化成 {x,y}（见 data/galleryScenes/*.json）。写成 [x,y] 时 loadJSON 不报错，
// 但坐标变 undefined，光线一步就走没了 —— 所以统一归一化。
const toPoints = (v) => Array.isArray(v)
  ? (v.length === 2 && v.every((n) => typeof n === "number") ? P(v[0], v[1]) : v.map(toPoints))
  : v && typeof v === "object" ? Object.fromEntries(Object.entries(v).map(([k, x]) => [k, toPoints(x)]))
  : v;

/** 跑一次仿真；返回每个探测器（屏）的功率与亮斑几何 */
function runScene(objsRaw) {
  return new Promise((resolve, reject) => {
    const scene = new ro.Scene();
    scene.loadJSON(JSON.stringify(toPoints({ version: 5, lengthScale: 1, width: 1500, height: 900, mode: "rays", objs: objsRaw })), () => {});
    if (scene.error) return reject(new Error("loadJSON: " + scene.error));
    const sim = new ro.Simulator(scene, null, null, null, null, null, false, Infinity, null, null, null);
    sim.on("simulationComplete", () => {
      const out = { processedRayCount: sim.processedRayCount, detectors: [] };
      for (const d of scene.objs.filter((o) => o.constructor.type === "Detector")) {
        const bins = Array.isArray(d.binData) ? d.binData : [];
        const n = bins.length || 1;
        const along = (t) => ({ x: d.p1.x + (d.p2.x - d.p1.x) * t, y: d.p1.y + (d.p2.y - d.p1.y) * t });
        let centroid = null, extent = null;
        const wsum = bins.reduce((a, b) => a + b, 0);
        if (wsum > 0) {
          let acc = 0;
          for (let i = 0; i < bins.length; i++) acc += bins[i] * (i + 0.5) / n;
          centroid = along(acc / wsum);
          const thr = 0.02 * Math.max(...bins);
          const on = [];
          for (let i = 0; i < bins.length; i++) if (bins[i] >= thr) on.push(i);
          if (on.length > 1) {
            const a = along((on[0] + 0.5) / n), b = along((on[on.length - 1] + 0.5) / n);
            extent = Math.hypot(b.x - a.x, b.y - a.y);
          }
        }
        out.detectors.push({ name: d.name, power: d.power, bins: bins.length, centroid, extent });
      }
      resolve(out);
    });
    sim.updateSimulation(false, false);   // 实测坑：不调这一步会零输出且像什么都没发生
  });
}

// 屏：竖直放置的探测器。binSize 1 ⇒ 分辨率约 1 个场景单位
const screen = (name, x, span) => ({ type: "Detector", name, p1: P(x, -span), p2: P(x, span), twoSided: true, irradMap: true, binSize: 1 });
const near = (a, b, tol) => a !== null && Math.abs(a - b) <= tol;

const results = [];
const GLASS_H = 200;

// ---------- 0) 基线：refIndex=1.0 的光线不该偏折 ----------
// PlaneGlass 的 p1/p2 都是界面上的点（不是法线；源码注释 "A point on the boundary"），
// 玻璃落在哪一侧不靠猜：先用 n=1 钉死直线基线，再由折射落点判定。
const straight = await runScene([
  { type: "PlaneGlass", name: "glass", p1: P(0, -GLASS_H), p2: P(0, GLASS_H), refIndex: 1.0, partialReflect: false },
  { type: "SingleRay", name: "ray", p1: P(-300, -200), p2: P(0, 0) },
  screen("screen", 300, 600),
]);
const baseY = straight.detectors.find((d) => d.name === "screen")?.centroid?.y ?? null;

// ---------- 1) 平面镜成像：像与物关于镜面对称（等价于反射等角） ----------
{
  const S = P(-300, 200), O = P(0, 0);       // 镜面沿 y=0 水平放置
  const slope = 200 / 300;                    // 入射方向 (300,-200) ⇒ 水平镜面反射后 (300,+200)
  const expY = O.y + slope * (300 - O.x);     // 屏在 x=300
  const got = await runScene([
    { type: "IdealMirror", name: "mirror", p1: P(-400, 0), p2: P(400, 0) },
    { type: "SingleRay", name: "ray", p1: S, p2: O },
    screen("screen", 300, 400),
  ]);
  const y = got.detectors[0].centroid?.y ?? null;
  results.push({
    id: "optics-plane-mirror", title: "平面镜成像（像与物关于镜面对称 / 反射等角）",
    analytic: { expected_screen_y: expY, image_y: -S.y },
    engine: got, check: { metric: "屏上亮斑 y", measured: y, expected: expY, tolerance: 2 },
    verdict: near(y, expY, 2) ? "pass" : "fail",
  });
}

// ---------- 2) 折射定律 n1 sinθ1 = n2 sinθ2 ----------
{
  const n = 1.5;
  const th1 = Math.atan(200 / 300);
  const enterY = Math.tan(Math.asin(Math.sin(th1) / n)) * 300;                    // 空气→玻璃：向法线偏
  const exitY = Math.tan(Math.asin(Math.min(1, n * Math.sin(th1)))) * 300;        // 玻璃→空气：离法线偏
  const got = await runScene([
    { type: "PlaneGlass", name: "glass", p1: P(0, -GLASS_H), p2: P(0, GLASS_H), refIndex: n, partialReflect: false },
    { type: "SingleRay", name: "ray", p1: P(-300, -200), p2: P(0, 0) },
    screen("screen", 300, 600),
  ]);
  const y = got.detectors[0].centroid?.y ?? null;
  const entered = y !== null && Math.abs(y - enterY) < Math.abs(y - exitY);
  const expY = entered ? enterY : exitY;
  results.push({
    id: "optics-refraction-snell", title: "折射定律 n1 sinθ1 = n2 sinθ2",
    baseline_control: { refIndex: 1.0, screen_y: baseY, expected: 200, verdict: near(baseY, 200, 2) ? "pass" : "fail" },
    analytic: { theta1_deg: th1 * 180 / Math.PI, predict_enter_y: enterY, predict_exit_y: exitY },
    geometry_convention_measured: y === null ? "unknown" : entered ? "玻璃在 x>0（光线由空气进入玻璃）" : "玻璃在 x<0（光线由玻璃离开）",
    engine: got, check: { metric: "折射后屏上亮斑 y", measured: y, expected: expY, tolerance: 2 },
    verdict: near(baseY, 200, 2) && near(y, expY, 2) ? "pass" : "fail",
  });
}

// ---------- 3) 全反射与临界角：扫描入射角，找折射光消失的那一格 ----------
{
  const n = 1.5;
  const tc = Math.asin(1 / n) * 180 / Math.PI;
  const sweep = [];
  for (const deg of [30, 36, 40, 42, 46, 52, 60]) {
    // 光源必须放在玻璃里。上一步实测出「玻璃在 p1→p2 的左手侧」，即 x<0 一侧，
    // 所以这里从 (-300, ...) 朝界面原点入射，透射光落在 x=+300 的屏上。
    const sx = -300, sy = -300 * Math.tan(deg * Math.PI / 180);
    const got = await runScene([
      { type: "PlaneGlass", name: "glass", p1: P(0, -GLASS_H), p2: P(0, GLASS_H), refIndex: n, partialReflect: false },
      { type: "SingleRay", name: "ray", p1: P(sx, sy), p2: P(0, 0) },
      screen("air", 300, 1200),
    ]);
    const d = got.detectors.find((x) => x.name === "air");
    // Detector.power 在没有光线命中时是 -1（哨兵值，不是 0）；bins 长度为 0 同样表示没收到光
    sweep.push({ incidence_deg: deg, transmitted_power: d.power, hit_y: d.centroid?.y ?? null, bins_lit: d.bins });
  }
  const lit = (s) => s.transmitted_power > 0.5 && s.hit_y !== null;
  const lastOn = [...sweep].reverse().find(lit);
  const firstOff = sweep.find((s) => !lit(s));
  results.push({
    id: "optics-total-internal-reflection", title: "全反射与临界角（扫描入射角求 θc）",
    analytic: { critical_angle_deg: tc },
    sweep,
    measured: { last_angle_with_transmission: lastOn?.incidence_deg ?? null, first_angle_without_transmission: firstOff?.incidence_deg ?? null },
    verdict: lastOn && firstOff && firstOff.incidence_deg - tc <= 2.5 && tc - lastOn.incidence_deg <= 2.5 ? "pass" : "fail",
    check: { metric: "θc 是否落在 (最后透射角, 首个全反射角] 内", tolerance_deg: 2.5 },
  });
}

// ---------- 4) 凹透镜：平行光发散，虚焦点由两个屏上的束宽反解 ----------
// w(L) = h*(L+|f|)/|f| ⇒ |f| = (w1*L2 - w2*L1)/(w2 - w1)。完全不读引擎自报的焦距。
{
  const h = 40, f = -100, L1 = 200, L2 = 500;
  const got = await runScene([
    { type: "IdealLens", name: "lens", p1: P(0, -200), p2: P(0, 200), focalLength: f },
    { type: "Beam", name: "beam", p1: P(-300, -h / 2), p2: P(-300, h / 2) },
    screen("s1", L1, 600),
    screen("s2", L2, 800),
  ]);
  const w1 = got.detectors.find((d) => d.name === "s1")?.extent ?? null;
  const w2 = got.detectors.find((d) => d.name === "s2")?.extent ?? null;
  const fit = w1 && w2 && Math.abs(w2 - w1) > 1e-6 ? (w1 * L2 - w2 * L1) / (w2 - w1) : null;
  results.push({
    id: "optics-concave-lens", title: "凹透镜发散（虚焦点位置可测，不读引擎自报焦距）",
    analytic: { expected_abs_f: -f, beam_height: h, screens: [L1, L2], formula: "w(L)=h*(L+|f|)/|f|" },
    measured: { width_at_200: w1, width_at_500: w2, fitted_abs_f: fit },
    engine: got, check: { metric: "束宽反解出的 |f|", measured: fit, expected: -f, tolerance: 15 },
    verdict: fit !== null && Math.abs(fit - (-f)) <= 15 ? "pass" : "fail",
  });
}

const summary = {
  generated_at: new Date().toISOString(),
  engine: "ray-optics 5.5.0 dist-node/rayOptics.js（真实光线追迹；解析式独立于引擎）",
  pass: results.filter((r) => r.verdict === "pass").length,
  fail: results.filter((r) => r.verdict !== "pass").length,
  results,
};
if (process.argv.includes("--json")) fs.writeFileSync(OUT, JSON.stringify(summary, null, 2) + "\n");
console.log(JSON.stringify(summary, null, 2));
