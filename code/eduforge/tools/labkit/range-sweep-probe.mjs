/** oblique45 的量程扫描：把页面自己声明的可调范围推满，看它有没有在某个角落开始说谎。
 *
 * 为什么单独扫一遍：L3 只测一个点（默认参数 + 改一次 v₀），L2 只测配方那一个场景。
 * 但页面把 v₀ 5~40、h₀ 0~30、θ 15~75、frictionAir 0~0.03 全交给了学生，
 * 任何一个角落出现 NaN / 不落地的曲线 / 与解析式对不上，都是「实验坏了」而不是「测试没覆盖」。
 *
 * 判据全部来自页面自己的声明：tolerances_pct（1%）、decision 的量程、DATA.acceptance。
 * 跑法：node code/eduforge/tools/labkit/range-sweep-probe.mjs [html 路径]
 */
import path from 'node:path'
import { createRequire } from 'node:module'
import { pathToFileURL } from 'node:url'

const require = createRequire(path.join(process.cwd(), 'noop.js'))
const { chromium } = require('playwright-core')
const { findChromium } = await import(pathToFileURL(path.resolve('source/library/ejss_headless_lab.mjs')).href)

const target = process.argv[2] || 'output/eduforge/candidates/labkit/oblique45/oblique45-range-max.html'
const browser = await chromium.launch({ executablePath: findChromium(), headless: true, args: ['--no-sandbox'] })
const page = await (await browser.newContext({ viewport: { width: 1280, height: 900 } })).newPage()
const consoleErrors = []
page.on('console', m => { if (m.type() === 'error') consoleErrors.push(String(m.text()).slice(0, 120)) })
page.on('pageerror', e => consoleErrors.push('pageerror ' + String(e).slice(0, 120)))
await page.goto(pathToFileURL(path.resolve(target)).href, { waitUntil: 'load' })
await page.waitForFunction(() => window.__STATUS === 'ready', null, { timeout: 25000 })

const meta = await page.evaluate(() => ({
  v0: window.__LAB_DATA__.decision.v0_range,
  h0: window.__LAB_DATA__.decision.h0_range,
  ang: window.__LAB_DATA__.decision.angle_range_oblique,
  tol: window.__LAB_DATA__.recipe.tolerances_pct,
  maxApex: window.__LAB_DATA__.decision.max_apex_m,
  maxRange: window.__LAB_DATA__.decision.max_range_m,
  maxT: window.__LAB_DATA__.decision.max_flight_time_s,
}))
const grid = {
  v0: [meta.v0[0], 12, 20, 30, meta.v0[1]],
  h0: [meta.h0[0], 8, meta.h0[1]],
  ang: [meta.ang[0], 30, 45, 60, meta.ang[1]],
  drag: [0, 0.01, meta.ang && 0.03],
}
const rows = []
for (const v0 of grid.v0) for (const h0 of grid.h0) for (const ang of grid.ang) {
  const r = await page.evaluate(([v0, h0, ang]) => {
    window.__LAB.setParams({ v0, h0, angle_deg: ang, friction_air: 0 })
    return { res: window.__RESULT, notice: /超出模板声明的可视范围/.test(document.querySelector('table.readout').innerText) }
  }, [v0, h0, ang])
  const s = r.res.scenarios[0]
  rows.push({ v0, h0, ang, drag: 0, T: s.measured.T, R: s.measured.R, H: s.measured.H, aT: s.analytic.T, aR: s.analytic.R, aH: s.analytic.H, noticed: r.notice })
}
for (const d of grid.drag) for (const ang of [30, 45, 60]) {
  const r = await page.evaluate(([v0, h0, ang, drag]) => window.__LAB.setParams({ v0, h0, angle_deg: ang, friction_air: drag }), [20, 0, ang, d])
  const s = r.scenarios[0]
  rows.push({ v0: 20, h0: 0, ang, drag: d, T: s.measured.T, R: s.measured.R, H: s.measured.H, aT: s.analytic.T, aR: s.analytic.R, aH: s.analytic.H })
}
// 画布在极端参数下是否还画着东西（取 3 个最"偏"的组合各截一次 canvas）
const shots = []
for (const [v0, h0, ang] of [[meta.v0[1], meta.h0[1], meta.ang[1]], [meta.v0[0], meta.h0[0], meta.ang[0]], [meta.v0[1], meta.h0[0], meta.ang[0]]]) {
  await page.evaluate(([v0, h0, ang]) => window.__LAB.setParams({ v0, h0, angle_deg: ang, friction_air: 0 }), [v0, h0, ang])
  await page.waitForTimeout(400)
  const el = await page.$('canvas')
  const buf = await el.screenshot()
  const nonBlank = new Set([...buf.slice(0, 4000)].map(x => x & 0xf0)).size
  shots.push({ v0, h0, ang, bytes: buf.length, distinct_rough: nonBlank })
}
await browser.close()

