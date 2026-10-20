/** 规范化 JSON 与哈希：渲染与证据都靠它保证「同一输入 → 同一字节」。 */
import { createHash } from 'node:crypto'

/** 递归排序对象键；数组保持顺序。 */
export function canonicalize(value) {
  if (Array.isArray(value)) return value.map(canonicalize)
  if (value && typeof value === 'object') {
    const out = {}
    for (const key of Object.keys(value).sort()) out[key] = canonicalize(value[key])
    return out
  }
  return value
}

/** 稳定序列化：不依赖对象字面量顺序。 */
export function canonicalJson(value) {
  return JSON.stringify(canonicalize(value))
}

export function sha256Hex(text) {
  return createHash('sha256').update(text, 'utf8').digest('hex')
}

/** 设计对象的指纹：不含 generated_at，纯内容。 */
export function designHash(design) {
  return `sha256:${sha256Hex(canonicalJson(design))}`
}
