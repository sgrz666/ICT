import { createServer } from "node:http";
import { createHash } from "node:crypto";
import { existsSync } from "node:fs";
import { readFileSync } from "node:fs";
import { readFile } from "node:fs/promises";
import { dirname, extname, join, resolve, sep } from "node:path";
import { fileURLToPath } from "node:url";

import { chromium, type Browser } from "playwright";
import { afterAll, beforeAll, describe, expect, it } from "vitest";

import { loadTemplateScene, rayOpticsAdapter } from "../../src/adapters/ray-optics/adapter";
import { buildOfflinePackage } from "../../src/export/offline-package";

// GATE-8 的离线检查（§5.4）。判据不是"能打开"，而是：
// 除了随包静态服务这个精确来源，不许有任何其他网络请求；出现即不通过。
const here = dirname(fileURLToPath(import.meta.url));

// 未发布的候选产物按计划落在 output/eduforge/candidates（§1.1），不是临时目录。
// 向上找到同时含 code/ 与 output/ 的工作区根，避免手数 ../ 层数反复写错
// （同一段代码里我已经数错过两次）。
function workspaceRoot(start: string): string {
  let dir = start;
  for (let i = 0; i < 12; i++) {
    if (existsSync(join(dir, "code")) && existsSync(join(dir, "output"))) return dir;
    const up = resolve(dir, "..");
    if (up === dir) break;
    dir = up;
  }
  throw new Error("WORKSPACE_ROOT_NOT_FOUND from " + start);
}

const OUT_DIR = join(workspaceRoot(here), "output", "eduforge", "candidates", "offline-package");

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

let pkgDir: string;
let server: ReturnType<typeof createServer>;
let origin = "";
let browser: Browser;

