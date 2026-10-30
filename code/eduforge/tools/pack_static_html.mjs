#!/usr/bin/env node
/**
 * 把已下载的物理实验页打包成「每实验一个静态 HTML」。
 *
 * 当前适配 PhET published 的 `*_all.html`（本身已是单文件）：
 *   1. 删掉 Cloudflare / canonical 等外链标签；
 *   2. 注入 CSP：connect-src 'none'，外部 script/img 全锁死；
 *   3. 用真 Chromium 以 file:// 打开，确认 SVG/canvas 真的渲染、页面无未捕获错误；
 *   4. 生成 manifest.json 与 index.html（实验 → 文件的索引）。
 *
 * 用法：
 *   node code/eduforge/tools/pack_static_html.mjs
 *   node code/eduforge/tools/pack_static_html.mjs --only ohms-law
 *   node code/eduforge/tools/pack_static_html.mjs --no-verify
 */
import { createHash } from 'node:crypto'
import { createRequire } from 'node:module'
import { existsSync, mkdirSync, readFileSync, writeFileSync } from 'node:fs'
import { dirname, join, resolve } from 'node:path'
import { fileURLToPath, pathToFileURL } from 'node:url'

const HERE = dirname(fileURLToPath(import.meta.url))
const REPO_ROOT = resolve(HERE, '../../..')
const DEFAULT_MANIFEST = join(REPO_ROOT, 'source', 'upstream', 'phet-published.json')
const DEFAULT_OUT = join(REPO_ROOT, 'output', 'eduforge', 'candidates', 'static-html', 'phet')

const CSP = [
  "default-src 'self' data: blob:",
  "script-src 'self' 'unsafe-inline' 'unsafe-eval' blob:",
  "style-src 'self' 'unsafe-inline'",
  "img-src 'self' data: blob:",
  "connect-src 'none'",
  "font-src 'self' data:",
  "media-src 'self' data: blob:",
  "worker-src 'self' blob:",
].join('; ')

function arg(name, fallback = undefined) {
  const i = process.argv.indexOf(`--${name}`)
  if (i < 0) return fallback
  const v = process.argv[i + 1]
  return v && !v.startsWith('--') ? v : true
}

