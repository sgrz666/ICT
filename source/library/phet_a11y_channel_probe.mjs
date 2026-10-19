/** PhET 成品里「无障碍层」能不能当控制通道用——定点实测，不再靠盲按 Tab。
 *
 * 上一轮（phet_headless_probe.mjs）留下三个没归因干净的量，这里一次解决：
 *  ① phetio_global 是 5 个候选名的析取（window.phetio / phet.phetioStudio / phet.phetioWrap /
 *     phet.phetio / phetioEngine / phetioSession），7/13 为真却说不出是哪一个 ⇒ 逐个拆开报；
 *  ② 旧记录写「queryParameters 只有 48 项框架级参数」，本轮读不到 phet.queryParameters ⇒
 *     把三个候选访问器（phet.queryParameters / phet.chipper.queryParameters / phet.phetcommon…）都试一遍，
 *     哪个读得到、读出来多少项，照实写，读不到就把旧数标成待复核（两份文档不能并存两个矛盾数）；
 *  ③ 键盘驱动上一轮是「盲按 14 次 Tab」，0/13 推动——这只能证明我没按到，不能证明仿真不支持键盘。
 *     这里改成**定点**：直接 focus 到带 aria-valuenow 的元素再按方向键，看数值动不动。
 *     动 = Agent 有一条不依赖 PhET-iO 的写通道；不动 = 这条通道实测不成立（并且记下元素坐标/可见性，
 *     说明是不是因为元素本身不可聚焦）。
 *
 * 用法：node source/library/phet_a11y_channel_probe.mjs
 */
import fs from "node:fs";
import path from "node:path";
import { createRequire } from "node:module";
import { pathToFileURL } from "node:url";
import { findChromium } from "./ejss_headless_lab.mjs";

const require = createRequire(path.join(process.cwd(), "noop.js"));
const ROOT = process.cwd();
const { chromium } = require("playwright-core");
const manifest = JSON.parse(fs.readFileSync(path.join(ROOT, "source/upstream/phet-published.json"), "utf-8"));
const exec = findChromium();

// 只看上一轮真能读到 aria-valuenow 的 6 只：没有数值元素就没法测「写了看不看得见」
const TARGETS = ["ohms-law", "geometric-optics", "wave-interference", "energy-skate-park-basics",
  "circuit-construction-kit-dc", "gas-properties"];

const dump = (p) => p.evaluate(() => {
  const phet = window.phet || {};
  const kind = (v) => (v === undefined ? "undefined" : v === null ? "null" : typeof v);
  const qp = [["phet.queryParameters", phet.queryParameters],
    ["phet.chipper.queryParameters", phet.chipper && phet.chipper.queryParameters],
    ["phet.phetcommon.queryParameters", phet.phetcommon && phet.phetcommon.queryParameters]]
    .map(([name, o]) => ({ name, present: kind(o) === "object", keys: o && typeof o === "object" ? Object.keys(o).length : null }));
  const els = [...document.querySelectorAll("[aria-valuenow]")];
  return {
    globals: {
      window_phetio: kind(window.phetio), phet_phetio: kind(phet.phetio),
      phet_phetioStudio: kind(phet.phetioStudio), phet_phetioWrap: kind(phet.phetioWrap),
      window_phetioEngine: kind(window.phetioEngine), window_phetioSession: kind(window.phetioSession),
      phet_tandem: kind(phet.tandem), phet_phetcommon: kind(phet.phetcommon),
    },
    phetio_dom_ids: document.querySelectorAll("[data-phetio-id]").length,
    query_parameters: qp,
    a11y: els.slice(0, 6).map((e) => ({
      tag: e.tagName, role: e.getAttribute("role"), now: e.getAttribute("aria-valuenow"),
      tabindex: e.getAttribute("tabindex"), text: (e.innerText || "").replace(/\s+/g, " ").slice(0, 30),
      rect: (({ x, y, width, height }) => ({ x: Math.round(x), y: Math.round(y), w: Math.round(width), h: Math.round(height) }))(e.getBoundingClientRect()),
    })),
  };
});

