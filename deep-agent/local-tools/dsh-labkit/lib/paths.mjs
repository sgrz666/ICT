/** 路径与命名：仓库根由插件位置反推，输出只允许落在 labkit 目录下。 */
import { dirname, join, resolve } from 'node:path'
import { fileURLToPath } from 'node:url'

const here = dirname(fileURLToPath(import.meta.url))

/** deep-agent/local-tools/dsh-labkit/lib → ICT */
export const repoRoot = resolve(here, '../../../..')
export const outRoot = join(repoRoot, 'output', 'eduforge', 'candidates', 'labkit')
export const defaultTemplateId = 'mechanics.projectile'

/** 只留字母数字下划线连字符；防止 ../、盘符与空格进路径。 */
export function safeName(value, fallback = 'experiment') {
  const v = String(value ?? '')
    .replace(/[^A-Za-z0-9_-]/g, '_')
    .replace(/^_+|_+$/g, '')
    .slice(0, 64)
  return v || fallback
}

export function outPaths(recipeId, outName) {
  const dir = join(outRoot, safeName(recipeId))
  const base = safeName(outName || `projectile-${recipeId}`)
  return {
    dir,
    html: join(dir, `${base}.html`),
    evidence: join(dir, `${base}.evidence.json`),
  }
}
