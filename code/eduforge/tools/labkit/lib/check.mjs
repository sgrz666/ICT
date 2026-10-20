/**
 * L1：设计校验。
 *
 * 只做「可判定的规则」：schema、量程、配方一致性、画面可行性、教学理由质量。
 * 物理对账在 L2（simulate.mjs），这里只用解析式做预测与提示，不加载 matter-js。
 */
import { analyticProjectile } from './projectile-core.mjs'
import { getRecipe, loadTemplate } from './template.mjs'

const ANGLE_EPS = 0.01
const PREDICTION_TOL_PCT = 1

function isNum(v) {
  return typeof v === 'number' && Number.isFinite(v)
}

function pushError(errors, code, field, message) {
  errors.push({ code, field, message })
}

function inRange(v, range) {
  return v >= range[0] && v <= range[1]
}

function relPct(measured, expected) {
  if (expected === 0) return measured === 0 ? 0 : Infinity
  return Math.abs((measured - expected) / expected) * 100
}

function normalize(template, recipe, params, errors) {
  const defaults = recipe.scenarios[0].params
  const v0 = isNum(params?.v0) ? params.v0 : defaults.v0
  const h0 = isNum(params?.h0) ? params.h0 : defaults.h0
  if (!isNum(params?.v0)) pushError(errors, 'PARAM_MISSING', 'params.v0', 'v0 必须是有限数字')
  if (!isNum(params?.h0)) pushError(errors, 'PARAM_MISSING', 'params.h0', 'h0 必须是有限数字')

  if (recipe.params_mode === 'pair') {
    const raw = params?.angles_deg
    if (!Array.isArray(raw) || raw.length !== 2 || !raw.every(isNum)) {
      pushError(errors, 'PARAM_SHAPE', 'params.angles_deg', '该配方需要 angles_deg: [θ1, θ2] 两个数字')
      return { normalized: null, scenarios: [] }
    }
    if (isNum(params?.angle_deg)) {
      pushError(errors, 'PARAM_SHAPE', 'params.angle_deg', '该配方用 angles_deg，不要用 angle_deg')
    }
    const angles = [...raw]
    return {
      normalized: { template_id: template.template_id, recipe_id: recipe.id, params: { v0, h0, angles_deg: angles } },
      scenarios: angles.map((angle, i) => ({
        id: recipe.scenarios[i]?.id ?? `s${i + 1}`,
        params: { v0, angle_deg: angle, h0 },
      })),
    }
  }

  const angle = isNum(params?.angle_deg) ? params.angle_deg : defaults.angle_deg
  if (!isNum(params?.angle_deg)) pushError(errors, 'PARAM_MISSING', 'params.angle_deg', 'angle_deg 必须是有限数字')
  if (Array.isArray(params?.angles_deg)) {
    pushError(errors, 'PARAM_SHAPE', 'params.angles_deg', '该配方用单个 angle_deg，不要用 angles_deg')
  }
  return {
    normalized: { template_id: template.template_id, recipe_id: recipe.id, params: { v0, angle_deg: angle, h0 } },
    scenarios: [{ id: recipe.scenarios[0].id, params: { v0, angle_deg: angle, h0 } }],
  }
}

function checkRecipeIdentity(recipe, scenarios, errors) {
  if (recipe.id === 'horizontal') {
    for (const s of scenarios) {
      if (Math.abs(s.params.angle_deg) > ANGLE_EPS) {
        pushError(errors, 'RECIPE_PARAM_CONFLICT', 'params.angle_deg', '平抛配方要求发射角为 0°')
      }
      if (s.params.h0 < 1) {
        pushError(errors, 'RECIPE_PARAM_CONFLICT', 'params.h0', '平抛配方要求初始高度至少 1 m，否则飞行时间为 0')
      }
    }
  }
  if (recipe.id === 'oblique45') {
    for (const s of scenarios) {
      if (Math.abs(s.params.angle_deg - 45) > ANGLE_EPS) {
        pushError(errors, 'RECIPE_PARAM_CONFLICT', 'params.angle_deg', '斜抛 45° 配方要求发射角为 45°')
      }
    }
  }
  if (recipe.id === 'complementary') {
    const [a, b] = scenarios.map(s => s.params.angle_deg)
    if (Math.abs(a + b - 90) > ANGLE_EPS) {
      pushError(errors, 'RECIPE_PARAM_CONFLICT', 'params.angles_deg', '互补角配方要求两个角度之和为 90°')
    }
  }
}

