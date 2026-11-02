/**
 * 交付包：一次通过 L1/L2/L3 的构建，同时落三份人能直接用的东西。
 *
 * - teacher.md：教师手册（学习目标、5E 流程、含答案的数据表、误区、预设问题）
 * - student.md：学生任务单（先预测、步骤、空表、分析、迁移）
 * - package.json：包清单（design_hash、文件、L2/L3 结果）
 *
 * 文案里的事实只来自三处：design、evidence、模板自带的 lesson.md / recipes.json。
 * 不在这一层重新解释物理，也不写公式副本——公式用模板 formulas_display 的原文。
 */
import { existsSync, mkdirSync, readFileSync, writeFileSync } from 'node:fs'
import { basename, dirname, join } from 'node:path'
import { canonicalJson, getRecipe, loadTemplate, sha256Hex } from './labkit.mjs'

const PARAM_META = {
  v0: ['初速度', 'm/s'],
  angle_deg: ['发射角', '°'],
  h0: ['初始高度', 'm'],
  friction_air: ['空气阻力系数', ''],
  angles_deg: ['互补角', '°'],
  length_m: ['摆长', 'm'],
  angle0_deg: ['初始角', '°'],
  voltage_v: ['电源电压', 'V'],
  resistance_ohm: ['电阻', 'Ω'],
  r2_ohm: ['第二只电阻', 'Ω'],
}

const RANGE_META = {
  v0_range: ['初速度', 'm/s'],
  angle_range: ['发射角', '°'],
  angle_range_oblique: ['斜抛发射角', '°'],
  h0_range: ['初始高度', 'm'],
  length_range: ['摆长', 'm'],
  voltage_range: ['电源电压', 'V'],
  resistance_range: ['电阻', 'Ω'],
}

const METRIC_META = {
  T: ['飞行时间 T', 's'],
  R: ['射程 R', 'm'],
  H: ['最高点 H', 'm'],
  apex_y: ['最高点 y', 'm'],
  ratio_R: ['射程比 R(θ)/R(90°−θ)', ''],
  I: ['电流 I', 'A'],
  U: ['电压 U', 'V'],
  U1: ['R1 两端电压 U1', 'V'],
  U2: ['R2 两端电压 U2', 'V'],
  I1: ['支路电流 I1', 'A'],
  I2: ['支路电流 I2', 'A'],
  Req: ['总电阻 Req', 'Ω'],
}

const STAGE_HINT = {
  'mechanics.projectile': '高中物理：运动的合成与分解、抛体运动',
  'mechanics.pendulum': '高中物理：简谐运动、单摆周期',
  'circuits.ohms_law': '初中物理：欧姆定律、串并联电路',
}

/** 每个配方在「一页速览」里优先展示的那条公式；找不到时退回 formulas_display 的第一条。 */
const FORMULA_KEY = {
  'mechanics.projectile': { horizontal: 'T', oblique45: 'R', complementary: 'ratio_R' },
  'mechanics.pendulum': { 'period-length': 'T0', 'angle-correction': 'Texact' },
  'circuits.ohms_law': { 'ohms-law': 'ohm', series: 'series', parallel: 'parallel' },
}

const SCHEMA = 'eduforge.labkit.delivery/v1'

const METRIC_ORDER = ['T', 'R', 'H', 'apex_y', 'ratio_R', 'I', 'U', 'U1', 'U2', 'I1', 'I2', 'Req']

function sortMetrics(keys) {
  return [...keys].sort((a, b) => {
    const ia = METRIC_ORDER.indexOf(a)
    const ib = METRIC_ORDER.indexOf(b)
    if (ia < 0 && ib < 0) return a.localeCompare(b)
    if (ia < 0) return 1
    if (ib < 0) return -1
    return ia - ib
  })
}

function fmtNum(v, digits = 4) {
  if (typeof v !== 'number' || !Number.isFinite(v)) return '—'
  const abs = Math.abs(v)
  if (abs >= 100) return v.toFixed(2)
  if (abs >= 1) return v.toFixed(digits)
  if (abs === 0) return '0'
  return v.toPrecision(4)
}

function unitSuffix(unit) {
  if (!unit) return ''
  return ['°', '%'].includes(unit) ? unit : ` ${unit}`
}

