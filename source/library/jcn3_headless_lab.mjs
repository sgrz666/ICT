/** 3JCN 演示页的控制面实测：那些 <input type=range> 是不是 Agent 真能用的改参通道。
 *
 * 结构探针（../upstream/3jcn/probe_3jcn_demo_interfaces.py）已经量出：抓下来的 14 页里
 * 14/14 都有 range 滑块，而且是**带名字带量程的物理量**（tempSlider 0~600、massMetalSlider 300~700、
 * density1 1~3 step 0.1…）。这比 PhET 成品清楚得多，但简报里那句警告正是针对这种情况：
 * 「控件存在」不等于「改了引擎跟着变」。所以这里跑三档判据，全在同一页里对照：
 *   ① readback —— 写值后 input.value 是否真变成新值（防被页面逻辑当场改回去）；
 *   ② observable —— 页面上的**数字读数**（body 文本里的数）是否跟着变；
 *   ③ control  —— 用同一个值再派发一次事件，读数必须**不变**：
 *      没有这一条，「任何事件都重绘/读数抖动」也会被我判成「改参生效」（老规矩：判据要能失败）。
 * 再加 reverse：把值改回原值，读数必须回到原来那一组——证明这是随参数走的，不是一次性噪声。
 *
 * 用法：node source/library/jcn3_headless_lab.mjs [--demo <本地 html 路径>] [--json <证据路径>]
 */
import fs from "node:fs";
import path from "node:path";
import { createHash } from "node:crypto";
import { createRequire } from "node:module";
import { pathToFileURL } from "node:url";
import { findChromium } from "./ejss_headless_lab.mjs";

const require = createRequire(path.join(process.cwd(), "noop.js"));
const ROOT = process.cwd();
const { chromium } = require("playwright-core");
const argv = process.argv;
const opt = (k, d) => (argv.includes(k) ? argv[argv.indexOf(k) + 1] : d);
const demo = opt("--demo", "source/upstream/3jcn/site/Phyc140/buoyant_force_exp.html");
// 页面是 ES module（import from "../jsm/three.module.js"），file:// 下被 CORS 挡；
// 所以这一支默认要求同源伺服（--url http://127.0.0.1:<port>/…），给 --demo 时退回 file:// 便于对照。
const urlArg = argv.includes("--url") ? argv[argv.indexOf("--url") + 1] : null;
const out = opt("--json", "source/library/jcn3-headless-lab-evidence.json");
const exec = findChromium();

const READ = () => {
  // 上一版把 body 里所有数字都当读数，结果采到的是滑块量程标注（100/200、1500/3000、10/100），
  // 对照组必然守不住。这一版只认「数字紧跟物理单位」的文本，并且跳过 input 本身。
  const UNIT = /(\d+(?:[.,]\d+)?)\s*(N|kN|mN|cm³|m³|mm³|kg|g|K|°C|V|A|W|Pa|atm|J|m\/s|km\/h|°|%|cm|mm|m)(?![a-zA-Z])/g;
  const readouts = [];
  const walk = document.createTreeWalker(document.body, NodeFilter.SHOW_TEXT);
  let node;
  while ((node = walk.nextNode())) {
    const txt = (node.textContent || "").replace(/\s+/g, " ").trim();
    if (!txt || (node.parentElement && node.parentElement.tagName === "INPUT")) continue;
    let m;
    UNIT.lastIndex = 0;
    while ((m = UNIT.exec(txt))) readouts.push(m[1] + m[2]);
  }
  const nums = readouts.map((x) => parseFloat(x.replace(/[^0-9.,-]/g, "").replace(",", ".")));
  return {
    sliders: [...document.querySelectorAll('input[type=range]')].map((e) => ({ id: e.id, min: +e.min, max: +e.max, step: +e.step, value: +e.value })),
    number_tokens: nums,
    readout_tokens: readouts.slice(0, 24),
    text: (document.body.innerText || "").replace(/\s+/g, " ").slice(0, 260),
    has_canvas: document.querySelectorAll("canvas").length,
  };
};
// 只比「读数指纹」：滑块自身 value 的变动当然会进 innerText，读数取的是滑块之外的数字
const fingerprint = (r) => r.number_tokens.join("|");

