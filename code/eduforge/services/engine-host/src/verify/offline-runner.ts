import { createServer, type Server } from "node:http";
import { createHash } from "node:crypto";
import { existsSync, readFileSync } from "node:fs";
import { readFile } from "node:fs/promises";
import { extname, join, resolve, sep } from "node:path";

import { chromium, type Browser, type Page } from "playwright";

import { assertWithinSandbox } from "../security/path-sandbox.js";

/**
 * 发布前的浏览器实测（Gate C §C.5）。
 *
 * 存在的理由：`index_present` 只证明入口文件在盘上。离线包真正出事的地方是
 * 「打开来一片空白 / 光路没画出来 / 偷偷出了网」，这三条只有在真浏览器里跑一遍才知道。
 * 判据不是"能打开"，而是这几件可测量的事实：
 *   manifest 在、入口在、欢迎页消失（场景真被载入）、光层画出了东西（sum 与 lit 都 > 0）、
 *   零出网请求（除包来源本身）、无页面错误。
 * 任何一条不成立就 `ok=false`——调用方（Publisher）据此拒绝发布。
 */

const MIME: Record<string, string> = {
  ".html": "text/html; charset=utf-8",
  ".js": "text/javascript; charset=utf-8",
  ".json": "application/json; charset=utf-8",
  ".css": "text/css; charset=utf-8",
  ".png": "image/png",
  ".svg": "image/svg+xml",
  ".jpg": "image/jpeg",
  ".ttf": "font/ttf",
  ".woff2": "font/woff2",
  ".map": "application/json",
  ".webmanifest": "application/manifest+json",
};

export type VerifyCheck = { id: string; passed: boolean; observed: string | number };

export type PackageVerification = {
  ok: boolean;
  entry: string | null;
  scene_sha256: string | null;
  checks: VerifyCheck[];
  screenshot_sha256: string | null;
  off_origin: string[];
  errors: string[];
};

function serveStatic(root: string): Promise<{ server: Server; origin: string }> {
  const server = createServer(async (req, res) => {
    const path = decodeURIComponent(new URL(req.url ?? "/", "http://127.0.0.1").pathname);
    let rel = path === "/" ? "index.html" : path.replace(/^\/+/, "");
    // join 而不是 resolve：resolve("simulator/", "index.html") 会拿 process.cwd() 去解析，
    // 得出一个包外的绝对路径，于是被下面的越权守卫判成 403——iframe 文档变成 403 的文本，
    // 页面"开了但什么都没有"。这个坑我在实测里踩过一次。
    if (!extname(rel)) rel = join(rel, "index.html");
    const target = resolve(root, rel);
    if (target !== root && !target.startsWith(root + sep)) {
      res.writeHead(403);
      return res.end("forbidden");
    }
    try {
      const body = await readFile(target);
      res.writeHead(200, { "content-type": MIME[extname(target)] ?? "application/octet-stream" });
      res.end(body);
    } catch {
      res.writeHead(404);
      res.end("not found");
    }
  });
  return new Promise(r => {
    server.listen(0, "127.0.0.1", () => {
      const a = server.address();
      r({ server, origin: `http://127.0.0.1:${typeof a === "object" && a ? a.port : 0}` });
    });
  });
}

const close = (server: Server) => new Promise<void>(r => server.close(() => r()));

/**
 * 光层读数：总光强与点亮像素数。两者同时为 0 说明"页面开了但光路没画出来"。
 *
 * 不假设 iframe 的层级与顺序：整份离线包（首页 → #sim → 上游模拟器自己的文档）与
 * 预览页的 frame 树不完全一样，按"第一个子 frame"取会取到没有光层的空 frame。
 * 这里遍历整棵 frame 树，找得到 `canvasLight` 的那个才读数。
 */
async function lightSignals(page: Page): Promise<{ sum: number; lit: number; frames: number; canvases: string }> {
  const all = page.frames();
  const seen: string[] = [];
  for (const frame of all) {
    const hit = await frame
      .evaluate(() => {
        const ids = [...document.querySelectorAll("canvas")].map(c => c.id || "(无名)");
        const c = document.getElementById("canvasLight") as HTMLCanvasElement | null;
        if (!c) return { found: null as null | { sum: number; lit: number }, ids };
        let g: CanvasRenderingContext2D | null = null;
        try {
          g = c.getContext("2d", { willReadFrequently: true });
        } catch {
          g = null;
        }
        if (!g) return { found: { sum: -3, lit: -3 }, ids };
        const d = g.getImageData(0, 0, c.width, c.height).data;
        let sum = 0;
        let lit = 0;
        for (let i = 0; i < d.length; i += 4) {
          sum += d[i] + d[i + 1] + d[i + 2];
          if (d[i] > 12 || d[i + 1] > 12 || d[i + 2] > 12) lit++;
        }
        return { found: { sum, lit }, ids };
      })
      .catch(() => null);
    if (!hit) continue;
    seen.push(...hit.ids);
    if (hit.found) return { ...hit.found, frames: all.length, canvases: seen.join(",") };
  }
  return { sum: -2, lit: -2, frames: all.length, canvases: seen.join(",") || "(一个 canvas 都没有)" };
}