function paramText(params) {
  if (!params || typeof params !== 'object' || Array.isArray(params)) return '—'
  const parts = Object.entries(params).map(([key, value]) => {
    const [label, unit] = PARAM_META[key] ?? [key, '']
    const text = Array.isArray(value) ? value.join(' / ') : String(value)
    return `${label} ${text}${unitSuffix(unit)}`
  })
  return parts.length ? parts.join('，') : '—'
}

function metricLabel(key) {
  const [label, unit] = METRIC_META[key] ?? [key, '']
  return unit ? `${label} (${unit})` : label
}

function metricKeys(scenario) {
  const keys = new Set()
  for (const [key, value] of Object.entries(scenario?.measured ?? {})) {
    if (typeof value === 'number') keys.add(key)
  }
  for (const [key, value] of Object.entries(scenario?.analytic ?? {})) {
    if (typeof value === 'number') keys.add(key)
  }
  return sortMetrics(keys)
}

function readingText(obj, keys) {
  if (!obj) return '—'
  const parts = keys
    .filter(key => typeof obj[key] === 'number')
    .map(key => `${key}=${fmtNum(obj[key])}`)
  return parts.length ? parts.join('，') : '—'
}

/** 从 lesson.md 里取出指定配方那一节：实验目的 / 操作步骤 / 观察要点 / 常见误区。 */
function parseLesson(text, recipeId) {
  const lines = String(text ?? '').split(/\r?\n/)
  const start = lines.findIndex(line => /^##\s+/.test(line) && line.includes(`（${recipeId}）`))
  if (start < 0) return {}
  let end = lines.findIndex((line, index) => index > start && /^##\s+/.test(line))
  if (end < 0) end = lines.length
  const fields = {}
  let key = null
  for (let index = start + 1; index < end; index += 1) {
    const line = lines[index]
    const match = line.match(/^-\s+\*\*(.+?)\*\*[：:]\s*(.*)$/)
    if (match) {
      key = match[1].trim()
      fields[key] = match[2].trim()
      continue
    }
    if (key && line.trim()) fields[key] = `${fields[key]} ${line.trim()}`.trim()
  }
  return fields
}

function maxDeviation(evidence) {
  let max = 0
  for (const scenario of evidence?.scenarios ?? []) {
    const keys = new Set([
      ...Object.keys(scenario?.measured ?? {}),
      ...Object.keys(scenario?.analytic ?? {}),
    ])
    for (const key of keys) {
      const measured = scenario?.measured?.[key]
      const analytic = scenario?.analytic?.[key]
      if (typeof measured !== 'number' || typeof analytic !== 'number' || analytic === 0) continue
      max = Math.max(max, Math.abs((measured - analytic) / analytic) * 100)
    }
    for (const check of scenario?.checks ?? []) {
      if (typeof check?.rel_error_pct === 'number') max = Math.max(max, check.rel_error_pct)
    }
  }
  return max
}

function formulaLines(template) {
  const formulas = template?.acceptance?.formulas_display
  if (!formulas || typeof formulas !== 'object') return []
  return Object.entries(formulas).map(([key, value]) => `- \`${key}\`：${value}`)
}

function rangeLines(template) {
  const decision = template?.decision
  if (!decision || typeof decision !== 'object') return []
  return Object.entries(decision)
    .filter(([key, value]) => key.endsWith('_range') && Array.isArray(value) && value.length === 2)
    .map(([key, value]) => {
      const [label, unit] = RANGE_META[key] ?? [key, '']
      return `${label} ${value[0]}–${value[1]}${unitSuffix(unit)}`
    })
}

function studentTable(_recipe, evidence) {
  const first = (evidence?.scenarios ?? []).find(s => s?.params && Object.keys(s.params).length)
  const allKeys = metricKeys(first)
  const metrics = allKeys.filter(key => !(key === 'apex_y' && allKeys.includes('H')))
  const header = `| 场景 | 参数 | ${metrics.map(metricLabel).join(' | ')} |`
  const divider = `|---|---|${metrics.map(() => '---').join('|')}|`
  const rows = []
  for (const scenario of evidence?.scenarios ?? []) {
    if (!scenario.params || Object.keys(scenario.params).length === 0) continue
    if (scenario.id === 'ratio') continue
    rows.push(`| ${scenario.id} | ${paramText(scenario.params)} | ${metrics.map(() => '____').join(' | ')} |`)
  }
  if (!rows.length) rows.push(`| 1 | ${paramText({})} | ${metrics.map(() => '____').join(' | ')} |`)
  return [header, divider, ...rows].join('\n')
}

function teacherTable(_recipe, evidence) {
  const header = `| 场景 | 参数 | 引擎读数（实测） | 解析值 | 偏差（%） |`
  const divider = '|---|---|---|---|---|'
  const rows = []
  for (const scenario of evidence?.scenarios ?? []) {
    const allKeys = metricKeys(scenario)
    const keys = allKeys.filter(key => !(key === 'apex_y' && allKeys.includes('H')))
    let worst = 0
    for (const key of keys) {
      const measured = scenario?.measured?.[key]
      const analytic = scenario?.analytic?.[key]
      if (typeof measured !== 'number' || typeof analytic !== 'number' || analytic === 0) continue
      worst = Math.max(worst, Math.abs((measured - analytic) / analytic) * 100)
    }
    for (const check of scenario?.checks ?? []) {
      if (typeof check?.rel_error_pct === 'number') worst = Math.max(worst, check.rel_error_pct)
    }
    rows.push(`| ${scenario.id} | ${paramText(scenario.params)} | ${readingText(scenario.measured, keys)} | ${readingText(scenario.analytic, keys)} | ${fmtNum(worst, 3)} |`)
  }
  return [header, divider, ...rows].join('\n')
}

function qualityLine(checks) {
  const c = checks ?? {}
  const canvas = typeof c.canvas_nonbg_ratio === 'number' ? `${fmtNum(c.canvas_nonbg_ratio * 100, 2)}%` : '—'
  const readout = typeof c.readout_max_rel_error === 'number' ? c.readout_max_rel_error.toExponential(2) : '—'
  return `网络请求 ${c.network_requests ?? '—'} · canvas 非背景 ${canvas} · 改参${c.range_changed ? '有效' : '无效'} · console error ${(c.console_errors ?? []).length} · 读数误差 ${readout}`
}

function lessonOr(fields, key, fallback) {
  return fields[key] && fields[key].trim() ? fields[key].trim() : fallback
}

/**
 * 生成三份交付物的文本。
 * @returns {{teacher: string, student: string, manifest: string, manifestObject: object}}
 */
export function buildDeliveryDocs({ repoRoot, design, evidence, checks, html, paths }) {
  const template = loadTemplate(repoRoot, design.template_id)
  const recipe = getRecipe(template, design.recipe_id)
  const lessonPath = join(template.dir, 'lesson.md')
  const lesson = existsSync(lessonPath) ? parseLesson(readFileSync(lessonPath, 'utf8'), design.recipe_id) : {}

  const purpose = lessonOr(lesson, '实验目的', recipe.intent)
  const steps = lessonOr(lesson, '操作步骤', design.student_task)
  const observe = lessonOr(lesson, '观察要点', recipe.intent)
  const misconception = lessonOr(lesson, '常见误区', '先让学生写下预测，再用读数纠正。')
  const stage = STAGE_HINT[template.template_id] ?? '按本地课标调整'
  const ranges = rangeLines(template)
  const formulas = formulaLines(template)
  const formulaMap = template?.acceptance?.formulas_display ?? {}
  const formulaKey = FORMULA_KEY[template.template_id]?.[recipe.id]
    ?? (recipe.metrics ?? []).find(key => formulaMap[key])
    ?? Object.keys(formulaMap)[0]
  const primaryFormula = formulaKey ? formulaMap[formulaKey] : recipe.intent
  const deviation = maxDeviation(evidence)
  const l3 = qualityLine(checks)
  const designHash = evidence?.design_hash ?? ''
  const preferredParams = ['angle_deg', 'angles_deg', 'length_m', 'resistance_ohm', 'voltage_v', 'v0']
  const primaryParam = preferredParams.find(key => key in (design.params ?? {}))
    ?? Object.keys(design.params ?? {})[0]
  const primaryParamLabel = primaryParam ? (PARAM_META[primaryParam]?.[0] ?? primaryParam) : '实验条件'
  const firstScenario = (evidence?.scenarios ?? []).find(s => s?.params && Object.keys(s.params).length)
  const measuredKeys = metricKeys(firstScenario)
  const primaryMetric = ['R', 'T', 'I', 'H'].find(key => measuredKeys.includes(key))
    ?? measuredKeys[0]
    ?? (recipe.metrics ?? [])[0]
    ?? '读数'
  const primaryMetricLabel = metricLabel(primaryMetric)
  const recordHint = recipe.affordances?.buttons?.includes('记录本次')
    ? '点击页面上的“记录本次”把读数写进页面表格，再抄到本单。'
    : '把页面上的读数抄到本单的表格里。'
  const file = name => basename(String(name ?? ''))
  const htmlName = file(html?.html_path ?? paths?.html)
  const evidenceName = file(paths?.evidence)
  const studentName = file(paths?.student)
  const manifestName = file(paths?.manifest)

  const teacher = [
    `# ${template.title} · ${recipe.title} — 教师手册`,
    '',
    `> 本手册在 L1 设计校验、L2 物理对账、L3 离线实测全部通过后生成。设计哈希 \`${designHash}\`，设计与证据绑定；改了参数，旧证据立即失配。`,
    '',
    '## 一页速览',
    '',
    '| 项 | 内容 |',
    '|---|---|',
    `| 适用学段 | ${stage}（按人教版章节整理，其他版本请按课标调整） |`,
    '| 建议时长 | 40 分钟（可拆成 1 课时探究 + 1 课时讲评） |',
    '| 实验类型 | 探究 + 验证 |',
    `| 核心公式 | ${primaryFormula} |`,
    `| 学生要做 | ${design.student_task} |`,
    `| 可调范围 | ${ranges.length ? ranges.join('；') : '由页面控件决定'} |`,
    `| 物理对账 | L2 ${evidence?.verdict ?? '—'}，最大偏差 ${fmtNum(deviation, 3)}%（容差 1%） |`,
    `| 离线实测 | ${l3} |`,
    '',
    '## 学习目标',
    '',
    `1. 能说出本实验要验证的关系：${purpose}`,
    `2. 能用自己的话解释：${observe}`,
    `3. 能识别并纠正一个前概念：${misconception}`,
    '',
    '## 实验原理',
    '',
    recipe.intent,
    '',
    ...formulas,
    '',
    '## 课堂流程（5E，40 分钟）',
    '',
    '### 引入（5 分钟）',
    '',
    `先不要打开页面。提出问题：“${misconception}” 你同意吗？让学生把判断和理由写在任务单的“先预测”里。`,
    '',
    '### 探究（15 分钟）',
    '',
    `学生按任务单操作：${design.student_task}`,
    '',
    '巡视时只提醒两件事：一次只改一个变量；每组读数至少记录一次。',
    '',
    '### 解释（10 分钟）',
    '',
    '把学生的读数与页面上的解析对照放在一起。先让学生说“你看到了什么”，再给公式；不要用公式替代观察。',
    '',
    '### 迁移（5 分钟）',
    '',
    `换一组参数或条件，问：结论还成立吗？边界在哪里？可参考任务单的迁移题。`,
    '',
    '### 评价（5 分钟）',
    '',
    '出口条：用一句话写出结论，并举一个生活或工程中的例子。能区分“读数相同”与“轨迹相同”的答案优先展示。',
    '',
    '## 操作步骤',
    '',
    steps,
    '',
    '## 数据记录表（教师版，含实测与解析值）',
    '',
    teacherTable(recipe, evidence),
    '',
    '> 学生版是同一张表的空表。实测值来自页面运行时同一份物理内核，解析值来自独立参考式；两者在 1% 容差内视为通过。',
    '',
    '## 常见误区与应对',
    '',
    `- **误区**：${misconception}`,
    '- **应对**：先让学生预测，再让读数说话；不要一上来就给正确结论。',
    '- **追问**：你的预测和读数不一致时，最可能改的是哪个条件？',
    '',
    '## 预设学生问题',
    '',
    `- “为什么${primaryMetricLabel}不是随${primaryParamLabel}线性变化？”（引导看公式或图像，而不是背结论）`,
    '- “页面读数和公式对不上时，先检查什么？”（先看参数是否出了配方范围、页面是否被改坏）',
    '- “这个结论在什么条件下不成立？”（把模型边界变成讨论题）',
    '',
    '## 质检与文件',
    '',
    '| 检查 | 结果 |',
    '|---|---|',
    '| L1 设计与文案 | pass（构建前置） |',
    `| L2 物理对账 | ${evidence?.verdict ?? '—'}，最大偏差 ${fmtNum(deviation, 3)}% |`,
    `| L3 离线实测 | ${l3} |`,
    `| 设计哈希 | \`${designHash}\` |`,
    '',
    `- 实验页面：\`${htmlName}\`${html?.bytes ? `（${(html.bytes / 1024).toFixed(1)} KB）` : ''}`,
    `- 物理证据：\`${evidenceName}\``,
    `- 学生任务单：\`${studentName}\``,
    `- 包清单：\`${manifestName}\``,
    '',
    '实验页面可离线运行，不需要网络；页面与证据同目录，便于归档和复查。',
    '',
  ].join('\n')

  const student = [
    `# ${template.title} · ${recipe.title} — 学生任务单`,
    '',
    '姓名：____________________　班级：____________________　日期：____________________',
    '',
    '## 实验目的',
    '',
    purpose,
    '',
    '## 先预测（动手前完成）',
    '',
    `1. 当你改变${primaryParamLabel}时，你预计${primaryMetricLabel}会怎样变化？写下你的预测和理由。`,
    '2. 你预计表格中哪一组读数最大或最小？为什么？',
    '',
    '## 操作步骤',
    '',
    steps,
    '',
    '## 数据记录',
    '',
    studentTable(recipe, evidence),
    '',
    `> ${recordHint}`,
    '',
    '## 分析与结论',
    '',
    '1. 比较你的预测与实测读数。哪一条最出乎意料？',
    '2. 实测值与解析值之间的最大偏差是多少？这个偏差说明模型在什么范围内可信？',
    '3. 用一句话写出本实验的结论。',
    '',
    '结论：________________________________________________________________________',
    '',
    '## 迁移',
    '',
    `1. 如果把${primaryParamLabel}再增大（或减小）一倍，${primaryMetricLabel}会怎样？用公式或图像说明。`,
    '2. 举一个生活或工程中的例子，说明这个规律在起作用。',
    '',
    '## 使用提示',
    '',
    '- 本页面是单文件 HTML，双击即可打开，不需要联网。',
    '- 每次只改一个变量；改完等读数稳定再记录。',
    '- 如果页面读数与公式明显对不上，先检查参数是否还在配方范围内。',
    '',
  ].join('\n')

  const manifestObject = {
    schema: SCHEMA,
    design,
    design_hash: designHash,
    template: {
      id: template.template_id,
      title: template.title,
      recipe_id: recipe.id,
      recipe_title: recipe.title,
      stage,
    },
    artifacts: {
      html: { file: htmlName, bytes: html?.bytes ?? null, sha256: html?.sha256 ?? null },
      evidence: { file: evidenceName, sha256: evidence ? sha256Hex(canonicalJson(evidence)) : null, hash_encoding: 'canonical-json' },
      render_manifest: { file: html?.artifact_manifest_path ? basename(html.artifact_manifest_path) : null },
      teacher: { file: basename(paths?.teacher ?? 'teacher.md') },
      student: { file: studentName },
    },
    checks: {
      l2: { verdict: evidence?.verdict ?? null, max_deviation_pct: Number(deviation.toFixed(6)), scenario_count: evidence?.scenarios?.length ?? 0 },
      l3: {
        design_hash: checks?.design_hash ?? null,
        html_sha256: checks?.html_sha256 ?? null,
        evidence_sha256: checks?.evidence_sha256 ?? null,
        network_requests: checks?.network_requests ?? null,
        canvas_nonbg_ratio: checks?.canvas_nonbg_ratio ?? null,
        range_changed: checks?.range_changed ?? null,
        console_errors: checks?.console_errors ?? [],
        readout_max_rel_error: checks?.readout_max_rel_error ?? null,
      },
    },
  }

  return {
    teacher,
    student,
    manifest: JSON.stringify(manifestObject, null, 2),
    manifestObject,
  }
}

/** 落盘三份交付物；返回路径，供工具摘要与 data 使用。 */
export function writeDeliveryPackage(args) {
  const docs = buildDeliveryDocs(args)
  const dir = args.paths?.dir ?? (args.paths?.teacher ? dirname(args.paths.teacher) : null)
  if (dir) mkdirSync(dir, { recursive: true })
  writeFileSync(args.paths.teacher, docs.teacher, 'utf8')
  writeFileSync(args.paths.student, docs.student, 'utf8')
  writeFileSync(args.paths.manifest, docs.manifest, 'utf8')
  return {
    teacher_path: args.paths.teacher,
    student_path: args.paths.student,
    manifest_path: args.paths.manifest,
    manifest: docs.manifestObject,
  }
}
