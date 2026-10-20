import { readFileSync } from 'node:fs'
import { checkDesign, renderSingleFile, simulateDesign, verifySingleFile } from '../lib/labkit.mjs'
import { errorBlock, fmt, hintBlock, scenarioTable } from '../lib/format.mjs'
import { defaultTemplateId, outPaths, repoRoot } from '../lib/paths.mjs'
import { designParams, resultSchema, renderResult } from '../lib/tool-schema.mjs'

export function registerBuild(ctx, defineTool) {
  ctx.tools.register(defineTool({
    name: 'experiment_build',
    description: '一条命令完成实验构建：L1 参数校验 → L2 物理对账 → 渲染单文件 HTML → L3 浏览器离线实测。标准请求直接用本工具；返回 HTML 路径或带阶段/错误码/建议的结构化失败。',
    parameters: designParams(),
    output: { schema: resultSchema(), render: renderResult },
    timeoutMs: 240_000,
    async execute(args, exec) {
      const design = {
        template_id: args.template_id || defaultTemplateId,
        recipe_id: args.recipe_id,
        params: args.params,
        why_recipe: args.why_recipe,
        student_task: args.student_task,
        ...(args.expected_numbers ? { expected_numbers: args.expected_numbers } : {}),
      }
      if (exec?.signal?.aborted) {
        return { ok: false, stage: 'L1', code: 'ABORTED', summary: '调用已取消。', data: {}, hints: [] }
      }

      const l1 = checkDesign({ repoRoot, design })
      if (!l1.ok) {
        return {
          ok: false, stage: 'L1', code: l1.errors[0]?.code || 'L1_FAILED',
          summary: `L1 参数校验未通过：\n${errorBlock(l1.errors)}${hintBlock(l1.hints)}`,
          data: { errors: l1.errors, predictions: l1.predictions }, hints: l1.hints,
        }
      }

      const paths = outPaths(args.recipe_id, args.out_name)
      const sim = simulateDesign({ repoRoot, design, outPath: paths.evidence })
      if (!sim.ok) {
        return {
          ok: false, stage: sim.stage || 'L2', code: sim.code || sim.errors?.[0]?.code || 'L2_FAILED',
          summary: `L2 物理对账未通过：\n${sim.errors ? errorBlock(sim.errors) : (sim.detail || '')}${hintBlock(sim.hints)}`,
          data: { simulation: sim }, hints: sim.hints || [],
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

      const ver = await verifySingleFile({ repoRoot, htmlPath: ren.html_path, evidencePath: sim.evidence_path })
      if (!ver.ok) {
        return {
          ok: false, stage: 'L3', code: ver.code || 'L3_FAILED',
          summary: `L3 单文件实测未通过：\n${(ver.errors || []).join('\n')}${hintBlock(ver.hints)}`,
          data: { html_path: ren.html_path, evidence_path: sim.evidence_path, checks: ver.checks, errors: ver.errors },
          hints: ver.hints || [],
        }
      }

      const c = ver.checks
      const summary = [
        '已生成并通过三层验收。',
        `文件：${ren.html_path}`,
        `证据：${sim.evidence_path}`,
        `大小：${fmt(ren.bytes / 1024, 1)} KB · sha256=${ren.sha256.slice(0, 16)}…`,
        '',
        scenarioTable(sim.scenarios),
        '',
        `L2 阻力对照：${fmt(sim.drag_control.ratio, 1)}×（要求 >5×）`,
        `L3：网络请求 ${c.network_requests} · canvas ${fmt(c.canvas_nonbg_ratio * 100, 2)}% · 改参 ${c.range_changed ? '有效' : '无效'} · console error ${c.console_errors.length} · 读数误差 ${c.readout_max_rel_error.toExponential(2)}`,
        '',
        '页面已嵌入：实验目的（why_recipe）、操作步骤（student_task）、解析式与读数表；',
        '无需再用 read/grep 检查 HTML 内容，直接把路径与读数汇报给用户即可。',
        '',
        '双击该 HTML 即可使用；页面内可调 v0 / 角度 / 高度，轨迹与读数实时更新。',
      ].join('\n')

      return {
        ok: true,
        stage: 'DONE',
        summary,
        data: {
          html_path: ren.html_path,
          evidence_path: sim.evidence_path,
          sha256: ren.sha256,
          bytes: ren.bytes,
          design_hash: ren.design_hash,
          scenarios: sim.scenarios,
          drag_control: sim.drag_control,
          checks: ver.checks,
        },
        hints: [],
      }
    },
  }))
}
