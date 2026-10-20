/**
 * 单文件 HTML 渲染器：模板 + 数据 + 内联引擎，纯字符串拼接。
 *
 * 确定性：不含时间戳、随机数、网络请求；同一 design + evidence 连渲两次 sha256 相同。
 * 页面运行时与 L2 共用 projectile-core.mjs（内联时剥掉 export 关键字）。
 */
import { mkdirSync, readFileSync, writeFileSync } from 'node:fs'
import { dirname, join } from 'node:path'
import { checkDesign } from './check.mjs'
import { assertUnder } from './fs-safe.mjs'
import { canonicalJson, designHash, sha256Hex } from './hash.mjs'
import { loadTemplate } from './template.mjs'

function escapeHtml(text) {
  return String(text)
    .replace(/&/g, '&amp;')
    .replace(/</g, '&lt;')
    .replace(/>/g, '&gt;')
    .replace(/"/g, '&quot;')
}

function jsStringSafe(json) {
  // 防止数据里出现 </script> 截断内联脚本。
  return json.replace(/</g, '\\u003c')
}

/**
 * @param {{repoRoot:string, design:object, evidence?:object, outPath:string, outRoot?:string}} input
 */
export function renderSingleFile({ repoRoot, design, evidence, outPath, outRoot }) {
  const l1 = checkDesign({ repoRoot, design })
  if (!l1.ok) return { ...l1, stage: 'L1' }

  const template = loadTemplate(repoRoot, design.template_id ?? 'mechanics.projectile')
  const recipe = template.recipes.find(r => r.id === l1.recipe_id)
  const hash = designHash(l1.normalized)

  if (evidence && evidence.design_hash && evidence.design_hash !== hash) {
    return {
      ok: false, stage: 'RENDER', code: 'EVIDENCE_STALE',
      detail: 'evidence 的 design_hash 与当前 design 不一致，先重跑 experiment_simulate。',
      hints: ['重新调用 experiment_simulate，再用新的 evidence 渲染。'],
    }
  }

  const root = outRoot ?? join(repoRoot, 'output', 'eduforge', 'candidates', 'labkit')
  const safeOut = assertUnder(root, outPath)

  const renderDir = join(template.dir, 'render')
  const htmlTemplate = readFileSync(join(renderDir, 'template.html'), 'utf8')
  const style = readFileSync(join(renderDir, 'style.css'), 'utf8')
  const runtime = readFileSync(join(renderDir, 'runtime.js'), 'utf8')
  const coreSource = readFileSync(join(repoRoot, 'code', 'eduforge', 'tools', 'labkit', 'lib', 'projectile-core.mjs'), 'utf8')
    .replace(/^export\s+/gm, '')
  const matter = readFileSync(join(repoRoot, 'code', 'eduforge', 'tools', 'labkit', 'vendor', 'matter.min.js'), 'utf8')
    // 保留 MIT 署名，去掉横幅里的 URL：单文件产物里不应出现任何可被误当成外链的字符串。
    .replace(/https?:\/\/\S+/g, '')

  const data = {
    meta: {
      title: template.title,
      template_id: template.template_id,
      recipe_id: recipe.id,
      recipe_title: recipe.title,
      design_hash: hash,
      engine_id: template.engine.id,
      engine_version: template.engine.version,
    },
    design: l1.normalized,
    recipe: {
      id: recipe.id,
      title: recipe.title,
      intent: recipe.intent,
      params_mode: recipe.params_mode,
      scenarios: recipe.scenarios,
      metrics: recipe.metrics,
      tolerances_pct: recipe.tolerances_pct,
      intent_keywords: recipe.intent_keywords,
    },
    decision: template.decision,
    engine: template.engine,
    render: template.render,
    acceptance: template.acceptance,
    evidence: evidence
      ? {
          verdict: evidence.verdict,
          scenarios: (evidence.scenarios ?? []).map(s => ({
            id: s.id,
            measured: s.measured,
            analytic: s.analytic,
          })),
          drag_control: evidence.drag_control,
        }
      : null,
  }

  const html = htmlTemplate
    .replace('__TITLE__', escapeHtml(`${template.title} · ${recipe.title}`))
    .replace('__STYLE__', () => style)
    .replace('__DATA__', () => jsStringSafe(canonicalJson(data)))
    .replace('__MATTER_JS__', () => matter)
    .replace('__CORE_JS__', () => coreSource)
    .replace('__RUNTIME_JS__', () => runtime)

  mkdirSync(dirname(safeOut), { recursive: true })
  writeFileSync(safeOut, html, 'utf8')

  return {
    ok: true,
    stage: 'RENDER',
    html_path: safeOut,
    sha256: sha256Hex(html),
    bytes: Buffer.byteLength(html, 'utf8'),
    design_hash: hash,
    recipe_id: recipe.id,
  }
}
