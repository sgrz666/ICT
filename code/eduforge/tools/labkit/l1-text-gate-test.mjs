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
    design: { template_id: 'mechanics.projectile', recipe_id: 'horizontal', params: { v0: 15, angle_deg: 0, h0: 20 }, why_recipe: whyFlat, student_task: '拖动初速度滑块，观察并记录射程 R 与飞行时间 T；对比其他角度的射程，验证结论。' },
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
  // 能力标签门：覆盖「记录 / 对照 / 阻力」这类没有宾语的动词
  {
    name: 'horizontal：要求「记录」且已声明记录能力 ⇒ 必须放行',
    design: { template_id: 'mechanics.projectile', recipe_id: 'horizontal', params: { v0: 15, angle_deg: 0, h0: 20 }, why_recipe: whyFlat, student_task: '拖动初速度滑块，观察并记录射程 R 与飞行时间 T，比较不同初速度下的落点。' },
    expect: 'ok',
  },
  {
    name: 'horizontal：要求「对比其他角度」但无角度对照能力 ⇒ 必须拦',
    design: { template_id: 'mechanics.projectile', recipe_id: 'horizontal', params: { v0: 15, angle_deg: 0, h0: 20 }, why_recipe: whyFlat, student_task: '拖动初速度滑块，观察并记录射程 R，再对比其他角度的射程，验证 45° 最大。' },
    expect: 'TEXT_AFFORDANCE',
  },
  {
    name: 'oblique45：记录 + 角度对照 + 阻力都声明过 ⇒ 必须放行',
    design: { template_id: 'mechanics.projectile', recipe_id: 'oblique45', params: { v0: 20, angle_deg: 45, h0: 0 }, why_recipe: why45, student_task: '记录三组射程 R，对比 30° 与 60° 的对照轨迹，再把空气阻力拉到 0.01 观察结论翻转。' },
    expect: 'ok',
  },
  {
    name: 'complementary：只提阻力（已声明）⇒ 必须放行',
    design: { template_id: 'mechanics.projectile', recipe_id: 'complementary', params: { v0: 20, h0: 0, angles_deg: [30, 60] }, why_recipe: '因为 30° 与 60° 互为余角，sin2θ 相同，射程应相等。', student_task: '记录两条轨迹的射程 R，并把空气阻力拉到 0.01 观察比值怎么偏离 1。' },
    expect: 'ok',
  },
]

let bad = 0
for (const c of cases) {
  const r = checkDesign({ repoRoot, design: c.design })
    // 必须把**全部**错误码都摊开：只问「有没有 TEXT_AFFORDANCE」会让 PARAM_MISSING 之类藏在门后面过关，
  // 于是"这条拦住了"其实混着别的坏掉的东西。
  const codes = [...new Set((r.errors || []).map(e => e.code))]
  const got = codes.length === 0 ? 'ok' : (codes.length === 1 ? codes[0] : codes.join('+'))
  const pass = got === c.expect
  if (!pass) bad += 1
  const first = (r.errors || [])[0]
  console.log(`  ${pass ? 'PASS' : 'FAIL'}  ${c.name}  → ${got}${first ? '：' + first.message.slice(0, 56) : ''}`)
}
console.log(`\n${cases.length - bad}/${cases.length} 符合预期`)
process.exit(bad ? 1 : 0)