// 判据与页面同源：T 的偏差实测恒等于 −dt（一步），R/H 是它按 v·dt 的传播，
// 所以每一项的下限是 max(配方相对容差, 分辨率占比)。这不是放水——放水是改阈值，
// 这里是把"这条判据在什么参数下才有意义"写进判据本身，页面显示的是同一个数。
const DT = 1 / 240
const bad = []
let overCases = 0, overNoticed = 0
for (const x of rows.filter(r => r.drag === 0)) {
  const dev = k => Math.abs(x[k] - x['a' + k]) / Math.abs(x['a' + k] || 1) * 100
  const floors = { T: DT / Math.abs(x.aT || 1) * 100, R: x.v0 * DT / Math.abs(x.aR || 1) * 100, H: x.v0 * DT / Math.abs(x.aH || 1) * 100 }
  for (const k of ['T', 'R', 'H']) {
    if (!Number.isFinite(x[k]) || x[k] <= 0) bad.push(`无有效读数 v0=${x.v0} h0=${x.h0} θ=${x.ang} ${k}=${x[k]}`)
    // 1.05 步：落点用相邻两帧线性插值，允许不足一步的余量
    else if (dev(k) > Math.max(1, floors[k]) * 1.05) bad.push(`偏离解析式 ${dev(k).toFixed(2)}% > 下限 ${Math.max(1, floors[k]).toFixed(2)}% v0=${x.v0} h0=${x.h0} θ=${x.ang} ${k}`)
  }
  // 越过模板声明的可视上限本身不是错，**不吭声才是**：页面必须显式告诉学生已越界、坐标已自动缩放
  const over = (x.H > meta.maxApex) || (x.R > meta.maxRange) || (x.T > meta.maxT)
  if (over) {
    overCases++
    if (x.noticed) overNoticed++
    else bad.push(`越界未提示 v0=${x.v0} h0=${x.h0} θ=${x.ang}（H=${x.H.toFixed(1)} R=${x.R.toFixed(1)} T=${x.T.toFixed(2)}）`)
  }
}
const dragRows = rows.filter(r => r.drag > 0)
const mono = dragRows.filter(r => r.drag === 0.01)
for (let i = 1; i < mono.length; i += 2) {
  const prev = mono[i - 1], cur = mono[i]
  if (cur.ang > prev.ang && cur.R > prev.R + 0.05) bad.push(`阻力下单调性可疑 θ${prev.ang}→θ${cur.ang} R ${prev.R.toFixed(2)}→${cur.R.toFixed(2)}`)
}
console.log(`扫描 ${rows.length} 组参数（无阻力 ${rows.length - dragRows.length} + 带阻力 ${dragRows.length}）`)
console.log('极端参数下画布:', JSON.stringify(shots))
console.log('控制台错误:', consoleErrors.length, consoleErrors.slice(0, 3))
console.log(`越界用例 ${overCases} 个，其中页面给了提示的 ${overNoticed} 个`)
console.log('问题条数:', bad.length)
for (const b of bad.slice(0, 14)) console.log('  ·', b)
process.exit(bad.length === 0 && consoleErrors.length === 0 ? 0 : 1)
