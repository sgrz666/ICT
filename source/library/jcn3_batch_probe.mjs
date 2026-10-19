/** 3JCN 批量探针：把「一只页面能驱动」扩成「整批逐只分档」。
 *
 * 为什么必须批量：上一轮只在 apparent_weight 一只上拿到 5/5 的写-观测-复原闭环，
 * 这跟当初 EJSS 只测两个模型就下结论是同一个错。3JCN 本地镜像里已有 31 份演示页，
 * 这一支把每只都跑同四条判据，按档位记账，不压成一个布尔：
 *   writable_and_readout   —— 写值后**页面自己的数字读数**跟着变（这一档才谈得上解析式对账）
 *   writable_and_picture   —— 数字读数没有，但画面变且能复原（画面须先过「不操作两帧一致」对照组）
 *   writable_only          —— 值写得进、回读得到，但看不到任何可观测后果
 *   dynamic_render         —— 页面自己在动，画面通道不可用（不是失败，是这一档不能用这条判据）
 *   no_control / load_failed
 *
 * 用法：node source/library/jcn3_batch_probe.mjs [--serve http://127.0.0.1:<port>] [--limit N]
 */
import fs from "node:fs";
import path from "node:path";
import { createRequire } from "node:module";
import { pathToFileURL } from "node:url";
import { findChromium } from "./ejss_headless_lab.mjs";

const require = createRequire(path.join(process.cwd(), "noop.js"));
const ROOT = process.cwd();
const { chromium } = require("playwright-core");
const argv = process.argv;
const SITE = path.join(ROOT, "source/upstream/3jcn/site");
const DIRS = ["Phyc140", "Phyc240", "Simulation", "thermodynamics"];
const limit = argv.includes("--limit") ? +argv[argv.indexOf("--limit") + 1] : 999;
const NAV = new Set(["simulation.html", "index.html", "about_3jcn.html", "patent.html"]);

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

const report = { measured_at: new Date().toISOString(), tool: "source/library/jcn3_batch_probe.mjs", pages: [], summary: {} };
const browser = await chromium.launch({ executablePath: findChromium(), headless: true, args: ["--no-sandbox", "--allow-file-access-from-files", "--use-gl=angle", "--use-angle=swiftshader", "--enable-unsafe-swiftshader"] });
const hash = (b) => require("node:crypto").createHash("sha1").update(b).digest("hex").slice(0, 12);
for (const rel of targets) {
  const row = { page: rel };
  const errs = [];
  const p = await (await browser.newContext({ viewport: { width: 1200, height: 800 } })).newPage();
  p.on("pageerror", (e) => errs.push(String(e).slice(0, 120)));
  try {
    await p.goto(pathToFileURL(path.join(SITE, ...rel.split("/"))).href, { waitUntil: "load", timeout: 60000 });
    await p.waitForTimeout(4500);
    const a = await p.evaluate(READ);
    row.sliders = a.sliders.map((s) => `${s.id}[${s.min}..${s.max}]`);
    row.slider_count = a.sliders.length;
    row.canvas = a.canvas;
    row.readouts = a.readouts;
    const f1 = hash(await p.screenshot());
    await p.waitForTimeout(1200);
    const f2 = hash(await p.screenshot());
    row.render_static = f1 === f2;
    const tries = [];
    for (const s of a.sliders.slice(0, 2)) {
      const before = a.readouts.join("|");
      const nv = s.value > s.min ? s.min : Math.min(s.max, s.min + (s.max - s.min) / 2);
      await p.evaluate(([id, v]) => {
        const e = document.getElementById(id);
        e.value = String(v);
        e.dispatchEvent(new Event("input", { bubbles: true }));
        e.dispatchEvent(new Event("change", { bubbles: true }));
        if (window.jQuery) window.jQuery(e).trigger("input").trigger("change");
      }, [s.id, nv]);
      await p.waitForTimeout(900);
      const after = await p.evaluate(READ);
      const fW = hash(await p.screenshot());
      await p.evaluate(([id, v]) => {
        const e = document.getElementById(id);
        e.value = String(v);
        e.dispatchEvent(new Event("input", { bubbles: true }));
        e.dispatchEvent(new Event("change", { bubbles: true }));
        if (window.jQuery) window.jQuery(e).trigger("input").trigger("change");
      }, [s.id, s.value]);
      await p.waitForTimeout(900);
      const fR = hash(await p.screenshot());
      tries.push({ slider: s.id, wrote: nv, readback: after.sliders.find((x) => x.id === s.id)?.value,
        readout_changed: after.readouts.join("|") !== before,
        picture_changed: fW !== f1, picture_reverted: fR === f1 });
    }
    row.writes = tries;
    const anyWrite = tries.some((t) => Math.abs(+t.readback - +t.wrote) < 1e-9);
    const anyReadout = tries.some((t) => t.readout_changed);
    const anyPicture = tries.some((t) => t.picture_changed);
    const pictureOk = row.render_static && tries.some((t) => t.picture_changed && t.picture_reverted);
    row.verdict = !row.slider_count ? "no_control" : !anyWrite ? "rejected"
      : anyReadout ? "writable_and_readout" : pictureOk ? "writable_and_picture"
      : !row.render_static && anyPicture ? "dynamic_render" : "writable_only";
    row.page_errors = errs.slice(0, 3);
  } catch (e) {
    row.verdict = "load_failed";
    row.error = String(e).slice(0, 140);
  } finally {
    await p.context().close();
  }
  report.pages.push(row);
  console.log("%s  %-34s sliders=%d canvas=%d 静态=%s 读数=%d => %s",
    row.verdict.padEnd(20), rel, row.slider_count ?? 0, row.canvas ?? 0, String(row.render_static ?? false), (row.readouts || []).length, (row.page_errors || []).length ? "err" : "");
}
await browser.close();
const c = (v) => report.pages.filter((r) => r.verdict === v).length;
report.summary = { pages: report.pages.length, writable_and_readout: c("writable_and_readout"), writable_and_picture: c("writable_and_picture"), writable_only: c("writable_only"), dynamic_render: c("dynamic_render"), no_control: c("no_control"), rejected: c("rejected"), load_failed: c("load_failed"),
  pages_with_dom_readouts: report.pages.filter((r) => (r.readouts || []).length > 0).length };
fs.writeFileSync(path.join(ROOT, "source/library/jcn3-batch-probe.json"), JSON.stringify(report, null, 2), "utf-8");
console.log("\n汇总:", JSON.stringify(report.summary));
