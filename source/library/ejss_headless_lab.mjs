/** EJSS 导出包的无头验收台：拼包 → 真浏览器里跑引擎 → 读数 → 与解析式对账。
 *
 * 为什么要有它：运行时控制面（window._model 的 serialize/unserialize/step）此前只能在对话里的
 * 浏览器手工验，等于「能演示」而不是「能验证」。这个脚本把同一条路挪到命令行，
 * 于是浏览器态引擎也能进回归测试，改一次参数就能重跑一次对账。
 *
 * 用法（本机已装的拼包脚本产出的目录，或直接给 zip 让它自己拼）：
 *   node source/library/ejss_headless_lab.mjs \
 *     --zip source/upstream/resources/docs/PP/Ch02/js_ejs_model_Illustration2_6.zip \
 *     --param y=45 --param a=-9.8 \
 *     --kinematic y,v,a --steps 19 --assert-baked y=45 --assert-baked a=-9.8 \
 *     --json source/library/ejss-headless-lab-evidence.json
 *
 * 判据故意做成两条独立的：
 *   ① 烘焙值必须出现在运行时状态里（证明「改参数」真的进了引擎，而不是只改了文件）；
 *   ② 每一步的位置/速度必须落在匀加速解析解上（证明跑的是这个模型的物理，不是空转）。
 * 只看「页面没报错」或「step 返回了」都不算通过。
 */

import { spawnSync } from "node:child_process";
import fs from "node:fs";
import os from "node:os";
import path from "node:path";
import { createRequire } from "node:module";
import { pathToFileURL, fileURLToPath } from "node:url";

const require = createRequire(path.join(process.cwd(), "noop.js"));
const ROOT = process.cwd();

function arg(name, def = null) {
  const i = process.argv.indexOf(`--${name}`);
  return i >= 0 && process.argv[i + 1] && !process.argv[i + 1].startsWith("--") ? process.argv[i + 1] : def;
}
function argAll(name) {
  const out = [];
  process.argv.forEach((a, i) => { if (a === `--${name}` && process.argv[i + 1]) out.push(process.argv[i + 1]); });
  return out;
}
const flags = new Set(process.argv);

function findChromium() {
  if (process.env.EJSS_CHROMIUM && fs.existsSync(process.env.EJSS_CHROMIUM)) return process.env.EJSS_CHROMIUM;
  const cache = process.env.PLAYWRIGHT_BROWSERS_PATH
    || path.join(os.homedir(), "AppData", "Local", "ms-playwright");
  let real = cache;
  try { real = fs.realpathSync(cache); } catch { /* 不是符号链接就用原路径 */ }
  const cands = [];
  for (const dir of fs.existsSync(real) ? fs.readdirSync(real) : []) {
    if (!/^chromium(-headless-shell)?-\d+$/.test(dir)) continue;
    for (const sub of ["chrome-win64/chrome.exe", "chrome-win/chrome.exe",
                       "chrome-headless-shell-win64/chrome-headless-shell.exe"]) {
      const p = path.join(real, dir, sub);
      if (fs.existsSync(p)) cands.push([Number(dir.split("-").pop()), p]);
    }
  }
  if (!cands.length) return null;
  cands.sort((a, b) => b[0] - a[0]);
  return cands[0][1];
}

/** 交给上游拼包脚本产出离线目录；只解析它打印的「输出 → <路径>」。 */
function assemble(zip, params) {
  const argv = [path.join(ROOT, "source", "upstream", "assemble_ejss_offline.py"), zip];
  for (const p of params) argv.push("--param", p);
  const r = spawnSync("python", argv, { cwd: ROOT, encoding: "utf-8", env: { ...process.env, PYTHONIOENCODING: "utf-8" } });
  const out = (r.stdout || "") + (r.stderr || "");
  const m = out.match(/输出 →\s*(\S+)/);
  return { code: r.status, dir: m ? m[1] : null, log: out };
}

function entryPage(dir) {
  const stack = [dir];
  while (stack.length) {
    const d = stack.pop();
    for (const e of fs.readdirSync(d, { withFileTypes: true })) {
      const p = path.join(d, e.name);
      if (e.isDirectory()) { if (e.name !== "_ejs_library" && e.name !== "assets") stack.push(p); continue; }
      if (/_[Ss]imulation\.xhtml$/.test(e.name) || e.name === "_simulation.xhtml") return p;
    }
  }
  return null;
}

