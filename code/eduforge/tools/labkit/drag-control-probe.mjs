/* 抛体模板「空气阻力控件」的回归探针。

 selftest 的 L1-L3 只覆盖默认路径（frictionAir=0），这条补上被开放出来的那一半：
 控件写进去之后，射程必须真的变、页面算出的偏离倍数必须与 L2 证据的 ratio 同定义且对得上、
 写回 0 必须可逆、拖滑块与 __LAB.setParams 两条路都要生效。
 为什么单独一条判据都不信「读数变了」：391.23 那个数最初被我按「射程比 ≥5」写过断言，
 实测只有 2.30 —— 判据口径必须与 L2 证据一致，否则绿的是探针、错的是结论。

 跑法（仓库根）：node code/eduforge/tools/labkit/drag-control-probe.mjs [html 路径]
 默认打 selftest 产出的 oblique45；截图写进被 .gitignore 挡住的 candidates/labkit/ 下。
*/
import path from 'node:path'
import { createRequire } from 'node:module'
import { pathToFileURL } from 'node:url'
import fs from 'node:fs'

const require = createRequire(path.join(process.cwd(), 'noop.js'))
const { chromium } = require('playwright-core')
// Windows: 动态 import 必须给 file:// URL，绝对盘路径会被当成协议名
const { findChromium } = await import(pathToFileURL(path.resolve('source/library/ejss_headless_lab.mjs')).href)

const target = process.argv[2] || 'output/eduforge/candidates/labkit/selftest/oblique45/oblique45.html'
const url = pathToFileURL(path.resolve(target)).href
const browser = await chromium.launch({ executablePath: findChromium(), headless: true, args: ['--no-sandbox'] })
const page = await (await browser.newContext({ viewport: { width: 1280, height: 900 } })).newPage()
const net = []
page.on('request', (r) => { const u = r.url(); if (!u.startsWith('file:') && !u.startsWith('data:')) net.push(u) })
await page.goto(url, { waitUntil: 'load' })
await page.waitForFunction(() => window.__STATUS === 'ready', null, { timeout: 20000 })

const snap = () => page.evaluate(() => ({
  friction_air: window.__RESULT.friction_air,
  R: window.__RESULT.scenarios[0].measured.R,
  T: window.__RESULT.scenarios[0].measured.T,
  H: window.__RESULT.scenarios[0].measured.H,
  analytic_R: window.__RESULT.scenarios[0].analytic.R,
  clean_R: window.__RESULT.scenarios[0].clean && window.__RESULT.scenarios[0].clean.R,
  range_ratio_clean_over_drag: window.__RESULT.range_ratio_clean_over_drag,
  ratio_vs_clean: window.__RESULT.ratio_vs_clean,
  range_ratio: window.__RESULT.range_ratio_clean_over_drag,
  table: document.querySelector('table.readout').innerText.replace(/\s+/g, ' ').slice(0, 220),
  slider_count: document.querySelectorAll('#controls input[type=range]').length,
  drag_value: document.querySelectorAll('#controls input[type=range]').length
    ? document.querySelectorAll('#controls input[type=range]')[document.querySelectorAll('#controls input[type=range]').length - 1].value : null,
}))

const before = await snap()
await page.screenshot({ path: 'output/eduforge/candidates/labkit/drag-control-off.png' })
await page.evaluate(() => window.__LAB.setParams({ friction_air: 0.01 }))
const after = await snap()
await page.screenshot({ path: 'output/eduforge/candidates/labkit/drag-control-on.png' })
// 再写回 0，确认是可逆通道而不是单向状态
await page.evaluate(() => window.__LAB.setParams({ friction_air: 0 }))
const reverted = await snap()
// 也验一下人真的拖滑块这条路（不只是 __LAB）
const uiDriven = await page.evaluate(() => {
  const inputs = document.querySelectorAll('#controls input[type=range]')
  const s = inputs[inputs.length - 1]
  s.value = '0.02'
  s.dispatchEvent(new Event('input', { bubbles: true }))
  return { R: window.__RESULT.scenarios[0].measured.R, f: window.__RESULT.friction_air }
})
await browser.close()

const checks = [
  ['默认无阻力：friction_air=0', before.friction_air === 0],
  ['默认射程≈解析式（<1%）', Math.abs(before.R - before.analytic_R) / before.analytic_R < 0.01],
  ['写 0.01 后射程显著变小', after.R < before.R * 0.6],
  ['__RESULT 记了 clean_R（同参数无阻力重跑）', !!after.clean_R && Math.abs(after.clean_R - before.R) < 1e-6],
  ['ratio_vs_clean ≥ 5（L2 判据，同定义）', after.ratio_vs_clean >= 5],
  ['页面算出的 ratio 与 L2 证据里的 391.23 一致（<0.5%）', Math.abs(after.ratio_vs_clean / 391.23 - 1) < 0.005],
  ['射程比≈2.30（与证据 40.7574/17.7558 一致）', Math.abs(after.range_ratio_clean_over_drag - 40.7574 / 17.7558) < 0.01],
  ['读数表出现「R(无阻力)/R(阻力…)」行', /无阻力.*\/.*阻力/.test(after.table)],
  ['写回 0 可逆（回到默认射程）', Math.abs(reverted.R - before.R) < 1e-6 && reverted.friction_air === 0],
  ['拖滑块这条路也生效（f=0.02 更短）', uiDriven.f === 0.02 && uiDriven.R < after.R],
  ['滑块数从 3 增到 4（v0/h0/θ/阻力）', after.slider_count === 4],
  ['全程零外部请求', net.length === 0],
]
console.log(JSON.stringify({ before, after, reverted, uiDriven, external: net.length }, null, 2))
let ok = 0
for (const [name, pass] of checks) { console.log((pass ? '  PASS ' : '  FAIL ') + name); ok += pass ? 1 : 0 }
console.log(`\n${ok}/${checks.length} pass`)
process.exit(ok === checks.length ? 0 : 1)
