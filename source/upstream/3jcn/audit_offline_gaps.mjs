/** 3JCN 离线缺口审计与补齐：以**浏览器真实发出的请求**为清单，而不是靠正则猜引用。
 *
 * 为什么要换办法：`mirror_3jcn_site.py` 用正则跟 src/href 与 import，但演示页会把资源路径**拼在 JS 里**
 * （GLTF 模型、贴图常是 `dir + name + '.glb'` 这种运行时字符串），正则永远漏。
 * 漏的结果不是「文件少一个」而是「本地跑起来静默半坏」：上一轮本地镜像出 3 条
 * `Cannot read properties of undefined (reading 'position')` 而真站 0 条，就是这个形状。
 *
 * 做法：在真站上打开给定页面，收集它发出的**全部同源请求**，逐个映射到 site/ 下的路径，
 * 盘上没有的就现场抓下来（只抓同源，跨域 jQuery/bootstrap 仍保持原样并记录），
 * 最后打印补齐清单与「补齐后仍缺」的剩余项——离线交付能不能成立，要看这张表，不看引用数。
 *
 * 用法：node source/upstream/3jcn/audit_offline_gaps.mjs [--page <相对路径>] [--dry]
 */
import fs from "node:fs";
import path from "node:path";
import { createRequire } from "node:module";
import { findChromium } from "../../library/ejss_headless_lab.mjs";

const require = createRequire(path.join(process.cwd(), "noop.js"));
const ROOT = process.cwd();
const { chromium } = require("playwright-core");
const argv = process.argv;
const SITE = path.join(ROOT, "source/upstream/3jcn/site");
const BASE = "https://www.new3jcn.com/";
const rel = argv.includes("--page") ? argv[argv.indexOf("--page") + 1] : "Phyc140/flat_mirror_prob.html";
const dry = argv.includes("--dry");

const missing = [], present = [], crossOrigin = [], failed = [];
const browser = await chromium.launch({ executablePath: findChromium(), headless: true, args: ["--no-sandbox", "--use-gl=angle", "--use-angle=swiftshader", "--enable-unsafe-swiftshader"] });
const p = await (await browser.newContext({ viewport: { width: 1280, height: 820 } })).newPage();
const seenUrls = new Set();
p.on("request", (r) => {
  const u = r.url();
  if (seenUrls.has(u)) return;
  seenUrls.add(u);
  if (!u.startsWith(BASE)) { if (!u.startsWith("data:")) crossOrigin.push(u); return; }
  const rel2 = decodeURIComponent(u.slice(BASE.length)).split("?")[0].split("#")[0];
  if (!rel2) return;
  const dst = path.join(SITE, ...rel2.split("/").filter((x) => x && x !== "." && x !== ".."));
  if (fs.existsSync(dst) && fs.statSync(dst).size > 0) present.push(rel2);
  else missing.push({ rel: rel2, url: u, dst });
});
const pageErrors = [];
p.on("pageerror", (e) => pageErrors.push(String(e).slice(0, 140)));

try {
  await p.goto(BASE + rel, { waitUntil: "networkidle", timeout: 90000 });
  await p.waitForTimeout(4000);
} catch (e) {
  console.log("打开真站页面失败：", String(e).slice(0, 140));
} finally {
  await p.context().close();
  await browser.close();
}
console.log(`真站 ${rel} 发出同源请求 ${present.length + missing.length} 个：盘上已有 ${present.length}，缺 ${missing.length}；跨域 ${crossOrigin.length}`);

let fetched = 0;
for (const m of missing) {
  if (dry) { console.log("  [dry] 会补", m.rel); continue; }
  try {
    const res = await fetch(m.url, { headers: { "User-Agent": "eduforge-resource-audit/1.0" } });
    if (!res.ok) { failed.push({ ...m, status: res.status }); continue; }
    const buf = Buffer.from(await res.arrayBuffer());
    fs.mkdirSync(path.dirname(m.dst), { recursive: true });
    fs.writeFileSync(m.dst, buf);
    fetched += 1;
    console.log(`  + ${m.rel} (${buf.length} B)`);
  } catch (e) {
    failed.push({ ...m, error: String(e).slice(0, 100) });
  }
}
const report = { audited_at: new Date().toISOString(), page: rel, tool: "source/upstream/3jcn/audit_offline_gaps.mjs",
  same_origin_requests: present.length + missing.length, already_on_disk: present.length,
  missing_before: missing.map((m) => m.rel), fetched_now: fetched,
  still_missing: failed.map((f) => ({ rel: f.rel, status: f.status || null, error: f.error || null })),
  cross_origin_not_mirrored: crossOrigin, page_errors_on_live: pageErrors };
fs.writeFileSync(path.join(ROOT, "source/upstream/3jcn/3jcn-offline-gaps.json"), JSON.stringify(report, null, 2), "utf-8");
console.log(`补齐 ${fetched} 个，真站自身也没给回来的 ${failed.length} 个；证据 source/upstream/3jcn/3jcn-offline-gaps.json`);