const report = {
  measured_at: new Date().toISOString(),
  tool: "source/library/ejss_headless_lab.mjs",
  args: { zip: arg("zip"), params: argAll("param"), kinematic: arg("kinematic"), steps: Number(arg("steps", 20)) },
  checks: [],
  failures: [],
  notes: [],
};

function check(name, ok, detail) {
  report.checks.push({ name, ok: !!ok, detail });
  if (!ok) report.failures.push(`${name}: ${JSON.stringify(detail)}`);
  console.log(`${ok ? "PASS" : "FAIL"} ${name} :: ${JSON.stringify(detail)}`);
}

/** 在同一个浏览器里把一个包跑起来，返回运行时控制面与轨迹。
 *  四个通用判据不需要知道模型物理：能否无异常加载、控制面是否真在、
 *  step 是否确定性推进、unserialize 写入是否真的改变后续状态。 */
export async function probePackage(browser, pagePath, { steps = 10, inject = null, injectFirst = false, primaryOverride = null } = {}) {
  const ctx = await browser.newContext();
  const p = await ctx.newPage();
  const errors = [];
  p.on("pageerror", (e) => errors.push(String(e).slice(0, 300)));
  p.on("requestfailed", (r) => errors.push(`requestfailed ${r.url().slice(-90)}`));
  const out = { page: path.basename(pagePath), errors: [], api: null, advanced: null, deterministic: null, write: null };
  try {
    const runOnce = async () => p.evaluate(({ n }) => {
      const m = window._model;
      if (!m) return null;
      const s = JSON.parse(m.serialize());
      const start = { ...s.model };
      const trace = [];
      for (let i = 0; i < n; i++) { m.step(); trace.push(JSON.parse(m.serialize()).model); }
      return { start, trace, envelope_keys: Object.keys(s) };
    }, { n: steps });

    await p.goto(pathToFileURL(pagePath).href, { waitUntil: "load", timeout: 60000 });
    out.api = await p.evaluate(() => {
      const m = window._model;
      if (!m) return { present: false, methods: [] };
      return { present: true, methods: ["initialize", "step", "update", "play", "pause", "reset", "serialize", "unserialize"].filter((k) => typeof m[k] === "function") };
    });
    if (!out.api.present) { out.errors = errors.slice(0, 5); return out; }

    const writeTest = (target) => p.evaluate(({ inject, n }) => {
      const m = window._model;
      const s = JSON.parse(m.serialize());
      const at = (obj, key) => { const mm = key.match(/^(\w+)\[(\d+)\]$/); return mm ? obj[mm[1]][Number(mm[2])] : obj[key]; };
      const put = (obj, key, val) => { const mm = key.match(/^(\w+)\[(\d+)\]$/); if (mm) obj[mm[1]][Number(mm[2])] = val; else obj[key] = val; };
      Object.entries(inject).forEach(([k, v]) => put(s.model, k, v));
      s.model.t = 0;
      m.unserialize(JSON.stringify(s));
      const read = JSON.parse(m.serialize()).model;
      const readback = Object.fromEntries(Object.keys(inject).map((k) => [k, at(read, k)]));
      const trace = [];
      for (let i = 0; i < n; i++) {
        m.step();
        const q = JSON.parse(m.serialize()).model;
        trace.push(Object.fromEntries(Object.keys(inject).map((k) => [k, at(q, k)])));
      }
      const key = Object.keys(inject)[0];
      return { readback, trace, stuck: Number(readback[key]) === Number(inject[key]), trace_head: trace.slice(0, 4).map((r) => r[key]) };
    }, { inject: target, n: steps });

    if (injectFirst && inject && primaryOverride) {
      // 干净页面上「先写后跑」：这才是 Agent 的实际用法，也排除「中途注入把积分器历史搞乱」这种假阳性
      out.mode = "inject_on_fresh_page";
      out.primary_var = primaryOverride;
      out.write = await writeTest(inject);
      return out;
    }

    const first = await runOnce();

    // 轨迹主角 = 步内变化量最大的数值量。数组状态（两车/多体模型的 x[]、v[]）也必须算进来：
    // 上一版只认标量，把 Problem 2.8 判成「状态没变、不可复现」，那是探针的盲区，不是模型的缺陷。
    const lastState = first.trace[first.trace.length - 1];
    const at = (obj, key) => {
      const mm = key.match(/^(\w+)\[(\d+)\]$/);
      return mm ? obj[mm[1]][Number(mm[2])] : obj[key];
    };
    const candidates = [];
    for (const k of Object.keys(first.start)) {
      if (/^(t|dt|animation|stepsPerDisplay|frameCount|page|_)/.test(k)) continue;
      const v0 = first.start[k], vN = lastState[k];
      if (typeof v0 === "number" && Number.isFinite(vN)) candidates.push([k, Math.abs(vN - v0)]);
      else if (Array.isArray(v0) && v0.every((x) => typeof x === "number") && Array.isArray(vN)) {
        v0.forEach((x, i) => { if (Number.isFinite(vN[i])) candidates.push([`${k}[${i}]`, Math.abs(vN[i] - x)]); });
      }
    }
    candidates.sort((a, b) => b[1] - a[1]);
    const primary = candidates.length ? candidates[0][0] : null;
    out.mode = "baseline";
    out.primary_var = primary;
    out.primary_delta = candidates.length ? candidates[0][1] : null;
    out.primary_kind = primary && primary.includes("[") ? "array_element" : "scalar";
    out.start_primary = primary ? at(first.start, primary) : null;
    out.t_after_steps = lastState?.t ?? null;
    out.advanced = out.t_after_steps > 0;
    out.trace_head = primary ? first.trace.slice(0, 4).map((s) => at(s, primary)) : null;
    out.start_keys = Object.keys(first.start).length;
    if (inject && primary) out.write = await writeTest(inject);
  } catch (e) {
    out.load_error = String(e).slice(0, 200);
  } finally {
    out.errors = errors.slice(0, 5);
    await ctx.close();
  }
  return out;
}

