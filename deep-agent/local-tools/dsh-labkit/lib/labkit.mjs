/** 核心库的单一入口：插件只从这里拿能力，不直接碰实现文件。 */
import { join } from 'node:path'
import { pathToFileURL } from 'node:url'
import { repoRoot } from './paths.mjs'

const coreUrl = file => pathToFileURL(join(repoRoot, 'code/eduforge/tools/labkit', file)).href
export const {
  checkDesign,
  renderSingleFile,
  simulateDesign,
  TEMPLATE_IDS,
  verifySingleFile,
} = await import(coreUrl('dispatcher.mjs'))
export const { designHash, canonicalJson, sha256Hex } = await import(coreUrl('lib/hash.mjs'))
export const { getRecipe, listTemplates, loadTemplate } = await import(coreUrl('lib/template.mjs'))
