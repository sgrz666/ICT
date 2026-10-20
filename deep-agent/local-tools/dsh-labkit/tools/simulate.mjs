import { simulateDesign } from '../lib/labkit.mjs'
import { errorBlock, fmt, hintBlock, scenarioTable } from '../lib/format.mjs'
import { defaultTemplateId, outPaths, repoRoot } from '../lib/paths.mjs'
import { designParams, resultSchema, renderResult } from '../lib/tool-schema.mjs'

export function registerSimulate(ctx, defineTool) {
  ctx.tools.register(defineTool({
    name: 'experiment_simulate',
    description: 'L2 物理对账：用 matter-js 固定步进跑真实轨迹，逐指标对照运动学解析式，并跑阻力对照组。只验证不渲染；需要成品时用 experiment_build。',
    parameters: designParams(),
    output: { schema: resultSchema(), render: renderResult },
    timeoutMs: 60_000,
    async execute(args) {
      const design = {
        template_id: args.template_id || defaultTemplateId,
        recipe_id: args.recipe_id,
        params: args.params,
        why_recipe: args.why_recipe,
        student_task: args.student_task,
        ...(args.expected_numbers ? { expected_numbers: args.expected_numbers } : {}),
      }
      const paths = outPaths(args.recipe_id, args.out_name)
      const r = simulateDesign({ repoRoot, design, outPath: paths.evidence })

      if (r.stage === 'L1') {
        return {
          ok: false, stage: 'L1', code: r.errors?.[0]?.code || 'L1_FAILED',
          summary: `L1 未通过，未进入物理对账：\n${errorBlock(r.errors)}${hintBlock(r.hints)}`,
          data: { errors: r.errors, hints: r.hints }, hints: r.hints,
        }
      }
      if (!r.ok && r.code) {
        return {
          ok: false, stage: 'L2', code: r.code,
          summary: `L2 引擎错误：${r.detail || ''}${hintBlock(r.hints)}`,
          data: r, hints: r.hints,
        }
      }

      const drag = r.drag_control
      const summary = [
        r.verdict === 'pass' ? 'L2 物理对账通过。' : 'L2 物理对账未通过。',
        scenarioTable(r.scenarios),
        '',
        `阻力对照：无阻力偏离 ${fmt(drag.deviation_no_drag_pct, 3)}%，开阻力偏离 ${fmt(drag.deviation_with_drag_pct, 3)}%，比值 ${fmt(drag.ratio, 1)}×（要求 >5× 且开阻力偏离 >1%）→ ${drag.verdict}`,
        `证据：${r.evidence_path}`,
        `标定加速度：${fmt(r.engine.calibrated_acceleration, 4)} m/s²（名义 ${r.engine.gravity}）`,
      ].join('\n')

      return {
        ok: r.ok,
        stage: 'L2',
        ...(r.ok ? {} : { code: 'L2_RECONCILE_FAIL' }),
        summary,
        data: {
          evidence_path: r.evidence_path,
          design_hash: r.design_hash,
          engine: r.engine,
          scenarios: r.scenarios,
          drag_control: r.drag_control,
        },
        hints: r.ok ? [] : r.hints,
      }
    },
  }))
}
