/** Explicit maintainer command: recompose pinned upstream, never edit it. */
import { mkdirSync, readFileSync, writeFileSync, readdirSync } from 'node:fs'
import { join } from 'node:path'
import { createHash } from 'node:crypto'
import { execFileSync } from 'node:child_process'
import { sourceRoot, serviceRoot, runtimeImport, runtimeRequire } from './layout.mjs'

export const PIN = '687f282e8625c6b8d11ff58211a90524be2e4317'
export const excluded = new Set([
  'otel','session-telemetry-otel','session-log-deepseek','plugin-package-inventory-deepseek',
  'command-feedback','deepseek-account','llm-deepseek-account','desktop-product-telemetry',
  'product-analytics','message-feedback','ui-message-feedback','account-controller',
  'ui-settings-account','ui-settings-session-log','schedule','tool-schedule',
  'workflow-ptc','tool-workflow','ptc-runtime','ptc-runtime-node','tool-cordis',
  'cordis-host-runner','cordis-inspect-providers','tool-plugin-manager','tool-plugin-market',
  'plugin-manager','plugin-market','ui-settings-plugins','ui-plugin-market',
  'web','web-fetch','web-search','web-deepseek-api','web-search-deepseek','web-fetch-http','tool-web',
  'mcp-resources','hmr','open-in-app','ui-open-in-app','office-to-pdf',
  'ui-schedule','ui-workflow-run','ui-cordis','ui-plugin-manager','ui-settings-plugin-inventory',
  'ui-settings-web-search','harness-dev-context','client-hmr','tool-working-directory','skill-office','workspace-dependencies',
])
function trim(entries) {
  return entries.filter(r => !excluded.has(r.id) && r.disabled !== true).map(r => {
    if (r.group) r.config = trim(r.config)
    if (r.config?.plugins) r.config.plugins = trim(r.config.plugins)
    return r
  })
}
export async function snapshot() {
  const commit = execFileSync('git', ['-C', sourceRoot, 'rev-parse', 'HEAD'], { encoding:'utf8' }).trim()
  if (commit !== PIN) throw new Error(`UPSTREAM_DRIFT: expected ${PIN}, got ${commit}`)
  const { loadOverlayPatches, composeEntries } = await runtimeImport('@deepseek-ai/dsh-app-boot')
  const read = path => loadOverlayPatches('eduforge', join(sourceRoot, path))
  const base = read('packages/bundle/base/cordis.patch.yml')
  const web = trim(composeEntries([base, read('packages/bundle/web-app/cordis.patch.yml')]))
  const standard = trim(composeEntries([read('packages/bundle/web-app/presets/standard.patch.yml')]))[0]
  standard.id = 'preset-eduforge-dev'
  Object.assign(standard.config, { id:'eduforge-dev', name:'开发助手', description:'原生文件、命令、技能、规划与子智能体；工作区写入受控。', order:2 })
  standard.config.plugins.find(r => r.id === 'persona').config.prefix = '你是启智AGENT开发助手，基于 {{model}} 模型。以可复核的文件、命令和测试完成用户任务。'
  standard.config.plugins.push({id:'tool-working-directory',name:'@deepseek-ai/dsh-tool-working-directory'})
  const teacher = {
    id:'preset-physics-lab', name:'@deepseek-ai/dsh-agent-preset', config:{
      id:'physics-lab', name:'教学实验', order:1, description:'由真实 LabKit 引擎生成并验证离线实验课。',
      plugins:[
        { id:'persona', name:'@deepseek-ai/dsh-persona', config:{prefix:'你是启智AGENT教学实验助手。先询问会改变设计的必要信息，使用 experiment_recipes 与 experiment_validate 选方案，再用 experiment_build 交付。只声称工具实际验证的能力；失败时如实说明。不手写仿真、不修改容差。'} },
        { id:'time-context', name:'@deepseek-ai/dsh-time-context' },
        structuredClone(standard.config.plugins.find(r => r.id === 'compaction')),
        { id:'tool-ask-user', name:'@deepseek-ai/dsh-tool-ask-user' },
        { id:'tool-present', name:'@deepseek-ai/dsh-tool-present' },
        { id:'eduforge-labkit', name:'@eduforge/labkit-plugin' },
      ],
    },
  }
  web.push(teacher, standard)
  const policy = web.find(r => r.id === 'sandbox-policy')
  policy.config.mode = 'workspace-write'
  web.find(r => r.id === 'approval').config.policy = 'ask'
  web.find(r => r.id === 'agent-preset-registry').config.default = 'physics-lab'
  web.find(r => r.id === 'tools').config = { mode:'native' }
  // Programmatic carrier retains the native developer core, without Web preset selection.
  // SDK itself supplies no approval channel; the unchanged approval service fails closed.
  const sdk = trim(composeEntries([base, read('packages/bundle/sdk-app/cordis.patch.yml')]))
  sdk.find(r => r.id === 'sandbox-policy').config.mode = 'workspace-write'
  sdk.find(r => r.id === 'approval').config.policy = 'ask'
  sdk.find(r => r.id === 'sdk-jsonrpc-server').config.maxTokensAsSuccess = false
  const configDir = join(serviceRoot,'config'); mkdirSync(configDir,{recursive:true})
  for(const [name,rows] of Object.entries({web,sdk})) writeFileSync(join(configDir,`${name}.json`),JSON.stringify(rows,null,2)+'\n')
  const brandPatch = execFileSync('git',['-C',sourceRoot,'diff','--binary','HEAD','--','apps/web','packages/bundle/web-app','packages/client','tsconfig.client.json','pnpm-lock.yaml'],{maxBuffer:16*1024*1024})
  writeFileSync(join(configDir,'brand-baseline.patch'),brandPatch)
  const localBrand={}
  const brandRoot=join(sourceRoot,'packages/client/ui-brand-qizhi')
  const visit=(folder,prefix='')=>{for(const e of readdirSync(folder,{withFileTypes:true})){
    if(['node_modules','lib','tests'].includes(e.name))continue
    const rel=prefix+e.name
    if(e.isDirectory())visit(join(folder,e.name),rel+'/')
    else if(!e.name.startsWith('.env'))localBrand['packages/client/ui-brand-qizhi/'+rel]=new Uint8Array(readFileSync(join(folder,e.name)))
  }}
  visit(brandRoot)
  const {zipSync}=runtimeRequire()('fflate')
  const brandArchive=zipSync(localBrand)
  writeFileSync(join(configDir,'brand-local-source.zip'),brandArchive)
  const brandFiles=Object.fromEntries(Object.entries(localBrand).map(([p,b])=>[p,createHash('sha256').update(b).digest('hex')]))
  writeFileSync(join(configDir,'upstream.lock.json'), JSON.stringify({commit,version:JSON.parse(readFileSync(join(sourceRoot,'apps/cli/package.json'))).version,brand_patch_sha256:createHash('sha256').update(brandPatch).digest('hex'),brand_local_archive_sha256:createHash('sha256').update(brandArchive).digest('hex'),brand_local_files:brandFiles,excluded_plugin_ids:[...excluded].sort()},null,2)+'\n')
}
if (process.argv.includes('--write')) await snapshot()
