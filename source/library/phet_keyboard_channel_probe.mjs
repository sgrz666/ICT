/** PhET 成品的键盘写通道：上一轮 5/6 只「元素不可聚焦」，这里查是不是我点错了地方。
 *
 * 现场证据（phet-a11y-channel-probe.json）：ohms-law 的两个无障碍 input 有实际尺寸（51×253，x=824），
 * 而 geometric-optics / wave-interference / energy-skate / cck-dc / gas-properties 的同类元素
 * rect 全是 0×0 —— 尺寸为 0 的元素当然 focus() 不进去。PhET 的做法是把无障碍 input 收在
 * 「交互区」里，交互区拿到焦点之后才展开。所以这不是「仿真不支持键盘」，而是我没先把交互区点亮。
 *
 * 测法：先点画布（把交互区拿到焦点），再沿 Tab 环走，看第一个带 aria-valuenow 的焦点元素出现没有、
 * 出现之后按方向键数值动不动、动的量是不是仿真自己念出来的那个量。
 * 判据分三档，不给布尔：
 *   keyboard_channel_verified   —— 焦点元素拿到且数值随按键变化（并且仿真自己的文本读数跟着变）
 *   focus_ring_reached          —— 拿到焦点元素但数值不动
 *   no_focusable_value_target   —— 走完 Tab 环也没遇到带 aria-valuenow 的可聚焦元素
 */
import fs from "node:fs";
import path from "node:path";
import { createRequire } from "node:module";
import { pathToFileURL } from "node:url";
import { findChromium } from "./ejss_headless_lab.mjs";

const require = createRequire(path.join(process.cwd(), "noop.js"));
const ROOT = process.cwd();
const { chromium } = require("playwright-core");
const manifest = JSON.parse(fs.readFileSync(path.join(ROOT, "source/upstream/phet-published.json"), "utf-8"));
const exec = findChromium();
const TARGETS = ["geometric-optics", "wave-interference", "energy-skate-park-basics", "circuit-construction-kit-dc", "gas-properties"];

const ACTIVE = () => {
  const e = document.activeElement;
  if (!e || e === document.body) return { tag: "BODY", now: null, label: null };
  const r = e.getBoundingClientRect();
  return {
    tag: e.tagName, now: e.getAttribute("aria-valuenow"),
    label: (e.getAttribute("aria-label") || "").replace(/\s+/g, " ").slice(0, 40),
    rect: { w: Math.round(r.width), h: Math.round(r.height) },
  };
};
// 仿真自己念出来的文本（不读引擎内部状态），用来确认「数值动」是画面上的量真的动了
const TEXT = () => (document.body.innerText || "").replace(/\s+/g, " ");