const report = { measured_at: new Date().toISOString(), tool: "source/library/jcn3_headless_lab.mjs", demo, chromium: exec, checks: [] };
const browser = await chromium.launch({ executablePath: exec, headless: true, args: ["--no-sandbox", "--allow-file-access-from-files"] });
const p = await (await browser.newContext({ viewport: { width: 1280, height: 820 } })).newPage();
const errs = [];
p.on("pageerror", (e) => errs.push(String(e).slice(0, 140)));
try {
  const target = urlArg || pathToFileURL(path.join(ROOT, demo)).href;
  report.target = target;
  await p.goto(target, { waitUntil: "load", timeout: 90000 });
  await p.waitForTimeout(6000);                     // 演示页要等 three.js 与 CDN 脚本就位
  const base = await p.evaluate(READ);
  report.baseline = base;
  // 3D 页面的物理后果多半画在 canvas 上而不是写在 DOM 文本里，所以画面是这一类的可观测量。
  // 但画面能当判据的前提是**它自己不动**：先连取两帧不作任何操作做对照组，两帧一致才允许用画面差异当证据
  // （PhET 那轮就是栽在「动画仿真不按键也在变画」上，同一课不能摔第二次）。
  const shot = async () => createHash("sha1").update(await p.screenshot()).digest("hex").slice(0, 12);
  const shotA = await shot();
  await p.waitForTimeout(1200);
  const shotB = await shot();
  report.render_control = { frame_a: shotA, frame_b: shotB, render_is_static: shotA === shotB,
    note: "render_is_static=false 时画面差异一律不作判据（动画本底），只能靠 DOM 读数" };
  console.log("渲染对照组：两帧 %s / %s ⇒ 静态=%s", shotA, shotB, report.render_control.render_is_static);
  console.log("基线：滑块 %d 个，读数 %d 个数字，canvas %d；文本 %s",
    base.sliders.length, base.number_tokens.length, base.has_canvas, base.text.slice(0, 90));
  if (!base.sliders.length) throw new Error("页面里没有 range 控件，判据不成立");

  const write = async (id, v) => p.evaluate(([id, v]) => {
    const e = document.getElementById(id);
    if (!e) return false;
    e.value = String(v);
    e.dispatchEvent(new Event("input", { bubbles: true }));
    e.dispatchEvent(new Event("change", { bubbles: true }));
    if (window.jQuery) window.jQuery(e).trigger("input").trigger("change");   // 这批改用 jQuery 绑事件
    return true;
  }, [id, v]);

  for (const s of base.sliders) {
    const row = { slider: s.id, range: [s.min, s.max, s.step], value: s.value };
    // ③ 对照组：同值再派发一次事件，读数不许变
    await write(s.id, s.value); await p.waitForTimeout(700);
    const ctrl = await p.evaluate(READ);
    row.control_noop = fingerprint(ctrl) === fingerprint(base);

    // ①② 写一个新值（往量程内侧取，避免撞端点）
    const target = s.value > s.min ? s.min : s.min + (s.max - s.min) * 0.25;
    const nv = Math.round(target / s.step) * s.step;
    const okSet = await write(s.id, nv);
    await p.waitForTimeout(900);
    const after = await p.evaluate(READ);
    const s2 = after.sliders.find((x) => x.id === s.id) || {};
    row.write = { attempted: nv, applied: okSet, readback: s2.value, readback_matches: Math.abs((s2.value ?? NaN) - nv) < 1e-9 };
    row.numbers_before = base.number_tokens;
    row.numbers_after = after.number_tokens;
    row.readout_changed = fingerprint(after) !== fingerprint(base);
    const shotAfter = await shot();
    // 画面通道只在「不操作时两帧一致」的前提下计分，并且要求改回原值后画面也回来（双向才排掉噪声）
    row.picture = { baseline: shotA, after_write: shotAfter, changed: shotAfter !== shotA, usable: report.render_control.render_is_static };
    row.text_changed = after.text.slice(0, 200) !== base.text.slice(0, 200);

    // reverse：改回原值，读数应回到基线那一组
    await write(s.id, s.value); await p.waitForTimeout(900);
    const back = await p.evaluate(READ);
    row.reverts_to_baseline = fingerprint(back) === fingerprint(base);
    const shotBack = await shot();
    row.picture.reverted_to_baseline = shotBack === shotA;
    // 判别实验：「改回原值画面没回来」有两种解释——页面是单向状态，或者我的复原没触发它的监听。
    // 分法就一个：点页面自己的 Reset（人真会用的那条路），再看画面回不回基线帧。
    const resetHit = await p.evaluate(() => {
      const b = [...document.querySelectorAll("button,[role=button],a,input[type=button]")].find((x) =>
        /reset/i.test((x.innerText || x.value || x.getAttribute("aria-label") || "")));
      if (!b) return null;
      b.click();
      return (b.innerText || b.value || "").trim().slice(0, 30);
    });
    await p.waitForTimeout(1500);
    const shotReset = await shot();
    row.reset = { button: resetHit, frame: shotReset, back_to_baseline: shotReset === shotA };
    row.interpretation = row.picture.changed
      ? (row.reset.back_to_baseline
        ? "写值改到画面、Reset 能回基线 ⇒ 复原是路径问题，画面通道成立"
        : "写值改到画面但 Reset 也回不去 ⇒ 页面是单向状态或 Reset 不清这参数，画面通道不可逆")
      : "写值没改到画面";
    const observable = row.readout_changed || (row.picture.usable && row.picture.changed && row.picture.reverted_to_baseline);
    row.observable_channel = row.readout_changed ? "dom_readout" : (observable ? "static_canvas" : "none");

    row.verdict = row.write.readback_matches && row.control_noop && observable && row.reverts_to_baseline
      ? "agent_writable_and_observable"
      : row.write.readback_matches && row.control_noop ? "accepted_but_no_observable_change"
      : row.write.readback_matches ? "readback_ok_but_control_group_fails"
      : "rejected";
    report.checks.push(row);
    console.log("  %s [%s..%s step %s] 写 %s→%s 回读=%s 匹配=%s 对照组不变=%s 读数变=%s 改回原值=%s => %s" % (
      s.id, s.min, s.max, s.step, s.value, row.write.attempted, row.write.readback,
      row.write.readback_matches, row.control_noop, row.readout_changed, row.reverts_to_baseline, row.verdict));
  }
} catch (e) {
  report.load_error = String(e).slice(0, 220);
} finally {
  report.page_errors = errs.slice(0, 6);
  await p.context().close();
  await browser.close();
}
const c = (f) => report.checks.filter(f).length;
report.summary = {
  sliders: report.checks.length,
  agent_writable_and_observable: c((r) => r.verdict === "agent_writable_and_observable"),
  accepted_but_no_observable_change: c((r) => r.verdict === "accepted_but_no_observable_change"),
  rejected: c((r) => r.verdict === "rejected"),
};
report.result = report.summary.agent_writable_and_observable > 0 ? "PASS" : report.checks.length ? "FAIL" : "ERROR";
fs.writeFileSync(path.join(ROOT, out), JSON.stringify(report, null, 2), "utf-8");
console.log("\n汇总:", JSON.stringify(report.summary), report.result, "| 页面异常", errs.length, "\n写入", out);
