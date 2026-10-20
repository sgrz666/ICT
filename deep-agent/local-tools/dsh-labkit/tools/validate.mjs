import { checkDesign } from '../lib/labkit.mjs'
import { errorBlock, fmt, hintBlock } from '../lib/format.mjs'
import { defaultTemplateId, repoRoot } from '../lib/paths.mjs'
import { designParams, resultSchema, renderResult } from '../lib/tool-schema.mjs'

function predictionLines(predictions) {
  const out = []
  for (const s of predictions?.scenarios ?? []) {
    out.push(`  ${s.id}: R=${fmt(s.analytic.R)} m, T=${fmt(s.analytic.T, 3)} s, H=${fmt(s.analytic.H)} m`)
  }
  if (typeof predictions?.ratio === 'number') out.push(`  ratio_R=${fmt(predictions.ratio, 4)}`)
  return out.join('\n')
}

export function registerValidate(ctx, defineTool) {
  ctx.tools.register(defineTool({
    name: 'experiment_validate',
    description: 'L1 设计校验：检查配方、参数范围、画面可行性与教学理由，并用解析式给出预测读数。想先确认再构建时调用；不确定就直接用 experiment_build。',
    parameters: designParams(),
    output: { schema: resultSchema(), render: renderResult },
    timeoutMs: 15_000,
    async execute(args) {
      const design = {
        template_id: args.template_id || defaultTemplateId,
        recipe_id: args.recipe_id,
        params: args.params,
        why_recipe: args.why_recipe,
        student_task: args.student_task,
        ...(args.expected_numbers ? { expected_numbers: args.expected_numbers } : {}),
      }
      const r = checkDesign({ repoRoot, design })
      const summary = r.ok
        ? `L1 通过（配方 ${r.recipe_id}）。\n解析预测：\n${predictionLines(r.predictions)}\n\n${r.normalized?.expected_numbers ? `已补全 expected_numbers：${JSON.stringify(r.normalized.expected_numbers)}` : ''}`
        : `L1 未通过：\n${errorBlock(r.errors)}${hintBlock(r.hints)}`
      return {
        ok: r.ok,
        stage: 'L1',
        ...(r.ok ? {} : { code: r.errors[0]?.code || 'L1_FAILED' }),
        summary,
        data: {
          recipe_id: r.recipe_id,
          normalized: r.normalized,
          predictions: r.predictions,
          errors: r.errors,
          hints: r.hints,
        },
        hints: r.errors.length ? r.hints : [],
      }
    },
  }))
}
