import { existsSync, readFileSync } from 'node:fs'
import { parseArgs } from 'node:util'
import { join } from 'node:path'
import { spawnSync } from 'node:child_process'
import { serviceRoot, installationAnchor, labkitEntry, runtimeRequire, sourceRoot } from './layout.mjs'
import { startRuntime } from './runtime.mjs'
const { values, positionals } = parseArgs({allowPositionals:true,options:{
  data:{type:'string'}, workspace:{type:'string'}, port:{type:'string',default:'3082'}, out:{type:'string'}, live:{type:'boolean',default:false},
}})
const action = positionals[0] || 'doctor'
try {
  if (action==='doctor') {
    const anchor=installationAnchor(); const require=runtimeRequire()
    const lock=JSON.parse(readFileSync(join(serviceRoot,'config/upstream.lock.json')))
    const checks={node_version:process.version,platform:process.platform,arch:process.arch,upstream_commit:lock.commit,
      native_boot:existsSync(require.resolve('@deepseek-ai/dsh/profile-boot')),
      labkit:existsSync(labkitEntry()),composition:existsSync(join(serviceRoot,'config/web.json')),
      packaged:anchor.startsWith(join(serviceRoot,'runtime')),credentials_present:Boolean(process.env.DEEPSEEK_API_KEY),
    }
    if(!checks.packaged){const git=spawnSync('git',['-C',sourceRoot,'rev-parse','HEAD'],{encoding:'utf8'});checks.upstream_matches_lock=git.status===0&&git.stdout.trim()===lock.commit}
    console.log(JSON.stringify(checks,null,2))
    if (!checks.native_boot || !checks.labkit || checks.upstream_matches_lock===false || Number(process.versions.node.split('.')[0])<24) process.exitCode=1
  } else if (action==='web' || action==='sdk') {
    await startRuntime({profile:action,dataRoot:values.data,workspace:values.workspace,port:Number(values.port)})
  } else if (action==='verify') {
    const result=spawnSync(process.execPath,['--test',join(serviceRoot,'tests','*.test.mjs')],{stdio:'inherit'})
    if(result.status!==0) process.exitCode=result.status||1
    else {
      if(existsSync(join(serviceRoot,'inventory.json'))){const {auditPackage}=await import('./package.mjs');const audit=await auditPackage(serviceRoot);if(!audit.ok)throw new Error(`PACKAGE_DRIFT: ${JSON.stringify(audit)}`)}
      const {verify}=await import('./verify.mjs'); await verify({live:values.live,out:values.out})
    }
  } else if (action==='package') {
    const {buildPackage}=await import('./package.mjs'); await buildPackage({outDir:values.out})
  } else throw new Error(`Unknown action ${action}; use doctor, web, sdk, verify, package`)
} catch(error) { console.error(`${error.code||'RUNTIME_ERROR'}: ${error.message}`); process.exitCode=1 }
