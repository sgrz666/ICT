/**
 * L2：物理对账。
 *
 * 观测 = matter-js 按固定步长真实步进；参考 = 与引擎无关的运动学解析式。
 * 解析式用的是 calibrate() 实测出来的 a_eff，不是名义 9.8——否则离散相位差会被
 * 误判成物理错误或反过来把错误放过。
 */
import { mkdirSync, writeFileSync } from 'node:fs'
import { createRequire } from 'node:module'
import { dirname, join } from 'node:path'
import { checkDesign } from './check.mjs'
import { canonicalize, designHash } from './hash.mjs'
import { createProjectileCore } from './projectile-core.mjs'
import { loadTemplate } from './template.mjs'

function near(metric, measured, analytic, tolerancePct) {
  const abs = Math.abs(measured - analytic)
  const rel = analytic === 0 ? (measured === 0 ? 0 : Infinity) : (abs / Math.abs(analytic)) * 100
  return {
    metric,
    measured: Number(measured.toFixed(4)),
    analytic: Number(analytic.toFixed(4)),
    abs_error: Number(abs.toFixed(5)),
    rel_error_pct: Number.isFinite(rel) ? Number(rel.toFixed(3)) : null,
    tolerance_pct: tolerancePct,
    verdict: rel <= tolerancePct ? 'pass' : 'fail',
  }
}

function metricValue(analytic, key) {
  if (key === 'T') return analytic.T
  if (key === 'R') return analytic.R
  if (key === 'H') return analytic.H
  if (key === 'apex_y') return analytic.apex_y
  throw new Error(`UNKNOWN_METRIC: ${key}`)
}

/**
 * @param {{repoRoot:string, design:object, outPath:string}} input
 */
export function simulateDesign({ repoRoot, design, outPath }) {
  const l1 = checkDesign({ repoRoot, design })
  if (!l1.ok) return { ...l1, stage: 'L1' }

  const template = loadTemplate(repoRoot, design.template_id ?? 'mechanics.projectile')
  const recipe = template.recipes.find(r => r.id === design.recipe_id)

  const require = createRequire(join(repoRoot, 'source', 'components', 'package.json'))
  const Matter = require('matter-js')
  const core = createProjectileCore(Matter, {
    gravity: template.engine.gravity,
    gravityScale: template.engine.gravity_scale,
    dtS: template.engine.dt_s,
    radius: template.engine.radius,
  })
  const cal = core.calibrate()
  const aEff = cal.a_measured

  const scenarios = []
  const scenarioDefs = recipe.params_mode === 'pair'
    ? l1.normalized.params.angles_deg.map((angle, idx) => ({
        id: recipe.scenarios[idx]?.id ?? `s${idx + 1}`,
        params: { v0: l1.normalized.params.v0, angle_deg: angle, h0: l1.normalized.params.h0 },
      }))
    : [{ id: recipe.scenarios[0].id, params: { ...l1.normalized.params } }]

  for (const s of scenarioDefs) {
    const { h0, v0, angle_deg: angleDeg } = s.params
    const flight = core.fly({ h0, v0, angleDeg, frictionAir: 0 })
    const analytic = core.analytic({ h0, v0, angleDeg, aEff })
    if (!flight.landed) {
      return {
        ok: false, stage: 'L2', code: 'ENGINE_ERROR',
        detail: `${s.id} 在 60 s 内没有落地，参数可能退化（v0 或角度过小）。`,
        hints: ['提高 v0 或把角度调到 15°..75°。'],
      }
    }
    const measured = {
      T: flight.landed.t,
      R: flight.landed.x,
      H: flight.apex.y,
      apex_y: flight.apex.y,
    }
    const checks = recipe.metrics
      .filter(k => k !== 'ratio_R')
      .map(k => near(k, metricValue(measured, k), metricValue(analytic, k), recipe.tolerances_pct[k] ?? 1))
    scenarios.push({
      id: s.id,
      params: { v0, angle_deg: angleDeg, h0 },
      measured: Object.fromEntries(Object.entries(measured).map(([k, v]) => [k, Number(v.toFixed(9))])),
      analytic: Object.fromEntries(Object.entries(analytic).map(([k, v]) => [k, Number(v.toFixed(9))])),
      checks,
      verdict: checks.every(c => c.verdict === 'pass') ? 'pass' : 'fail',
    })
  }

  if (recipe.params_mode === 'pair') {
    const ratio = scenarios[0].measured.R / scenarios[1].measured.R
    const check = near('ratio_R', ratio, 1, recipe.tolerances_pct.ratio_R ?? 1)
    scenarios.push({
      id: 'ratio',
      params: { v0: l1.normalized.params.v0, h0: l1.normalized.params.h0 },
      measured: { ratio_R: Number(ratio.toFixed(9)) },
      analytic: { ratio_R: 1 },
      checks: [check],
      verdict: check.verdict,
    })
  }

  // 阻力对照组：证明这套容差真的能区分「无阻力理想抛体」与「其实一直在衰减」。
  const controlParams = { v0: 20, angleDeg: 45, h0: 0 }
  const clean = core.fly({ ...controlParams, frictionAir: 0 })
  const draggy = core.fly({ ...controlParams, frictionAir: template.acceptance.drag_control.friction_air })
  const analyticR = core.analytic({ ...controlParams, aEff }).R
  const devClean = Math.abs(clean.landed.x - analyticR) / analyticR
  const devDrag = Math.abs(draggy.landed.x - analyticR) / analyticR
  const dragControl = {
    params: { v0: 20, angle_deg: 45, h0: 0 },
    friction_air: template.acceptance.drag_control.friction_air,
    analytic_range: Number(analyticR.toFixed(4)),
    range_no_drag: Number(clean.landed.x.toFixed(4)),
    range_with_drag: Number(draggy.landed.x.toFixed(4)),
    deviation_no_drag_pct: Number((devClean * 100).toFixed(3)),
    deviation_with_drag_pct: Number((devDrag * 100).toFixed(3)),
    ratio: Number((devDrag / Math.max(devClean, 1e-12)).toFixed(2)),
    verdict: devDrag > template.acceptance.drag_control.min_ratio_vs_clean * devClean
      && devDrag > template.acceptance.drag_control.min_deviation_pct / 100
      ? 'pass' : 'fail',
  }

  const verdict = scenarios.every(s => s.verdict === 'pass') && dragControl.verdict === 'pass' ? 'pass' : 'fail'
  const evidence = {
    schema: 'eduforge.labkit.projectile.evidence/v1',
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
    drag_control: dragControl,
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
    drag_control: dragControl,
    hints: verdict === 'pass' ? [] : ['逐项看 scenarios[].checks 的 rel_error_pct；先在同配方内微调 v0/h0，再考虑换配方。'],
  }
}
