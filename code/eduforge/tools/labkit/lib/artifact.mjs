/** 渲染清单把设计、HTML 字节与 L2 证据绑定；不替代真实浏览器验收。 */
import { readFileSync, writeFileSync } from 'node:fs'
import { canonicalJson, designHash, sha256Hex } from './hash.mjs'

const SCHEMA = 'eduforge.labkit.render/v1'
export const artifactManifestPath = htmlPath => `${htmlPath}.manifest.json`

export function writeArtifactManifest({ htmlPath, html, design, evidence }) {
  const path = artifactManifestPath(htmlPath)
  const manifest = {
    schema: SCHEMA,
    design,
    design_hash: designHash(design),
    html_sha256: sha256Hex(html),
    evidence_sha256: evidence ? sha256Hex(canonicalJson(evidence)) : null,
  }
  writeFileSync(path, `${JSON.stringify(manifest, null, 2)}\n`, 'utf8')
  return path
}

export function verifyArtifactManifest({ htmlPath, evidence }) {
  const fail = (code, detail) => ({ ok: false, stage: 'L3', code, detail, hints: ['重新运行 experiment_build 或 experiment_render；保留同一次生成的 HTML、evidence 与 .html.manifest.json。'] })
  let manifest
  let html
  try {
    manifest = JSON.parse(readFileSync(artifactManifestPath(htmlPath), 'utf8'))
    html = readFileSync(htmlPath)
  } catch (e) {
    return fail('ARTIFACT_UNREADABLE', e.message)
  }
  if (manifest.schema !== SCHEMA || !manifest.design || manifest.design_hash !== designHash(manifest.design)) {
    return fail('ARTIFACT_DESIGN_MISMATCH', '渲染清单的设计指纹无效。')
  }
  if (manifest.html_sha256 !== sha256Hex(html)) {
    return fail('ARTIFACT_HTML_MISMATCH', 'HTML 已变化，与渲染清单的 sha256 不同。')
  }
  if (manifest.evidence_sha256 !== sha256Hex(canonicalJson(evidence)) || evidence.design_hash !== manifest.design_hash
      || evidence.template_id !== manifest.design.template_id || evidence.recipe_id !== manifest.design.recipe_id) {
    return fail('ARTIFACT_EVIDENCE_MISMATCH', 'L2 证据与渲染清单或设计不匹配。')
  }
  if (evidence.verdict !== 'pass' || !Array.isArray(evidence.scenarios) || evidence.scenarios.length === 0) {
    return fail('ARTIFACT_EVIDENCE_INVALID', 'L2 证据没有通过或缺少场景。')
  }
  return { ok: true, manifest, bytes: html.length }
}
