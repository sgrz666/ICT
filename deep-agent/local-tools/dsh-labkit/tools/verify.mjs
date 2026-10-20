import { verifySingleFile } from '../lib/labkit.mjs'
import { fmt, hintBlock } from '../lib/format.mjs'
import { repoRoot } from '../lib/paths.mjs'
import { resultSchema, renderResult } from '../lib/tool-schema.mjs'

export function registerVerify(ctx, defineTool) {
  ctx.tools.register(defineTool({
    name: 'experiment_verify',
    description: 'L3 单文件实测：用真 Chromium 以 file:// 打开，断网检查零外链、canvas 非空、改参后轨迹变化、无 console error、页面读数与 L2 证据一致、体积上限。对已有成品做复验时调用。',
    parameters: {
      html_path: { type: 'string', required: true, description: '单文件 HTML 的绝对路径（须在 output/eduforge/candidates/labkit 下）。' },
      evidence_path: { type: 'string', required: true, description: '对应 evidence.json 的绝对路径。' },
    },
    output: { schema: resultSchema(), render: renderResult },
    timeoutMs: 120_000,
    async execute(args) {
      const r = await verifySingleFile({
        repoRoot,
        htmlPath: args.html_path,
        evidencePath: args.evidence_path,
      })
      const c = r.checks || {}
      const lines = [
        r.ok ? 'L3 单文件实测通过。' : `L3 单文件实测未通过（${r.code || 'L3_FAILED'}）。`,
        c.status ? `页面状态：${c.status}` : '',
        c.status ? `网络请求：${c.network_requests}（要求 0）` : '',
        c.status ? `canvas 非背景像素：${fmt((c.canvas_nonbg_ratio || 0) * 100, 2)}%（要求 >2%；不透明 ${fmt((c.canvas_opaque_ratio || 0) * 100, 1)}%，颜色 ${c.canvas_distinct_colors ?? 0} 种，要求 ≥8）` : '',
        c.status ? `改 v0：${fmt(c.v0_before, 1)} → ${fmt(c.v0_after, 1)} m/s；射程 ${fmt(c.range_before, 2)} → ${fmt(c.range_after, 2)} m（要求变化 >5%）` : '',
        c.status ? `console error：${(c.console_errors || []).length}` : '',
        c.status ? `读数一致性：最大相对误差 ${c.readout_max_rel_error?.toExponential?.(2) ?? c.readout_max_rel_error}（要求 ≤1e-6）` : '',
        c.bytes ? `体积：${fmt(c.bytes / 1024, 1)} KB（上限 2048 KB）` : '',
        r.detail ? `详情：${r.detail}` : '',
        ...(r.errors || []),
      ].filter(Boolean)
      return {
        ok: r.ok,
        stage: 'L3',
        ...(r.ok ? {} : { code: r.code || 'L3_FAILED' }),
        summary: `${lines.join('\n')}${hintBlock(r.hints)}`,
        data: r,
        hints: r.hints || [],
      }
    },
  }))
}
