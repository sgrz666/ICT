/** L1「文案承诺 vs 页面控件」这道门的回归测试。
 *
 * 为什么单独一份：这道门是因为一句一路绿灯进了交付件的文案才加的
 * （dsh 写的 student_task 让student「点击发射」，而产物上只有暂停/重播）。
 * 加门而不留反例，下一次改规则时没人知道它本来要拦什么。
 * 跑法：node code/eduforge/tools/labkit/l1-text-gate-test.mjs
 */
import { checkDesign } from './lib/check.mjs'

const repoRoot = process.cwd()
const why45 = '因为 45° 时 sin2θ=1，射程 R=v0²sin2θ/g 最大，调节初速度可观察 R 随 v0² 增大。'
const whyFlat = '因为平抛竖直方向是自由落体，飞行时间只由高度 h0 决定，与初速度无关。'
const cases = [
  {
    name: 'oblique45：承诺不存在的「发射」按钮 ⇒ 必须拦',
    design: { template_id: 'mechanics.projectile', recipe_id: 'oblique45', params: { v0: 20, angle_deg: 45, h0: 0 }, why_recipe: why45, student_task: '拖动初速度滑块，观察并记录落点射程 R、飞行时间 T 与最高点高度 H；点击发射或重放，验证相同初速度下 45° 射程最大。' },
    expect: 'TEXT_AFFORDANCE',
  },
  {
    name: 'oblique45：改成只提「暂停 / 重播」⇒ 必须放行',
    design: { template_id: 'mechanics.projectile', recipe_id: 'oblique45', params: { v0: 20, angle_deg: 45, h0: 0 }, why_recipe: why45, student_task: '用「暂停 / 重播」控制动画，观察并记录落点射程 R、飞行时间 T 与最高点高度 H，验证 45° 射程最大。' },
    expect: 'ok',
  },
  {
    name: 'horizontal：要「对比其他角度」但既无第二场景也无对照开关 ⇒ 必须拦',
    design: { template_id: 'mechanics.projectile', recipe_id: 'horizontal', params: { v0: 15, h0: 20 }, why_recipe: whyFlat, student_task: '拖动初速度滑块，观察并记录射程 R 与飞行时间 T；对比其他角度的射程，验证结论。' },
    expect: 'TEXT_AFFORDANCE',
  },
  {
    name: 'oblique45：要对照且本配方确有对照叠加 ⇒ 必须放行',
    design: { template_id: 'mechanics.projectile', recipe_id: 'oblique45', params: { v0: 20, angle_deg: 45, h0: 0 }, why_recipe: why45, student_task: '勾上「叠加 30° / 60° 对照」，观察并记录三条轨迹的射程 R，验证 45° 最大。' },
    expect: 'ok',
  },
  {
    name: '文案提到不存在的开关「自动发射」⇒ 必须拦',
    design: { template_id: 'mechanics.projectile', recipe_id: 'oblique45', params: { v0: 20, angle_deg: 45, h0: 0 }, why_recipe: why45, student_task: '勾选「自动发射」，观察并记录射程 R 与飞行时间 T 的变化。' },
    expect: 'TEXT_AFFORDANCE',
  },
]

let bad = 0
for (const c of cases) {
  const r = checkDesign({ repoRoot, design: c.design })
  const hits = (r.errors || []).filter(e => e.code === 'TEXT_AFFORDANCE')
  const got = hits.length ? 'TEXT_AFFORDANCE' : (r.ok ? 'ok' : 'OTHER:' + (r.errors || []).map(e => e.code).join(','))
  const pass = got === c.expect
  if (!pass) bad += 1
  console.log(`  ${pass ? 'PASS' : 'FAIL'}  ${c.name}  → ${got}${hits.length ? '：' + hits[0].message.slice(0, 60) : ''}`)
}
console.log(`\n${cases.length - bad}/${cases.length} 符合预期`)
process.exit(bad ? 1 : 0)