export async function verifyOfflinePackage(
  pkgDir: string,
  options: { settleMs?: number } = {}
): Promise<PackageVerification> {
  assertWithinSandbox(pkgDir);
  const settleMs = options.settleMs ?? 8000;
  const checks: VerifyCheck[] = [];
  const out: PackageVerification = {
    ok: false, entry: null, scene_sha256: null, checks,
    screenshot_sha256: null, off_origin: [], errors: [],
  };

  const manifestPath = resolve(pkgDir, "manifest.json");
  if (!existsSync(manifestPath)) {
    checks.push({ id: "manifest_present", passed: false, observed: manifestPath });
    return out;
  }
  let manifest: { entry?: unknown; scene_sha256?: unknown };
  try {
    manifest = JSON.parse(readFileSync(manifestPath, "utf8"));
  } catch (e) {
    checks.push({ id: "manifest_parseable", passed: false, observed: String(e) });
    return out;
  }
  const rawEntry = manifest.entry;
  if (typeof rawEntry !== "string" || !rawEntry.trim()) {
    checks.push({ id: "entry_declared", passed: false, observed: "entry 缺失或非字符串" });
    return out;
  }

  // 严格检查 entry：必须是相对路径，禁止以 / 或盘符开头，禁止含空字节
  if (rawEntry.includes("\0") || rawEntry.startsWith("/") || /^[a-zA-Z]:/.test(rawEntry)) {
    checks.push({ id: "entry_declared", passed: false, observed: `非法 entry: ${rawEntry}` });
    return out;
  }

  // 清单里的 entry 必须严格落在 www/ 目录下，禁止路径逃逸（如 ../ 或 www/../../）
  const root = resolve(pkgDir, "www");
  const target = resolve(pkgDir, rawEntry);
  if (target !== root && !target.startsWith(root + sep)) {
    checks.push({ id: "entry_declared", passed: false, observed: `entry 越权逃逸出 www: ${rawEntry}` });
    return out;
  }

  out.entry = rawEntry;
  out.scene_sha256 = typeof manifest.scene_sha256 === "string" ? manifest.scene_sha256 : null;
  checks.push({ id: "entry_declared", passed: true, observed: rawEntry });

  checks.push({ id: "entry_file_present", passed: existsSync(target), observed: target });
  if (!existsSync(target)) return out;

  const urlPath = "/" + rawEntry.replace(/^www\/?/, "");
  const { server, origin } = await serveStatic(root);
  let browser: Browser | null = null;
  try {
    browser = await chromium.launch();
    const page = await browser.newPage({ viewport: { width: 1400, height: 900 } });
    page.on("request", req => {
      try {
        const reqOrigin = new URL(req.url()).origin;
        if (reqOrigin !== origin) out.off_origin.push(req.url());
      } catch {
        out.off_origin.push(req.url());
      }
    });
    page.on("pageerror", e => out.errors.push(String(e)));
    await page.goto(origin + urlPath, { waitUntil: "load" });
    await page.waitForTimeout(settleMs);

    // 不用 frameLocator(...).isHidden()：元素不存在时它也返回 true，于是「iframe 文档
    // 根本没 load 出来」会伪装成「场景已载入」；而且 Locator 的自动等待会在这里空耗 30s。
    // 直接遍历 frame 树，找到有 #welcome 的那个文档，问它此刻到底可不可见。
    let welcome: { found: boolean; hidden: boolean } = { found: false, hidden: false };
    for (const f of page.frames()) {
      const hit = await f
        .evaluate(() => {
          const e = document.getElementById("welcome") as HTMLElement | null;
          if (!e) return null;
          return { hidden: e.style.display === "none" || e.offsetParent === null || e.getClientRects().length === 0 };
        })
        .catch(() => null);
      if (hit) {
        welcome = { found: true, hidden: hit.hidden };
        break;
      }
    }
    checks.push({
      id: "scene_loaded",
      passed: welcome.found && welcome.hidden,
      observed: welcome.found
        ? welcome.hidden
          ? "欢迎页已被隐藏（场景真被载入）"
          : "欢迎页仍在显示（场景没进去）"
        : "没有任何 frame 里存在 #welcome（模拟器文档没加载出来）",
    });

    const light = await lightSignals(page);
    checks.push({
      id: "rays_rendered",
      passed: light.sum > 0 && light.lit > 0,
      observed: `光强 ${light.sum}，点亮像素 ${light.lit}（${light.frames} 个 frame，canvas 名录：${light.canvases}）`,
    });

    checks.push({ id: "zero_egress", passed: out.off_origin.length === 0, observed: out.off_origin.length });
    checks.push({ id: "no_page_errors", passed: out.errors.length === 0, observed: out.errors.join(" | ") || "无" });

    const buf = await page.locator("#sim").screenshot().catch(() => null);
    if (buf) out.screenshot_sha256 = createHash("sha256").update(buf).digest("hex");
    checks.push({ id: "screenshot_taken", passed: out.screenshot_sha256 !== null, observed: out.screenshot_sha256 ?? "无" });

    out.ok = checks.every(c => c.passed);
    await page.close();
  } finally {
    if (browser) await browser.close();
    await close(server);
  }
  return out;
}
