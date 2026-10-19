/** PhET 官方发布成品的控制面探针：把「iframe 能打开 ≠ Agent 能改实验」这句话逐只仿真量一遍。
 *
 * 三件事分开测，别混成一个结论：
 *  ① 离线能不能跑（file:// 直开，统计 JS 异常与资源失败）；
 *  ② URL 参数到底能控制到哪一层——用两个**框架级**旋钮当探针：?screens=2（换屏）与 ?locale=es（换语言），
 *     看整页 PNG 是否随之改变；改变得了才说明「URL 参数被消费」，但这只证明能换壳，不证明能改物理量；
 *  ③ 有没有 PhET-iO 的工具化接口（`data-phetio-id` 计数 + phetio 全局对象），
 *     那才是官方给的「外部程序改参数」入口；没有就只能靠人手点，或对 GPL 源码自己重新构建。
 *
 * 用法：node source/library/phet_headless_probe.mjs [--json source/library/phet-headless-probe.json]
 */

import fs from "node:fs";
import path from "node:path";
import { createRequire } from "node:module";
import { pathToFileURL } from "node:url";
import { findChromium } from "./ejss_headless_lab.mjs";
import { createHash } from "node:crypto";

const require = createRequire(path.join(process.cwd(), "noop.js"));
const ROOT = process.cwd();
const { chromium } = require("playwright-core");
const manifest = JSON.parse(fs.readFileSync(path.join(ROOT, "source/upstream/phet-published.json"), "utf-8"));
const out = path.join(ROOT, process.argv.includes("--json") ? process.argv[process.argv.indexOf("--json") + 1] : "source/library/phet-headless-probe.json");
const exec = findChromium();

const settle = (p, ms = 3500) => p.waitForTimeout(ms);
// 遥测桩在 file:// 下必然报错（发布包内嵌 Cloudflare RUM：sendBeacon 只允许 HTTP(S)）。
// 那是网络桩，不是仿真本体；混在一起统计会把 13 只全判成「起不来」。
const TELEMETRY = /sendBeacon|cdn-cgi\/rum|google-analytics|googletagmanager|\/rum\?|Beacons are only supported/i;
async function read(p) {
  return p.evaluate(() => {
    const phet = window.phet || null;
    const keys = (o) => (o && typeof o === "object" ? Object.keys(o).sort() : null);
    const a11y = [...document.querySelectorAll("[aria-valuenow]")].slice(0, 12).map((e) => ({
      role: e.getAttribute("role"), now: e.getAttribute("aria-valuenow"),
      min: e.getAttribute("aria-valuemin"), max: e.getAttribute("aria-valuemax"),
      label: (e.getAttribute("aria-label") || e.innerText || "").replace(/\s+/g, " ").slice(0, 40),
    }));
    return {
      title: document.title,
      has_phet_ns: !!phet,
      phetio_dom_ids: document.querySelectorAll("[data-phetio-id]").length,
      // 命名空间存在 ≠ 接口可用：把 phet.phetio 里到底有什么列出来，判据后面按能不能调用来下
      phet_ns_keys: keys(phet),
      phetio_ns_keys: keys(phet && phet.phetio),
      phetio_global: !!(window.phetio || (phet && (phet.phetioStudio || phet.phetioWrap || phet.phetio)) || window.phetioEngine || window.phetioSession),
      phetio_callable: !!(window.phetio && (window.phetio.phetioEngine || window.phetio.session)
        || (phet && phet.phetio && (phet.phetio.phetioClient || phet.phetio.dataStream || typeof phet.phetio.tandemGetters === "object"))),
      qp_keys: keys(phet && (phet.queryParameters || (phet.phetcommon && phet.phetcommon.queryParameters))),
      joist_sim: !!(phet && phet.joist && phet.joist.sim),
      a11y_sliders: a11y,
      sliders: document.querySelectorAll("[role=slider], input[type=range]").length,
      buttons: document.querySelectorAll("button, [role=button]").length,
      body_text: (document.body.innerText || "").replace(/\s+/g, " ").slice(0, 90),
    };
  });
}
function hash(buf) { return createHash("sha1").update(buf).digest("hex").slice(0, 12); }

