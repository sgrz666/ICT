/**
 * 交付包文档自检：对 3 个模板、8 个配方各跑一次 L1/L2，再用真实证据生成三份文档。
 *
 * 不跑 L3（浏览器实测由 selftest.mjs 覆盖），目的是在新增模板/配方时快速发现
 * 「文档生成对某个实验不成立」——例如某配方没有 ratios 场景、或 metrics 为空。
 *
 * 跑法：node deep-agent/local-tools/dsh-labkit/selftest-docs.mjs
 */
import { mkdirSync, readFileSync } from 'node:fs'
import { join } from 'node:path'
import { checkDesign, simulateDesign, loadTemplate } from './lib/labkit.mjs'
import { buildDeliveryDocs } from './lib/package.mjs'
import { outRoot, repoRoot } from './lib/paths.mjs'

const outDir = join(outRoot, 'selftest', 'docs-all')
mkdirSync(outDir, { recursive: true })

const TASKS = {
  horizontal: '拖动初速度滑块，用“记录本次”按钮记录三次射程与飞行时间；比较不同初速度下的读数。',
  oblique45: '拖动发射角滑块，用“记录本次”记录不同角度的射程与最高点；比较 30°、45°、60° 的读数。',
  complementary: '拖动发射角滑块分别到 30° 与 60°，用“记录本次”按钮各记一次，比较两行射程与飞行时间；再改变初速度重复一次。',
  'period-length': '把摆长依次设为 0.5、1.0、2.0 m，记录每次周期；比较摆长翻倍时周期的变化。',
  'angle-correction': '把初始角依次设为 5°、10°、30°，记录每次周期；比较小角度公式与实测的偏差。',
  'ohms-law': '把电阻依次设为 100、220、470 Ω，记录电流表读数；比较电流与电阻的关系。',
  series: '固定 R1=100 Ω，把 R2 从 100 Ω 调到 300 Ω；记录总电流与两只电阻上的电压。',
  parallel: '固定 R1=100 Ω，把 R2 从 100 Ω 调到 300 Ω；记录两支路电流与总电流。',
}

const WHYS = {
  'mechanics.projectile': '因为抛体的飞行时间、射程与最高点分别由竖直与水平分量决定，所以固定其他量、只改一个参数才能看出因果。',
  'mechanics.pendulum': '因为单摆周期由摆长与重力加速度决定，所以改变摆长并记录周期，才能验证 T 与 √L 的关系。',
  'circuits.ohms_law': '因为欧姆定律与串并联规律都描述电压、电流、电阻之间的定量关系，所以用读数与解析式对照才能判断规律是否成立。',
}

let failed = 0
for (const templateId of ['mechanics.projectile', 'mechanics.pendulum', 'circuits.ohms_law']) {
  const template = loadTemplate(repoRoot, templateId)
  for (const recipe of template.recipes) {
    const params = recipe.id === 'complementary'
      ? { v0: 20, h0: 0, angles_deg: [30, 60] }
      : { ...(recipe.scenarios?.[0]?.params ?? {}) }
    const design = {
      template_id: templateId,
      recipe_id: recipe.id,
      params,
      why_recipe: WHYS[templateId],
      student_task: TASKS[recipe.id],
    }

    const l1 = checkDesign({ repoRoot, design })
    if (!l1.ok) {
      console.log(`FAIL ${templateId}/${recipe.id} L1 ${l1.errors?.[0]?.code}: ${l1.errors?.[0]?.message}`)
      failed += 1
      continue
    }

    const evidencePath = join(outDir, `${templateId.replace(/\W/g, '_')}-${recipe.id}.evidence.json`)
    const sim = simulateDesign({ repoRoot, design, outPath: evidencePath })
    if (!sim.ok) {
      console.log(`FAIL ${templateId}/${recipe.id} L2 ${sim.code}: ${sim.detail ?? ''}`)
      failed += 1
      continue
    }

    const evidence = JSON.parse(readFileSync(evidencePath, 'utf8'))
    let docs
    try {
      docs = buildDeliveryDocs({
        repoRoot,
        design,
        evidence,
        checks: { network_requests: 0, canvas_nonbg_ratio: 0.02, range_changed: true, console_errors: [], readout_max_rel_error: 0 },
        html: { html_path: 'x.html', bytes: 1024, sha256: 'x' },
        paths: { dir: outDir, html: 'x.html', evidence: 'x.evidence.json', teacher: 'x.teacher.md', student: 'x.student.md', manifest: 'x.package.json' },
      })
    } catch (error) {
      console.log(`FAIL ${templateId}/${recipe.id} DOC ${error.message}`)
      failed += 1
      continue
    }

    const ok = docs.teacher.includes('## 课堂流程')
      && docs.student.includes('## 数据记录')
      && docs.student.includes('## 先预测')
      && docs.manifest.includes('eduforge.labkit.delivery/v1')
    console.log(`${ok ? 'PASS' : 'FAIL'} ${templateId}/${recipe.id} | teacher ${docs.teacher.length} chars | student ${docs.student.length} chars`)
    if (!ok) failed += 1
  }
}

console.log(failed ? `\n${failed} 项失败` : '\n8/8 配方文档生成通过')
process.exit(failed ? 1 : 0)
