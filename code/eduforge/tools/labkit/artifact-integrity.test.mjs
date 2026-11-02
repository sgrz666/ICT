import assert from 'node:assert/strict'
import { mkdtempSync, readFileSync, writeFileSync } from 'node:fs'
import { tmpdir } from 'node:os'
import { dirname, join, resolve } from 'node:path'
import { fileURLToPath } from 'node:url'
import test from 'node:test'
import { renderSingleFile, simulateDesign, verifySingleFile } from './dispatcher.mjs'

const repoRoot = resolve(dirname(fileURLToPath(import.meta.url)), '../../../..')
const outRoot = mkdtempSync(join(tmpdir(), 'labkit-integrity-'))
console.log(`Integrity test artifacts: ${outRoot}`)
const design = {
  template_id: 'circuits.ohms_law', recipe_id: 'ohms-law', params: { voltage_v: 5, resistance_ohm: 100 },
  why_recipe: '同一电压下电流与电阻成反比，因为 I=U/R。',
  student_task: '改变电阻，记录电流表读数并比较。',
}

function fixture(name, selectedDesign = design) {
  const htmlPath = join(outRoot, `${name}.html`)
  const evidencePath = join(outRoot, `${name}.evidence.json`)
  const sim = simulateDesign({ repoRoot, design: selectedDesign, outPath: evidencePath })
  assert.equal(sim.ok, true)
  const evidence = JSON.parse(readFileSync(evidencePath, 'utf8'))
  const rendered = renderSingleFile({ repoRoot, outRoot, design: selectedDesign, evidence, outPath: htmlPath })
  assert.equal(rendered.ok, true)
  return { repoRoot, outRoot, htmlPath, evidencePath, evidence, rendered }
}

test('real Chromium verifies a newly rendered artifact with bound design, HTML and evidence hashes', async () => {
  const f = fixture('valid')
  const result = await verifySingleFile(f)
  assert.equal(result.ok, true, JSON.stringify(result))
  assert.equal(result.checks.network_requests, 0)
  assert.equal(result.checks.design_hash, f.rendered.design_hash)
  assert.equal(result.checks.html_sha256, f.rendered.sha256)
  assert.ok(f.rendered.artifact_manifest_path)
})

test('HTML changed after render is rejected even if browser behavior is identical', async () => {
  const f = fixture('tampered-html')
  writeFileSync(f.htmlPath, `${readFileSync(f.htmlPath, 'utf8')}\n<!-- post-render edit -->`)
  const result = await verifySingleFile(f)
  assert.equal(result.ok, false)
  assert.equal(result.code, 'ARTIFACT_HTML_MISMATCH')
})

test('evidence design hash changed with identical readouts is rejected', async () => {
  const f = fixture('tampered-evidence')
  f.evidence.design_hash = `sha256:${'0'.repeat(64)}`
  writeFileSync(f.evidencePath, JSON.stringify(f.evidence))
  const result = await verifySingleFile(f)
  assert.equal(result.ok, false)
  assert.equal(result.code, 'ARTIFACT_EVIDENCE_MISMATCH')
})

test('evidence outside the configured output root is rejected before reading', async () => {
  const f = fixture('outside-root')
  const result = await verifySingleFile({ ...f, evidencePath: join(repoRoot, 'not-authorized.evidence.json') })
  assert.equal(result.ok, false)
  assert.equal(result.code, 'PATH_ESCAPE')
})

test('missing required evidence metrics cannot pass through skipped comparisons', async () => {
  const f = fixture('missing-metric')
  delete f.evidence.scenarios[0].measured.U
  writeFileSync(f.evidencePath, JSON.stringify(f.evidence))
  renderSingleFile({ repoRoot, outRoot, design, evidence: f.evidence, outPath: f.htmlPath })
  const result = await verifySingleFile(f)
  assert.equal(result.ok, false)
  assert.ok(result.errors.some(error => error.startsWith('L3_READOUT_MISSING:')))
})

test('pendulum verification measures every L2 scenario in the real browser', async () => {
  const f = fixture('pendulum-all-scenarios', {
    template_id: 'mechanics.pendulum', recipe_id: 'period-length', params: {},
    why_recipe: '周期由摆长决定，因为 T=2π√(L/g)，摆长翻 4 倍时周期只变 2 倍。',
    student_task: '改变摆长，记录每次的周期并比较倍数关系。',
  })
  const result = await verifySingleFile(f)
  assert.equal(result.ok, true, JSON.stringify(result))
  assert.equal(result.checks.readout_compared_fields, f.evidence.scenarios.filter(s => s.id !== 'ratio').length)
})
