import { listTemplates, loadTemplate } from '../lib/labkit.mjs'
import { defaultTemplateId, repoRoot } from '../lib/paths.mjs'
import { resultSchema, renderResult } from '../lib/tool-schema.mjs'

function rangeText(d) {
  return Object.entries(d || {})
    .filter(([, v]) => Array.isArray(v) && v.length === 2 && v.every(x => typeof x === 'number'))
    .map(([k, v]) => `${k} ${v[0]}..${v[1]}`)
    .join('；')
}

export function registerRecipes(ctx, defineTool) {
  ctx.tools.register(defineTool({
    name: 'experiment_recipes',
    description: '列出可用物理实验模板与配方（抛体 / 单摆 / 直流电路）、默认参数、参数范围与验收容差。用户要求制作/生成物理实验时先调用它；拿到配方后用 experiment_build 一次完成。',
    parameters: {
      template_id: {
        type: 'string',
        description: '模板 id：mechanics.projectile / mechanics.pendulum / circuits.ohms_law。省略时列出全部模板。',
      },
    },
    output: { schema: resultSchema(), render: renderResult },
    timeoutMs: 15_000,
    async execute(args) {
      try {
        if (!args.template_id) {
          const templates = listTemplates(repoRoot)
          const lines = [
            '可用实验模板：',
            ...templates.map(t => `- ${t.template_id} | ${t.title}\n  配方：${t.recipes.map(r => `${r.id}（${r.title}）`).join(' / ')}`),
            '',
            '下一步：选一个 template_id 后再调用本工具，获取该模板的配方细节与量程；或在 experiment_build 里直接传 template_id + recipe_id。',
          ]
          return {
            ok: true,
            stage: 'LOAD',
            summary: lines.join('\n'),
            data: {
              templates: templates.map(t => ({ template_id: t.template_id, title: t.title, recipes: t.recipes.map(r => ({ id: r.id, title: r.title })) })),
            },
            hints: [],
          }
        }

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
        const lines = [
          `可用配方（模板 ${template.template_id} · ${template.title}）：`,
          ...recipes.map(r => `- ${r.id} | ${r.title}\n  默认参数：${JSON.stringify(r.default_params)}\n  验收指标：${r.metrics.join(', ')}（容差 ${JSON.stringify(r.tolerances_pct)}）`),
          '',
          `参数范围：${rangeText(template.decision)}`,
          '',
          '下一步：写 design（template_id + recipe_id + params + why_recipe + student_task），直接调 experiment_build；需要先看校验结果时调 experiment_validate。',
        ]
        return {
          ok: true,
          stage: 'LOAD',
          summary: lines.join('\n'),
          data: { template_id: template.template_id, title: template.title, recipes, decision: template.decision, engine: template.engine },
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
