/**
 * L1：单摆设计校验。
 *
 * 配方是「多场景扫描」：period-length 固定 L=0.5/1/2，angle-correction 固定 θ=5/10/30。
 * Agent 选配方即可；不接受逐场景改参（否则扫描点就不是教学点了）。
 */
import { pendulumAnalytic } from './core.mjs'
import { loadTemplate } from '../lib/template.mjs'

const PREDICTION_TOL_PCT = 1

function isNum(v) { return typeof v === 'number' && Number.isFinite(v) }
function inRange(v, r) { return v >= r[0] && v <= r[1] }
function push(errors, code, field, message) { errors.push({ code, field, message }) }
function relPct(a, b) { return b === 0 ? (a === 0 ? 0 : Infinity) : Math.abs((a - b) / b) * 100 }

function checkReason(template, recipe, design, errors) {
  const r = template.reason
  const why = typeof design.why_recipe === 'string' ? design.why_recipe.trim() : ''
  const task = typeof design.student_task === 'string' ? design.student_task.trim() : ''
  if (why.length < 12) {
    push(errors, 'REASON_MISSING', 'why_recipe', 'why_recipe 至少 12 个字')
  } else {
    if (!recipe.intent_keywords.some(k => why.includes(k))) {
      push(errors, 'REASON_WEAK', 'why_recipe', `理由至少要点到一个关键词：${recipe.intent_keywords.join(' / ')}`)
    }
    if (!r.variables.some(v => why.includes(v))) {
      push(errors, 'REASON_WEAK', 'why_recipe', `理由至少要点到一个物理量：${r.variables.join(' / ')}`)
    }
    if (!/因为|因此|所以|由于|从而|说明|意味着/.test(why)) {
      push(errors, 'REASON_WEAK', 'why_recipe', '理由要写出因果关系（因为/因此/所以/由于/从而）')
    }
    if (!/\d/.test(why) && r.generic_phrases.some(p => why.includes(p))) {
      push(errors, 'REASON_WEAK', 'why_recipe', '理由不能只有空话，至少给出一个可检验的量或结论')
    }
  }
  if (task.length < 10) {
    push(errors, 'REASON_MISSING', 'student_task', 'student_task 至少 10 个字')
  } else {
    if (!r.task_verbs.some(v => task.includes(v))) push(errors, 'REASON_WEAK', 'student_task', `学生任务要包含操作动词：${r.task_verbs.join(' / ')}`)
    if (!r.task_metrics.some(v => task.includes(v))) push(errors, 'REASON_WEAK', 'student_task', `学生任务要包含观测量：${r.task_metrics.join(' / ')}`)
  }
}

function checkExpected(recipe, predictions, design, errors, hints) {
  const expected = design.expected_numbers
  if (expected === undefined) return null
  if (!expected || typeof expected !== 'object' || Array.isArray(expected)) {
    push(errors, 'EXPECTED_SHAPE', 'expected_numbers', 'expected_numbers 必须是对象；不确定就省略')
    return null
  }
  for (const key of recipe.metric_keys) {
    if (!(key in expected)) {
      push(errors, 'EXPECTED_MISSING', `expected_numbers.${key}`, `缺少 ${key}`)
      continue
    }
    if (!isNum(expected[key])) {
      push(errors, 'EXPECTED_SHAPE', `expected_numbers.${key}`, '必须是有限数字')
      continue
    }
    const target = predictions.values[key]
    if (target !== undefined && relPct(expected[key], target) > PREDICTION_TOL_PCT) {
      push(errors, 'PREDICTION_MISMATCH', `expected_numbers.${key}`, `你写的 ${expected[key]} 与解析值 ${target.toFixed(4)} 相差 ${relPct(expected[key], target).toFixed(2)}%`)
      hints.push(`把 ${key} 改成 ${target.toFixed(3)}，或删掉 expected_numbers 让工具补全。`)
    }
  }
  return expected
}

/**
 * @param {{repoRoot:string, design:object}} input
 */