const report = { measured_at: new Date().toISOString(), tool: "source/library/phet_a11y_channel_probe.mjs", sims: [] };
const browser = await chromium.launch({ executablePath: exec, headless: true, args: ["--no-sandbox", "--allow-file-access-from-files"] });
try {
  for (const sim of TARGETS) {
    const item = manifest.sims.find((s) => s.sim === sim);
    const row = { sim };
    const p = await (await browser.newContext({ viewport: { width: 1100, height: 720 } })).newPage();
    try {
      await p.goto(pathToFileURL(path.join(ROOT, item.file)).href, { waitUntil: "load", timeout: 90000 });
      await p.waitForTimeout(4000);
      const info = await dump(p);
      row.read = info;
      // 定点写：逐个 aria-valuenow 元素，先 focus（拿不到焦点就试点击其矩形中心），再按方向键
      row.writes = [];
      for (let i = 0; i < Math.min(info.a11y.length, 4); i++) {
        const before = await p.evaluate((idx) => document.querySelectorAll("[aria-valuenow]")[idx]?.getAttribute("aria-valuenow") ?? null, i);
        const gotFocus = await p.evaluate((idx) => {
          const e = document.querySelectorAll("[aria-valuenow]")[idx];
          if (!e) return "no-element";
          if (e.getAttribute("tabindex") === null) e.setAttribute("tabindex", "-1");
          e.focus();
          return document.activeElement === e ? "focused" : "not-focusable";
        }, i);
        for (const k of ["ArrowRight", "ArrowRight", "ArrowUp"]) await p.keyboard.press(k);
        await p.waitForTimeout(500);
        const afterKeys = await p.evaluate((idx) => document.querySelectorAll("[aria-valuenow]")[idx]?.getAttribute("aria-valuenow") ?? null, i);
        const clicked = await p.evaluate((idx) => {
          const e = document.querySelectorAll("[aria-valuenow]")[idx];
          if (!e) return null;
          e.dispatchEvent(new KeyboardEvent("keydown", { key: "End", bubbles: true }));
          e.dispatchEvent(new Event("input", { bubbles: true }));
          return "dispatched";
        }, i);
        await p.waitForTimeout(400);
        const afterEvents = await p.evaluate((idx) => document.querySelectorAll("[aria-valuenow]")[idx]?.getAttribute("aria-valuenow") ?? null, i);
        row.writes.push({ index: i, before, gotFocus, after_keyboard: afterKeys, keyboard_changed: afterKeys !== before, synthetic_events: clicked, after_synthetic: afterEvents, synthetic_changed: afterEvents !== before });
      }
      row.writable_any = row.writes.some((w) => w.keyboard_changed || w.synthetic_changed);
    } catch (e) {
      row.error = String(e).slice(0, 160);
    } finally {
      await p.context().close();
    }
    report.sims.push(row);
    console.log(`${sim.padEnd(30)} phetio全局=${JSON.stringify(row.read?.globals?.window_phetio)}/${JSON.stringify(row.read?.globals?.phet_phetio)} `
      + `qp=${(row.read?.query_parameters || []).filter((q) => q.present).map((q) => `${q.name}:${q.keys}`).join(",") || "读不到"} `
      + `数值元素=${(row.read?.a11y || []).length} 写成功=${row.writable_any ? "Y" : "N"}`);
    for (const w of row.writes || []) console.log(`    [${w.index}] ${w.before} ->键盘 ${w.after_keyboard} (${w.keyboard_changed ? "变" : "不变"}) 合成事件 ${w.after_synthetic} (${w.synthetic_changed ? "变" : "不变"}) 焦点=${w.gotFocus}`);
  }
} finally {
  await browser.close();
}
const n = (f) => report.sims.filter(f).length;
report.summary = {
  sims: report.sims.length,
  query_parameters_readable: n((r) => (r.read?.query_parameters || []).some((q) => q.present)),
  any_write_channel: n((r) => r.writable_any),
};
fs.writeFileSync(path.join(ROOT, "source/library/phet-a11y-channel-probe.json"), JSON.stringify(report, null, 2), "utf-8");
console.log("\n汇总:", JSON.stringify(report.summary), "\n写入 source/library/phet-a11y-channel-probe.json");
