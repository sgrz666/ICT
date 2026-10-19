/** 3JCN 批量探针：把「一只页面能驱动」扩成「整批逐只分档」。
 *
 * 为什么必须批量：上一轮只在 apparent_weight 一只上拿到 5/5 的写-观测-复原闭环，
 * 这跟当初 EJSS 只测两个模型就下结论是同一个错。3JCN 本地镜像里已有 31 份演示页，
 * 这一支把每只都跑同四条判据，按档位记账，不压成一个布尔：
 *   writable_and_readout   —— 写值后**页面自己的数字读数**跟着变（这一档才谈得上解析式对账）
 *   writable_and_picture   —— 数字读数没有，但画面变且能复原（画面须先过「不操作两帧一致」对照组）
 *   writable_only          —— 值写得进、回读得到，但看不到任何可观测后果
 *   dynamic_render         —— 页面自己在动，画面通道不可用（不是失败，是这一档不能用这条判据）
 *   no_control / canvas_absent / load_failed
 *
 * 2026-10-19 这一版改了三处，都是上一轮的自伤：
 * ① 画面哈希只取 **canvas 元素**，不再取整页。上一版整页截图，于是「DOM 文字区重排」也被算成
 *    「画面跟着参数变」，在 canvas=0 的页面上照样报出 picture_changed=true —— 把「控件有反应」
 *    误报成「3D 场景被驱动」。
 * ② 走 **同源伺服 + 断网开关**，不再用 file://。这批页面是 ES module（import "../jsm/three.module.js"），
 *    file:// 下被 CORS 挡，canvas 从来就没起来过；而不断网时 CDN 与 threejs.org 的资源还能兜住，
 *    报出来的「能跑」里混着「本机恰好有网」。所以默认打 `offline/` 那棵派生树并掐掉非本机请求。
 * ③ 加 `--repeat N`：**同一条判据连跑两遍**，两遍一致才算「稳定」。apparent_weight 的温度滑块
 *    第一次「复原没回到基线帧」、第二次回去了 —— 只跑一遍就会把这种边界样本和 4 只稳定样本混成
 *    一个「5/5」。
 *
 * 用法：node source/library/jcn3_batch_probe.mjs [--tree offline|site] [--repeat 2] [--limit N] [--no-offline-block]
 *       （脚本自己起伺服，不需要事先手动 python -m http.server）
 */
import fs from "node:fs";
import path from "node:path";
import { spawn } from "node:child_process";
import { createRequire } from "node:module";
import { findChromium } from "./ejss_headless_lab.mjs";

const require = createRequire(path.join(process.cwd(), "noop.js"));
const ROOT = process.cwd();
const { chromium } = require("playwright-core");
const argv = process.argv;
const opt = (k, d) => (argv.includes(k) ? argv[argv.indexOf(k) + 1] : d);
const TREE = opt("--tree", "offline");                       // 交付形态是 offline/，site/ 留着做 A/B
const SITE = path.join(ROOT, "source/upstream/3jcn", TREE);
const DIRS = ["Phyc140", "Phyc240", "Simulation", "thermodynamics"];
const limit = argv.includes("--limit") ? +argv[argv.indexOf("--limit") + 1] : 999;
const REPEAT = +opt("--repeat", "1");
const BLOCK = !argv.includes("--no-offline-block");
const NAV = new Set(["simulation.html", "index.html", "about_3jcn.html", "patent.html"]);

// 伺服：ES module 必须同源。起一个 python http.server 指向这一棵树，端口写进证据里便于复现。
const PORT = 8137;
const server = spawn("python", ["-m", "http.server", String(PORT), "--directory", SITE], { stdio: "ignore" });
const sleep = (ms) => new Promise((r) => setTimeout(r, ms));
async function waitServer() {
  for (let i = 0; i < 40; i++) {
    try { const r = await fetch(`http://127.0.0.1:${PORT}/`); if (r.status < 500) return true; } catch { /* 还没起来 */ }
    await sleep(250);
  }
  return false;
}
const up = await waitServer();
if (!up) { console.error("伺服没起来（127.0.0.1:%d），批量探针不做静默降级", PORT); server.kill(); process.exit(1); }

const pages = [];
for (const d of DIRS) {
  const abs = path.join(SITE, d);
  if (!fs.existsSync(abs)) continue;
  for (const f of fs.readdirSync(abs)) {
    if (f.endsWith(".html") && !NAV.has(f)) pages.push(d + "/" + f);
  }
}
const targets = pages.slice(0, limit);

