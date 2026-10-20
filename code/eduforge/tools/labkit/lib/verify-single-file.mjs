/**
 * L3：单文件实测。
 *
 * 用真 Chromium 以 file:// 打开，断网，检查六件事：
 *   1. 零 http(s)/ws 请求
 *   2. canvas 非空
 *   3. 改 v0 后射程确实变化
 *   4. 无 console error / pageerror
 *   5. 页面读数与 L2 evidence 同场景一致
 *   6. 文件不超过 2 MB
 *
 * 这不是「看起来能打开」的冒烟测试：读数对不上、画布空白、偷偷联网，都会判 fail。
 */
import { readFileSync, statSync } from 'node:fs'
import { createRequire } from 'node:module'
import { join } from 'node:path'
import { pathToFileURL } from 'node:url'
import { assertUnder } from './fs-safe.mjs'

const MAX_BYTES = 2 * 1024 * 1024
const READOUT_REL_TOL = 1e-6

function relErr(a, b) {
  const denom = Math.max(Math.abs(b), 1e-9)
  return Math.abs(a - b) / denom
}

/**
 * @param {{repoRoot:string, htmlPath:string, evidencePath:string, outRoot?:string}} input
 */
export async function verifySingleFile({ repoRoot, htmlPath, evidencePath, outRoot }) {
  const root = outRoot ?? join(repoRoot, 'output', 'eduforge', 'candidates', 'labkit')
  let safeHtml
  try {
    safeHtml = assertUnder(root, htmlPath)
  } catch (e) {
    return { ok: false, stage: 'L3', code: 'PATH_ESCAPE', detail: e.message, hints: ['把 HTML 放到 output/eduforge/candidates/labkit 下。'] }
  }
  const evidence = JSON.parse(readFileSync(evidencePath, 'utf8'))
  const bytes = statSync(safeHtml).size

  let chromium
  try {
    const require = createRequire(join(repoRoot, 'code', 'eduforge', 'services', 'engine-host', 'package.json'))
    chromium = require('playwright').chromium
  } catch (e) {
    return {
      ok: false, stage: 'L3', code: 'PW_NOT_AVAILABLE',
      detail: '找不到 Playwright。',
      hints: ['在 code/eduforge/services/engine-host 下执行 pnpm install，并确认已缓存 Chromium。'],
    }
  }

  const network = []
  const consoleErrors = []
  let browser
  try {
    browser = await chromium.launch({ headless: true })
    const context = await browser.newContext({ viewport: { width: 1280, height: 900 }, offline: true })
    const page = await context.newPage()

    page.on('request', req => {
      const url = req.url()
      if (!url.startsWith('file:') && !url.startsWith('data:') && !url.startsWith('blob:')) network.push(url)
    })
    page.on('console', msg => {
      if (msg.type() === 'error') consoleErrors.push(msg.text())
    })
    page.on('pageerror', err => consoleErrors.push(`pageerror: ${err.message}`))
    await page.route('**/*', route => {
      const url = route.request().url()
      if (url.startsWith('file:') || url.startsWith('data:') || url.startsWith('blob:')) return route.continue()
      return route.abort()
    })

    await page.goto(pathToFileURL(safeHtml).href, { waitUntil: 'load', timeout: 30_000 })
    await page.waitForFunction(() => window.__STATUS === 'ready' || window.__STATUS === 'error', { timeout: 15_000 })
    const status = await page.evaluate(() => window.__STATUS)
    if (status !== 'ready') {
      const detail = await page.evaluate(() => (window.__RESULT && window.__RESULT.error) || '页面未就绪')
      return { ok: false, stage: 'L3', code: 'L3_PAGE_ERROR', detail, hints: ['看页面 badge 的错误信息；通常是内联脚本语法或 Matter 未挂到 window。'] }
    }

    const canvas = await page.evaluate(() => {
      const c = document.querySelector('canvas')
      if (!c) return null
      const g = c.getContext('2d')
      const d = g.getImageData(0, 0, c.width, c.height).data
      let nonBg = 0
      let opaque = 0
      const colors = new Set()
      const total = d.length / 4
      for (let i = 0; i < d.length; i += 4) {
        // 全透明像素不算「画了东西」；否则一张从未绘制的 canvas 会被误判为 100% 非背景。
        if (d[i + 3] < 8) continue
        opaque += 1
        const dr = Math.abs(d[i] - 251)
        const dg = Math.abs(d[i + 1] - 252)
        const db = Math.abs(d[i + 2] - 250)
        if (dr + dg + db > 24) nonBg += 1
        colors.add(((d[i] >> 4) << 8) | ((d[i + 1] >> 4) << 4) | (d[i + 2] >> 4))
      }
      return {
        width: c.width,
        height: c.height,
        nonBgRatio: nonBg / total,
        opaqueRatio: opaque / total,
        distinctColors: colors.size,
      }
    })
    if (!canvas) {
      return { ok: false, stage: 'L3', code: 'L3_NO_CANVAS', detail: '页面没有 canvas。', hints: ['检查模板是否被改坏。'] }
    }

    const before = await page.evaluate(() => ({
      v0: window.__RESULT.params.v0,
      R: window.__RESULT.scenarios[0].measured.R,
      result: window.__RESULT,
    }))
    await page.evaluate(() => window.__LAB.setParams({ v0: window.__RESULT.params.v0 * 1.25 }))
    await new Promise(resolve => setTimeout(resolve, 200))
    const after = await page.evaluate(() => ({
      v0: window.__RESULT.params.v0,
      R: window.__RESULT.scenarios[0].measured.R,
    }))
    const rangeChanged = before.R > 0 && Math.abs(after.R - before.R) / before.R > 0.05

    const pageScenarios = before.result.scenarios ?? []
    let maxRel = 0
    let compared = 0
    for (const ev of evidence.scenarios ?? []) {
      if (!ev.params || typeof ev.params.angle_deg !== 'number') continue
      const ps = pageScenarios.find(s => s.id === ev.id)
      if (!ps) continue
      for (const key of ['T', 'R', 'H']) {
        maxRel = Math.max(maxRel, relErr(ps.measured[key], ev.measured[key]))
        compared += 1
      }
    }

    const checks = {
      status,
      network_requests: network.length,
      canvas_nonbg_ratio: Number(canvas.nonBgRatio.toFixed(4)),
      canvas_opaque_ratio: Number(canvas.opaqueRatio.toFixed(4)),
      canvas_distinct_colors: canvas.distinctColors,
      v0_before: before.v0,
      v0_after: after.v0,
      range_before: before.R,
      range_after: after.R,
      range_changed: rangeChanged,
      console_errors: consoleErrors,
      readout_compared_fields: compared,
      readout_max_rel_error: maxRel,
      bytes,
    }

    const failures = []
    if (network.length > 0) failures.push(`L3_NETWORK: ${network.slice(0, 3).join(', ')}`)
    if (canvas.opaqueRatio < 0.5 || canvas.nonBgRatio < 0.02 || canvas.distinctColors < 8) {
      failures.push(
        `L3_BLANK_CANVAS: opaque=${canvas.opaqueRatio.toFixed(3)}, nonBg=${canvas.nonBgRatio.toFixed(4)}, colors=${canvas.distinctColors}`,
      )
    }
    if (!rangeChanged) failures.push(`L3_NO_RESPONSE_TO_INPUT: 改 v0 后射程未变化（${before.R} → ${after.R}）`)
    if (consoleErrors.length > 0) failures.push(`L3_CONSOLE_ERROR: ${consoleErrors.slice(0, 3).join(' | ')}`)
    if (compared === 0) failures.push('L3_READOUT_MISMATCH: 没有可对比的读数')
    else if (maxRel > READOUT_REL_TOL) failures.push(`L3_READOUT_MISMATCH: 最大相对误差 ${maxRel.toExponential(2)} > ${READOUT_REL_TOL}`)
    if (bytes > MAX_BYTES) failures.push(`L3_TOO_LARGE: ${bytes} bytes > ${MAX_BYTES}`)

    return {
      ok: failures.length === 0,
      stage: 'L3',
      verdict: failures.length === 0 ? 'pass' : 'fail',
      html_path: safeHtml,
      checks,
      errors: failures,
      hints: failures.length === 0 ? [] : ['先看 checks 里具体哪一项失败；不要改物理或放宽容差来「修好」它。'],
    }
  } catch (e) {
    const detail = String(e && e.message || e)
    const notReady = /Timeout|waitForFunction|__STATUS/i.test(detail)
    return {
      ok: false, stage: 'L3',
      code: notReady ? 'L3_NOT_READY' : 'L3_RUNNER_ERROR',
      detail,
      hints: notReady
        ? ['页面没有在 15s 内进入 ready；检查 __STATUS 钩子、初始化异常与 canvas 是否存在。']
        : ['确认 Chromium 可启动；若报 Executable doesn\'t exist，在 engine-host 下跑 pnpm exec playwright install chromium。'],
    }
  } finally {
    if (browser) await browser.close().catch(() => {})
  }
}