function sha256(text) { return createHash('sha256').update(text).digest('hex') }
function escAttr(s) {
  return String(s).replace(/&/g, '&amp;').replace(/"/g, '&quot;').replace(/</g, '&lt;').replace(/>/g, '&gt;')
}
function decodeEntities(s) {
  return s
    .replace(/&#x([0-9a-f]+);/gi, (_, h) => String.fromCodePoint(parseInt(h, 16)))
    .replace(/&#(\d+);/g, (_, d) => String.fromCodePoint(Number(d)))
    .replace(/&amp;/g, '&').replace(/&quot;/g, '"').replace(/&#39;/g, "'")
    .replace(/&lt;/g, '<').replace(/&gt;/g, '>')
}
function cleanTitle(s) {
  return decodeEntities(s).replace(/[\u202A-\u202E\u2066-\u2069]/g, '').trim()
}

/** PhET `_all.html` 的离线清洗：去外链、注入 CSP、写入来源元信息。 */
export function cleanPhetHtml(html, sourceRel, sourceSha) {
  let out = html
  // Cloudflare beacon（唯一一个显式外链 script；GTM/yotta 在 bundle 内部，由 CSP 拦）
  out = out.replace(/<script[^>]+src="https:\/\/static\.cloudflareinsights\.com\/[^"]*"[^>]*>\s*<\/script>/gi, '')
  out = out.replace(/<link[^>]+rel="canonical"[^>]*>/gi, '')
  if (!/http-equiv="Content-Security-Policy"/i.test(out)) {
    out = out.replace(/<head[^>]*>/i, m => `${m}\n<meta http-equiv="Content-Security-Policy" content="${escAttr(CSP)}">`)
  }
  out = out.replace(
    /<head[^>]*>/i,
    m => `${m}\n<meta name="eduforge:source" content="${escAttr(sourceRel)}">\n<meta name="eduforge:source-sha256" content="${sourceSha}">`,
  )
  return out
}

async function verifyOne(browser, htmlPath) {
  const context = await browser.newContext({ viewport: { width: 1280, height: 900 }, offline: true })
  const page = await context.newPage()
  const requests = []
  const responses = []
  const consoleErrors = []
  const pageErrors = []
  const isLocal = u => u.startsWith('file:') || u.startsWith('data:') || u.startsWith('blob:')

  page.on('request', r => { if (!isLocal(r.url())) requests.push(r.url()) })
  page.on('response', r => { if (!isLocal(r.url())) responses.push(r.url()) })
  page.on('console', m => { if (m.type() === 'error') consoleErrors.push(m.text()) })
  page.on('pageerror', e => pageErrors.push(e.message))
  await page.route('**/*', route => (isLocal(route.request().url()) ? route.continue() : route.abort()))

  try {
    await page.goto(pathToFileURL(htmlPath).href, { waitUntil: 'load', timeout: 30_000 })
    await page.waitForFunction(
      () => document.querySelectorAll('svg').length > 0 || document.querySelectorAll('canvas').length > 0,
      { timeout: 15_000 },
    ).catch(() => {})
    await page.waitForTimeout(2500)
    const info = await page.evaluate(() => ({
      title: document.title,
      svgs: document.querySelectorAll('svg').length,
      canvases: document.querySelectorAll('canvas').length,
      simText: (document.querySelector('#sim')?.innerText || document.body.innerText || '').trim().slice(0, 80),
    }))
    const cspViolations = consoleErrors.filter(e => /Content Security Policy/i.test(e))
    const simErrors = consoleErrors.filter(e => !/Content Security Policy/i.test(e))
    return {
      ok: (info.svgs > 0 || info.canvases > 0) && pageErrors.length === 0 && simErrors.length === 0,
      ...info,
      network_requests_attempted: requests.length,
      network_responses: responses.length,
      csp_violations: cspViolations.length,
      sim_console_errors: simErrors,
      page_errors: pageErrors,
    }
  } finally {
    await context.close()
  }
}

function coversExperiment(mapped, title) {
  const parts = String(mapped || '').split('/').map(s => s.trim()).filter(Boolean)
  return parts.find(p => p.includes(title) || title.includes(p.replace(/（.*?）/g, '').trim())) || null
}

function experimentTable(entries, experiments) {
  if (!experiments.length) return ''
  const rows = experiments.map(ex => {
    const hit = entries.find(e => coversExperiment(e.mapped_experiments, ex.title))
    const link = hit
      ? `<a href="./${escAttr(hit.output_file)}">${escAttr(hit.sim)}.html</a>`
      : '<span class="muted">未覆盖（多文件资源，待打包）</span>'
    return `<tr><td>${escAttr(ex.title)}</td><td>${escAttr(ex.domain || '')}</td><td>${link}</td></tr>`
  }).join('\n')
  return `
  <h2 class="section-title">按实验索引（${experiments.length} 个登记实验）</h2>
  <table class="index-table">
    <thead><tr><th>实验</th><th>学科</th><th>静态 HTML</th></tr></thead>
    <tbody>${rows}</tbody>
  </table>`
}

function indexHtml(entries, experiments = []) {
  const cards = entries.map(e => `
    <a class="card" href="./${escAttr(e.output_file)}">
      <div class="tag">${escAttr(e.version ? 'v' + e.version : 'PhET')}</div>
      <h2>${escAttr(e.title)}</h2>
      <p class="sim">${escAttr(e.sim)}</p>
      <p class="maps">${escAttr(e.mapped_experiments)}</p>
      <div class="meta">
        <span>${(e.bytes / 1024 / 1024).toFixed(1)} MB</span>
        <span class="${e.checks.ok ? 'ok' : 'bad'}">${e.checks.ok ? '离线实测通过' : '离线实测失败'}</span>
        <span>${e.checks.svgs} SVG / ${e.checks.canvases} canvas</span>
      </div>
    </a>`).join('\n')

  return `<!doctype html>
<html lang="zh-CN">
<head>
<meta charset="utf-8">
<title>物理实验静态 HTML 包 · PhET</title>
<meta name="viewport" content="width=device-width, initial-scale=1">
<style>
  :root { --bg:#f6f7f4; --panel:#fff; --ink:#1c2321; --muted:#5b6663; --line:#d9ddd7; --accent:#0f766e; }
  * { box-sizing:border-box; }
  body { margin:0; background:var(--bg); color:var(--ink); font-family:system-ui,-apple-system,"Segoe UI","Microsoft YaHei",sans-serif; }
  .page { max-width:1200px; margin:0 auto; padding:28px 22px 40px; }
  header { border-bottom:1px solid var(--line); padding-bottom:14px; margin-bottom:20px; }
  h1 { font-size:24px; margin:0 0 6px; }
  .sub { color:var(--muted); font-size:14px; line-height:1.6; }
  .grid { display:grid; grid-template-columns:repeat(auto-fill,minmax(280px,1fr)); gap:14px; }
  .card { display:block; background:var(--panel); border:1px solid var(--line); border-radius:14px; padding:16px; text-decoration:none; color:inherit; transition:border-color .15s, transform .15s; }
  .card:hover { border-color:#9ec9c0; transform:translateY(-1px); }
  .tag { display:inline-block; font-size:11px; color:var(--accent); background:#e3f1ee; border-radius:999px; padding:2px 8px; margin-bottom:8px; }
  h2 { font-size:16px; margin:0 0 4px; line-height:1.35; }
  .sim { font-size:12px; color:var(--muted); margin:0 0 8px; font-family:ui-monospace,Consolas,monospace; }
  .maps { font-size:13px; color:#33403c; margin:0 0 12px; line-height:1.5; min-height:38px; }
  .meta { display:flex; gap:10px; flex-wrap:wrap; font-size:11.5px; color:var(--muted); border-top:1px solid var(--line); padding-top:9px; }
  .ok { color:#157347; } .bad { color:#b45309; }
  .muted { color:#8a9490; }
  .section-title { font-size:18px; margin:30px 0 10px; }
  .index-table { width:100%; border-collapse:collapse; background:var(--panel); border:1px solid var(--line); border-radius:12px; overflow:hidden; font-size:13px; }
  .index-table th, .index-table td { text-align:left; padding:9px 12px; border-bottom:1px solid var(--line); }
  .index-table th { background:#f0f3ef; color:var(--muted); font-weight:600; font-size:12px; }
  .index-table tr:last-child td { border-bottom:0; }
  .index-table a { color:var(--accent); text-decoration:none; }
  .index-table a:hover { text-decoration:underline; }
  footer { margin-top:22px; font-size:12px; color:var(--muted); border-top:1px solid var(--line); padding-top:12px; }
</style>
</head>
<body>
<div class="page">
  <header>
    <h1>物理实验静态 HTML 包 · PhET</h1>
    <div class="sub">每个实验一个单文件 HTML；已去外链、加 CSP 锁网、逐个用真 Chromium 以 file:// 实测。共 ${entries.length} 个文件。</div>
  </header>
  <div class="grid">${cards}</div>
  ${experimentTable(entries, experiments)}
  <footer>来源：PhET Interactive Simulations, University of Colorado Boulder（CC BY-NC 4.0）。打包脚本：code/eduforge/tools/pack_static_html.mjs。</footer>
</div>
</body>
</html>
`
}

async function main() {
  const manifestPath = arg('manifest', DEFAULT_MANIFEST)
  const outDir = arg('out', DEFAULT_OUT)
  const experimentsPath = arg('experiments', join(REPO_ROOT, 'source', 'library', 'experiments.json'))
  const only = arg('only')
  const verify = !arg('no-verify', false)

  const manifest = JSON.parse(readFileSync(manifestPath, 'utf8'))
  const experiments = existsSync(experimentsPath)
    ? (JSON.parse(readFileSync(experimentsPath, 'utf8')).experiments ?? [])
    : []
  let sims = manifest.sims
  if (only) sims = sims.filter(s => s.sim === only)
  if (!sims.length) throw new Error(`没有匹配的 sim：${only || '(all)'}`)

  mkdirSync(outDir, { recursive: true })
  let chromium = null
  if (verify) {
    const require = createRequire(join(REPO_ROOT, 'code', 'eduforge', 'services', 'engine-host', 'package.json'))
    chromium = require('playwright').chromium
  }
  const browser = chromium ? await chromium.launch({ headless: true }) : null
  const entries = []

  try {
    for (const sim of sims) {
      const src = join(REPO_ROOT, sim.file)
      if (!existsSync(src)) {
        console.log(`[SKIP] ${sim.sim}: 源文件不存在 ${sim.file}`)
        continue
      }
      const raw = readFileSync(src, 'utf8')
      const sourceSha = sha256(raw)
      const cleaned = cleanPhetHtml(raw, sim.file, sourceSha)
      const outputFile = `${sim.sim}.html`
      const outPath = join(outDir, outputFile)
      writeFileSync(outPath, cleaned, 'utf8')

      const titleMatch = cleaned.match(/<title[^>]*>([\s\S]*?)<\/title>/i)
      const title = cleanTitle(titleMatch ? titleMatch[1] : sim.sim)
      const mapped = sim.maps_to_experiments || ''
      const entry = {
        sim: sim.sim,
        title,
        version: sim.version || '',
        mapped_experiments: mapped,
        source_file: sim.file,
        source_sha256: sourceSha,
        output_file: outputFile,
        bytes: Buffer.byteLength(cleaned, 'utf8'),
        output_sha256: sha256(cleaned),
        checks: { ok: null },
      }
      if (browser) {
        entry.checks = await verifyOne(browser, outPath)
        entry.checks.ok = entry.checks.ok === true
      }
      entries.push(entry)
      const c = entry.checks
      console.log(
        `[${browser ? (c.ok ? 'PASS' : 'FAIL') : 'PACK'}] ${sim.sim.padEnd(28)} ` +
        `${(entry.bytes / 1024 / 1024).toFixed(1)} MB · ` +
        `${c.svgs ?? '-'} SVG / ${c.canvases ?? '-'} canvas · ` +
        `net ${c.network_responses ?? '-'} · csp ${c.csp_violations ?? '-'} · simErr ${c.sim_console_errors?.length ?? '-'}`,
      )
    }
  } finally {
    if (browser) await browser.close()
  }

  const coverage = experiments.map(ex => {
    const hit = entries.find(e => coversExperiment(e.mapped_experiments, ex.title))
    return {
      experiment_id: ex.id,
      title: ex.title,
      domain: ex.domain,
      covered: Boolean(hit),
      sim: hit ? hit.sim : null,
      output_file: hit ? hit.output_file : null,
    }
  })
  const result = {
    schema: 'eduforge.static_html.phet/v1',
    source_manifest: manifestPath.replace(REPO_ROOT + '\\', '').replace(/\\/g, '/'),
    count: entries.length,
    experiments_total: experiments.length,
    experiments_covered: coverage.filter(c => c.covered).length,
    experiments_uncovered: coverage.filter(c => !c.covered).map(c => c.experiment_id),
    coverage,
    sims: entries,
  }
  writeFileSync(join(outDir, 'manifest.json'), `${JSON.stringify(result, null, 2)}\n`, 'utf8')
  writeFileSync(join(outDir, 'index.html'), indexHtml(entries, experiments), 'utf8')

  const passed = entries.filter(e => e.checks.ok === true).length
  console.log(`\n${passed}/${entries.length} 离线实测通过；登记实验覆盖 ${result.experiments_covered}/${result.experiments_total}；输出：${outDir}`)
  if (browser && passed !== entries.length) process.exitCode = 1
}

if (process.argv[1] && pathToFileURL(process.argv[1]).href === import.meta.url) {
  main().catch(e => { console.error(e); process.exitCode = 1 })
}