export { findChromium, assemble, entryPage };

async function main() {
  const zip = arg("zip");
  if (!zip) throw new Error("必须给 --zip");
  const params = argAll("param");
  const kin = (arg("kinematic") || "").split(",").filter(Boolean);
  if (!fs.existsSync(zip)) throw new Error(`zip 不在盘上: ${zip}`);

  const asm = assemble(zip, params);
  check("拼包脚本退出码为 0", asm.code === 0, { code: asm.code, dir: asm.dir });
  if (!asm.dir) throw new Error("拼包脚本没有报出输出目录");
  report.assemble_log_tail = asm.log.split("\n").filter(Boolean).slice(-6);

  const page = entryPage(asm.dir);
  check("找到仿真主页面", !!page, { entry: page && path.basename(page) });
  if (!page) throw new Error("没有仿真主页面");

  const chromiumPath = findChromium();
  check("本机有可用的 chromium（Playwright 缓存）", !!chromiumPath, { path: chromiumPath });
  if (!chromiumPath) throw new Error("找不到 chromium 可执行文件；设 EJSS_CHROMIUM 指定");

  const { chromium } = require("playwright-core");
  const browser = await chromium.launch({
    executablePath: chromiumPath,
    headless: true,
    args: ["--allow-file-access-from-files", "--disable-file-system-access-proxy", "--no-sandbox"],
  });
  try {
    const ctx = await browser.newContext();
    const p = await ctx.newPage();
    const errors = [];
    p.on("pageerror", (e) => errors.push(String(e).slice(0, 300)));
    p.on("requestfailed", (r) => errors.push(`requestfailed ${r.url().slice(-90)} ${r.failure()?.errorText || ""}`));
    const t0 = Date.now();
    await p.goto(pathToFileURL(page).href, { waitUntil: "load", timeout: 60000 });
    const api = await p.evaluate(() => {
      const m = window._model;
      if (!m) return { present: false };
      return {
        present: true,
        methods: ["initialize", "step", "update", "play", "pause", "reset", "serialize", "unserialize"]
          .filter((k) => typeof m[k] === "function"),
      };
    });
    check("页面里有 window._model 全套控制面", api.present && api.methods.length >= 6, api);

    const steps = Number(arg("steps", 20));
    const run = await p.evaluate(({ n }) => {
      const m = window._model;
      const s = JSON.parse(m.serialize());
      const start = { ...s.model };
      const trace = [];
      for (let i = 0; i < n; i++) {
        m.step();
        const q = JSON.parse(m.serialize()).model;
        trace.push({ t: q.t, snap: q });
      }
      return { start, trace, serialize_keys: Object.keys(s) };
    }, { n: steps });

    for (const spec of argAll("assert-baked")) {
      const [k, v] = spec.split("=");
      const got = run.start[k];
      check(`烘焙值确实进了运行时状态 ${k}=${v}`, String(got) === String(v) || Number(got) === Number(v),
        { expected: v, engine_value: got });
    }

    if (kin.length === 3) {
      const [pos, vel, acc] = kin;
      const y0 = run.start[pos], v0 = run.start[vel], a = run.start[acc];
      const tolPct = Number(arg("tol", 1e-6));
      const rows = run.trace.map(({ t, snap }) => {
        const yA = y0 + v0 * t + 0.5 * a * t * t;
        const vA = v0 + a * t;
        return {
          t: Number(t.toFixed(6)),
          y_engine: snap[pos], y_analytic: Number(yA.toFixed(10)),
          v_engine: snap[vel], v_analytic: Number(vA.toFixed(10)),
          y_rel_err_pct: yA === 0 ? 0 : Math.abs((snap[pos] - yA) / yA) * 100,
          v_rel_err_pct: vA === 0 ? 0 : Math.abs((snap[vel] - vA) / vA) * 100,
        };
      });
      report.kinematic_trace = rows;
      const worst = rows.reduce((m, r) => Math.max(m, r.y_rel_err_pct, r.v_rel_err_pct), 0);
      check(`每一步都落在匀加速解析解上（容差 ${tolPct}%）`, worst <= tolPct,
        { steps: rows.length, worst_rel_err_pct: worst, last: rows[rows.length - 1] });
      check("引擎确实推进了时间", Number(run.trace[run.trace.length - 1].t) > 0,
        { t_after_steps: run.trace[run.trace.length - 1].t });
    }

    // 写值回路：用完整信封写回一个新起点，跑一步，看是否跟着走（这是 Agent 真正要的能力）
    const injected = arg("inject");
    if (injected) {
      const pairs = Object.fromEntries(injected.split(",").map((kv) => { const [k, v] = kv.split("="); return [k, Number(v)]; }));
      const res = await p.evaluate(({ pairs }) => {
        const m = window._model;
        const s = JSON.parse(m.serialize());
        Object.assign(s.model, pairs, { t: 0 });
        m.unserialize(JSON.stringify(s));
        const imm = JSON.parse(m.serialize()).model;
        const readback = Object.fromEntries(Object.keys(pairs).map((k) => [k, imm[k]]));
        m.step();
        const after = JSON.parse(m.serialize()).model;
        return { readback, after_t: after.t, after };
      }, { pairs });
      const mismatch = Object.entries(pairs).filter(([k, v]) => Number(res.readback[k]) !== v);
      check(`unserialize 写值后立即回读一致 ${injected}`, mismatch.length === 0,
        { expected: pairs, readback: res.readback, mismatch });
      if (kin.length === 3) {
        const [pos, vel, acc] = kin;
        const y0 = pairs[pos] ?? res.readback[pos], v0 = pairs[vel] ?? res.readback[vel];
        const a = res.after[acc];
        const t = res.after_t;
        const yA = y0 + v0 * t + 0.5 * a * t * t;
        check("写值后的第一步仍与解析解一致", Math.abs((res.after[pos] - yA) / (yA || 1)) * 100 <= Number(arg("tol", 1e-6)),
          { injected: pairs, t, y_engine: res.after[pos], y_analytic: Number(yA.toFixed(10)) });
      }
    }

    check("页面加载与步进期间没有 JS 异常/资源失败", errors.length === 0, { errors: errors.slice(0, 5) });
    report.elapsed_ms = Date.now() - t0;
  } finally {
    await browser.close();
  }

  report.result = report.failures.length ? "FAIL" : "PASS";
  report.pass_count = report.checks.filter((c) => c.ok).length;
  report.check_count = report.checks.length;
  const out = arg("json");
  if (out) fs.writeFileSync(out, JSON.stringify(report, null, 2), "utf-8");
  console.log(`\n${report.result}: ${report.pass_count}/${report.check_count} 项通过` +
    (out ? `，证据写入 ${out}` : ""));
  process.exitCode = report.failures.length ? 1 : 0;
}

// 只有直接跑这个文件时才执行 CLI；被 sweep 脚本 import 时只暴露函数。
if (process.argv[1] && path.resolve(process.argv[1]) === path.resolve(fileURLToPath(import.meta.url))) {
  main().catch((e) => { console.error("ERROR:", e.message); process.exitCode = 2; });
}