const READ = () => {
  const UNIT = /(\d+(?:[.,]\d+)?)\s*(N|kN|mN|cm³|m³|kg|g|K|°C|V|A|W|Pa|kPa|atm|J|m\/s|km\/h|°|%|cm|mm|m)(?![a-zA-Z])/g;
  const out = [];
  const w = document.createTreeWalker(document.body, NodeFilter.SHOW_TEXT);
  let n;
  while ((n = w.nextNode())) {
    const t = (n.textContent || "").replace(/\s+/g, " ").trim();
    if (!t || n.parentElement?.tagName === "INPUT") continue;
    let m; UNIT.lastIndex = 0;
    while ((m = UNIT.exec(t))) out.push(m[1] + m[2]);
  }
  return {
    sliders: [...document.querySelectorAll('input[type=range]')].map((e) => ({ id: e.id, min: +e.min, max: +e.max, step: +e.step, value: +e.value })),
    readouts: out.slice(0, 20),
    canvas: document.querySelectorAll("canvas").length,
  };
};

const report = { measured_at: new Date().toISOString(), tool: "source/library/jcn3_batch_probe.mjs",
  tree: TREE, serve: `http://127.0.0.1:${PORT}/`, network: BLOCK ? "blocked_except_localhost" : "open (不代表离线)",
  repeat: REPEAT, canvas_only_picture_hash: true, pages: [], summary: {} };
const browser = await chromium.launch({ executablePath: findChromium(), headless: true, args: ["--no-sandbox", "--allow-file-access-from-files", "--use-gl=angle", "--use-angle=swiftshader", "--enable-unsafe-swiftshader"] });
const hash = (b) => require("node:crypto").createHash("sha1").update(b).digest("hex").slice(0, 12);

// 画面证据只认 canvas 自己的像素；没有 canvas 就不给哈希，避免「整页有变化」被当成「场景被驱动」
async function shotOf(p) {
  const n = await p.evaluate(() => document.querySelectorAll("canvas").length);
  if (!n) return null;
  const el = await p.$("canvas");
  if (!el) return null;
  return hash(await el.screenshot());
}

async function onePass(rel, pass) {
  const row = { page: rel, pass };
  const errs = [];
  const blocked = [];
  const p = await (await browser.newContext({ viewport: { width: 1200, height: 800 } })).newPage();
  p.on("pageerror", (e) => errs.push(String(e).slice(0, 120)));
  p.on("console", (m) => { if (m.type() === "error") errs.push("console " + String(m.text()).slice(0, 110)); });
  if (BLOCK) {
    await p.route("**/*", (route) => {
      const u = route.request().url();
      const host = new URL(u).hostname;
      if (host === "127.0.0.1" || host === "localhost") return route.continue();
      blocked.push(u.slice(0, 110));
      return route.abort();
    });
  }
  try {
    await p.goto(`http://127.0.0.1:${PORT}/${rel}`, { waitUntil: "load", timeout: 60000 });
    await p.waitForTimeout(4500);
    const a = await p.evaluate(READ);
    row.sliders = a.sliders.map((s) => `${s.id}[${s.min}..${s.max}]`);
    row.slider_count = a.sliders.length;
    row.canvas = a.canvas;
    row.readouts = a.readouts;
    row.blocked_external = blocked.length;
    const f1 = await shotOf(p);
    await p.waitForTimeout(1200);
    const f2 = await shotOf(p);
    // canvas 都不存在时 render_static 没有意义，不能写 true（上一版 f1===f2 在「两个都取不到」时恒真）
    row.render_static = f1 !== null && f2 !== null && f1 === f2;
    const tries = [];
    for (const s of a.sliders.slice(0, 2)) {
      const before = a.readouts.join("|");
      const nv = s.value > s.min ? s.min : Math.min(s.max, s.min + (s.max - s.min) / 2);
      const setVal = ([id, v]) => {
        const e = document.getElementById(id);
        e.value = String(v);
        e.dispatchEvent(new Event("input", { bubbles: true }));
        e.dispatchEvent(new Event("change", { bubbles: true }));
        if (window.jQuery) window.jQuery(e).trigger("input").trigger("change");
      };
      await p.evaluate(setVal, [s.id, nv]);
      await p.waitForTimeout(900);
      const after = await p.evaluate(READ);
      const fW = await shotOf(p);
      await p.evaluate(setVal, [s.id, s.value]);
      await p.waitForTimeout(900);
      const fR = await shotOf(p);
      tries.push({ slider: s.id, wrote: nv, readback: after.sliders.find((x) => x.id === s.id)?.value,
        readout_changed: after.readouts.join("|") !== before,
        picture_changed: f1 !== null && fW !== null && fW !== f1,
        picture_reverted: f1 !== null && fR !== null && fR === f1 });
    }
    row.writes = tries;
    const anyWrite = tries.some((t) => Math.abs(+t.readback - +t.wrote) < 1e-9);
    const anyReadout = tries.some((t) => t.readout_changed);
    const pictureOk = row.render_static && tries.some((t) => t.picture_changed && t.picture_reverted);
    row.verdict = !row.slider_count ? "no_control" : row.canvas === 0 && !anyReadout ? "canvas_absent"
      : !anyWrite ? "rejected"
      : anyReadout ? "writable_and_readout" : pictureOk ? "writable_and_picture" : "writable_only";
    row.page_errors = errs.slice(0, 3);
  } catch (e) {
    row.verdict = "load_failed";
    row.error = String(e).slice(0, 140);
    row.page_errors = errs.slice(0, 3);
  } finally {
    await p.context().close();
  }
  return row;
}

