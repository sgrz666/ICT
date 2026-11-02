import test from 'node:test'
import assert from 'node:assert/strict'
import { existsSync } from 'node:fs'

test('runtime exposes an explicit composition with isolated teaching tools', async () => {
  const module = new URL('../src/composition.mjs', import.meta.url)
  assert.ok(existsSync(module), 'native composition implementation must exist')
  const { readComposition, walkEntries } = await import(module.href)
  const rows = readComposition('web')
  const all = walkEntries(rows)
  for (const forbidden of ['session-log-deepseek', 'otel', 'deepseek-account', 'schedule', 'workflow-ptc', 'tool-web']) {
    assert.ok(!all.some(r => r.id === forbidden), `excluded plugin ${forbidden}`)
  }
  const presets = rows.filter(r => r.name === '@deepseek-ai/dsh-agent-preset')
  assert.deepEqual(presets.map(r => r.config.id).sort(), ['eduforge-dev', 'physics-lab'])
  const teaching = presets.find(r => r.config.id === 'physics-lab')
  assert.ok(teaching.config.plugins.some(r => r.id === 'eduforge-labkit'))
  assert.ok(teaching.config.plugins.some(r => r.id === 'compaction'))
  assert.ok(!walkEntries(teaching.config.plugins).some(r => /tool-(fs|pwsh|bash|goal|subagent)/.test(r.id)))
  assert.ok(!rows.some(r => /^tool-(fs|pwsh|bash|goal|subagent)/.test(r.id)), 'no global tool leakage')
  assert.equal(rows.find(r => r.id === 'sandbox-policy').config.mode, 'workspace-write')
  assert.equal(rows.find(r => r.id === 'approval').config.policy, 'ask')
})

test('deployment configuration substitutes only owned placeholders', async () => {
  const module = new URL('../src/composition.mjs', import.meta.url)
  assert.ok(existsSync(module))
  const { materializeComposition } = await import(module.href)
  const rows = materializeComposition('web', { labkitUrl: 'file:///C:/portable/plugin/index.mjs' })
  const teacher = rows.find(r => r.id === 'preset-physics-lab')
  assert.equal(teacher.config.plugins.find(r => r.id === 'eduforge-labkit').name, 'file:///C:/portable/plugin/index.mjs')
  assert.throws(() => materializeComposition('other', {}), /profile/i)
})
