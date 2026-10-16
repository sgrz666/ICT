import { createHash } from "node:crypto";

import { chromium, type Browser, type Frame, type Page } from "playwright";

import { createPreviewServer, type PreviewServer } from "../../src/preview/server";
import { UPSTREAM_DIST } from "../../src/upstream_paths";

// e2e 共用夹具。之前两个测试文件各抄一份 helper，批量改一处漏一处，
// 直接造成过一次 ReferenceError。

export type RenderSignals = { sum: number; lit: number };

/** 光层的两个独立读数：总光强与点亮像素数。 */
export async function lightSignals(frame: Frame): Promise<RenderSignals> {
  return await frame.evaluate(() => {
    const c = document.getElementById("canvasLight") as HTMLCanvasElement | null;
    if (!c) return { sum: -1, lit: -1 };
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
  });
}

/**
 * 等渲染真正稳定：总光强与点亮像素数**同时**连续不变才算完成。
 * 只看一个信号会在渲染中途出现平台期而误判，届时截图哈希会偶然不一致，
 * 把"渲染不确定"这种假结论喂给控制组。
 */
export async function waitForStableRender(frame: Frame, maxMs = 60000): Promise<RenderSignals> {
  let prev: RenderSignals = { sum: -2, lit: -2 };
  let stable = 0;
  const started = Date.now();
  while (Date.now() - started < maxMs) {
    const now = await lightSignals(frame);
    if (now.sum > 0 && now.sum === prev.sum && now.lit === prev.lit) {
      if (++stable >= 3) return now;
    } else {
      stable = 0;
    }
    prev = now;
    await new Promise(r => setTimeout(r, 600));
  }
  throw new Error("渲染在 " + maxMs + "ms 内未稳定，不能取截图作判据");
}

export async function openPreview(
  browser: Browser,
  preview: PreviewServer,
  port: number,
  scene: unknown
): Promise<{ page: Page; frame: Frame }> {
  const page = await browser.newPage({ viewport: { width: 1400, height: 900 } });
  const reg = await preview.register(scene);
  await page.goto(reg.url(port), { waitUntil: "load" });
  await page.waitForTimeout(7000);
  const frame = page.frames().find(f => f.parentFrame() === page.mainFrame());
  if (!frame) throw new Error("预览 iframe 的 Frame 没找到");
  return { page, frame };
}

export async function shotHash(page: Page): Promise<string> {
  const buf = await page.locator("#sim").screenshot();
  return createHash("sha256").update(buf).digest("hex");
}

export function startBrowser(): Promise<Browser> {
  return chromium.launch();
}

export function startPreview(): { preview: PreviewServer; listen: () => Promise<number> } {
  const preview = createPreviewServer(UPSTREAM_DIST);
  return { preview, listen: () => preview.listen() };
}