for (let pass = 0; pass < REPEAT; pass++) {
  for (const rel of targets) {
    const row = await onePass(rel, pass + 1);
    report.pages.push(row);
    console.log("p%d %-16s %-34s sliders=%d canvas=%d 静态=%s 读数=%d 被拦=%d => %s",
      pass + 1, row.verdict, rel, row.slider_count ?? 0, row.canvas ?? 0, String(row.render_static ?? false),
      (row.readouts || []).length, row.blocked_external ?? 0, (row.page_errors || []).length ? "err:" + row.page_errors[0].slice(0, 60) : "");
  }
}
await browser.close();
server.kill();

// 逐页把多趟合档：只有**每一趟都给 picture 通道**才叫 writable_and_picture（稳定），
// 有一趟给不上就单列 unstable —— 边界样本不能与稳定样本混成一个数。
const byPage = new Map();
for (const r of report.pages) (byPage.get(r.page) || byPage.set(r.page, []).get(r.page)).push(r);
const merged = [];
for (const [page, rows] of byPage) {
  const v = rows.map((r) => r.verdict);
  const stable = new Set(v).size === 1;
  const best = v.includes("writable_and_readout") ? "writable_and_readout" : v.includes("writable_and_picture") ? "writable_and_picture"
    : v.includes("writable_only") ? "writable_only" : v.includes("canvas_absent") ? "canvas_absent"
    : v.includes("rejected") ? "rejected" : v.includes("load_failed") ? "load_failed" : "no_control";
  merged.push({ page, verdict: stable ? best : best + "_unstable", passes: v,
    canvas: Math.max(...rows.map((r) => r.canvas ?? 0)), sliders: rows[0].slider_count,
    blocked_external: rows.map((r) => r.blocked_external ?? 0).join("/"),
    page_errors: rows.flatMap((r) => r.page_errors || []).slice(0, 3) });
}
report.per_page = merged;
const c = (v) => merged.filter((r) => r.verdict === v).length;
report.summary = { pages: merged.length, passes: REPEAT,
  writable_and_readout: c("writable_and_readout"), writable_and_picture: c("writable_and_picture"),
  writable_only: c("writable_only"), canvas_absent: c("canvas_absent"), no_control: c("no_control"),
  rejected: c("rejected"), load_failed: c("load_failed"),
  unstable: merged.filter((r) => r.verdict.endsWith("_unstable")).length,
  pages_with_dom_readouts: merged.filter((r) => r.verdict === "writable_and_readout").length,
  pages_rendering_offline: merged.filter((r) => r.canvas > 0).length,
  any_blocked_runtime_left: merged.filter((r) => +String(r.blocked_external).split("/")[0] > 0).length };
fs.writeFileSync(path.join(ROOT, "source/library/jcn3-batch-probe.json"), JSON.stringify(report, null, 2), "utf-8");
console.log("\n汇总:", JSON.stringify(report.summary));