function checkRanges(template, recipe, scenarios, errors, hints) {
  const d = template.decision
  for (const s of scenarios) {
    const p = s.params
    if (!inRange(p.v0, d.v0_range)) {
      pushError(errors, 'PARAM_OUT_OF_RANGE', `${s.id}.v0`, `v0=${p.v0} 超出教学量程 ${d.v0_range.join('..') } m/s`)
      hints.push(`把 v0 改到 ${d.v0_range[0]}..${d.v0_range[1]} m/s 之间。`)
    }
    if (!inRange(p.h0, d.h0_range)) {
      pushError(errors, 'PARAM_OUT_OF_RANGE', `${s.id}.h0`, `h0=${p.h0} 超出教学量程 ${d.h0_range.join('..')} m`)
      hints.push(`把 h0 改到 ${d.h0_range[0]}..${d.h0_range[1]} m 之间。`)
    }
    if (!inRange(p.angle_deg, d.angle_range)) {
      pushError(errors, 'PARAM_OUT_OF_RANGE', `${s.id}.angle_deg`, `角度 ${p.angle_deg}° 超出 0..90°`)
    }
    if (recipe.id !== 'horizontal' && !inRange(p.angle_deg, d.angle_range_oblique)) {
      pushError(errors, 'PARAM_OUT_OF_RANGE', `${s.id}.angle_deg`, `斜抛配方角度需在 ${d.angle_range_oblique.join('..')}° 内`)
      hints.push(`把角度改到 ${d.angle_range_oblique[0]}..${d.angle_range_oblique[1]}°。`)
    }
  }
}

function deriveHints(template, scenarios, predictions, errors, hints) {
  const d = template.decision
  const g = template.engine.gravity
  for (const [i, s] of scenarios.entries()) {
    const a = predictions[i].analytic
    if (a.R > d.max_range_m) {
      const th = (s.params.angle_deg * Math.PI) / 180
      const sin2 = Math.sin(2 * th)
      let vmax
      if (s.params.angle_deg <= ANGLE_EPS) {
        vmax = d.max_range_m / a.T
      } else if (sin2 > 1e-6) {
        vmax = Math.sqrt((d.max_range_m * g) / sin2)
      }
      pushError(errors, 'VIEWPORT_OVERFLOW', `${s.id}.R`, `射程 ${a.R.toFixed(1)} m 超过画面可读上限 ${d.max_range_m} m`)
      hints.push(
        vmax && Number.isFinite(vmax)
          ? `在该角度下把 v0 降到 ≤ ${Math.floor(vmax * 10) / 10} m/s，射程即可落回 ${d.max_range_m} m 内。`
          : `增大角度或降低 v0，让射程不超过 ${d.max_range_m} m。`,
      )
    }
    if (a.T > d.max_flight_time_s) {
      pushError(errors, 'VIEWPORT_OVERFLOW', `${s.id}.T`, `飞行时间 ${a.T.toFixed(2)} s 超过 ${d.max_flight_time_s} s`)
      const hmax = 0.5 * g * d.max_flight_time_s * d.max_flight_time_s
      hints.push(`把 h0 降到 ≤ ${Math.floor(hmax * 10) / 10} m 或降低 v0，飞行时间即可落回 ${d.max_flight_time_s} s 内。`)
    }
    if (a.H > d.max_apex_m) {
      pushError(errors, 'VIEWPORT_OVERFLOW', `${s.id}.H`, `最高点 ${a.H.toFixed(1)} m 超过 ${d.max_apex_m} m`)
      const th = (s.params.angle_deg * Math.PI) / 180
      const sin = Math.sin(th)
      if (sin > 1e-6) {
        const vmax = Math.sqrt((2 * (d.max_apex_m - s.params.h0) * g)) / sin
        if (Number.isFinite(vmax) && vmax > 0) {
          hints.push(`把 v0 降到 ≤ ${Math.floor(vmax * 10) / 10} m/s，最高点即可落回 ${d.max_apex_m} m 内。`)
        }
      }
    }
  }
}

