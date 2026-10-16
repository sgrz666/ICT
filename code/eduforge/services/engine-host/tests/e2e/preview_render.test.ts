import { afterAll, beforeAll, describe, expect, it } from "vitest";
import type { Browser } from "playwright";

import { loadTemplateScene, rayOpticsAdapter } from "../../src/adapters/ray-optics/adapter";
import { createPreviewServer, type PreviewServer } from "../../src/preview/server";
import { UPSTREAM_DIST } from "../../src/upstream_paths";
import {
  lightSignals,
  openPreview,
  shotHash,
  startBrowser,
  waitForStableRender,
} from "./render_harness";

// GATE-3 浏览器可判性：改过的场景在真实浏览器里渲染，且判据可复现。
// 判据不是"页面打开了"，而是控制组逐位一致 + 实验组确实不同。
const DIST = process.env.EDUFORGE_RAYOPTICS_DIST ?? UPSTREAM_DIST;

let preview: PreviewServer;
let port = 0;
let browser: Browser;

beforeAll(async () => {
  preview = createPreviewServer(DIST);
  port = await preview.listen();
  browser = await startBrowser();
}, 120000);

afterAll(async () => {
  await browser?.close();
  await preview?.close();
});

function sceneWithFocalLength(cm: number) {
  const candidate = rayOpticsAdapter.apply(loadTemplateScene(), {
    op: "set_parameter",
    entity_id: "lens_1",
    parameter: "focal_length_cm",
    value: cm,
  });
  expect(candidate.validation.ok).toBe(true);
  return candidate.native;
}

async function renderOnce(native: unknown) {
  const { page, frame } = await openPreview(browser, preview, port, native);
  const errors: string[] = [];
  page.on("pageerror", e => errors.push(String(e)));
  const signals = await waitForStableRender(frame);
  const hash = await shotHash(page);
  await page.close();
  return { hash, signals, errors };
}

describe("候选场景在真实浏览器里运行", () => {
  it("控制组：同一场景两次渲染逐位一致", async () => {
    const a = await renderOnce(sceneWithFocalLength(10));
    const b = await renderOnce(sceneWithFocalLength(10));
    expect(a.errors).toEqual([]);
    expect(a.signals.sum).toBeGreaterThan(0);
    expect(b.hash).toBe(a.hash);
    expect(b.signals).toEqual(a.signals);
  }, 300000);

  it("实验组：焦距 10cm 与 15cm 渲染出的光路不同", async () => {
    const f10 = await renderOnce(sceneWithFocalLength(10));
    const f15 = await renderOnce(sceneWithFocalLength(15));
    expect(f10.errors).toEqual([]);
    expect(f15.errors).toEqual([]);
    // 本机实测基线：f=10 sum=302526662 lit=476563；f=15 sum=287776335 lit=453202。
    // 只断言"不同"是不够的（第 15 轮发现哈希本身在无稳定等待时会漂），
    // 因此同时比两个独立信号。
    expect(f15.hash).not.toBe(f10.hash);
    expect(f15.signals.sum).toBeLessThan(f10.signals.sum);
    expect(f15.signals.lit).toBeLessThan(f10.signals.lit);
  }, 300000);

  it("预览服务拒绝越出 dist 目录的路径请求", async () => {
    const res = await fetch("http://127.0.0.1:" + port + "/../../../../Windows/win.ini");
    expect([403, 404]).toContain(res.status);
  });

  it("注册端点回 201 且预览页含 iframe", async () => {
    const res = await fetch(`http://127.0.0.1:${port}/scene`, {
      method: "POST",
      headers: { "content-type": "application/json" },
      body: JSON.stringify(loadTemplateScene()),
    });
    expect(res.status).toBe(201);
    const body = (await res.json()) as { path: string };
    const page = await browser.newPage();
    await page.goto(`http://127.0.0.1:${port}${body.path}`, { waitUntil: "load" });
    expect(await page.locator("#sim").count()).toBe(1);
    await page.close();
  });

  it("页面自身无脚本错误且光层在画", async () => {
    const { page, frame } = await openPreview(browser, preview, port, sceneWithFocalLength(12));
    const errors: string[] = [];
    page.on("pageerror", e => errors.push(String(e)));
    expect(await frame.title()).toContain("射线光学模拟");
    const settled = await waitForStableRender(frame);
    expect(settled.sum).toBeGreaterThan(0);
    expect((await lightSignals(frame)).sum).toBe(settled.sum);
    expect(errors).toEqual([]);
    await page.close();
  }, 300000);
});
