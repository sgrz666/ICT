import { mkdtempSync, writeFileSync } from 'node:fs'
import { tmpdir } from 'node:os'
import { join } from 'node:path'
import { sourceRoot, runtimeImport } from './layout.mjs'
import { startRuntime } from './runtime.mjs'

const output=process.argv[2]
const variant=process.argv[3]||'pruned'
let rt
if(variant==='baseline') {
  const data=mkdtempSync(join(tmpdir(),'eduforge-original-'))
  process.env.DSH_HOME=join(data,'home');process.env.DSH_TELEMETRY_DISABLED='1';process.chdir(data)
  const quiet=join(data,'quiet.patch.yml')
  writeFileSync(quiet,'- id: web-runtime\n  config:\n    printUrl: false\n    openBrowser: false\n    surfaceContext: true\n')
  const {runProfile}=await runtimeImport('@deepseek-ai/dsh/profile-boot')
  const {loadLayeredEnv}=await runtimeImport('@deepseek-ai/dsh-app-boot')
  const start=performance.now()
  rt=await runProfile({profile:'web',environment:loadLayeredEnv('benchmark'),patchFiles:[join(sourceRoot,'../patches/ict-web-pruned.patch.yml'),quiet],args:['--no-open','--port','0']})
  await rt.ctx.loader.await();rt.startupMs=performance.now()-start
}else{
  rt=await startRuntime({dataRoot:mkdtempSync(join(tmpdir(),'eduforge-benchmark-')),port:0,quiet:true})
}
await (await runtimeImport('@deepseek-ai/dsh-app-boot')).auditStartupEntries(rt.ctx,'benchmark',()=>{})
await new Promise(r=>setTimeout(r,1000))
const modules=Array.from(rt.ctx.loader.entries()).filter(e=>e.fiber).map(e=>({id:e.id,name:e.options.name,state:e.fiber.state}))
const record={variant,startup_ms:Math.round(rt.startupMs),idle_rss_bytes:process.memoryUsage().rss,loaded_plugin_rows:modules.length,
  presets:rt.ctx.get('agentPresets')?await rt.ctx.agentPresets.list():[],modules,scope:'One fresh process after 1s idle. Baseline uses existing privacy overlay; no model turns. Source tree size is not a runtime-size comparator.'}
await rt.ctx.fiber.dispose()
if(output)writeFileSync(output,JSON.stringify(record,null,2)+'\n')
console.log(JSON.stringify({...record,modules:undefined},null,2))
