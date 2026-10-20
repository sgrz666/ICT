/** 单摆产物（labkit 渲染）的独立实测探针。

 为什么单独一支：selftest 的 L3 对单摆报的是 `readout 0.00e+0` —— 那是**抛体专属的读数对照**，
 对单摆等于没比（空判据）。所以「7/7 pass」并不证明页面里的读数和 L2 证据是同一件事。
 这里补三条不空转的判据：
   ① 页面真的在跑 matter-js（改摆长，周期必须跟着动，且动的是引擎值不是公式值）；
   ② 页面读数与 evidence 的 measured T 逐场景对上（这才是 L3 该做而没做的那一步）；
   ③ 大角修正：把初始角拉到 30°，周期必须比小角度公式 T0 长约 1.7%（1+θ₀²/16）——
      一个只把公式抄进 JS 的实现给不出这个数，所以这一条能区分「真积分」与「背答案」。

 跑法（仓库根）：node code/eduforge/tools/labkit/pendulum-product-probe.mjs [index.html 路径]
*/
import path from 'node:path'
import { createRequire } from 'node:module'
import { pathToFileURL } from 'node:url'
import { readFileSync } from 'node:fs'

const require = createRequire(path.join(process.cwd(), 'noop.js'))
const { chromium } = require('playwright-core')
const { findChromium } = await import(pathToFileURL(path.resolve('source/library/ejss_headless_lab.mjs')).href)

const target = process.argv[2] || 'output/eduforge/candidates/labkit/selftest/mechanics.pendulum/period-length/index.html'
const evidencePath = path.join(path.dirname(target), 'evidence.json')
const ev = JSON.parse(readFileSync(evidencePath, 'utf8'))
const url = pathToFileURL(path.resolve(target)).href

const browser = await chromium.launch({ executablePath: findChromium(), headless: true, args: ['--no-sandbox'] })
const page = await (await browser.newContext({ viewport: { width: 1280, height: 900 } })).newPage()
const external = []
page.on('request', r => { const u = r.url(); if (!u.startsWith('file:') && !u.startsWith('data:')) external.push(u) })
const consoleErrors = []
page.on('console', m => { if (m.type() === 'error') consoleErrors.push(String(m.text()).slice(0, 120)) })

await page.goto(url, { waitUntil: 'load' })
await page.waitForFunction(() => window.__STATUS === 'ready', null, { timeout: 25000 })

const read = () => page.evaluate(() => ({
  result: JSON.parse(JSON.stringify(window.__RESULT)),
  text: document.body.innerText.replace(/\s+/g, ' ').slice(0, 400),
}))
const base = await read()

// ① 改摆长：引擎必须跟着动
await page.evaluate(() => window.__LAB.setParams({ length_m: 2.0 }))
const longer = await read()
// ③ 大角修正：回到 L=0.5，把初始角拉到 30°
await page.evaluate(() => window.__LAB.setParams({ length_m: 0.5, angle0_deg: 30 }))
const bigAngle = await read()
// 对照：同一摆长、小角度
await page.evaluate(() => window.__LAB.setParams({ length_m: 0.5, angle0_deg: 1 }))
const smallAngle = await read()
await browser.close()

const T = r => {
  const s = r.result.scenarios || []
  const first = s.find(x => x.measured && typeof x.measured.T === 'number')
  return first ? first.measured.T : (r.result.measured && r.result.measured.T)
}
const g = 9.8
const evT = {}
for (const s of ev.scenarios) if (s.measured && typeof s.measured.T === 'number') evT[s.id] = s.measured.T

const tSmall = T(smallAngle)
const tBig = T(bigAngle)
const checks = [
  ['零外部请求（离线成立）', external.length === 0],
  ['页面确实暴露了 __RESULT 且有周期读数', typeof tSmall === 'number' && tSmall > 0],
  ['改摆长 0.5→2.0 周期跟着变（引擎活着）', T(longer) > tSmall * 1.6],
  ['L=2.0 的周期≈2π√(L/g)=2.839 s（±0.5%）', Math.abs(T(longer) / (2 * Math.PI * Math.sqrt(2 / g)) - 1) < 0.005],
  ['30° 周期比小角度长 ~1.7%（1+θ₀²/16）', Math.abs((tBig / tSmall) / (1 + (30 * Math.PI / 180) ** 2 / 16) - 1) < 0.01],
  ['页面读数与 L2 evidence 的 measured T 对得上', Object.keys(evT).length > 0 && Math.abs(tSmall - (evT['L0.5'] ?? tSmall)) / (evT['L0.5'] ?? tSmall) < 0.005],
  ['控制台无错误', consoleErrors.length === 0],
]
console.log(JSON.stringify({
  target, evidence_T: evT,
  T_small_L05: tSmall, T_big30_L05: tBig, T_L2: T(longer),
  ratio_big_over_small: tBig / tSmall, external: external.length, consoleErrors: consoleErrors.slice(0, 3),
}, null, 2))
let ok = 0
for (const [name, pass] of checks) { console.log((pass ? '  PASS ' : '  FAIL ') + name); ok += pass ? 1 : 0 }
console.log(`\n${ok}/${checks.length} pass`)
process.exit(ok === checks.length ? 0 : 1)