function checkReasons(template, recipe, design, errors) {
  const r = template.reason
  const why = typeof design.why_recipe === 'string' ? design.why_recipe.trim() : ''
  const task = typeof design.student_task === 'string' ? design.student_task.trim() : ''

  if (why.length < 12) {
    pushError(errors, 'REASON_MISSING', 'why_recipe', 'why_recipe 至少 12 个字，必须说明为什么选这个配方')
  } else {
    const hitIntent = recipe.intent_keywords.some(k => why.includes(k))
    const hitVar = r.variables.some(v => why.includes(v))
    const hitCausal = /因为|因此|所以|由于|从而|说明|意味着/.test(why)
    if (!hitIntent) pushError(errors, 'REASON_WEAK', 'why_recipe', `理由至少要点到一个配方关键词：${recipe.intent_keywords.join(' / ')}`)
    if (!hitVar) pushError(errors, 'REASON_WEAK', 'why_recipe', `理由至少要点到一个物理量：${r.variables.join(' / ')}`)
    if (!hitCausal) pushError(errors, 'REASON_WEAK', 'why_recipe', '理由要写出因果关系（因为/因此/所以/由于/从而）')
    if (!/\d/.test(why) && r.generic_phrases.some(p => why.includes(p))) {
      pushError(errors, 'REASON_WEAK', 'why_recipe', '理由不能只有「更有趣/更直观」这类空话，至少给出一个可检验的量或结论')
    }
  }

  if (task.length < 10) {
    pushError(errors, 'REASON_MISSING', 'student_task', 'student_task 至少 10 个字，必须写学生要做什么、看什么')
  } else {
    if (!r.task_verbs.some(v => task.includes(v))) {
      pushError(errors, 'REASON_WEAK', 'student_task', `学生任务要包含操作动词：${r.task_verbs.join(' / ')}`)
    }
    if (!r.task_metrics.some(v => task.includes(v))) {
      pushError(errors, 'REASON_WEAK', 'student_task', `学生任务要包含观测量：${r.task_metrics.join(' / ')}`)
    }
  }
}

