/** 核心库的单一入口：插件只从这里拿能力，不直接碰实现文件。 */
export {
  checkDesign,
  renderSingleFile,
  simulateDesign,
  TEMPLATE_IDS,
  verifySingleFile,
} from '../../../../code/eduforge/tools/labkit/dispatcher.mjs'
export { designHash } from '../../../../code/eduforge/tools/labkit/lib/hash.mjs'
export { getRecipe, listTemplates, loadTemplate } from '../../../../code/eduforge/tools/labkit/lib/template.mjs'
