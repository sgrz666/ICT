import { existsSync, mkdirSync, writeFileSync, readFileSync } from 'node:fs'
import { join, resolve } from 'node:path'
import { pathToFileURL } from 'node:url'
import { homedir } from 'node:os'
import { installationAnchor, labkitEntry, labkitRoot, runtimeImport, runtimeRequire, serviceRoot } from './layout.mjs'
import { materializeComposition } from './composition.mjs'

export function defaultDataRoot() { return join(process.env.LOCALAPPDATA || homedir(), 'EduForge', 'agent-runtime') }

export async function startRuntime({ profile='web', dataRoot=defaultDataRoot(), workspace, port=3082, quiet=false, entries }={}) {
  const data = resolve(dataRoot)
  const cwd = resolve(workspace || join(data, 'workspace'))
  mkdirSync(cwd,{recursive:true})
  process.env.DSH_HOME = join(data, 'home')
  process.env.DSH_TELEMETRY_DISABLED = '1'
  process.env.DSH_PERMISSION_MODE = 'workspace-write'
  process.env.EDUFORGE_LABKIT_ROOT = labkitRoot()
  process.env.EDUFORGE_DSH_INSTALL_ANCHOR = installationAnchor()
  process.env.EDUFORGE_LABKIT_OUTPUT_ROOT = join(data, 'labkit')
  process.env.CHROME_LOG_FILE = join(data,'chromium.log')
  const browsers = join(serviceRoot,'runtime','browsers')
  if(existsSync(browsers)) process.env.PLAYWRIGHT_BROWSERS_PATH = browsers
  process.chdir(cwd)
  const { runProfile } = await runtimeImport('@deepseek-ai/dsh/profile-boot')
  const { loadProfileDirectory, loadLayeredEnv } = await runtimeImport('@deepseek-ai/dsh-app-boot')
  const { entryListSchema } = await runtimeImport('@deepseek-ai/cordis-plugin-include')
  const yaml = runtimeRequire()('js-yaml')
  const dir = join(data, 'home','profiles',`eduforge-${profile}`)
  mkdirSync(dir,{recursive:true})
  const manifest = join(dir,'package.json')
  const bundleName='@eduforge/runtime-bundle'
  const profileManifest=existsSync(manifest)?JSON.parse(readFileSync(manifest,'utf8')):{name:`eduforge-${profile}`,private:true}
  profileManifest.dsh??={};profileManifest.dsh.profile??={}
  profileManifest.dsh.profile.bundles=[bundleName,...(profileManifest.dsh.profile.bundles||[]).filter(n=>n!==bundleName)]
  writeFileSync(manifest,JSON.stringify(profileManifest,null,2)+'\n')
  const patch = join(dir,'cordis.patch.yml')
  if (!existsSync(patch)) writeFileSync(patch,'[]\n')
  const rows = entries || materializeComposition(profile,{labkitUrl:pathToFileURL(labkitEntry()).href})
  if (quiet && profile==='web') Object.assign(rows.find(r=>r.id==='web-runtime').config, {printUrl:false,openBrowser:false})
  const bundleDir=join(dir,'node_modules','@eduforge','runtime-bundle')
  mkdirSync(bundleDir,{recursive:true})
  writeFileSync(join(bundleDir,'package.json'),JSON.stringify({name:bundleName,version:'0.1.0',private:true,dsh:{bundle:{patch:'./cordis.patch.yml'}}},null,2)+'\n')
  const generated = join(bundleDir,'cordis.patch.yml')
  writeFileSync(generated, yaml.dump([{insert:rows}],{schema:entryListSchema,noRefs:true,lineWidth:-1}))
  const loaded = loadProfileDirectory('eduforge',dir,installationAnchor())
  if(loaded.skippedBundles.length)throw new Error(`PROFILE_BUNDLE_FAILED: ${loaded.skippedBundles.map(b=>b.reason).join('; ')}`)
  const started = performance.now()
  const runtime = await runProfile({environment:loadLayeredEnv('eduforge'),profile:`eduforge-${profile}`,
    resolvedProfile:{profile:loaded,installAnchor:installationAnchor()},patchFiles:[],
    args:profile==='web'?['--no-open','--host','127.0.0.1','--port',String(port)]:[],
  })
  await runtime.ctx.loader.await()
  return {...runtime, startupMs:performance.now()-started, dataRoot:data, workspace:cwd}
}
