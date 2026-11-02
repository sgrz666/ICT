/** 直流电路单文件 HTML 渲染器：模板 + 数据 + 内联 MNA 内核（无外部引擎）。 */
import { mkdirSync, readFileSync, writeFileSync } from 'node:fs'
import { dirname, join } from 'node:path'
import { checkDesign } from './check.mjs'
import { assertUnder } from '../lib/fs-safe.mjs'
import { writeArtifactManifest } from '../lib/artifact.mjs'
import { canonicalJson, designHash, sha256Hex } from '../lib/hash.mjs'
import { loadTemplate } from '../lib/template.mjs'

function escapeHtml(text) {
  return String(text).replace(/&/g, '&amp;').replace(/</g, '&lt;').replace(/>/g, '&gt;').replace(/"/g, '&quot;')
}
function jsStringSafe(json) { return json.replace(/</g, '\\u003c') }

export function renderSingleFile({ repoRoot, design, evidence, outPath, outRoot }) {
  const l1 = checkDesign({ repoRoot, design })
  if (!l1.ok) return { ...l1, stage: 'L1' }

  const template = loadTemplate(repoRoot, design.template_id ?? 'circuits.ohms_law')
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
  const coreSource = readFileSync(join(repoRoot, 'code', 'eduforge', 'tools', 'labkit', 'circuit', 'core.mjs'), 'utf8')
    .replace(/^export\s+/gm, '')

  const initial = evidence?.scenarios?.[0]?.params ?? recipe.scenarios[0].params
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
      metric_keys: recipe.metric_keys,
      tolerances_pct: recipe.tolerances_pct,
    },
    decision: template.decision,
    engine: template.engine,
    render: template.render,
    acceptance: template.acceptance,
    initial,
    evidence: evidence
      ? {
          verdict: evidence.verdict,
          cross_check: evidence.cross_check,
          scenarios: (evidence.scenarios ?? []).map(s => ({ id: s.id, params: s.params, measured: s.measured, analytic: s.analytic })),
        }
      : null,
  }

  const html = htmlTemplate
    .replace('__TITLE__', escapeHtml(`${template.title} · ${recipe.title}`))
    .replace('__STYLE__', () => style)
    .replace('__DATA__', () => jsStringSafe(canonicalJson(data)))
    .replace('__CORE_JS__', () => coreSource)
    .replace('__RUNTIME_JS__', () => runtime)

  mkdirSync(dirname(safeOut), { recursive: true })
  writeFileSync(safeOut, html, 'utf8')
  return {
    ok: true,
    stage: 'RENDER',
    html_path: safeOut,
    artifact_manifest_path: writeArtifactManifest({ htmlPath: safeOut, html, design: l1.normalized, evidence }),
    sha256: sha256Hex(html),
    bytes: Buffer.byteLength(html, 'utf8'),
    design_hash: hash,
    recipe_id: recipe.id,
  }
}