const report = {
  measured_at: new Date().toISOString(),
  tool: "source/library/phet_headless_probe.mjs",
  chromium: exec,
  note_screens: "只有真有多屏的仿真才会因 ?screens=2 改变画面；单屏仿真这一项为 false 是物理事实，不是失败",
  sims: [],
};
const browser = await chromium.launch({ executablePath: exec, headless: true, args: ["--no-sandbox", "--allow-file-access-from-files"] });
try {
  for (const item of manifest.sims) {
    const file = path.join(ROOT, item.file);
    if (!fs.existsSync(file)) { report.sims.push({ sim: item.sim, load_clean: false, why: "文件不在盘上" }); continue; }
    const base = pathToFileURL(file).href;
    const row = { sim: item.sim, version: item.version, bytes: item.bytes, license_line: item.license_line };
    const errs = [];
    const byTag = {};
    for (const [tag, url] of [["plain", base], ["screens2", base + "?screens=2"], ["es", base + "?locale=es"]]) {
      const p = await (await browser.newContext({ viewport: { width: 1100, height: 720 } })).newPage();
      // 报错要按「哪一次加载」归账：?screens=2 在单屏仿真上会抛 invalid screen index，
      // 那是探针自己塞了个不被接受的参数，不是仿真坏了。混在一起统计就把仪器故障记到了被测对象头上。
      byTag[tag] = [];
      p.on("pageerror", (e) => { const m = String(e).slice(0, 140); errs.push(m); byTag[tag].push(m); });
      p.on("requestfailed", (r) => { const m = "REQ " + r.url().slice(-70); errs.push(m); byTag[tag].push(m); });
      try {
        await p.goto(url, { waitUntil: "load", timeout: 90000 });
        await settle(p);
        const info = await read(p);
        const png = await p.screenshot();
        info.png_sha1 = hash(png); info.png_bytes = png.length;
        row[tag] = info;
        if (tag === "plain") {
          // 官方说成品支持键盘操作；这里用「按键盘能不能把某个无障碍数值推动」来实测——
          // 推动得了就是 Agent 可用的控制通道（虽然没有 PhET-iO 那样的显式 API），推不动就照实写推不动。
          // 注意：键盘驱动放在取完 png 之后，保证 plain 的指纹仍是「未干预的初始态」，
          // 否则 screens/locale 两项的画面对照就变成「初始态 vs 被按过的态」，判据不成立。
          const before = JSON.stringify(info.a11y_sliders);
          for (let i = 0; i < 14; i++) await p.keyboard.press("Tab");
          for (const k of ["ArrowRight", "ArrowRight", "ArrowUp", "PageUp", "End"]) await p.keyboard.press(k);
          await settle(p, 1200);
          const after = await read(p);
          const pngAfter = await p.screenshot();
          row.keyboard_drive = {
            a11y_targets: info.a11y_sliders.length,
            a11y_before: info.a11y_sliders, a11y_after: after.a11y_sliders,
            a11y_changed: JSON.stringify(after.a11y_sliders) !== before,
            picture_changed: hash(pngAfter) !== info.png_sha1,
          };
        }
      } catch (e) {
        row[tag] = { error: String(e).slice(0, 140) };
      } finally {
        await p.context().close();
      }
    }
    row.errors_all = errs;
    row.errors_by_load = byTag;
    row.errors_telemetry = errs.filter((e) => TELEMETRY.test(e));
    row.errors_sim = errs.filter((e) => !TELEMETRY.test(e));
    row.errors_plain_load = (byTag.plain || []).filter((e) => !TELEMETRY.test(e));
    row.errors_screens2_load = (byTag.screens2 || []).filter((e) => !TELEMETRY.test(e));
    row.load_clean = errs.length === 0 && !!row.plain && !row.plain.error;
    // 「仿真本体干净」只看基线那一次加载：带 ?screens=2 的那次是探针自找的
    row.sim_body_clean = row.errors_plain_load.length === 0 && !!row.plain && !row.plain.error;
    // 画面对照还要排掉「变成报错页」这种假阳性：画面确实不同，但那是错误提示，不是换屏成功
    row.screens2_is_error_page = !!((row.screens2 && !row.screens2.error) && ((row.screens2.body_text || "").trim() === ""))
      || row.errors_screens2_load.some((e) => /invalid screen index/i.test(e));
    row.screens_picture_differs = !!(row.plain && row.screens2 && row.plain.png_sha1 !== row.screens2.png_sha1);
    row.screens_change_picture = row.screens_picture_differs && !row.screens2_is_error_page;
    row.locale_change_picture = !!(row.plain && row.es && row.plain.png_sha1 !== row.es.png_sha1);
    row.instrumented_for_phetio = (row.plain?.phetio_dom_ids || 0) > 0 || !!row.plain?.phetio_global;
    report.sims.push(row);
    console.log(`${item.sim.padEnd(32)} v${(row.version || "?").padEnd(8)} 仿真本体干净=${row.sim_body_clean ? "Y" : "N"}`
      + ` 遥测桩报错=${row.errors_telemetry.length} 本体报错=${row.errors_sim.length}`
      + ` | phetio命名空间=${row.plain?.phetio_global ? "Y" : "n"} 可调用=${row.plain?.phetio_callable ? "Y" : "n"} id=${row.plain?.phetio_dom_ids ?? "?"}`
      + ` | a11y数值=${(row.plain?.a11y_sliders || []).length} 键盘推动=${row.keyboard_drive?.a11y_changed ? "Y" : "n"}/改画=${row.keyboard_drive?.picture_changed ? "Y" : "n"}`
      + ` | 换屏改画=${row.screens_change_picture ? "Y" : "n"} 换语言改画=${row.locale_change_picture ? "Y" : "n"}`);
    if (row.errors_sim.length) console.log("    本体报错：", row.errors_sim.slice(0, 2).join(" | "));
  }
} finally {
  await browser.close();
}
const n = (f) => report.sims.filter(f).length;
report.summary = {
  sims: report.sims.length,
  load_clean_no_error_at_all: n((r) => r.load_clean),
  screens_param_picture_differs_raw: n((r) => r.screens_picture_differs),
  screens_param_rejected_by_sim: n((r) => r.screens2_is_error_page),
  sim_body_clean: n((r) => r.sim_body_clean),
  telemetry_stub_only_failures: n((r) => !r.load_clean && r.sim_body_clean),
  with_phet_namespace: n((r) => r.plain?.has_phet_ns),
  phetio_namespaced: n((r) => !!r.plain?.phetio_global),
  phetio_callable: n((r) => !!r.plain?.phetio_callable),
  instrumented_for_phetio: n((r) => r.instrumented_for_phetio),
  screens_param_changes_picture: n((r) => r.screens_change_picture),
  locale_param_changes_picture: n((r) => r.locale_change_picture),
  keyboard_moves_a11y_state: n((r) => r.keyboard_drive?.a11y_changed),
  keyboard_changes_picture: n((r) => r.keyboard_drive?.picture_changed),
  has_a11y_values: n((r) => (r.plain?.a11y_sliders || []).length > 0),
  note_keyboard_changes_picture: "这一项只作记录、不作判据：动画类仿真不按键也在变画，没做「不按键」对照组，所以 picture_changed 不能当键盘驱动成功的证据；键盘通道的证据只看 a11y_changed，定点写另见 phet_a11y_channel_probe.mjs / phet_ohms_writeproof.mjs",
};
// 结论必须由上面的实测数字派生，不预先写死：第一轮我就把「13 只都拿不到接口」写进了结论文案，
// 结果实测出 7 只有 phetio 命名空间——写死的结论会变成假账。
report.summary.conclusion =
  `URL 参数只到框架层（?screens=2 / ?locale=es 改变画面 ${report.summary.screens_param_changes_picture}/13、${report.summary.locale_param_changes_picture}/13），`
  + `而可被外部程序调用的 PhET-iO 接口（phetio_callable）实测 ${report.summary.phetio_callable}/13；`
  + `phet.phetio 命名空间存在 ${report.summary.phetio_namespaced}/13 但 data-phetio-id 全为 ${Math.max(...report.sims.map((r) => r.plain?.phetio_dom_ids ?? 0))}——存在不等于可用；`
  + `键盘能推动无障碍数值的 ${report.summary.keyboard_moves_a11y_state}/13，说明「Agent 靠模拟操作驱动」这条替代通道是否成立要看这一项，不能靠断言。`;
report.result = report.summary.sim_body_clean === report.summary.sims ? "PASS" : "PART";
fs.writeFileSync(out, JSON.stringify(report, null, 2), "utf-8");
console.log("\n汇总:", JSON.stringify(report.summary), "\n写入", path.relative(ROOT, out));
