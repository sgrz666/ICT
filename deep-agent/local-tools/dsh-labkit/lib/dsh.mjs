/**
 * 从上游已构建产物直接导入 defineTool。
 *
 * dsh 的工具包在 workspace 内，但本插件刻意放在上游树之外（不改 deep-agent/deepseek-harness）。
 * 相对路径导入只依赖目录结构，不需要 package.json / node_modules / pnpm install。
 */
export { defineTool } from '../../../deepseek-harness/packages/core/tools/lib/index.js'
