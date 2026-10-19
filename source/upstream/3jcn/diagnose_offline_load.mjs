/** 离线包为什么没有画面：把「控制台 + 失败请求 + 非 2xx 响应」三样都记下来。
 *
 * jcn3_headless_lab.mjs 只收 `pageerror`，而 ES module 的 import 失败在 Chromium 里是
 * **控制台错误 + requestfailed，不抛页面异常** —— 所以「canvas 0」在旧探针里是完全哑的：
 * 既没有异常条数，也说不出缺哪一个文件。这一支专为回答「到底还差什么」而写：
 *   console（全部级别，带 origin:line）、requestfailed（URL + failure text）、
 *   response status>=400、以及页面里 `<canvas>` / `<script type=module>` / `window.THREE` 的实际状态。
 * 同一支脚本喂 site/ 与 offline/ 各跑一遍就是 A/B：真站有画面而离线没有 ⇒ 差的是包内资源；
 * 两边都没画面 ⇒ 是别的原因（显卡/软件 WebGL、或页面本来就不靠 canvas）。
 *
 * 用法：node source/upstream/3jcn/diagnose_offline_load.mjs --url http://127.0.0.1:8123/Phyc140/apparent_weight_exp.html [--offline]
 */
import fs from "node:fs";
import path from "node:path";
import { createRequire } from "node:module";
import { findChromium } from "../../library/ejss_headless_lab.mjs";

const require = createRequire(path.join(process.cwd(), "noop.js"));
const ROOT = process.cwd();
const { chromium } = require("playwright-core");
const argv = process.argv;
const opt = (k, d) => (argv.includes(k) ? argv[argv.indexOf(k) + 1] : d);
const url = opt("--url", null);
if (!url) { console.error("必须给 --url（页面是 ES module，file:// 会被 CORS 挡）"); process.exit(2); }
const out = opt("--json", "source/upstream/3jcn/3jcn-offline-diagnosis.json");
const exec = findChromium();
const WEBGL_NOTE = "headless chromium 若无 WebGL，画面判据在这台机器上先天为 0，要先排除这一条再谈离线包";

const rep = { measured_at: new Date().toISOString(), url, offline: argv.includes("--offline"), tool: "diagnose_offline_load.mjs" };
const browser = await chromium.launch({ executablePath: exec, headless: true, args: ["--no-sandbox", "--enable-unsafe-swiftshader", "--use-gl=swiftshader"] });
const p = await (await browser.newContext({ viewport: { width: 1280, height: 820 } })).newPage();

const console_msgs = [], failed = [], bad_status = [];
p.on("console", (m) => {
  const loc = m.location() || {};
  console_msgs.push({ type: m.type(), text: String(m.text()).slice(0, 300), at: `${loc.url || ""}:${loc.lineNumber ?? ""}`.slice(0, 220) });
});
p.on("pageerror", (e) => console_msgs.push({ type: "pageerror", text: String(e).slice(0, 300), at: "page" }));
p.on("requestfailed", (r) => failed.push({ url: r.url().slice(0, 160), why: String(r.failure()?.errorText).slice(0, 60) }));
p.on("response", (r) => { if (r.status() >= 400) bad_status.push({ url: r.url().slice(0, 160), status: r.status() }); });

const blocked = [];
if (rep.offline) {
  await p.route("**/*", (route) => {
    const host = new URL(route.request().url()).hostname;
    if (host === "127.0.0.1" || host === "localhost") return route.continue();
    blocked.push(route.request().url().slice(0, 120));
    return route.abort();
  });
}

try {
  await p.goto(url, { waitUntil: "load", timeout: 90000 });
  await p.waitForTimeout(7000);
  rep.probe = await p.evaluate(() => {
    const cvs = [...document.querySelectorAll("canvas")];
    return {
      canvas_count: cvs.length,
      canvas_sizes: cvs.map((c) => `${c.width}x${c.height} css=${c.clientWidth}x${c.clientHeight}`),
      module_scripts: [...document.querySelectorAll('script[type=module]')].length,
      range_sliders: document.querySelectorAll('input[type=range]').length,
      body_chars: (document.body.innerText || "").replace(/\s+/g, " ").length,
      body_head: (document.body.innerText || "").replace(/\s+/g, " ").slice(0, 160),
      // WebGL 能力单独测：这一条若是 false，「画面为 0」就与离线包无关，是本机的渲染后端问题
      webgl: (() => { try { const c = document.createElement("canvas");
        return !!(c.getContext("webgl2") || c.getContext("webgl")); } catch (e) { return "throw:" + String(e).slice(0, 60); } })(),
      three_global: typeof window.THREE,
    };
  });
} catch (e) {
  rep.load_error = String(e).slice(0, 220);
} finally {
  await p.context().close();
  await browser.close();
}

// 归类：module 加载类错误单独计数，别和 jQuery 噪音混在一起
const isModuleErr = (m) => /Failed to (fetch|resolve|load)|Cannot find module|Unexpected token|not a valid ECMAScript|mimeType/i.test(m.text);
rep.console_total = console_msgs.length;
rep.module_errors = console_msgs.filter(isModuleErr);
rep.other_console = console_msgs.filter((m) => !isModuleErr(m)).slice(0, 12);
rep.request_failed = failed.slice(0, 15);
rep.response_errors = bad_status.slice(0, 15);
rep.blocked_external = blocked.length;
rep.blocked_sample = blocked.slice(0, 5);
rep.verdict = !(rep.probe?.canvas_count > 0)
  ? (rep.module_errors.length ? "NO_CANVAS_WITH_MODULE_ERRORS" : rep.probe?.webgl === false ? "NO_CANVAS_WEBGL_UNAVAILABLE" : "NO_CANVAS_NO_MODULE_ERROR_SEE_CONSOLE")
  : "CANVAS_PRESENT";

fs.writeFileSync(path.join(ROOT, out), JSON.stringify(rep, null, 2), "utf-8");
console.log(JSON.stringify({ url, offline: rep.offline, verdict: rep.verdict, probe: rep.probe,
  module_errors: rep.module_errors.length, request_failed: failed.length, response_errors: bad_status.length,
  blocked_external: blocked.length, webgl_note: WEBGL_NOTE }, null, 2));
for (const m of rep.module_errors.slice(0, 8)) console.log("  MODULE ERR:", m.text, "@", m.at);
for (const f of rep.request_failed.slice(0, 8)) console.log("  FAILED:", f.url, "|", f.why);
for (const b of rep.response_errors.slice(0, 8)) console.log("  HTTP", b.status, b.url);
console.log("写入", out);
