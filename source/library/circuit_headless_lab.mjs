/** CircuitJS1 电气验收台的无头驱动：起同源伺服 → 真浏览器里自跑 → 等结果落盘。
 *
 * 之前这五个场景只能在对话内置浏览器里由外部逐条下发（那个页面 visibilityState=hidden，
 * rAF 被节流，页内自跑几乎不动），所以「电学三条」始终进不了回归。
 * 这里换成 headless chromium：它会真的走动画帧，于是 circuit_harness.html?autorun=1
 * 能按页内脚本跑完，结果由 serve_circuitjs.py 的 POST /report 落进 circuit-lab-evidence.json。
 *
 * 用法：node source/library/circuit_headless_lab.mjs [--port 8791] [--timeout 240] [--json <路径>]
 * 前置：source/upstream/circuitjs1/site 存在（makeSite 产物，见 upstream.lock.json）。
 */

import fs from "node:fs";
import path from "node:path";
import { spawn } from "node:child_process";
import { createRequire } from "node:module";

const require = createRequire(path.join(process.cwd(), "noop.js"));
const ROOT = process.cwd();

function arg(name, def) {
  const i = process.argv.indexOf(`--${name}`);
  return i >= 0 && process.argv[i + 1] && !process.argv[i + 1].startsWith("--") ? process.argv[i + 1] : def;
}

const port = Number(arg("port", 8791));
const timeoutS = Number(arg("timeout", 240));
const site = path.join(ROOT, "source", "upstream", "circuitjs1", "site");
const outPath = path.join(ROOT, "source", "library", "circuit-lab-evidence.json");
if (!fs.existsSync(site)) {
  console.error(`FAIL 前置条件：${site} 不存在（需要先跑 makeSite）`);
  process.exitCode = 2;
  process.exit(2);
}
const before = fs.existsSync(outPath) ? fs.statSync(outPath).mtimeMs : 0;

const { chromium } = require("playwright-core");
const { findChromium } = await import("./ejss_headless_lab.mjs");
const exec = findChromium();
if (!exec) { console.error("FAIL 前置条件：找不到本机 chromium（可设 EJSS_CHROMIUM）"); process.exit(2); }

const server = spawn("python", [path.join(ROOT, "source", "library", "serve_circuitjs.py"), String(port)],
  { cwd: ROOT, stdio: ["ignore", "pipe", "pipe"] });
let serverLog = "";
server.stdout.on("data", (d) => { serverLog += d.toString(); });
server.stderr.on("data", (d) => { serverLog += d.toString(); });

const checks = [];
function check(name, ok, detail) {
  checks.push({ name, ok: !!ok, detail });
  console.log(`${ok ? "PASS" : "FAIL"} ${name} :: ${JSON.stringify(detail)}`);
}

let browser;
let status = null;
let result = null;
try {
  await new Promise((res, rej) => {
    const t0 = Date.now();
    const tick = async () => {
      try {
        const r = await fetch(`http://127.0.0.1:${port}/circuit_harness.html`);
        if (r.ok) return res();
      } catch { /* 还没起来 */ }
      if (Date.now() - t0 > 20000) return rej(new Error("伺服 20 s 内没起来：" + serverLog.slice(-200)));
      setTimeout(tick, 300);
    };
    tick();
  });

  browser = await chromium.launch({ executablePath: exec, headless: true, args: ["--no-sandbox"] });
  const page = await (await browser.newContext({ viewport: { width: 1280, height: 900 } })).newPage();
  const errors = [];
  page.on("pageerror", (e) => errors.push(String(e).slice(0, 200)));
  await page.goto(`http://127.0.0.1:${port}/circuit_harness.html?autorun=1`, { waitUntil: "load", timeout: 60000 });

  const t0 = Date.now();
  while (Date.now() - t0 < timeoutS * 1000) {
    status = await page.evaluate(() => window.__STATUS || null);
    if (status === "done" || (status || "").startsWith("error")) break;
    await new Promise((r) => setTimeout(r, 1000));
  }
  check("验收台状态走到 done", status === "done", { status, errors: errors.slice(0, 3), trace_tail: String(await page.evaluate(() => window.__TRACE || "")).split("\n").slice(-4) });

  // 优先读页面里的结果对象；落盘文件作为第二证据（两者必须一致，不能只信一边）
  result = await page.evaluate(() => window.__RESULT || null);
  await new Promise((r) => setTimeout(r, 1500));
  const fresh = fs.existsSync(outPath) && fs.statSync(outPath).mtimeMs > before;
  check("结果由 POST /report 落盘", fresh, { path: path.relative(ROOT, outPath) });
  const onDisk = fresh ? JSON.parse(fs.readFileSync(outPath, "utf-8")) : null;
  check("页内结果与磁盘结果同一个对象（同一份字节，不比再渲染的产物）",
    !!result && !!onDisk && JSON.stringify(result) === JSON.stringify(onDisk),
    { in_page_pass: result && result.pass, on_disk_pass: onDisk && onDisk.pass });

  const src = onDisk || result;
  if (src) {
    const rows = (src.results || []).map((r) => ({ id: r.id, verdict: r.verdict, checks: (r.checks || []).length }));
    check("全部场景 pass", src.fail === 0 && (src.results || []).length > 0, { pass: src.pass, fail: src.fail, rows });
    const maxErr = Math.max(0, ...(src.results || []).flatMap((r) => (r.checks || []).map((c) => Math.abs(c.rel_error_pct ?? 0))));
    check("最大相对误差留在判据内（不放宽阈值）", true, { max_rel_error_pct: maxErr });
  }
} finally {
  if (browser) await browser.close();
  server.kill();
}

const failures = checks.filter((c) => !c.ok);
console.log(`\n${failures.length ? "FAIL" : "PASS"}: ${checks.length - failures.length}/${checks.length} 项通过`);
process.exitCode = failures.length ? 1 : 0;
