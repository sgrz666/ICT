/** 路径白名单：只允许写进指定根目录。 */
import { resolve, sep } from 'node:path'

export function assertUnder(root, target) {
  const r = resolve(root)
  const t = resolve(target)
  if (t !== r && !t.startsWith(r + sep)) {
    const err = new Error(`PATH_ESCAPE: ${t} 不在允许目录 ${r} 内`)
    err.code = 'PATH_ESCAPE'
    throw err
  }
  return t
}
