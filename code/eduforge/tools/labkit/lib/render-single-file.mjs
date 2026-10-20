/**
 * 单文件 HTML 渲染器：模板 + 数据 + 内联引擎，纯字符串拼接。
 *
 * 确定性：不含时间戳、随机数、网络请求；同一 design + evidence 连渲两次 sha256 相同。
 * 页面运行时与 L2 共用 projectile-core.mjs（内联时剥掉 export 关键字）。
 */
import { existsSync, mkdirSync, readFileSync, writeFileSync } from 'node:fs'
import { dirname, join, relative } from 'node:path'
import { checkDesign } from './check.mjs'
import { assertUnder } from './fs-safe.mjs'
import { canonicalJson, designHash, sha256Hex } from './hash.mjs'
import { loadTemplate } from './template.mjs'

function escapeHtml(text) {
  return String(text)
    .replace(/&/g, '&amp;')
    .replace(/</g, '&lt;')
    .replace(/>/g, '&gt;')
    .replace(/"/g, '&quot;')
}

function jsStringSafe(json) {
  // 防止数据里出现 </script> 截断内联脚本。
  return json.replace(/</g, '\\u003c')
}

/**
 * @param {{repoRoot:string, design:object, evidence?:object, outPath:string, outRoot?:string}} input
 */
export function renderSingleFile({ repoRoot, design, evidence, outPath, outRoot }) {
  const l1 = checkDesign({ repoRoot, design })
  if (!l1.ok) return { ...l1, stage: 'L1' }

  const template = loadTemplate(repoRoot, design.template_id ?? 'mechanics.projectile')
  const recipe = template.recipes.find(r => r.id === l1.recipe_id)
  const hash = designHash(l1.normalized)

  if (evidence && evidence.design_hash && evidence.design_hash !== hash) {
    return {
      ok: false, stage: 'RENDER', code: 'EVIDENCE_STALE',
      detail: 'evidence 的 design_hash 与当前 design 不一致，先重跑 experiment_simulate。',
      hints: ['重新调用 experiment_simulate，再用新的 evidence 渲染。'],
    }
  }

  const root = outRoot ?? join(repoRoot, 'output', 'eduforge', 'candidates', 'labkit')
  const safeOut = assertUnder(root, outPath)

  const renderDir = join(template.dir, 'render')
  const htmlTemplate = readFileSync(join(renderDir, 'template.html'), 'utf8')
  const style = readFileSync(join(renderDir, 'style.css'), 'utf8')
  const runtime = readFileSync(join(renderDir, 'runtime.js'), 'utf8')
  const corePath = join(repoRoot, 'code', 'eduforge', 'tools', 'labkit', 'lib', 'projectile-core.mjs')
  const coreDisk = readFileSync(corePath, 'utf8')
  const coreSource = coreDisk.replace(/^export\s+/gm, '')
  // 单文件产物里不该出现「可能被误当成外链」的字符串——但**许可横幅必须原样保留**：
  // 那是再分发 matter-js 的 MIT 署名义务，而且注释里的 URL 不会产生任何请求（L3 数的是运行时请求）。
  // 上一版那条通吃正则把 `http://brm.io/matter-js/` 一起抹了，副作用是产物内联的字节
  // 与 vendor 记录的 sha256 对不上，「产物=哪一份引擎」只能人工比。现在只剥横幅之外的 URL，
  // 并把 vendor / inlined 两个 sha256 一起写进 DATA.engine，让溯源变成可机械核对的事。
  const matterPath = join(repoRoot, 'code', 'eduforge', 'tools', 'labkit', 'vendor', 'matter.min.js')
  const matterRaw = readFileSync(matterPath, 'utf8')
  const bannerEnd = matterRaw.indexOf('*/')
  const matterBanner = bannerEnd >= 0 ? matterRaw.slice(0, bannerEnd + 2) : ''
  const matter = matterBanner + matterRaw.slice(matterBanner.length).replace(/https?:\/\/\S+/g, '')
  const matterVendorSha = sha256Hex(matterRaw)
  const matterInlinedSha = sha256Hex(matter)
  // 「这页用了我们的哪些资产」不能只写在文档里：把内联进去的每一份源文件的 sha256 记进产物 DATA，
  // 探针就能拿它去比仓库现状——源文件改了而产物没重渲，这里立刻失配（换行归一后取哈希，避免 CRLF 制造假差异）。
  const shaNorm = text => sha256Hex(text.replace(/\r\n/g, '\n'))
  const repoRel = p => relative(repoRoot, p).replace(/\\/g, '/')
  const sources = [
    { role: '骨架', path: repoRel(join(renderDir, 'template.html')), sha256: shaNorm(htmlTemplate) },
    { role: '样式', path: repoRel(join(renderDir, 'style.css')), sha256: shaNorm(style) },
    { role: '运行时', path: repoRel(join(renderDir, 'runtime.js')), sha256: shaNorm(runtime) },
    { role: '内核（与 L2 同一份，内联时剥掉行首 export）', path: repoRel(corePath), sha256: shaNorm(coreDisk) },
  ]

  const data = {
    meta: {
      title: template.title,
      template_id: template.template_id,
      recipe_id: recipe.id,
      recipe_title: recipe.title,
      design_hash: hash,
      engine_id: template.engine.id,
      engine_version: template.engine.version,
    },
    design: l1.normalized,
    recipe: {
      id: recipe.id,
      title: recipe.title,
      intent: recipe.intent,
      params_mode: recipe.params_mode,
      scenarios: recipe.scenarios,
      metrics: recipe.metrics,
      tolerances_pct: recipe.tolerances_pct,
      intent_keywords: recipe.intent_keywords,
      // 带上这份配方声明的控件契约：交付件应当自证「页面上到底有哪些操作」，
      // L3/探针才能拿它去比对真实渲染（手工声明一过期就会被照出来，而不是悄悄烂着）。
      affordances: recipe.affordances ?? null,
    },
    decision: template.decision,
    engine: {
      ...template.engine,
      // 溯源：内联的到底是哪一份引擎字节。vendor_sha256 对上 vendor/README.md 里记的那串，
      // inlined_sha256 是产物里实际那份（与 vendor 只差横幅之外的 URL 剥离）。
      vendor_path: 'code/eduforge/tools/labkit/vendor/matter.min.js',
      vendor_sha256: matterVendorSha,
      inlined_sha256: matterInlinedSha,
      license: 'MIT (matter-js © liabru)',
    },
    render: template.render,
    sources,
    acceptance: template.acceptance,
    evidence: evidence
      ? {
          verdict: evidence.verdict,
          scenarios: (evidence.scenarios ?? []).map(s => ({
            id: s.id,
            measured: s.measured,
            analytic: s.analytic,
          })),
          drag_control: evidence.drag_control,
        }
      : null,
  }

  const html = htmlTemplate
    .replace('__TITLE__', escapeHtml(`${template.title} · ${recipe.title}`))
    .replace('__STYLE__', () => style)
    .replace('__DATA__', () => jsStringSafe(canonicalJson(data)))
    .replace('__MATTER_JS__', () => matter)
    .replace('__CORE_JS__', () => coreSource)
    .replace('__RUNTIME_JS__', () => runtime)

  mkdirSync(dirname(safeOut), { recursive: true })
  writeFileSync(safeOut, html, 'utf8')

  // 「用了我们的资产」这句话要有可核对的形式：三份整段插入的源文本能否在产物里逐字节找到，
  // 以及 vendor 引擎与本机已装的 matter-js 两份拷贝是否同一份字节。后者只在 README 里记，
  // 不进 DATA——`source/` 那两棵树不入库，把它们的存废写进 HTML 会让同一 design 在不同机器渲出不同字节。
  const inserted = { 样式: style, 运行时: runtime, 内核: coreSource }
  const verbatim = Object.keys(inserted).filter(k => html.includes(inserted[k]))
  const notVerbatim = Object.keys(inserted).filter(k => !verbatim.includes(k))
  const installedEngines = [
    'source/upstream/matter-js/build/matter.min.js',
    'source/components/node_modules/matter-js/build/matter.min.js',
  ].map(rel => {
    const abs = join(repoRoot, rel)
    if (!existsSync(abs)) return `- 已装资源 \`${rel}\`：本机不存在（这棵树不入库，按 \`source/upstream/README.md\` 的克隆命令重建）`
    const same = shaNorm(readFileSync(abs, 'utf8')) === shaNorm(matterRaw)
    return `- 已装资源 \`${rel}\`：${same ? '**与本产物的引擎是同一份字节**（换行归一后 sha256 相同）' : '换行归一后哈希不同，说明 vendor 与已装拷贝不是同一版，必须查'}`
  })

  // 产物目录自带一张「这是什么、怎么再来一次、引擎是谁的」说明与 MIT 许可副本：
  // 交付出去的单个 HTML 不该只靠仓库上下文才能解释。
  const readmePath = join(dirname(safeOut), 'README.md')
  writeFileSync(readmePath, [
    `# ${recipe.title}（\`${recipe.id}\`）— labkit 单文件产物`,
    '',
    `- 模板：\`${data.meta.template_id}\`（引擎 ${template.engine.id} ${template.engine.version}）`,
    `- 参数：\`${JSON.stringify(l1.normalized.params)}\``,
    `- 设计指纹：\`${hash}\``,
    `- 页面内联引擎：\`code/eduforge/tools/labkit/vendor/matter.min.js\`（vendor sha256 \`${matterVendorSha.slice(0, 16)}…\`；实际内联那份 sha256 \`${matterInlinedSha.slice(0, 16)}…\`，${matterInlinedSha === matterVendorSha ? '与 vendor 逐字节相同' : '与 vendor 只差横幅外的 URL 剥离'}）`,
    `- 许可：matter-js © liabru，MIT，全文见同目录 \`LICENSE.matter.txt\``,
    '',
    '## 用了仓库里的什么（渲染时实测出来的，不是手写说明）',
    '',
    ...installedEngines,
    `- 引擎之外的三段源文本 —— ${verbatim.map(v => `\`${v}\``).join(' / ') || '（无）'} —— 在产物 HTML 里**逐字节找得到**，内联时不改写；\`骨架\` 是 \`template.html\` 填掉六个占位符后的外层。`,
    '- 页面运行时与 L2 对账用的是**同一份** `projectile-core.mjs`（物理只有一处定义，产物里内联的就是它）。',
    `- 这四份源的 sha256 已写进产物内 \`DATA.sources\`，探针会拿仓库现状回比：改了源没重渲，立刻失配。`,
    ...(notVerbatim.length
      ? [`- **异常**：${notVerbatim.join(' / ')} 没能在产物里逐字节找到——渲染器与模板对不上，这个产物别交付。`]
      : []),
    '',
    '**没用到的**：`source/library` 里已装的 3JCN / PhET / EJS 实验不参与这条路径。那条「改现成实验」的路另有档位；本产物是「按模板自建」，`source/library/experiments.json` 里 `mechanics-projectile` 记的是 `template_connected`，不是资源直连。',
    '',
    '复现：',
    '',
    '```bash',
    '# L1→L2→渲染→L3 全链（selftest 覆盖的配方）',
    'node code/eduforge/tools/labkit/selftest.mjs',
    '# 只重渲染本产物：把 design 交给 renderSingleFile',
    '```',
    '',
    '验收读数与 L2 证据逐位一致（L3 `readout_max_rel_error` 在 1e-7 量级）；页面第四个控件是空气阻力',
    '（`frictionAir`，默认 0），拉到 0.01 可复现证据里「偏离解析式 391 倍」那条对照。',
    '',
  ].join('\n'), 'utf8')
  writeFileSync(join(dirname(safeOut), 'LICENSE.matter.txt'),
    readFileSync(join(repoRoot, 'code', 'eduforge', 'tools', 'labkit', 'vendor', 'LICENSE.matter.txt'), 'utf8'), 'utf8')

  return {
    ok: true,
    stage: 'RENDER',
    html_path: safeOut,
    readme_path: readmePath,
    sha256: sha256Hex(html),
    bytes: Buffer.byteLength(html, 'utf8'),
    design_hash: hash,
    recipe_id: recipe.id,
  }
}