export function checkDesign({ repoRoot, design }) {
  const errors = []
  const hints = []
  if (!design || typeof design !== 'object' || Array.isArray(design)) {
    return { ok: false, stage: 'L1', errors: [{ code: 'DESIGN_SCHEMA', field: 'design', message: 'design 必须是对象' }], hints: ['传入 {template_id, recipe_id, why_recipe, student_task}。'] }
  }
  let template
  try {
    template = loadTemplate(repoRoot, design.template_id ?? 'mechanics.pendulum')
  } catch {
    return { ok: false, stage: 'L1', errors: [{ code: 'TEMPLATE_NOT_FOUND', field: 'template_id', message: `找不到模板：${design.template_id ?? 'mechanics.pendulum'}` }], hints: [] }
  }
  const recipe = template.recipes.find(r => r.id === design.recipe_id)
  if (!recipe) {
    return { ok: false, stage: 'L1', errors: [{ code: 'RECIPE_UNKNOWN', field: 'recipe_id', message: `未知配方：${design.recipe_id}` }], hints: [`可用配方：${template.recipes.map(r => r.id).join(' / ')}`] }
  }

  // 多场景扫描：params 可以传（模型常带默认值），但会被忽略；逐场景改参会破坏教学扫描点。
  const params = design.params ?? {}
  const warnings = []
  if (params && typeof params === 'object' && Object.keys(params).length > 0) {
    warnings.push('该配方是固定扫描，params 已忽略；页面内仍可拖动改变摆长/初始角。')
  }

  const scenarios = recipe.scenarios.map(s => ({ id: s.id, params: { ...s.params } }))
  const d = template.decision
  for (const s of scenarios) {
    if (!inRange(s.params.length_m, d.length_range)) {
      push(errors, 'PARAM_OUT_OF_RANGE', `${s.id}.length_m`, `摆长 ${s.params.length_m} 超出 ${d.length_range.join('..')} m`)
    }
    if (!inRange(s.params.angle0_deg, d.angle_range)) {
      push(errors, 'PARAM_OUT_OF_RANGE', `${s.id}.angle0_deg`, `初始角 ${s.params.angle0_deg}° 超出 ${d.angle_range.join('..')}°`)
    }
  }

  const predictions = {
    scenarios: scenarios.map(s => ({
      id: s.id,
      params: s.params,
      analytic: pendulumAnalytic({
        lengthM: s.params.length_m,
        angle0Deg: s.params.angle0_deg,
        gravity: template.engine.gravity,
      }),
    })),
  }
  const values = {}
  // metric_keys 的键名与场景顺序对齐（T_L0.5 / T_5 ...）
  for (const [i, s] of scenarios.entries()) {
    const key = recipe.metric_keys[i]
    if (key) values[key] = predictions.scenarios[i].analytic.Texact
  }
  if (recipe.id === 'period-length') {
    values.ratio = predictions.scenarios[2].analytic.Texact / predictions.scenarios[0].analytic.Texact
  }
  predictions.values = values

  for (const s of predictions.scenarios) {
    if (s.analytic.Texact > d.max_period_s) {
      push(errors, 'VIEWPORT_OVERFLOW', `${s.id}.T`, `周期 ${s.analytic.Texact.toFixed(2)} s 超过画面可读上限 ${d.max_period_s} s`)
      hints.push('降低摆长，让周期落在画面范围内。')
    }
  }
  checkReason(template, recipe, design, errors)
  const expected = checkExpected(recipe, predictions, design, errors, hints)

  const normalized = {
    template_id: template.template_id,
    recipe_id: recipe.id,
    params: {},
    why_recipe: design.why_recipe,
    student_task: design.student_task,
    expected_numbers: expected ?? Object.fromEntries(Object.entries(values).map(([k, v]) => [k, +v.toFixed(3)])),
  }

  return {
    ok: errors.length === 0,
    stage: 'L1',
    template_id: template.template_id,
    recipe_id: recipe.id,
    normalized,
    predictions,
    errors,
    hints: [...new Set(hints)],
    warnings,
  }
}
