/** L1：直流电路设计校验（欧姆定律 / 串联 / 并联）。 */
import { analyticOhm, analyticParallel, analyticSeries } from './core.mjs'
import { loadTemplate } from '../lib/template.mjs'

function isNum(v) { return typeof v === 'number' && Number.isFinite(v) }
function inRange(v, r) { return v >= r[0] && v <= r[1] }
function push(e, code, field, message) { e.push({ code, field, message }) }
function rel(a, b) { return b === 0 ? (a === 0 ? 0 : Infinity) : Math.abs((a - b) / b) * 100 }

function predict(recipeId, p) {
  if (recipeId === 'ohms-law') return analyticOhm(p)
  if (recipeId === 'series') return analyticSeries(p)
  if (recipeId === 'parallel') return analyticParallel(p)
  throw new Error(`RECIPE_UNKNOWN: ${recipeId}`)
}

function checkReason(template, recipe, design, errors) {
  const r = template.reason
  const why = typeof design.why_recipe === 'string' ? design.why_recipe.trim() : ''
  const task = typeof design.student_task === 'string' ? design.student_task.trim() : ''
  if (why.length < 12) {
    push(errors, 'REASON_MISSING', 'why_recipe', 'why_recipe 至少 12 个字')
  } else {
    if (!recipe.intent_keywords.some(k => why.includes(k))) push(errors, 'REASON_WEAK', 'why_recipe', `理由至少要点到一个关键词：${recipe.intent_keywords.join(' / ')}`)
    if (!r.variables.some(v => why.includes(v))) push(errors, 'REASON_WEAK', 'why_recipe', `理由至少要点到一个物理量：${r.variables.join(' / ')}`)
    if (!/因为|因此|所以|由于|从而|说明|意味着/.test(why)) push(errors, 'REASON_WEAK', 'why_recipe', '理由要写出因果关系')
  }
  if (task.length < 10) {
    push(errors, 'REASON_MISSING', 'student_task', 'student_task 至少 10 个字')
  } else {
    if (!r.task_verbs.some(v => task.includes(v))) push(errors, 'REASON_WEAK', 'student_task', `学生任务要包含操作动词：${r.task_verbs.join(' / ')}`)
    if (!r.task_metrics.some(v => task.includes(v))) push(errors, 'REASON_WEAK', 'student_task', `学生任务要包含观测量：${r.task_metrics.join(' / ')}`)
  }
}

export function checkDesign({ repoRoot, design }) {
  const errors = []
  const hints = []
  if (!design || typeof design !== 'object') {
    return { ok: false, stage: 'L1', errors: [{ code: 'DESIGN_SCHEMA', field: 'design', message: 'design 必须是对象' }], hints: [] }
  }
  let template
  try {
    template = loadTemplate(repoRoot, design.template_id ?? 'circuits.ohms_law')
  } catch {
    return { ok: false, stage: 'L1', errors: [{ code: 'TEMPLATE_NOT_FOUND', field: 'template_id', message: `找不到模板：${design.template_id}` }], hints: [] }
  }
  const recipe = template.recipes.find(r => r.id === design.recipe_id)
  if (!recipe) {
    return { ok: false, stage: 'L1', errors: [{ code: 'RECIPE_UNKNOWN', field: 'recipe_id', message: `未知配方：${design.recipe_id}` }], hints: [`可用配方：${template.recipes.map(r => r.id).join(' / ')}`] }
  }

  const raw = design.params ?? {}
  const defaults = recipe.scenarios[0].params
  const voltage_v = isNum(raw.voltage_v) ? raw.voltage_v : defaults.voltage_v
  const resistance_ohm = isNum(raw.resistance_ohm) ? raw.resistance_ohm : defaults.resistance_ohm
  const needsR2 = recipe.id !== 'ohms-law'
  const r2_ohm = isNum(raw.r2_ohm) ? raw.r2_ohm : defaults.r2_ohm

  if (!isNum(voltage_v)) push(errors, 'PARAM_MISSING', 'params.voltage_v', 'voltage_v 必须是有限数字')
  if (!isNum(resistance_ohm)) push(errors, 'PARAM_MISSING', 'params.resistance_ohm', 'resistance_ohm 必须是有限数字')
  if (needsR2 && !isNum(r2_ohm)) push(errors, 'PARAM_MISSING', 'params.r2_ohm', '该配方需要 r2_ohm')

  const d = template.decision
  if (!inRange(voltage_v, d.voltage_range)) {
    push(errors, 'PARAM_OUT_OF_RANGE', 'params.voltage_v', `电压 ${voltage_v} V 超出 ${d.voltage_range.join('..')} V`)
    hints.push(`把电压改到 ${d.voltage_range[0]}..${d.voltage_range[1]} V。`)
  }
  if (!inRange(resistance_ohm, d.resistance_range)) {
    push(errors, 'PARAM_OUT_OF_RANGE', 'params.resistance_ohm', `电阻 ${resistance_ohm} Ω 超出 ${d.resistance_range.join('..')} Ω`)
    hints.push(`把 R1 改到 ${d.resistance_range[0]}..${d.resistance_range[1]} Ω。`)
  }
  if (needsR2 && !inRange(r2_ohm, d.resistance_range)) {
    push(errors, 'PARAM_OUT_OF_RANGE', 'params.r2_ohm', `电阻 ${r2_ohm} Ω 超出 ${d.resistance_range.join('..')} Ω`)
  }

  const params = { voltage_v, resistance_ohm, ...(needsR2 ? { r2_ohm } : {}) }
  const prediction = predict(recipe.id, params)
  const I = recipe.id === 'series' ? prediction.I : (recipe.id === 'parallel' ? prediction.I : prediction.I)
  if (Number.isFinite(I) && I > d.max_current_a) {
    push(errors, 'VIEWPORT_OVERFLOW', 'params.current', `总电流 ${I.toFixed(3)} A 超过教学上限 ${d.max_current_a} A`)
    hints.push('增大电阻或降低电压，让电流落在 2 A 以内。')
  }

  checkReason(template, recipe, design, errors)
  const expected = design.expected_numbers
  if (expected !== undefined) {
    if (!expected || typeof expected !== 'object' || Array.isArray(expected)) {
      push(errors, 'EXPECTED_SHAPE', 'expected_numbers', 'expected_numbers 必须是对象；不确定就省略')
    } else {
      for (const key of recipe.metric_keys) {
        if (!(key in expected) || !isNum(expected[key])) {
          push(errors, 'EXPECTED_MISSING', `expected_numbers.${key}`, `缺少或非法 ${key}`)
          continue
        }
        if (rel(expected[key], prediction[key]) > 1) {
          push(errors, 'PREDICTION_MISMATCH', `expected_numbers.${key}`, `你写的 ${expected[key]} 与解析值 ${prediction[key].toFixed(6)} 不一致`)
          hints.push(`把 ${key} 改成 ${prediction[key].toFixed(6)}，或删掉 expected_numbers。`)
        }
      }
    }
  }

  const normalized = {
    template_id: template.template_id,
    recipe_id: recipe.id,
    params,
    why_recipe: design.why_recipe,
    student_task: design.student_task,
    expected_numbers: expected ?? Object.fromEntries(recipe.metric_keys.map(k => [k, Number(prediction[k].toFixed(6))])),
  }
  return {
    ok: errors.length === 0,
    stage: 'L1',
    template_id: template.template_id,
    recipe_id: recipe.id,
    normalized,
    predictions: { scenarios: [{ id: 'main', params, analytic: prediction }] },
    errors,
    hints: [...new Set(hints)],
    warnings: [],
  }
}
