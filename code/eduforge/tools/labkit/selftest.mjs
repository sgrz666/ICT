#!/usr/bin/env node
/**
 * LabKit 自检：抛体 / 单摆 / 直流电路各配方各跑一遍 L1 → L2 → 渲染 → L3。
 *
 * 跑法：node code/eduforge/tools/labkit/selftest.mjs
 * 产物：output/eduforge/candidates/labkit/selftest/<template>/<recipe>/...
 * 退出码：0 全过；1 任一失败。
 */
import { readFileSync } from 'node:fs'
import { dirname, join, resolve } from 'node:path'
import { fileURLToPath } from 'node:url'
import { renderSingleFile, simulateDesign, verifySingleFile } from './dispatcher.mjs'

const here = dirname(fileURLToPath(import.meta.url))
const repoRoot = resolve(here, '../../../..')
const outRoot = join(repoRoot, 'output', 'eduforge', 'candidates', 'labkit', 'selftest')

const CASES = [
  {
    name: 'mechanics.projectile/horizontal',
    design: {
      template_id: 'mechanics.projectile',
      recipe_id: 'horizontal',
      params: { v0: 15, angle_deg: 0, h0: 20 },
      why_recipe: '水平抛出时竖直方向是自由落体，因此飞行时间只由高度决定。',
      student_task: '改变初速度，记录射程和飞行时间并比较。',
    },
  },
  {
    name: 'mechanics.projectile/complementary',
    design: {
      template_id: 'mechanics.projectile',
      recipe_id: 'complementary',
      params: { v0: 20, h0: 0, angles_deg: [30, 60] },
      why_recipe: '30° 与 60° 互为余角，因此 sin2θ 相同，射程应相等。',
      student_task: '分别设置 30° 和 60°，记录射程并比较两者。',
    },
  },
  {
    name: 'mechanics.pendulum/period-length',
    design: {
      template_id: 'mechanics.pendulum',
      recipe_id: 'period-length',
      params: {},
      why_recipe: '周期由摆长决定，因为 T=2π√(L/g)，摆长翻 4 倍时周期只变 2 倍。',
      student_task: '改变摆长，记录每次的周期并比较倍数关系。',
    },
  },
  {
    name: 'mechanics.pendulum/angle-correction',
    design: {
      template_id: 'mechanics.pendulum',
      recipe_id: 'angle-correction',
      params: {},
      why_recipe: '振幅增大时小角度近似失效，因为周期会随初始角增大，30° 需按椭圆积分修正。',
      student_task: '改变初始角，记录每次的周期并比较小角度公式的偏差。',
    },
  },
  {
    name: 'circuits.ohms_law/ohms-law',
    design: {
      template_id: 'circuits.ohms_law',
      recipe_id: 'ohms-law',
      params: { voltage_v: 5, resistance_ohm: 100 },
      why_recipe: '同一电压下电流与电阻成反比，因为 I=U/R。',
      student_task: '改变电阻，记录电流表读数并比较。',
    },
  },
  {
    name: 'circuits.ohms_law/series',
    design: {
      template_id: 'circuits.ohms_law',
      recipe_id: 'series',
      params: { voltage_v: 5, resistance_ohm: 100, r2_ohm: 220 },
      why_recipe: '串联电流处处相同，因为只有一条路径，电压按阻值分配。',
      student_task: '改变 R2，记录总电流和两只电阻的电压并比较。',
    },
  },
  {
    name: 'circuits.ohms_law/parallel',
    design: {
      template_id: 'circuits.ohms_law',
      recipe_id: 'parallel',
      params: { voltage_v: 5, resistance_ohm: 100, r2_ohm: 220 },
      why_recipe: '并联各支路电压相同，因为两端都接在电源上，电流按电阻反比分配。',
      student_task: '改变 R2，记录两支路电流并比较总电流。',
    },
  },
]

let failed = 0
for (const c of CASES) {
  const dir = join(outRoot, c.name)
  const evidencePath = join(dir, 'evidence.json')
  const htmlPath = join(dir, 'index.html')

  const sim = simulateDesign({ repoRoot, design: c.design, outPath: evidencePath })
  if (!sim.ok) {
    failed += 1
    console.log(`[FAIL] ${c.name} L2: ${sim.code || ''} ${sim.detail || JSON.stringify(sim.errors)}`)
    continue
  }
  const evidence = JSON.parse(readFileSync(evidencePath, 'utf8'))
  const render = renderSingleFile({ repoRoot, design: c.design, evidence, outPath: htmlPath })
  if (!render.ok) {
    failed += 1
    console.log(`[FAIL] ${c.name} RENDER: ${render.code || ''} ${render.detail || JSON.stringify(render.errors)}`)
    continue
  }
  const ver = await verifySingleFile({ repoRoot, htmlPath: render.html_path, evidencePath })
  if (!ver.ok) {
    failed += 1
    console.log(`[FAIL] ${c.name} L3: ${(ver.errors || []).join('; ')}`)
    continue
  }
  console.log(
    `[PASS] ${c.name.padEnd(42)} | ${(render.bytes / 1024).toFixed(1)} KB | ` +
    `canvas ${(ver.checks.canvas_nonbg_ratio * 100).toFixed(2)}% | ` +
    `readout ${ver.checks.readout_max_rel_error.toExponential(2)} | ` +
    `network ${ver.checks.network_requests}`,
  )
}

console.log(`\n${CASES.length - failed}/${CASES.length} pass`)
process.exit(failed === 0 ? 0 : 1)
