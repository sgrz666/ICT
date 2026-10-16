import { chromium, type Browser, type Frame, type Page } from "playwright";
import { expect, it } from "vitest";

import { loadTemplateScene } from "../../src/adapters/ray-optics/adapter";
import { createPreviewServer } from "../../src/preview/server";
import { UPSTREAM_DIST } from "../../src/upstream_paths";
import { lightSignals, openPreview, shotHash, waitForStableRender } from "./render_harness";

// GATE-3 浏览器交互侧。两条对计划的修正写在这里，免得下次又按错假设排活：
//  1) 上游**没有"播放/暂停"按钮**，仿真自动跑，所以"运行"以光层信号作证据；
//  2) iframe 内用"复制分享链接"读场景拿不到剪贴板（隐藏菜单项的 click 不触发 Vue 处理器），
//     那条路径第 4 轮是在直接打开页面时验过的，不在这里冒充。
// 复位判据 = #welcome 可见性 + 光层归零；新增对象判据 = objBar 出现 + 画面改变。

async function welcomeVisible(frame: Frame): Promise<boolean> {
  return await frame.evaluate(() => {
    const w = document.getElementById("welcome");
    if (!w) return false;
    const s = getComputedStyle(w);
    return s.display !== "none" && s.visibility !== "hidden" && Number(s.opacity) !== 0;
  });
}

it("载入即隐藏欢迎页、光层在画；清空后回到无场景且光层归零", async () => {
  const preview = createPreviewServer(UPSTREAM_DIST);
  const port = await preview.listen();
  const browser: Browser = await chromium.launch();
  const { page, frame } = await openPreview(browser, preview, port, loadTemplateScene());
  const errors: string[] = [];
  page.on("pageerror", e => errors.push(String(e)));

  expect(await frame.title()).toContain("射线光学模拟");
  // 节点必须在，否则"不可见"就成空洞判断
  expect(await frame.locator("#welcome").count()).toBe(1);
  expect(await welcomeVisible(frame)).toBe(false);
  const before = await waitForStableRender(frame);
  expect(before.sum).toBeGreaterThan(0);

  await frame.evaluate(() => {
    for (const el of Array.from(document.querySelectorAll("button,a,li,.dropdown-item"))) {
      const own = Array.from(el.childNodes)
        .filter(n => n.nodeType === 3).map(n => (n.textContent || "").trim()).join("").trim();
      if (own === "清空") { ((el.closest("button,a,li") || el) as HTMLElement).click(); return; }
    }
  });
  await page.waitForTimeout(3000);

  expect(await welcomeVisible(frame)).toBe(true);
  const after = await lightSignals(frame);
  expect(after.sum).toBe(0);
  expect(after.lit).toBe(0);
  expect(errors).toEqual([]);

  await browser.close();
  await preview.close();
}, 300000);

it("侧栏工具菜单可新增对象：展开光源分组选单一光线并点画布，objBar 出现且画面改变", async () => {
  const preview = createPreviewServer(UPSTREAM_DIST);
  const port = await preview.listen();
  const browser: Browser = await chromium.launch();
  const { page, frame }: { page: Page; frame: Frame } =
    await openPreview(browser, preview, port, loadTemplateScene());
  const errors: string[] = [];
  page.on("pageerror", e => errors.push(String(e)));

  await waitForStableRender(frame);
  const shotBefore = await shotHash(page);

  // 工具项在折叠下拉里，必须先展开分组
  await frame.locator("#lightSourceToolsDropdown").click();
  await frame.locator("#tool_SingleRay_label").click();
  // 选中态由上游自己维护，不是我们替它设的值
  expect(await frame.locator("#tool_SingleRay").isChecked()).toBe(true);

  const box = (await page.locator("#sim").boundingBox())!;
  // 用画布自身矩形：按 iframe 外框坐标点下去会落到画布外（第一次就是这样，什么都没变）
  const rect = await frame.evaluate(() => {
    const c = document.getElementById("canvasGrid") as HTMLCanvasElement | null;
    if (!c) return null;
    const r = c.getBoundingClientRect();
    return { x: r.x, y: r.y, w: r.width, h: r.height };
  });
  expect(rect).toBeTruthy();
  await page.mouse.click(box.x + rect!.x + rect!.w * 0.22, box.y + rect!.y + rect!.h * 0.22);
  await page.waitForTimeout(3500);

  const bar = await frame.evaluate(() => {
    const el = document.querySelector("#obj-bar,.obj-bar,#objBar,[class*=objbar]");
    return el
      ? { present: true, controls: el.querySelectorAll("input,button,select").length }
      : { present: false, controls: 0 };
  });
  await waitForStableRender(frame);
  const shotAfter = await shotHash(page);

  expect(bar.present, "objBar 未出现 ⇒ 对象没真的进场景").toBe(true);
  expect(bar.controls).toBeGreaterThan(0);
  // 不用"总光强必须增加"当判据：一条细光线相对点光源已点的 47.6 万像素落在噪声内，
  // 实测两者几乎相等，那种断言只会造出假失败。
  expect(shotAfter).not.toBe(shotBefore);
  expect(errors).toEqual([]);

  await browser.close();
  await preview.close();
}, 300000);
