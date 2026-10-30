/**
 * dsh-labkit 交付包自检：走一次真实的 experiment_build 处理函数（L1→L2→渲染→L3→交付包），
 * 再核对三份文档是否落盘、内容是否包含关键段落、包清单能否解析。
 *
 * 跑法：node deep-agent/local-tools/dsh-labkit/selftest.mjs
 * 需要本机已装 Playwright Chromium（与 LabKit selftest 同一条依赖）。
 */
import { existsSync, readFileSync } from 'node:fs'
import { registerBuild } from './tools/build.mjs'

const tools = {}
const ctx = { tools: { register: tool => { tools[tool.name] = tool } } }
registerBuild(ctx, tool => tool)

const design = {
  template_id: 'mechanics.projectile',
  recipe_id: 'complementary',
  params: { v0: 20, h0: 0, angles_deg: [30, 60] },
  why_recipe: '因为 30° 与 60° 互补，sin2θ 相同，所以射程应当相等；用同一初速度对照两角，能把“射程相同”与“轨迹相同”区分开。',
  student_task: '拖动发射角滑块分别到 30° 与 60°，用“记录本次”按钮各记一次，比较两行射程与飞行时间；再改变初速度重复一次。',
}

let failed = 0
function check(name, ok, detail = '') {
  console.log(`${ok ? 'PASS' : 'FAIL'} ${name}${detail ? ` — ${detail}` : ''}`)
  if (!ok) failed += 1
}

const outName = process.argv[2] || 'selftest-package'
const result = await tools.experiment_build.execute({ ...design, out_name: outName }, {})
check('experiment_build ok', result.ok === true, result.summary?.split('\n')[0] ?? '')
if (!result.ok) {
  console.error(result.summary)
  process.exit(1)
}

for (const key of ['html_path', 'evidence_path', 'teacher_path', 'student_path', 'manifest_path']) {
  check(`${key} 存在`, typeof result.data[key] === 'string' && existsSync(result.data[key]), result.data[key] ?? '')
}

const teacher = readFileSync(result.data.teacher_path, 'utf8')
const student = readFileSync(result.data.student_path, 'utf8')
const manifest = JSON.parse(readFileSync(result.data.manifest_path, 'utf8'))

check('教师手册含课堂流程', teacher.includes('## 课堂流程（5E'))
check('教师手册含含答案数据表', teacher.includes('数据记录表（教师版'))
check('学生任务单含先预测', student.includes('## 先预测'))
check('学生任务单含空白数据表', student.includes('____'))
check('包清单 schema', manifest.schema === 'eduforge.labkit.delivery/v1')
check('包清单 design_hash', manifest.design_hash === result.data.design_hash)
check('包清单三份文档', manifest.artifacts.teacher?.file && manifest.artifacts.student?.file)
check('L2 通过', manifest.checks.l2.verdict === 'pass', `max ${manifest.checks.l2.max_deviation_pct}%`)
check('L3 零外链', manifest.checks.l3.network_requests === 0)
check('L3 读数一致', Number(manifest.checks.l3.readout_max_rel_error) < 1e-6)

console.log(failed ? `\n${failed} 项失败` : '\n交付包自检通过')
process.exit(failed ? 1 : 0)
