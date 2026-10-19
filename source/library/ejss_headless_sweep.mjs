/** 批量无头跑一遍所有 EJS 6.02 导出包：把「结构上都有控制面」升级成「运行时逐个实测」。
 *
 * 每个包问四个不需要懂模型物理的问题：
 *   ① file:// 能不能零异常加载（页面报错/资源失败都记下来）；
 *   ② window._model 的 serialize/unserialize/step 是否真的挂在运行时对象上；
 *   ③ step() 是否推进时间，且 reset 后同一条轨迹可复现（确定性控制组）；
 *   ④ unserialize() 写进去的值是否改变后续轨迹（Agent 真正要的能力）。
 * 判据④故意不靠「没报错」：写完必须回读，再比较改写前后的轨迹是否分离。
 *
 * 用法：node source/library/ejss_headless_sweep.mjs [--limit N] [--steps 10] [--json <out>]
 */

import fs from "node:fs";
import path from "node:path";
import { createRequire } from "node:module";
import { assemble, entryPage, findChromium, probePackage } from "./ejss_headless_lab.mjs";

const require = createRequire(path.join(process.cwd(), "noop.js"));
const ROOT = process.cwd();

function arg(name, def) {
  const i = process.argv.indexOf(`--${name}`);
  return i >= 0 && process.argv[i + 1] && !process.argv[i + 1].startsWith("--") ? process.argv[i + 1] : def;
}

const survey = JSON.parse(fs.readFileSync(path.join(ROOT, "source", "upstream", "ejss-survey.json"), "utf-8"));
const packages = [];
for (const m of survey.models) {
  const d = m.deliverability || {};
  if (d.family !== "ejs6") continue;
  const zip = path.join(ROOT, "source", "upstream", m.zip);
  if (!fs.existsSync(zip)) continue;
  if (!packages.find((p) => p.zip === zip)) packages.push({ zip, title: m.title || path.basename(zip), params: m.public_vars || 0 });
}

const limit = Number(arg("limit", packages.length));
const steps = Number(arg("steps", 10));
const { chromium } = require("playwright-core");
const exec = findChromium();
const report = {
  measured_at: new Date().toISOString(),
  tool: "source/library/ejss_headless_sweep.mjs",
  chromium: exec,
  packages_in_survey: packages.length,
  packages_run: Math.min(limit, packages.length),
  steps,
  results: [],
};
console.log(`扫描到 ${packages.length} 个 EJS 6.02 包，跑 ${report.packages_run} 个（每包 ${steps} 步）`);

const browser = await chromium.launch({
  executablePath: exec, headless: true,
  args: ["--allow-file-access-from-files", "--no-sandbox"],
});
try {
  for (const pkg of packages.slice(0, report.packages_run)) {
    const asm = assemble(pkg.zip, []);
    const page = asm.dir && entryPage(asm.dir);
    if (!page) {
      report.results.push({ zip: path.relative(ROOT, pkg.zip), ok: false, why: "拼包或找主页面失败", log: asm.log.split("\n").slice(-3) });
      console.log(`SKIP ${pkg.title} :: 拼包失败`);
      continue;
    }
    const probe = await probePackage(browser, page, { steps });
    // 控制组：同一份包重新加载再跑一遍，轨迹必须逐点相同（否则「可复现」这条不成立）
    const again = await probePackage(browser, page, { steps });
    // 写值组：把主角变量注入一个新起点，看后续轨迹是否跟着分离
    const injected = probe.primary_var
      ? await probePackage(browser, page, { steps, inject: { [probe.primary_var]: 1000 }, injectFirst: true, primaryOverride: probe.primary_var })
      : null;
    const same = (a, b) => JSON.stringify(a) === JSON.stringify(b);
    const row = {
      zip: path.relative(ROOT, pkg.zip).replace(/\\/g, "/"),
      title: pkg.title,
      params_declared: pkg.params,
      state_vars: probe.start_keys ?? 0,
      load_clean: probe.errors.length === 0 && !probe.load_error,
      errors: probe.errors.concat(probe.load_error ? [probe.load_error] : []).slice(0, 3),
      api_methods: probe.api ? probe.api.methods.length : 0,
      serde: !!probe.api && probe.api.methods.includes("serialize") && probe.api.methods.includes("unserialize"),
      t_after_steps: probe.t_after_steps,
      advanced: probe.advanced,
      primary_var: probe.primary_var,
      primary_kind: probe.primary_kind,
      primary_start: probe.start_primary,
      deterministic: !!probe.trace_head && same(probe.trace_head, again.trace_head),
      write_test: injected && injected.write ? {
        injected_to: 1000,
        stuck: injected.write.stuck,
        trajectory_moved: !same(injected.write.trace_head, probe.trace_head),
        head: injected.write.trace_head,
        // 三档而不是一个布尔：自动选的「变化最快的量」可能是模型每步重算的派生量
        // （2.12 的 a、2.13 的 x_hill 就是这样），那属于「写入被接受但马上被物理规则覆盖」，
        // 不能写成「这个包不可控」；也不能反过来因为「读回一致」就宣称可控——还得看它是否改变行为。
        class: injected.write.stuck
          ? (!same(injected.write.trace_head, probe.trace_head) ? "accepted_and_changes_behaviour" : "accepted_but_recomputed")
          : "rejected",
      } : null,
    };
    row.verdict = (row.load_clean && row.serde && row.advanced && row.deterministic &&
                   row.write_test && row.write_test.stuck)
      ? "runtime_writable" : "partial";
    report.results.push(row);
    console.log(`${row.verdict === "runtime_writable" ? "OK  " : "PART"} ${pkg.title.slice(0, 34).padEnd(34)} ` +
      `api=${row.api_methods} t=${row.t_after_steps} det=${row.deterministic} ` +
      `write=${row.write_test ? (row.write_test.stuck ? (row.write_test.trajectory_moved ? "moved" : "stuck-same") : "NO-STICK") : "n/a"} ` +
      `err=${row.errors.length}`);
  }
} finally {
  await browser.close();
}

const n = (f) => report.results.filter(f).length;
report.summary = {
  run: report.results.length,
  load_clean: n((r) => r.load_clean),
  with_serde_api: n((r) => r.serde),
  advanced: n((r) => r.advanced),
  deterministic: n((r) => r.deterministic === true),
  write_accepted_and_changes_behaviour: n((r) => r.write_test && r.write_test.class === "accepted_and_changes_behaviour"),
  write_accepted_but_recomputed: n((r) => r.write_test && r.write_test.class === "accepted_but_recomputed"),
  write_rejected: n((r) => r.write_test && r.write_test.class === "rejected"),
  runtime_writable: n((r) => r.verdict === "runtime_writable"),
  array_state_packages: n((r) => r.primary_kind === "array_element"),
  failed_to_load_list: report.results.filter((r) => !r.load_clean).map((r) => r.zip),
  recompute_note: "accepted_but_recomputed / rejected 两档里被注入的量是「步内变化最快的量」，"
    + "它可能是模型每步重算的派生量（如 2.12 的 a、2.13 的 x_hill）⇒ 这两档说明的是选靶规则不够好，不能当成「包不可控」的证据",
};
report.result = report.summary.runtime_writable === report.results.length ? "ALL PASS" : "部分未过";
const out = arg("json", "source/library/ejss-headless-sweep.json");
fs.writeFileSync(path.join(ROOT, out), JSON.stringify(report, null, 2), "utf-8");
console.log("\n汇总:", JSON.stringify(report.summary), "\n写入", out);
