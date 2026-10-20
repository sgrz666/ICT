import { readFileSync } from 'node:fs'
import { renderSingleFile, simulateDesign } from '../lib/labkit.mjs'
import { errorBlock, fmt, hintBlock } from '../lib/format.mjs'
import { defaultTemplateId, outPaths, repoRoot } from '../lib/paths.mjs'
import { designParams, resultSchema, renderResult } from '../lib/tool-schema.mjs'

export function registerRender(ctx, defineTool) {
  ctx.tools.register(defineTool({
    name: 'experiment_render',
    description: '把设计渲染成单文件 HTML（内联 matter-js，双击即开）。内部会先跑 L1/L2 保证页面带的是通过物理对账的证据；不做浏览器实测。要完整交付请用 experiment_build。',
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
      const sim = simulateDesign({ repoRoot, design, outPath: paths.evidence })
      if (!sim.ok) {
        return {
          ok: false,
          stage: sim.stage,
          code: sim.code || sim.errors?.[0]?.code || 'L2_FAILED',
          summary: `渲染前校验未通过：\n${sim.errors ? errorBlock(sim.errors) : (sim.detail || '物理对账未通过')}${hintBlock(sim.hints)}`,
          data: { simulation: sim },
          hints: sim.hints || [],
        }
      }
      const evidence = JSON.parse(readFileSync(sim.evidence_path, 'utf8'))
      const ren = renderSingleFile({ repoRoot, design, evidence, outPath: paths.html })
      if (!ren.ok) {
        return {
          ok: false, stage: 'RENDER', code: ren.code || 'RENDER_FAILED',
          summary: `渲染失败：${ren.detail || errorBlock(ren.errors)}${hintBlock(ren.hints)}`,
          data: { render: ren }, hints: ren.hints || [],
        }
      }
      return {
        ok: true,
        stage: 'RENDER',
        summary: [
          '已渲染单文件 HTML（未做浏览器实测）。',
          `文件：${ren.html_path}`,
          `大小：${fmt(ren.bytes / 1024, 1)} KB · sha256=${ren.sha256.slice(0, 16)}…`,
          `证据：${sim.evidence_path}`,
          '下一步：调 experiment_verify 做 file:// 离线实测。',
        ].join('\n'),
        data: {
          html_path: ren.html_path,
          evidence_path: sim.evidence_path,
          sha256: ren.sha256,
          bytes: ren.bytes,
          design_hash: ren.design_hash,
          scenarios: sim.scenarios,
        },
        hints: [],
      }
    },
  }))
}
