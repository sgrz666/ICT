/**
 * EduForge LabKit — dsh 原生实验构建工具。
 *
 * 六个模型可见工具：recipes / validate / simulate / render / verify / build。
 * 插件本身不依赖 npm 包，也不修改 deepseek-harness 上游树；
 * 由 profile 的 cordis.patch.yml 以相对路径插入。
 */
import { defineTool } from './lib/dsh.mjs'
import { registerBuild } from './tools/build.mjs'
import { registerRecipes } from './tools/recipes.mjs'
import { registerRender } from './tools/render.mjs'
import { registerSimulate } from './tools/simulate.mjs'
import { registerValidate } from './tools/validate.mjs'
import { registerVerify } from './tools/verify.mjs'

export const name = 'eduforge-labkit'
export const inject = ['tools', 'systemPrompt']

export function apply(ctx) {
  if (typeof defineTool !== 'function') {
    throw new Error(
      'eduforge-labkit: 无法从 deepseek-harness/packages/core/tools/lib/index.js 导入 defineTool。' +
      ' 先在 deep-agent/deepseek-harness 下执行 pnpm run build。',
    )
  }

  ctx.systemPrompt.section({
    name: 'eduforge:labkit',
    order: 1150,
    text: () =>
      '当用户要求制作、生成或修改物理实验时：先调 experiment_recipes 读取配方与参数范围；' +
      '标准需求直接调 experiment_build，一次完成 L1 参数校验、L2 物理对账、单文件渲染与 L3 离线实测。' +
      '只有需要分步排查时才使用 experiment_validate / experiment_simulate / experiment_render / experiment_verify。' +
      '不得自行编写物理公式、手写 HTML 或修改验收容差；实验页面必须由这些工具生成。' +
      'experiment_build 成功后直接汇报 HTML 路径与实测读数，不要再用 read / grep / pwsh 去检查产物内容——' +
      '页面已嵌入实验目的、操作步骤、解析式与读数表。' +
      '若 experiment_build 返回 ok=false，按 hints 调整参数或理由后重试，最多 3 次；仍失败则如实上报。',
  })

  registerRecipes(ctx, defineTool)
  registerValidate(ctx, defineTool)
  registerSimulate(ctx, defineTool)
  registerRender(ctx, defineTool)
  registerVerify(ctx, defineTool)
  registerBuild(ctx, defineTool)
}
