/** L2：单摆物理对账（matter-js 步进 vs 小角度/椭圆积分解析解）。 */
import { mkdirSync, writeFileSync } from 'node:fs'
import { createRequire } from 'node:module'
import { dirname, join } from 'node:path'
import { checkDesign } from './check.mjs'
import { createPendulumCore } from './core.mjs'
import { canonicalize, designHash } from '../lib/hash.mjs'
import { loadTemplate } from '../lib/template.mjs'

function near(metric, measured, analytic, tol) {
  const rel = analytic === 0 ? (measured === 0 ? 0 : Infinity) : Math.abs((measured - analytic) / analytic) * 100
  return {
    metric,
    measured: Number(measured.toFixed(6)),
    analytic: Number(analytic.toFixed(6)),
    rel_error_pct: Number.isFinite(rel) ? Number(rel.toFixed(4)) : null,
    tolerance_pct: tol,
    verdict: rel <= tol ? 'pass' : 'fail',
  }
}

export function simulateDesign({ repoRoot, design, outPath }) {
  const l1 = checkDesign({ repoRoot, design })
  if (!l1.ok) return { ...l1, stage: 'L1' }
  const template = loadTemplate(repoRoot, design.template_id ?? 'mechanics.pendulum')
  const recipe = template.recipes.find(r => r.id === design.recipe_id)

  const require = createRequire(join(repoRoot, 'source', 'components', 'package.json'))
  const Matter = require('matter-js')
  const core = createPendulumCore(Matter, {
    gravity: template.engine.gravity,
    gravityScale: template.engine.gravity_scale,
    dtS: template.engine.dt_s,
    radius: template.engine.radius,
  })
  const cal = core.calibrate()
  const aEff = cal.a_measured

  const scenarios = []
  for (const [i, s] of l1.predictions.scenarios.entries()) {
    const { length_m: lengthM, angle0_deg: angle0Deg } = s.params
    const run = core.swing({ lengthM, angle0Deg, damping: 0 })
    const measured = { T: run.period }
    const analytic = s.analytic
    const checks = [near('T', measured.T, analytic.Texact, recipe.tolerances_pct.T ?? 1)]
    scenarios.push({
      id: s.id,
      params: s.params,
      measured: { T: Number(run.period.toFixed(6)), max_stretch_m: Number(run.maxStretch.toExponential(2)) },
      analytic: {
        T0: Number(analytic.T0.toFixed(6)),
        Texact: Number(analytic.Texact.toFixed(6)),
        correction_pct: Number(analytic.correction_pct.toFixed(3)),
      },
      checks,
      verdict: checks.every(c => c.verdict === 'pass') ? 'pass' : 'fail',
    })
  }

  if (recipe.id === 'period-length' && scenarios.length === 3) {
    const ratio = scenarios[2].measured.T / scenarios[0].measured.T
    const check = near('ratio_T(L2)/T(L0.5)', ratio, 2, recipe.tolerances_pct.ratio ?? 1)
    scenarios.push({
      id: 'ratio',
      params: { from: 'L0.5', to: 'L2' },
      measured: { ratio: Number(ratio.toFixed(6)) },
      analytic: { ratio: 2 },
      checks: [check],
      verdict: check.verdict,
    })
  }

  const verdict = scenarios.every(s => s.verdict === 'pass') ? 'pass' : 'fail'
  const evidence = {
    schema: 'eduforge.labkit.pendulum.evidence/v1',
    template_id: template.template_id,
    recipe_id: recipe.id,
    design_hash: designHash(l1.normalized),
    engine: {
      id: template.engine.id,
      version: Matter.version,
      dt_s: template.engine.dt_s,
      gravity: template.engine.gravity,
      gravity_scale: template.engine.gravity_scale,
      calibrated_acceleration: Number(aEff.toFixed(6)),
    },
    scenarios,
    verdict,
    generated_at: new Date().toISOString(),
  }

  mkdirSync(dirname(outPath), { recursive: true })
  writeFileSync(outPath, `${JSON.stringify(canonicalize(evidence), null, 2)}\n`, 'utf8')
  return {
    ok: verdict === 'pass',
    stage: 'L2',
    verdict,
    evidence_path: outPath,
    design_hash: evidence.design_hash,
    engine: evidence.engine,
    scenarios,
    hints: verdict === 'pass' ? [] : ['逐项看 scenarios[].checks 的 rel_error_pct；先用默认扫描点，别改配方。'],
  }
}
