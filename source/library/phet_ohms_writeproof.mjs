/** PhET 成品能不能「改物理量并验证」——拿 ohms-law 做一次性写通路证明。
 *
 * 起因：逐只探针（phet_headless_probe.mjs）在 ohms-law 上按到无障碍元素时，
 * aria-valuenow 从 4.5→6、500→560 真的动了；其它 5 只同类元素「不可聚焦」，动不了。
 * 但「属性数字变了」不等于「物理量改了」——可能只是无障碍层的字符串自己跳。
 * 所以这里做闭环：改电阻 → 读仿真画面上显示的电流 → 和 V/R 对一遍。
 * 对得上，才允许把「成品不能改参」这句改成「成品没有参数 API，但无障碍层焦点+方向键是一条可用的写通路（至少这只成立）」。
 *
 * 读数一律从仿真自己画出来的文本里取（body innerText），不读引擎自报的内部状态。
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
const item = manifest.sims.find((s) => s.sim === "ohms-law");
const exec = findChromium();

// 页面文本里把「数字 + 单位」抓出来。第一版只匹配了 V / Ω / A / mA，结果仿真把电流念成
// 「Current now 40.9 milliamps」——单位是拼写出来的，正则没抓到，写通路明明成立却被判 FAIL。
// 所以单位要同时收符号与英文单词两种写法。UNIT 必须写在 READ 内部：READ 会被序列化进页面执行，取不到外层常量。
const READ = () => {
  const UNIT = { volt: "(?:V|volts?)", ohm: "(?:\u03a9|ohms?)", amp: "(?:A|amps?)", milliamp: "(?:mA|milliamps?)" };
  const txt = (document.body.innerText || "").replace(/\s+/g, " ");
  const grab = (unit) => {
    const re = new RegExp("([\\d]+(?:[.,]\\d+)?)\\s*" + unit + "\\b", "g");
    const all = [];
    let m;
    while ((m = re.exec(txt))) all.push(parseFloat(m[1].replace(",", ".")));
    return all;
  };
  return {
    text: txt.slice(0, 400),
    values: [...document.querySelectorAll("[aria-valuenow]")].map((e) => e.getAttribute("aria-valuenow")),
    volt: grab(UNIT.volt), ohm: grab(UNIT.ohm),
    milliamp: grab(UNIT.milliamp), amp: grab(UNIT.amp),
  };
};

const report = { measured_at: new Date().toISOString(), tool: "source/library/phet_ohms_writeproof.mjs", sim: item.sim, version: item.version, steps: [] };
const browser = await chromium.launch({ executablePath: exec, headless: true, args: ["--no-sandbox", "--allow-file-access-from-files"] });
const p = await (await browser.newContext({ viewport: { width: 1100, height: 760 } })).newPage();
try {
  await p.goto(pathToFileURL(path.join(ROOT, item.file)).href, { waitUntil: "load", timeout: 90000 });
  await p.waitForTimeout(4000);
  report.baseline = await p.evaluate(READ);
  console.log("基线:", JSON.stringify(report.baseline.values), "| 文本:", report.baseline.text.slice(0, 120));

  // 逐个无障碍元素试焦点：上一轮只有 ohms-law 的两个元素 focus 得进去
  const idxs = (report.baseline.values || []).map((_, i) => i);
  for (const idx of idxs) {
    const focusable = await p.evaluate((i) => {
      const e = document.querySelectorAll("[aria-valuenow]")[i];
      if (!e) return false;
      if (e.getAttribute("tabindex") === null) e.setAttribute("tabindex", "-1");
      e.focus();
      return document.activeElement === e;
    }, idx);
    if (!focusable) { report.steps.push({ element: idx, focusable: false }); continue; }
    for (const target of (idx === 0 ? [2, 6, 9] : [300, 1000, 200])) {
      // 用方向键把该元素推到目标附近（每步 20 Ω 是本机实测步进，不硬编：推 60 次后取最接近值）
      let cur = parseFloat((await p.evaluate(READ)).values[idx]);
      let presses = 0;
      while (Math.abs(cur - target) > (idx === 0 ? 0.3 : 25) && presses < 60) {
        await p.keyboard.press(cur < target ? "ArrowRight" : "ArrowLeft");
        presses++;
        cur = parseFloat((await p.evaluate(READ)).values[idx]);
      }
      await p.waitForTimeout(1200);
      const r = await p.evaluate(READ);
      const V = parseFloat(r.values[0]);       // 第一只是电池电压
      const R = parseFloat(r.values[1]);       // 第二只是电阻
      const I_A = V / R;                       // 解析式：I = V/R（安培）
      const shown = r.amp.concat(r.milliamp.map((x) => x / 1000)).filter((x) => x > 0);
      const best = shown.length ? shown.reduce((a, b) => (Math.abs(b - I_A) < Math.abs(a - I_A) ? b : a)) : null;
      const rel = best === null ? null : Math.abs(best - I_A) / I_A;
      const text_V = r.volt.length ? Math.max(...r.volt) : null;
      const text_R = r.ohm.length ? Math.max(...r.ohm) : null;
      report.steps.push({ element: idx, focusable: true, target, presses, read: r, V, R, I_expected_A: I_A, I_shown_A: best, rel_error: rel, text_V, text_R, obeys_ohm: rel !== null && rel < 0.05 });
      console.log(`元素${idx} → 目标 ${target}: V=${V} R=${R} 期望 I=${I_A.toFixed(5)} A，画面读到 ${best === null ? "无" : best.toFixed(5) + " A"} 相对误差 ${rel === null ? "n/a" : (rel * 100).toFixed(2) + "%"} ${rel !== null && rel < 0.05 ? "PASS" : "FAIL"}`);
      console.log(`   画面文本: ${r.text.slice(0, 150)}`);
    }
  }
} finally {
  await p.context().close();
  await browser.close();
}
const passes = report.steps.filter((s) => s.obeys_ohm).length;
report.summary = { elements_focusable: report.steps.filter((s) => s.focusable).map((s) => s.element).filter((v, i, a) => a.indexOf(v) === i), write_steps: report.steps.filter((s) => s.focusable).length, ohm_checks_passed: passes };
report.result = passes >= 2 ? "PASS" : passes === 1 ? "PART" : "FAIL";
fs.writeFileSync(path.join(ROOT, "source/library/phet-ohms-writeproof.json"), JSON.stringify(report, null, 2), "utf-8");
console.log("\n汇总:", JSON.stringify(report.summary), report.result, "\n写入 source/library/phet-ohms-writeproof.json");
