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
const prov = await page.evaluate(() => ({
  vendor: window.__LAB_DATA__.engine.vendor_sha256,
  inlined: window.__LAB_DATA__.engine.inlined_sha256,
}))
// 对照叠加：勾上之后，「45° 射程最大」这句话必须能被页面自己的引擎输出检验
const cmpOn = await page.evaluate(() => {
  // 上一段为了验「拖滑块这条路」把阻力留在了 0.02；这里必须先归零，
  // 否则「45° 最大」当然不成立——那不是页面的错，是探针自己带着脏状态去判。
  window.__LAB.setParams({ friction_air: 0 })
  const cb = [...document.querySelectorAll('#controls input[type=checkbox]')].pop()
  if (!cb) return { present: false }
  cb.checked = true
  cb.dispatchEvent(new Event('change', { bubbles: true }))
  const sc = (window.__RESULT.scenarios || []).map(x => ({ id: x.id, R: x.measured.R }))
  // 同一批对照再跑一次带阻力的：有阻力时低角度飞得更远，45° 不再最大
  window.__LAB.setParams({ friction_air: 0.02 })
  const dragged = (window.__RESULT.scenarios || []).map(x => ({ id: x.id, R: x.measured.R }))
  window.__LAB.setParams({ friction_air: 0 })
  return {
    present: true,
    scenarios: sc,
    dragged,
    legend: [...document.querySelectorAll('#legend .item')].map(x => x.textContent.trim()),
    task: document.getElementById('task').textContent,
    buttons: [...document.querySelectorAll('button')].map(x => x.textContent.trim()),
  }
})
await browser.close()

// 溯源防回归：产物内联的引擎字节必须等于 vendor 那份，且 DATA 里记的两个 sha 要能自证。
// 上一版构建器把 MIT 横幅里的 URL 也抹了，导致「同一份引擎两个哈希」，排查时先被骗一次。
const fsMod = await import('node:fs')
const vendorBytes = fsMod.readFileSync(path.resolve('code/eduforge/tools/labkit/vendor/matter.min.js'))
const { createHash } = await import('node:crypto')
const sha = b => createHash('sha256').update(b).digest('hex')
const rawHtml = fsMod.readFileSync(path.resolve(target))
const blocks = [...rawHtml.toString('utf8').matchAll(/<script[^>]*>([\s\S]*?)<\/script>/g)].map(m => m[1])
const matterBlock = blocks.reduce((a, b) => (b.length > (a ? a.length : 0) && b.length > 50000 ? b : a), null)
const checks = [
  ['DATA.engine.vendor_sha256 == vendor 实际字节 sha', prov.vendor === sha(vendorBytes)],
  ['DATA.engine.inlined_sha256 == 产物里那段引擎的 sha', prov.inlined === sha(Buffer.from(matterBlock || '', 'utf8'))],
  ['内联引擎与 vendor 逐字节相同（横幅 URL 未被抹）', sha(vendorBytes) === prov.inlined],
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
  ['有「叠加 30°/60° 对照」这个开关', cmpOn.present === true],
  ['勾上后场景数到 3（45° + 两个对照）', (cmpOn.scenarios || []).length === 3],
  ['引擎输出真能证「45° 最大」：R(30°) 与 R(60°) 都小于 R(45°)', (() => {
    const m = Object.fromEntries((cmpOn.scenarios || []).map(x => [x.id, x.R]))
    return m.main > m.cmp30 && m.main > m.cmp60
  })()],
  ['互补角等射程（|R30−R60|/R45 < 0.5%）', (() => {
    const m = Object.fromEntries((cmpOn.scenarios || []).map(x => [x.id, x.R]))
    return m.main && Math.abs(m.cmp30 - m.cmp60) / m.main < 0.005
  })()],
  ['图例随之变成 3 条引擎曲线', (cmpOn.legend || []).filter(x => x.includes('引擎')).length >= 3],
  // 文案与可得控件一致：步骤里写「点击X」，页面上就必须真有叫 X 的按钮
  ['步骤文案不承诺不存在的按钮', (() => {
    const t = cmpOn.task || ''
    const verbs = [...t.matchAll(/点击([一-龥A-Za-z]{1,6})/g)].map(m => m[1])
    return verbs.length === 0 || verbs.every(v => (cmpOn.buttons || []).some(b => b.includes(v) || v.includes(b)))
  })()],
  ['步骤文案提到对照/其他角度时，页面确实有对照', !/其他角度|对照/.test(cmpOn.task || '') || (cmpOn.scenarios || []).length >= 3],
  ['带阻力时 45° 不再最大（R30 > R45），这条结论自己会翻', (() => {
    const m = Object.fromEntries((cmpOn.dragged || []).map(x => [x.id, x.R]))
    return m.cmp30 > m.main
  })()],
]
console.log(JSON.stringify({ before, after, reverted, uiDriven, external: net.length }, null, 2))
let ok = 0
for (const [name, pass] of checks) { console.log((pass ? '  PASS ' : '  FAIL ') + name); ok += pass ? 1 : 0 }
console.log(`\n${ok}/${checks.length} pass`)
process.exit(ok === checks.length ? 0 : 1)
