#!/usr/bin/env node
/**
 * LabKit 自检：三个配方各跑一遍 L1 → L2 → 渲染 → L3。
 *
 * 跑法：node code/eduforge/tools/labkit/selftest.mjs
 * 产物：output/eduforge/candidates/labkit/selftest/<recipe>/...
 * 退出码：0 全过；1 任一失败。
 */
import { readFileSync } from 'node:fs'
import { dirname, join, resolve } from 'node:path'
import { fileURLToPath } from 'node:url'
import { renderSingleFile } from './lib/render-single-file.mjs'
import { simulateDesign } from './lib/simulate.mjs'
import { verifySingleFile } from './lib/verify-single-file.mjs'

const here = dirname(fileURLToPath(import.meta.url))
const repoRoot = resolve(here, '../../../..')
const outRoot = join(repoRoot, 'output', 'eduforge', 'candidates', 'labkit', 'selftest')

const CASES = [
  {
    name: 'horizontal',
    design: {
      template_id: 'mechanics.projectile',
      recipe_id: 'horizontal',
      params: { v0: 15, angle_deg: 0, h0: 20 },
      why_recipe: '水平抛出时竖直方向是自由落体，因此飞行时间只由高度决定。',
      student_task: '改变初速度，记录射程和飞行时间并比较。',
    },
  },
  {
    name: 'oblique45',
    design: {
      template_id: 'mechanics.projectile',
      recipe_id: 'oblique45',
      params: { v0: 20, angle_deg: 45, h0: 0 },
      why_recipe: '射程在 45° 时最大，因为 sin2θ 在 45° 取到 1。',
      student_task: '调整发射角并记录射程，比较哪个角度最远。',
    },
  },
  {
    name: 'complementary',
    design: {
      template_id: 'mechanics.projectile',
      recipe_id: 'complementary',
      params: { v0: 20, h0: 0, angles_deg: [30, 60] },
      why_recipe: '30° 与 60° 互为余角，因此 sin2θ 相同，射程应相等。',
      student_task: '分别设置 30° 和 60°，记录射程并比较两者。',
    },
  },
]

let failed = 0
for (const c of CASES) {
  const dir = join(outRoot, c.name)
  const evidencePath = join(dir, `${c.name}.evidence.json`)
  const htmlPath = join(dir, `${c.name}.html`)

  const sim = simulateDesign({ repoRoot, design: c.design, outPath: evidencePath })
  if (!sim.ok) {
    failed += 1
    console.log(`[FAIL] ${c.name} L2: ${sim.code || ''} ${sim.detail || JSON.stringify(sim.errors)}`)
    continue
  }
  const evidence = JSON.parse(readFileSync(evidencePath, 'utf8'))
  const ren = renderSingleFile({ repoRoot, design: c.design, evidence, outPath: htmlPath })
  if (!ren.ok) {
    failed += 1
    console.log(`[FAIL] ${c.name} RENDER: ${ren.code || ''} ${ren.detail || JSON.stringify(ren.errors)}`)
    continue
  }
  const ver = await verifySingleFile({ repoRoot, htmlPath: ren.html_path, evidencePath })
  if (!ver.ok) {
    failed += 1
    console.log(`[FAIL] ${c.name} L3: ${(ver.errors || []).join('; ')}`)
    continue
  }
  console.log(
    `[PASS] ${c.name} | ${(ren.bytes / 1024).toFixed(1)} KB | ` +
    `canvas ${(ver.checks.canvas_nonbg_ratio * 100).toFixed(2)}% | ` +
    `readout ${ver.checks.readout_max_rel_error.toExponential(2)} | ` +
    `network ${ver.checks.network_requests}`,
  )
}

console.log(`\n${CASES.length - failed}/${CASES.length} pass`)
process.exit(failed === 0 ? 0 : 1)
