import { loadTemplate } from '../lib/labkit.mjs'
import { defaultTemplateId, repoRoot } from '../lib/paths.mjs'
import { resultSchema, renderResult } from '../lib/tool-schema.mjs'

export function registerRecipes(ctx, defineTool) {
  ctx.tools.register(defineTool({
    name: 'experiment_recipes',
    description: '列出可用物理实验配方、默认参数、参数范围与验收容差。用户要求制作/生成物理实验时先调用它；拿到配方后用 experiment_build 一次完成。',
    parameters: {
      template_id: {
        type: 'string',
        description: '模板 id，默认 mechanics.projectile（抛体运动）。',
      },
    },
    output: { schema: resultSchema(), render: renderResult },
    timeoutMs: 15_000,
    async execute(args) {
      try {
        const template = loadTemplate(repoRoot, args.template_id || defaultTemplateId)
        const recipes = template.recipes.map(r => ({
          id: r.id,
          title: r.title,
          intent: r.intent,
          params_mode: r.params_mode,
          default_params: r.scenarios[0]?.params ?? null,
          scenarios: r.scenarios.map(s => ({ id: s.id, params: s.params })),
          metrics: r.metrics,
          tolerances_pct: r.tolerances_pct,
        }))
        const d = template.decision
        const lines = [
          `可用配方（模板 ${template.template_id} · ${template.title}）：`,
          ...recipes.map(r => `- ${r.id} | ${r.title}\n  默认参数：${JSON.stringify(r.default_params)}\n  验收指标：${r.metrics.join(', ')}（容差 ${JSON.stringify(r.tolerances_pct)}）`),
          '',
          `参数范围：v0 ${d.v0_range.join('..')} m/s；h0 ${d.h0_range.join('..')} m；斜抛角 ${d.angle_range_oblique.join('..')}°。`,
          `画面约束：射程 ≤ ${d.max_range_m} m，飞行时间 ≤ ${d.max_flight_time_s} s，最高点 ≤ ${d.max_apex_m} m。`,
          '',
          '下一步：写 design（recipe_id + params + why_recipe + student_task），直接调 experiment_build；需要先看校验结果时调 experiment_validate。',
        ]
        return {
          ok: true,
          stage: 'LOAD',
          summary: lines.join('\n'),
          data: { template_id: template.template_id, title: template.title, recipes, decision: d, engine: template.engine },
          hints: [],
        }
      } catch (e) {
        return {
          ok: false,
          stage: 'LOAD',
          code: e.code || 'TEMPLATE_NOT_FOUND',
          summary: `读取模板失败：${e.message}`,
          data: {},
          hints: ['确认 code/eduforge/catalog/templates 下存在对应 manifest.yaml 与 recipes.json。'],
        }
      }
    },
  }))
}