beforeAll(async () => {
  const candidate = rayOpticsAdapter.apply(loadTemplateScene(), {
    op: "set_parameter",
    entity_id: "lens_1",
    parameter: "focal_length_cm",
    value: 15,
  });
  expect(candidate.validation.ok).toBe(true);

  const pkg = await buildOfflinePackage(candidate.native, OUT_DIR, { title: "凸透镜成像 离线包" });
  pkgDir = pkg.dir;

  const root = resolve(pkgDir, "www");
  server = createServer(async (req, res) => {
    const path = decodeURIComponent(new URL(req.url ?? "/", "http://x").pathname);
    let rel = path === "/" ? "index.html" : path.replace(/^\/+/, "");
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
  const port = await new Promise<number>(r => server.listen(0, "127.0.0.1", () => {
    const a = server.address();
    r(typeof a === "object" && a ? a.port : 0);
  }));
  origin = `http://127.0.0.1:${port}`;
  browser = await chromium.launch();
}, 180000);

afterAll(async () => {
  await browser?.close();
  await new Promise<void>(r => server?.close(() => r()));
});

async function openAndCollect(url: string) {
  const page = await browser.newPage({ viewport: { width: 1400, height: 900 } });
  const offOrigin: string[] = [];
  const requests: string[] = [];
  const errors: string[] = [];
  page.on("request", req => {
    requests.push(req.url());
    if (!req.url().startsWith(origin) && !req.url().startsWith("file://")) offOrigin.push(req.url());
  });
  page.on("pageerror", e => errors.push(String(e)));
  await page.goto(url, { waitUntil: "load" });
  await page.waitForTimeout(6000);

  // 严格检查 #welcome 元素存在性与隐藏状态，消除 locator.isHidden() 在元素不存在时的假阳性
  let welcomeFound = false;
  let welcomeHidden = false;
  for (const f of page.frames()) {
    const hit = await f
      .evaluate(() => {
        const e = document.getElementById("welcome") as HTMLElement | null;
        if (!e) return null;
        return { hidden: e.style.display === "none" || e.offsetParent === null || e.getClientRects().length === 0 };
      })
      .catch(() => null);
    if (hit) {
      welcomeFound = true;
      welcomeHidden = hit.hidden;
      break;
    }
  }

  // 遍历 frame 树提取 canvasLight 真实像素读数，断言光路真画出来了
  let light = { sum: 0, lit: 0 };
  for (const f of page.frames()) {
    const hit = await f
      .evaluate(() => {
        const c = document.getElementById("canvasLight") as HTMLCanvasElement | null;
        if (!c) return null;
        let g: CanvasRenderingContext2D | null = null;
        try {
          g = c.getContext("2d", { willReadFrequently: true });
        } catch {
          g = null;
        }
        if (!g) return { sum: -1, lit: -1 };
        const d = g.getImageData(0, 0, c.width, c.height).data;
        let sum = 0;
        let lit = 0;
        for (let i = 0; i < d.length; i += 4) {
          sum += d[i] + d[i + 1] + d[i + 2];
          if (d[i] > 12 || d[i + 1] > 12 || d[i + 2] > 12) lit++;
        }
        return { sum, lit };
      })
      .catch(() => null);
    if (hit && hit.sum >= 0) {
      light = hit;
      break;
    }
  }

  const sized = await page
    .evaluate(() =>
      [...document.querySelectorAll("iframe")].length > 0 &&
      [...document.querySelectorAll("canvas")].length
    )
    .catch(() => 0);
  await page.close();
  return { offOrigin, requests, errors, welcomeFound, welcomeHidden, light, sized };
}

describe("GATE-8 离线包", () => {
  it("包结构齐全，且落在计划规定的 candidates 目录", () => {
    expect(pkgDir).toBeTruthy();
    expect(pkgDir.split("\\").join("/")).toContain("output/eduforge/candidates/offline-package");
    expect(existsSync(join(pkgDir, "www", "simulator", "main.js"))).toBe(true);
    const manifest = JSON.parse(readFileSync(join(pkgDir, "manifest.json"), "utf8"));
    expect(manifest.engine_version).toBe("5.5.0");
    expect(manifest.scene_sha256).toMatch(/^[0-9a-f]{64}$/);
    // 哈希必须锁得住包里那份文件字节——换一种序列化方式再比是验不了的
    const sceneBytes = readFileSync(join(pkgDir, "www", "scene", "native.json"));
    expect(createHash("sha256").update(sceneBytes).digest("hex")).toBe(manifest.scene_sha256);
    const scene = JSON.parse(sceneBytes.toString("utf8"));
    expect(scene.objs.find((o: { name: string }) => o.name === "lens_1").focalLength).toBe(150);
  });

  it("经随包静态服务打开：零出网请求、场景载入、无页面错误与非零光层", async () => {
    const r = await openAndCollect(`${origin}/index.html`);
    // §5.4：拦截清单非空即不通过
    expect(r.offOrigin).toEqual([]);
    expect(r.welcomeFound).toBe(true);
    expect(r.welcomeHidden).toBe(true);
    expect(r.light.lit).toBeGreaterThan(0);
    expect(r.light.sum).toBeGreaterThan(0);
    expect(r.errors).toEqual([]);
    expect(r.requests.length).toBeGreaterThan(3); // 确实取过资源，不是空白页
    // 所有请求都必须落在包来源内
    for (const u of r.requests) expect(u.startsWith(origin)).toBe(true);
  }, 45000);

  it("实测确认 file:// 直开不可用（上游 i18n 运行时 HTTP 取词），所以单文件 HTML 需要额外预注入层", async () => {
    const r = await openAndCollect(`file:///${join(pkgDir, "www", "index.html").replace(/\\/g, "/")}`);
    // 这里断言的是"我们知道它不行且知道为什么不行"：locale JSON 取不到
    const localeMissing = r.requests.some(u => u.includes("/locales/") && u.startsWith("file:"));
    expect(localeMissing || r.errors.length > 0 || !r.welcomeHidden || !r.welcomeFound).toBe(true);
  }, 45000);
});
