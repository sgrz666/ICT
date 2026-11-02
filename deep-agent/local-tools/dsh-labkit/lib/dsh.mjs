/**
 * 从上游已构建产物直接导入 defineTool。
 *
 * dsh 的工具包在 workspace 内，但本插件刻意放在上游树之外（不改 deep-agent/deepseek-harness）。
 * 发行时从 EDUFORGE_DSH_INSTALL_ANCHOR 解析包；未指定时沿用原相对目录结构。
 */
import { createRequire } from 'node:module'
import { pathToFileURL } from 'node:url'

const anchor = process.env.EDUFORGE_DSH_INSTALL_ANCHOR
const source = anchor
  ? pathToFileURL(createRequire(anchor).resolve('@deepseek-ai/dsh-tools')).href
  : new URL('../../../deepseek-harness/packages/core/tools/lib/index.js', import.meta.url).href
export const { defineTool } = await import(source)
