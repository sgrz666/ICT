import test from 'node:test'
import assert from 'node:assert/strict'
import { mkdtempSync, mkdirSync, writeFileSync, readFileSync, readdirSync, lstatSync } from 'node:fs'
import { tmpdir } from 'node:os'
import { join } from 'node:path'
import { createRequire } from 'node:module'
import { createHash } from 'node:crypto'

function packageAt(dir, name, version, dependencies = {}, body = 'module.exports = {}', extra = {}) {
  mkdirSync(dir, { recursive: true })
  writeFileSync(join(dir, 'package.json'), JSON.stringify({ name, version, main: 'index.cjs', dependencies, ...extra }))
  writeFileSync(join(dir, 'index.cjs'), body)
  return dir
}

test('packaged dependencies preserve conflicting versions and singleton required peers without source links', async () => {
  const { collectPackageGraph, materializePackageGraph } = await import('../src/package-graph.mjs')
  const root = mkdtempSync(join(tmpdir(), 'eduforge-package-graph-'))
  const source = join(root, 'source', 'node_modules')
  const a = packageAt(join(source, 'a'), 'a', '1.0.0', { shared: '1.0.0' }, "module.exports = [require('shared'), require('peer')]", { peerDependencies: { peer: '1.0.0' } })
  const b = packageAt(join(source, 'b'), 'b', '1.0.0', { shared: '2.0.0' }, "module.exports = [require('shared'), require('peer')]", { peerDependencies: { peer: '1.0.0' }, optionalDependencies: { absent: '1.0.0' } })
  packageAt(join(a, 'node_modules', 'shared'), 'shared', '1.0.0', {}, "module.exports = 'one'")
  packageAt(join(b, 'node_modules', 'shared'), 'shared', '2.0.0', {}, "module.exports = 'two'")
  packageAt(join(source, 'peer'), 'peer', '1.0.0', {}, 'module.exports = { singleton: true }')
  const graph = collectPackageGraph({ seeds: [a, b] })
  const output = join(root, 'output')
  const result = materializePackageGraph({ graph, outDir: output })
  const require = createRequire(join(output, 'package.json'))
  const first = require('a'), second = require('b')
  assert.equal(first[0], 'one')
  assert.equal(second[0], 'two')
  assert.equal(first[1], second[1])
  assert.equal(result.resolutionErrors.length, 0)
  const walk = dir => { for (const e of readdirSync(dir, { withFileTypes: true })) { const path = join(dir, e.name); assert.equal(lstatSync(path).isSymbolicLink(), false); if (e.isDirectory()) walk(path) } }
  walk(output)
})

test('missing mandatory runtime dependency fails instead of silently packaging an incomplete graph', async () => {
  const { collectPackageGraph } = await import('../src/package-graph.mjs')
  const root = mkdtempSync(join(tmpdir(), 'eduforge-package-missing-'))
  const app = packageAt(join(root, 'app'), 'app', '1.0.0', { 'missing-required-eduforge-fixture': '1.0.0' })
  assert.throws(() => collectPackageGraph({ seeds: [app] }), /missing-required-eduforge-fixture/)
})

test('building refuses to overwrite an existing output directory', async () => {
  const { buildPackage } = await import('../src/package.mjs')
  const output = mkdtempSync(join(tmpdir(), 'eduforge-existing-package-'))
  writeFileSync(join(output, 'sentinel.txt'), 'keep')
  await assert.rejects(buildPackage({ outDir: output }), /already exists/i)
  assert.equal(readFileSync(join(output, 'sentinel.txt'), 'utf8'), 'keep')
})

test('package audit rejects a changed file against its inventory', async () => {
  const module=await import('../src/package.mjs')
  assert.equal(typeof module.auditPackage,'function','package audit must exist')
  const dir=mkdtempSync(join(tmpdir(),'eduforge-inventory-'))
  writeFileSync(join(dir,'file.txt'),'abc')
  writeFileSync(join(dir,'inventory.json'),JSON.stringify({files:[{path:'file.txt',bytes:3,sha256:createHash('sha256').update('abc').digest('hex')}]}))
  assert.equal((await module.auditPackage(dir)).ok,true)
  writeFileSync(join(dir,'file.txt'),'changed')
  assert.equal((await module.auditPackage(dir)).ok,false)
})
