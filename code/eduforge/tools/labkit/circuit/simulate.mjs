/**
 * L2：直流电路对账。
 *
 * 观测 = 自包含 MNA 求解器；参考 = 欧姆定律/串并联解析式。
 * 另外读 CircuitJS1 2026-10-19 的实测证据做外部交叉验证：
 * 同一组 V/R 下，MNA 与上游引擎的读数必须一致（双精度下应为 1e-15 量级）。
 */
import { existsSync, mkdirSync, readFileSync, writeFileSync } from 'node:fs'
import { dirname, join } from 'node:path'
import { checkDesign } from './check.mjs'
import {
  analyticOhm,
  analyticParallel,
  analyticSeries,
  buildOhm,
  buildParallel,
  buildSeries,
  measureFromSolution,
  solveDC,
} from './core.mjs'
import { canonicalize, designHash } from '../lib/hash.mjs'
import { loadTemplate } from '../lib/template.mjs'

function relPct(a, b) {
  if (b === 0) return a === 0 ? 0 : Infinity
  return Math.abs((a - b) / b) * 100
}

function near(metric, measured, analytic, tol) {
  const rel = relPct(measured, analytic)
  return {
    metric,
    measured: Number(measured.toFixed(9)),
    analytic: Number(analytic.toFixed(9)),
    rel_error_pct: Number.isFinite(rel) ? Number(rel.toFixed(9)) : null,
    tolerance_pct: tol,
    verdict: rel <= tol ? 'pass' : 'fail',
  }
}

function solveFor(recipeId, p) {
  const netlist = recipeId === 'ohms-law'
    ? buildOhm(p)
    : recipeId === 'series' ? buildSeries(p) : buildParallel(p)
  const sol = solveDC(netlist)
  return { netlist, sol, measured: measureFromSolution(recipeId, sol) }
}

function crossCheck(repoRoot) {
  const evidencePath = join(repoRoot, 'source', 'library', 'circuit-lab-evidence.json')
  if (!existsSync(evidencePath)) {
    return { available: false, source: evidencePath, checks: [], verdict: 'na' }
  }
  const source = JSON.parse(readFileSync(evidencePath, 'utf8'))
  const checks = []
  const add = (caseId, metric, mna, engineVal) => {
    const rel = relPct(mna, engineVal)
    checks.push({
      case: caseId,
      metric,
      mna: Number(mna.toFixed(12)),
      circuitjs1: Number(engineVal.toFixed(12)),
      rel_error_pct: Number.isFinite(rel) ? Number(rel.toExponential(3)) : null,
      verdict: rel <= 1e-6 ? 'pass' : 'fail',
    })
  }

  const ohm = source.results?.find(r => r.id === 'ohms-law')
  for (const row of ohm?.engine ?? []) {
    const m = solveFor('ohms-law', { voltage_v: 5, resistance_ohm: row.R }).measured
    add('ohms-law', `I(R=${row.R})`, m.I, row.i_measured)
  }
  const series = source.results?.find(r => r.id === 'circuits-series')
  if (series?.engine?.length >= 2) {
    const m = solveFor('series', { voltage_v: 5, resistance_ohm: 100, r2_ohm: 220 }).measured
    add('series', 'I', m.I, series.engine[0].i)
    add('series', 'U1', m.U1, series.engine[0].v)
    add('series', 'U2', m.U2, series.engine[1].v)
  }
  const parallel = source.results?.find(r => r.id === 'circuits-parallel')
  if (parallel?.engine?.length >= 2) {
    const m = solveFor('parallel', { voltage_v: 5, resistance_ohm: 100, r2_ohm: 220 }).measured
    add('parallel', 'I1', m.I1, parallel.engine[0].i)
    add('parallel', 'I2', m.I2, parallel.engine[1].i)
  }
  return {
    available: true,
    source: 'source/library/circuit-lab-evidence.json（CircuitJS1，2026-10-19）',
    checks,
    verdict: checks.length && checks.every(c => c.verdict === 'pass') ? 'pass' : 'fail',
  }
}

export function simulateDesign({ repoRoot, design, outPath }) {
  const l1 = checkDesign({ repoRoot, design })
  if (!l1.ok) return { ...l1, stage: 'L1' }
  const template = loadTemplate(repoRoot, design.template_id ?? 'circuits.ohms_law')
  const recipe = template.recipes.find(r => r.id === design.recipe_id)
  const params = l1.normalized.params
  const analytic = recipe.id === 'ohms-law' ? analyticOhm(params)
    : recipe.id === 'series' ? analyticSeries(params) : analyticParallel(params)
  const { sol, measured } = solveFor(recipe.id, params)

  const metricKeys = recipe.metric_keys
  const checks = metricKeys.map(k => near(k, measured[k], analytic[k], recipe.tolerances_pct[k] ?? 1e-6))
  const scenario = {
    id: 'main',
    params,
    measured: Object.fromEntries(Object.entries(measured).map(([k, v]) => [k, Number(v.toFixed(9))])),
    analytic: Object.fromEntries(Object.entries(analytic).map(([k, v]) => [k, Number(v.toFixed(9))])),
    checks,
    verdict: checks.every(c => c.verdict === 'pass') ? 'pass' : 'fail',
  }

  const xcheck = crossCheck(repoRoot)
  const verdict = scenario.verdict === 'pass' && xcheck.verdict !== 'fail' ? 'pass' : 'fail'
  const evidence = {
    schema: 'eduforge.labkit.circuit.evidence/v1',
    template_id: template.template_id,
    recipe_id: recipe.id,
    design_hash: designHash(l1.normalized),
    engine: {
      id: template.engine.id,
      version: template.engine.version,
      solver: template.engine.solver,
      node_voltages: sol.nodeVoltages.map(v => Number(v.toFixed(9))),
      source_current_a: Number(sol.sourceCurrents.V1.toFixed(9)),
    },
    scenarios: [scenario],
    cross_check: xcheck,
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
    scenarios: [scenario],
    cross_check: xcheck,
    hints: verdict === 'pass' ? [] : ['先看 scenarios[].checks 与 cross_check.checks；不要把容差放宽来「修好」它。'],
  }
}
