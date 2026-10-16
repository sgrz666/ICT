import { expect, it } from "vitest";
import { chromium, type Frame, type Page } from "playwright";

import { createPreviewServer } from "../../src/preview/server";
import { loadTemplateScene } from "../../src/adapters/ray-optics/adapter";
import { openPreview, shotHash, waitForStableRender } from "./render_harness";

// §5.2/§5.3 的桥接与消息协议。宿主页是教师前端 PreviewFrame 的最小等价物，
// 所以这里测的就是切片 8 要依赖的那份契约。
async function hostPageOf(port: number, id: string): Promise<{ page: Page; log: Frame }> {
  const browser = await chromium.launch();
  const page = await browser.newPage({ viewport: { width: 1400, height: 900 } });
  await page.goto(`http://127.0.0.1:${port}/host/${id}`, { waitUntil: "load" });
  return { page, log: page.mainFrame() };
}

async function readLog(page: Page): Promise<string[]> {
  return await page.evaluate(() =>
    (document.getElementById("log") as HTMLElement).textContent
      .split("\n")
      .filter(Boolean)
  );
}

async function waitForLog(page: Page, needle: string, timeoutMs = 45000): Promise<string[]> {
  const started = Date.now();
  while (Date.now() - started < timeoutMs) {
    const lines = await readLog(page);
    if (lines.some(l => l.includes(needle))) return lines;
    await new Promise(r => setTimeout(r, 400));
  }
  throw new Error("日志里没等到 " + needle + "；当前=" + JSON.stringify(await readLog(page)));
}

it("桥接：ready 只报一次、改参数后重报并回 change、非法值回 error、原版本仍可访问", async () => {
  const preview = createPreviewServer();
  const port = await preview.listen();
  const reg = await preview.register(loadTemplateScene());
  const id = reg.id;

  const { page } = await hostPageOf(port, id);
  const errors: string[] = [];
  page.on("pageerror", e => errors.push(String(e)));

  // 1) 初始 ready 恰好一次
  let lines = await waitForLog(page, "eduforge.ready");
  expect(lines.filter(l => l.includes("eduforge.ready"))).toHaveLength(1);
  expect(lines[0]).toContain(id);

  // 2) 改焦距 → parameter_changed + 第二次 ready，且报的是**新** revision
  await page.evaluate(() => (window as any).__setParam("lens_1", "focal_length_cm", 15));
  lines = await waitForLog(page, "eduforge.parameter_changed");
  const readys = lines.filter(l => l.includes("eduforge.ready"));
  expect(readys).toHaveLength(2);
  expect(lines.some(l => l.includes("eduforge.parameter_changed") && l.includes('"value":15'))).toBe(true);
  const newRev = JSON.parse(readys[1]).revision_id as string;
  expect(newRev).not.toBe(id);

  // 3) 编辑前的版本仍可访问（§7.5 第 3 条"编辑前版本保持可恢复"）
  expect((await fetch(`http://127.0.0.1:${port}/p/${id}`)).status).toBe(200);
  expect((await fetch(`http://127.0.0.1:${port}/p/${newRev}`)).status).toBe(200);

  // 4) 越界值必须回 error，不能静默接受
  await page.evaluate(() => (window as any).__setParam("lens_1", "focal_length_cm", 999));
  lines = await waitForLog(page, "eduforge.error");
  const err = JSON.parse(lines.filter(l => l.includes("eduforge.error")).slice(-1)[0]);
  expect(err.code).toBe("APPLY_FAILED");
  expect(errors).toEqual([]);

  await page.context().browser()!.close();
  await preview.close();
}, 300000);

it("桥接：渲染确实随参数变化，且同值改回可控", async () => {
  const preview = createPreviewServer();
  const port = await preview.listen();
  const browser = await chromium.launch();

  const ctx = await browser.newContext({ viewport: { width: 1400, height: 900 } });
  const page = (await ctx.newPage()) as Page;
  const scene = loadTemplateScene();

  // 基线：包装页直接开
  const { page: p1, frame: f1 } = await openPreview(browser, preview, port, scene);
  await waitForStableRender(f1);
  const hash10 = await shotHash(p1);
  await p1.close();

  // 服务端改到 15cm 再开，画面必须不同
  const res = await fetch(`http://127.0.0.1:${port}/param`, {
    method: "POST",
    headers: { "content-type": "application/json" },
    body: JSON.stringify({ revision: (await preview.register(scene)).id, entity_id: "lens_1", parameter: "focal_length_cm", value: 15 }),
  });
  expect(res.status).toBe(200);
  const body = (await res.json()) as { revision: string };
  const { page: p2, frame: f2 } = await (async () => {
    const pp = await ctx.newPage();
    await pp.goto(`http://127.0.0.1:${port}/p/${body.revision}`, { waitUntil: "load" });
    const fr = pp.frames().find(f => f.parentFrame() === pp.mainFrame())!;
    return { page: pp, frame: fr };
  })();
  await waitForStableRender(f2);
  const hash15 = await shotHash(p2);
  expect(hash15).not.toBe(hash10);
  await p2.close();

  await browser.close();
  await preview.close();
}, 300000);
