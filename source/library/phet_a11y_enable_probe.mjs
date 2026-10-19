/** 为什么同样有 [aria-valuenow]，ohms-law 的无障碍 input 有尺寸（51×253、可 focus、可写），
 * 另外 5 只却是 0×0、focus 不进去？——不猜开关名字，直接把两组的 queryParameters 键做差集，
 * 再用实测验证候选：带上某个参数重新加载，看那批 0×0 的 input 会不会展开成有尺寸、可聚焦、可写。
 *
 * 这一步值得做，是因为它决定 PhET 这条线的定位：如果只是一个开关的差别，
 * 「成熟成品」就能整批升成「Agent 可驱动」；如果试遍候选仍是 0×0，那就照实写「逐只不通，别当通用能力」。
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

const GOOD = "ohms-law";                    // 对照组：input 有尺寸、已实测可写
const BAD = ["geometric-optics", "wave-interference", "energy-skate-park-basics",
  "circuit-construction-kit-dc", "gas-properties"];
const CANDIDATES = ["?a11y=visible", "?a11y=label", "?a11y=sound", "?accessibility=true",
  "?supportsMultipleSim=visible", "?fuzz=false", "?peak=0"];

const probe = (p) => p.evaluate(() => {
  const qp = (window.phet && window.phet.chipper && window.phet.chipper.queryParameters) || {};
  const els = [...document.querySelectorAll("[aria-valuenow]")];
  const sized = els.filter((e) => { const r = e.getBoundingClientRect(); return r.width > 0 && r.height > 0; });
  let focusOk = null;
  if (els[0]) {
    const e = els[0];
    if (e.getAttribute("tabindex") === null) e.setAttribute("tabindex", "-1");
    e.focus();
    focusOk = document.activeElement === e;
  }
  return {
    qp_keys_a11: Object.keys(qp).filter((k) => /a11|access|label|input|touch|mouse|pick/i.test(k)).sort(),
    qp_total: Object.keys(qp).length,
    peers: els.length, peers_with_size: sized.length,
    peer_display: els.slice(0, 3).map((e) => getComputedStyle(e).display + "/" + getComputedStyle(e).visibility + "/" + Math.round(e.getBoundingClientRect().width)),
    first_focusable: focusOk,
  };
});

const report = { measured_at: new Date().toISOString(), tool: "source/library/phet_a11y_enable_probe.mjs", rows: [] };
const browser = await chromium.launch({ executablePath: exec, headless: true, args: ["--no-sandbox", "--allow-file-access-from-files"] });
try {
  for (const sim of [GOOD, ...BAD]) {
    const item = manifest.sims.find((s) => s.sim === sim);
    const file = pathToFileURL(path.join(ROOT, item.file)).href;
    for (const qs of ["", ...CANDIDATES]) {
      const p = await (await browser.newContext({ viewport: { width: 1100, height: 760 } })).newPage();
      const row = { sim, query: qs || "(基线)" };
      try {
        await p.goto(file + qs, { waitUntil: "load", timeout: 90000 });
        await p.waitForTimeout(3500);
        Object.assign(row, await probe(p));
        // 有尺寸且可聚焦，就真按一次方向键，看数值动不动——展开不等于可写
        if (row.first_focusable) {
          const b = await p.evaluate(() => document.querySelectorAll("[aria-valuenow]")[0].getAttribute("aria-valuenow"));
          for (const k of ["ArrowRight", "ArrowRight", "ArrowUp"]) await p.keyboard.press(k);
          await p.waitForTimeout(500);
          const a = await p.evaluate(() => document.querySelectorAll("[aria-valuenow]")[0].getAttribute("aria-valuenow"));
          row.write_test = { before: b, after: a, changed: b !== a };
        }
      } catch (e) {
        row.error = String(e).slice(0, 120);
      } finally {
        await p.context().close();
      }
      report.rows.push(row);
      console.log(`${sim.padEnd(30)}${(row.query).padEnd(26)} qp(a11键)=${JSON.stringify(row.qp_keys_a11 || [])} input=${row.peers ?? "?"} 有尺寸=${row.peers_with_size ?? "?"} 可聚焦=${row.first_focusable ?? "?"} 写=${row.write_test ? (row.write_test.changed ? "Y " + row.write_test.before + "→" + row.write_test.after : "N") : "-"}`);
    }
  }
} finally {
  await browser.close();
}
const n = (f) => report.rows.filter(f).length;
report.summary = {
  loads: report.rows.length,
  any_variant_expanded_the_inputs: n((r) => (r.peers_with_size || 0) > 0),
  any_variant_made_it_focusable: n((r) => r.first_focusable === true),
  any_variant_written: n((r) => r.write_test && r.write_test.changed),
};
fs.writeFileSync(path.join(ROOT, "source/library/phet-a11y-enable-probe.json"), JSON.stringify(report, null, 2), "utf-8");
console.log("\n汇总:", JSON.stringify(report.summary), "\n写入 source/library/phet-a11y-enable-probe.json");
