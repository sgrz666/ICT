import assert from 'node:assert/strict'
import { cpSync, mkdirSync, mkdtempSync } from 'node:fs'
import { tmpdir } from 'node:os'
import { basename, dirname, join, resolve } from 'node:path'
import { execFileSync } from 'node:child_process'
import { fileURLToPath, pathToFileURL } from 'node:url'
import test from 'node:test'

const repoRoot = resolve(dirname(fileURLToPath(import.meta.url)), '../../..')
const fixtureRoot = mkdtempSync(join(tmpdir(), 'labkit-portable-'))
const dataRoot = join(fixtureRoot, 'user data', 'experiments')
console.log(`Portable test artifacts: ${fixtureRoot}`)

function run(code, root = repoRoot) {
  return JSON.parse(execFileSync(process.execPath, ['--input-type=module', '-e', code], {
    env: { ...process.env, EDUFORGE_LABKIT_ROOT: root, EDUFORGE_LABKIT_OUTPUT_ROOT: dataRoot },
    encoding: 'utf8',
  }))
}

test('explicit asset and output roots are independent of plugin location', () => {
  const url = pathToFileURL(join(repoRoot, 'deep-agent/local-tools/dsh-labkit/lib/paths.mjs')).href
  const root = join(fixtureRoot, 'copied assets')
  const result = run(`const p = await import(${JSON.stringify(url)}); console.log(JSON.stringify({root:p.repoRoot,out:p.outRoot,paths:p.outPaths('ohms-law','../portable')}))`, root)
  assert.equal(result.root, root)
  assert.equal(result.out, dataRoot)
  assert.equal(basename(result.paths.html), 'portable.html')
  assert.equal(dirname(dirname(result.paths.html)), join(dataRoot,'ohms-law'))
})

test('plugin loads the real core from an explicitly relocated asset tree and renders into user data', () => {
  const root = join(fixtureRoot, 'copied assets')
  for (const rel of ['code/eduforge/tools/labkit', 'code/eduforge/catalog/templates/circuits/ohms-law']) {
    const target = join(root, rel)
    mkdirSync(dirname(target), { recursive: true })
    cpSync(join(repoRoot, rel), target, { recursive: true })
  }
  const url = pathToFileURL(join(repoRoot, 'deep-agent/local-tools/dsh-labkit/tools/render.mjs')).href
  const design = {
    template_id: 'circuits.ohms_law', recipe_id: 'ohms-law', params: { voltage_v: 5, resistance_ohm: 100 },
    why_recipe: '同一电压下电流与电阻成反比，因为 I=U/R。',
    student_task: '改变电阻，记录电流表读数并比较。', out_name: 'portable',
  }
  const result = run(`const {registerRender}=await import(${JSON.stringify(url)});let t;registerRender({tools:{register:x=>t=x}},x=>x); console.log(JSON.stringify(await t.execute(${JSON.stringify(design)})))`, root)
  assert.equal(result.ok, true, JSON.stringify(result))
  assert.equal(basename(result.data.html_path), 'portable.html')
  assert.equal(dirname(dirname(result.data.html_path)), join(dataRoot,'ohms-law'))
  assert.equal(result.data.scenarios[0].measured.I, 0.05)
  assert.ok(result.data.artifact_manifest_path)
})

test('simultaneous same-name builds publish distinct complete artifact sets', () => {
  const url = pathToFileURL(join(repoRoot, 'deep-agent/local-tools/dsh-labkit/tools/build.mjs')).href
  const design = {template_id:'circuits.ohms_law',recipe_id:'ohms-law',params:{voltage_v:5,resistance_ohm:100},
    why_recipe:'因为 I=U/R，同一电压下电阻增加，所以电流减小。',student_task:'改变电阻，记录电流表读数并比较。',out_name:'concurrent'}
  const results=run(`const {registerBuild}=await import(${JSON.stringify(url)});let t;registerBuild({tools:{register:x=>t=x}},x=>x);const d=${JSON.stringify(design)};console.log(JSON.stringify(await Promise.all([t.execute(d),t.execute({...d,params:{voltage_v:5,resistance_ohm:200}})])))`)
  assert.ok(results.every(r=>r.ok),JSON.stringify(results))
  assert.notEqual(results[0].data.html_path,results[1].data.html_path)
  assert.notEqual(results[0].data.design_hash,results[1].data.design_hash)
})