function checkExpected(recipe, predictions, design, errors, hints) {
  const expected = design.expected_numbers
  if (expected === undefined) return null
  if (expected === null || typeof expected !== 'object' || Array.isArray(expected)) {
    pushError(errors, 'EXPECTED_SHAPE', 'expected_numbers', 'expected_numbers 必须是对象；不确定就省略')
    return null
  }
  const target = recipe.params_mode === 'pair'
    ? { R_30: predictions.scenarios[0].analytic.R, R_60: predictions.scenarios[1].analytic.R, ratio: predictions.ratio }
    : {
        ...(predictions.scenarios[0].analytic.T !== undefined ? { T: predictions.scenarios[0].analytic.T } : {}),
        R: predictions.scenarios[0].analytic.R,
        ...(recipe.metric_keys.includes('H') ? { H: predictions.scenarios[0].analytic.H } : {}),
        ...(recipe.metric_keys.includes('apex_y') ? { apex_y: predictions.scenarios[0].analytic.apex_y } : {}),
      }
  for (const key of recipe.metric_keys) {
    if (!(key in expected)) {
      pushError(errors, 'EXPECTED_MISSING', `expected_numbers.${key}`, `缺少 ${key}；工具算得 ${target[key]}`)
      continue
    }
    const v = expected[key]
    if (!isNum(v)) {
      pushError(errors, 'EXPECTED_SHAPE', `expected_numbers.${key}`, '必须是有限数字')
      continue
    }
    const err = relPct(v, target[key])
    if (err > PREDICTION_TOL_PCT) {
      pushError(errors, 'PREDICTION_MISMATCH', `expected_numbers.${key}`, `你写的 ${v} 与解析值 ${target[key].toFixed(4)} 相差 ${err.toFixed(2)}%`)
      hints.push(`把 ${key} 改成 ${target[key].toFixed(2)}，或直接删掉 expected_numbers 让工具补全。`)
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
  const warnings = []

  if (!design || typeof design !== 'object' || Array.isArray(design)) {
    return {
      ok: false, stage: 'L1', errors: [{ code: 'DESIGN_SCHEMA', field: 'design', message: 'design 必须是对象' }],
      hints: ['传入 {recipe_id, params, why_recipe, student_task}。'], warnings: [],
    }
  }

  const template = (() => {
    try {
      return loadTemplate(repoRoot, design.template_id ?? 'mechanics.projectile')
    } catch (e) {
      return null
    }
  })()
  if (!template) {
    return {
      ok: false, stage: 'L1',
      errors: [{ code: 'TEMPLATE_NOT_FOUND', field: 'template_id', message: `找不到模板：${design.template_id ?? 'mechanics.projectile'}` }],
      hints: ['确认 code/eduforge/catalog/templates 下存在对应 manifest.yaml。'], warnings: [],
    }
  }
  let recipe
  try {
    recipe = getRecipe(template, design.recipe_id)
  } catch (e) {
    return {
      ok: false, stage: 'L1',
      errors: [{ code: 'RECIPE_UNKNOWN', field: 'recipe_id', message: `未知配方：${design.recipe_id}` }],
      hints: [`可用配方：${template.recipes.map(r => r.id).join(' / ')}`], warnings: [],
    }
  }

  const { normalized, scenarios } = normalize(template, recipe, design.params ?? {}, errors)
  checkRecipeIdentity(recipe, scenarios, errors)
  checkRanges(template, recipe, scenarios, errors, hints)

  if (scenarios.length === 0) {
    return {
      ok: false, stage: 'L1', template_id: template.template_id, recipe_id: recipe.id,
      normalized: null, predictions: { scenarios: [] }, errors, hints: [...new Set(hints)], warnings,
    }
  }

  const predictions = {
    scenarios: scenarios.map(s => ({
      id: s.id,
      params: s.params,
      analytic: analyticProjectile({
        h0: s.params.h0,
        v0: s.params.v0,
        angleDeg: s.params.angle_deg,
        aEff: template.engine.gravity,
      }),
    })),
  }
  if (recipe.params_mode === 'pair' && predictions.scenarios.length === 2) {
    predictions.ratio = predictions.scenarios[0].analytic.R / predictions.scenarios[1].analytic.R
    predictions.ratio_metric = 'ratio_R'
  }

  deriveHints(template, scenarios, predictions.scenarios, errors, hints)
  checkReasons(template, recipe, design, errors)
  const expected = checkExpected(recipe, predictions, design, errors, hints)

  if (normalized) {
    normalized.why_recipe = design.why_recipe
    normalized.student_task = design.student_task
    normalized.expected_numbers = expected ?? (recipe.params_mode === 'pair'
      ? {
          R_30: +predictions.scenarios[0].analytic.R.toFixed(2),
          R_60: +predictions.scenarios[1].analytic.R.toFixed(2),
          ratio: +predictions.ratio.toFixed(3),
        }
      : Object.fromEntries(recipe.metric_keys.map(k => [
          k,
          +(k === 'T' ? predictions.scenarios[0].analytic.T
            : k === 'R' ? predictions.scenarios[0].analytic.R
            : k === 'H' ? predictions.scenarios[0].analytic.H
            : predictions.scenarios[0].analytic.apex_y).toFixed(2),
        ])))
  }

  const ok = errors.length === 0
  return {
    ok,
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