const report = { measured_at: new Date().toISOString(), tool: "source/library/phet_keyboard_channel_probe.mjs", sims: [] };
const browser = await chromium.launch({ executablePath: exec, headless: true, args: ["--no-sandbox", "--allow-file-access-from-files"] });
try {
  for (const sim of TARGETS) {
    const item = manifest.sims.find((s) => s.sim === sim);
    const row = { sim, version: item.version };
    const p = await (await browser.newContext({ viewport: { width: 1100, height: 760 } })).newPage();
    try {
      await p.goto(pathToFileURL(path.join(ROOT, item.file)).href, { waitUntil: "load", timeout: 90000 });
      await p.waitForTimeout(4000);
      row.before_click_text = (await p.evaluate(TEXT)).slice(0, 120);
      // 第一阶段（点画布中心 + 走 Tab 环）5/5 都拿不到可聚焦的数值元素，而上一轮读到的画面文本
      // 全停在「Welcome to …」——这 5 只都带启动屏，ohms-law 没有。所以这一版先把启动屏关掉再走环：
      // 点带 play/continue/accept 字样的按钮，按不中就用空格与回车兜一遍。
      row.welcome_dismissed = await p.evaluate(() => {
        const btns = [...document.querySelectorAll("button,[role=button],a")];
        const hit = btns.find((b) => /play|continue|accept|got it|start|ok|close/i.test((b.innerText || b.getAttribute("aria-label") || "")));
        if (hit) { hit.click(); return (hit.innerText || hit.getAttribute("aria-label") || "").slice(0, 40); }
        return null;
      });
      if (!row.welcome_dismissed) { await p.keyboard.press("Space"); await p.waitForTimeout(400); await p.keyboard.press("Enter"); }
      await p.waitForTimeout(1500);
      row.text_after_dismiss = (await p.evaluate(TEXT)).slice(0, 120);
      // 点画布中心：把交互区拿到焦点（PhET 的无障碍 input 平时收着）
      const box = await p.evaluate(() => {
        const c = document.querySelector("canvas");
        if (!c) return null;
        const r = c.getBoundingClientRect();
        return { x: r.x + r.width / 2, y: r.y + r.height / 2 };
      });
      row.canvas_center = box;
      if (box) await p.mouse.click(box.x, box.y);
      await p.waitForTimeout(600);
      row.peer_sizes_after_click = await p.evaluate(() => [...document.querySelectorAll("[aria-valuenow]")].slice(0, 8)
        .map((e) => { const r = e.getBoundingClientRect(); return { tag: e.tagName, now: e.getAttribute("aria-valuenow"), w: Math.round(r.width), h: Math.round(r.height) }; }));
      // 沿 Tab 环找第一个带 aria-valuenow 的焦点元素
      const ring = [];
      let target = null;
      for (let i = 0; i < 30 && !target; i++) {
        await p.keyboard.press("Tab");
        const a = await p.evaluate(ACTIVE);
        ring.push(a);
        if (a.now !== null && a.now !== undefined) target = { tab_steps: i + 1, ...a };
      }
      row.tab_ring_first_8 = ring.slice(0, 8);
      row.value_target = target;
      if (!target) {
        row.verdict = "no_focusable_value_target";
        row.tab_ring_length = ring.length;
      } else {
        const textBefore = await p.evaluate(TEXT);
        const traj = [target.now];
        for (let i = 0; i < 5; i++) { await p.keyboard.press("ArrowRight"); await p.waitForTimeout(250); traj.push(await p.evaluate(() => document.activeElement.getAttribute("aria-valuenow"))); }
        const textAfter = await p.evaluate(TEXT);
        row.trajectory = traj;
        row.value_changed = traj[traj.length - 1] !== traj[0];
        row.sim_text_changed = textAfter.slice(0, 900) !== textBefore.slice(0, 900);
        row.text_before_snippet = textBefore.slice(0, 200);
        row.text_after_snippet = textAfter.slice(0, 200);
        row.verdict = row.value_changed
          ? (row.sim_text_changed ? "keyboard_channel_verified_with_text" : "keyboard_channel_verified_value_only")
          : "focus_ring_reached";
      }
    } catch (e) {
      row.error = String(e).slice(0, 160);
      row.verdict = "load_failed";
    } finally {
      await p.context().close();
    }
    report.sims.push(row);
    console.log(`${sim.padEnd(30)} 交互区点击后尺寸=${JSON.stringify((row.peer_sizes_after_click || []).slice(0, 2))} `
      + `目标=${row.value_target ? `Tab第${row.value_target.tab_steps}步 ${row.value_target.tag}=${row.value_target.now}` : "无"} 判定=${row.verdict}`);
  }
} finally {
  await browser.close();
}
const tally = {};
for (const r of report.sims) tally[r.verdict] = (tally[r.verdict] || 0) + 1;
report.summary = { sims: report.sims.length, verdicts: tally };
fs.writeFileSync(path.join(ROOT, "source/library/phet-keyboard-channel-probe.json"), JSON.stringify(report, null, 2), "utf-8");
console.log("\n汇总:", JSON.stringify(report.summary), "\n写入 source/library/phet-keyboard-channel-probe.json");
