import { mkdtempSync, mkdirSync, writeFileSync, readFileSync, unlinkSync, rmdirSync, existsSync } from 'node:fs'
import { tmpdir, homedir } from 'node:os'
import { join, resolve } from 'node:path'
import { randomUUID } from 'node:crypto'
import diagnostics from 'node:diagnostics_channel'
import { startRuntime } from './runtime.mjs'
import { runtimeImport, serviceRoot } from './layout.mjs'
import { readComposition } from './composition.mjs'

export async function verify({ live=false, out }={}) {
  const dataRoot=mkdtempSync(join(tmpdir(),'eduforge-runtime-verify-'))
  const boundaryRoot=mkdtempSync(join(homedir(),'.eduforge-boundary-'))
  const reportPath=resolve(out||join(dataRoot,'verification.json'))
  const report={schema:'eduforge.agent-runtime.verification/v1',generated_at:new Date().toISOString(),
    checks:[], pending:[], measurements:{}, network_origins:[]}
  const check=(id,ok,detail)=>{report.checks.push({id,status:ok?'pass':'fail',detail});return ok}
  const channel=diagnostics.channel('undici:request:create')
  const origins=new Set()
  const observer=({request})=>{try{origins.add(new URL(request.origin).origin)}catch{}}
  channel.subscribe(observer)
  let rt
  const handles=[]
  try {
    rt=await startRuntime({dataRoot,port:0,quiet:true})
    const {ctx}=rt
    const {auditStartupEntries}=await runtimeImport('@deepseek-ai/dsh-app-boot')
    await auditStartupEntries(ctx,'eduforge',()=>{})
    report.modules=Array.from(ctx.loader.entries()).filter(e=>e.fiber).map(e=>({id:e.id,name:e.options.name.startsWith('file:')?'@eduforge/labkit-plugin':e.options.name,state:e.fiber.state}))
    report.measurements={startup_ms:Math.round(rt.startupMs),rss_bytes:process.memoryUsage().rss,configured_host_rows:readComposition().length,loaded_plugin_rows:report.modules.length}
    const roster=await ctx.agentPresets.list()
    check('presets_ready',roster.length===2 && roster.every(r=>!r.broken),roster)
    const origin=ctx.webServer.getOrigin()
    const login=await fetch(ctx.connection.authenticatedUrl(origin),{redirect:'manual'})
    const cookie=login.headers.getSetCookie().map(v=>v.split(';')[0]).join('; ')
    const res=login.status>=300&&login.status<400 ? await fetch(new URL(login.headers.get('location'),origin),{headers:{cookie}}) : login
    check('web_http',res.ok && (await res.text()).includes('<html'),res.status)
    for (const preset of ['physics-lab','eduforge-dev']) {
      const scope=await ctx.agentPresets.acquireScope(preset)
      const schemas=ctx.tools.schemas(scope.key)
      const names=schemas.map(t=>t.name).sort()
      if(preset==='physics-lab') check('teacher_tool_allowlist',JSON.stringify(names)===JSON.stringify([
        'ask_user_question','experiment_build','experiment_recipes','experiment_render','experiment_simulate','experiment_validate','experiment_verify','present',
      ].sort()),names)
      else check('developer_core_tools',['read','write','edit','pwsh','skill','todo_write','create_goal','subagent_fork','job_list'].every(t=>names.includes(t)),names)
      await scope[Symbol.asyncDispose]()
      const handle=await ctx.agents.create({sessionId:`verify-${randomUUID()}`,meta:{cwd:rt.workspace,agentPreset:preset},
        agentOptions:ctx.agentDefaultModel.currentSelection(), setup:async agentCtx=>{await ctx.agentPresets.mount(agentCtx,preset)},
      })
      handles.push(handle)
      const {scopeOf}=await runtimeImport('@deepseek-ai/dsh-scope','@deepseek-ai/dsh-tools')
      if(preset==='eduforge-dev') check('developer_spawn_tool',ctx.tools.schemas(scopeOf(handle.agent.ctx)).some(t=>t.name==='subagent'),'Agent-scoped spawn registration')
      const call=(name,args,timeout=60000)=>ctx.tools.execute({callId:`call-${randomUUID()}`,name,arguments:args,agent:handle.agent,signal:AbortSignal.timeout(timeout)})
      if(preset==='physics-lab') {
        const denied=await call('pwsh',{command:'Write-Output should-not-run'})
        check('teacher_execution_denied',denied.isError===true,denied)
        const recipes=await call('experiment_recipes',{})
        check('real_labkit_recipes',!recipes.isError,recipes)
        const built=await call('experiment_build',{
          template_id:'mechanics.projectile',recipe_id:'complementary',params:{v0:20,h0:0,angles_deg:[30,60]},
          why_recipe:'因为 30° 与 60° 互补，sin2θ 相同，所以同一初速度下两条轨迹的射程应当相等。',
          student_task:'拖动发射角滑块到 30° 与 60°，记录并比较射程与飞行时间。',out_name:'runtime-verification',
        })
        check('teacher_real_build',!built.isError && built.value?.ok===true,built)
        if(built.value?.ok) {
          const paths=built.value.data
          writeFileSync(paths.html_path,readFileSync(paths.html_path,'utf8')+'<!-- modified after verification -->')
          const tamper=await call('experiment_verify',{html_path:paths.html_path,evidence_path:paths.evidence_path})
          check('teacher_tamper_rejected',!tamper.isError && tamper.value?.ok===false,tamper)
        }
      } else {
        writeFileSync(join(rt.workspace,'unread.txt'),'original\n')
        const denied=await call('write',{file_path:'unread.txt',content:'must not overwrite unread file'})
        check('read_before_write',denied.isError===true && JSON.stringify(denied).includes('FS_NOT_OBSERVED') && readFileSync(join(rt.workspace,'unread.txt'),'utf8')==='original\n',denied)
        const outside=join(boundaryRoot,'outside.txt');writeFileSync(outside,'boundary marker')
        await call('read',{file_path:outside})
        const escape=await call('write',{file_path:outside,content:'must not change'})
        check('workspace_write_boundary',escape.isError===true && JSON.stringify(escape).includes('FS_SANDBOX_DENIED') && readFileSync(outside,'utf8')==='boundary marker',escape)
        const shell=await call('pwsh',{command:"Write-Output 'EDUFORGE_SANDBOX_PROBE'",description:'Probe native workspace sandbox',timeoutMs:10000})
        if(shell.isError && JSON.stringify(shell).includes('INVALID_ARGS')) check('sandbox_probe_contract',false,shell)
        else if(shell.isError) report.pending.push({id:'os_process_isolation',reason:'Native sandbox probe did not execute successfully; no permission downgrade performed.',detail:shell})
        else {
          const escaped=outside.replaceAll("'","''")
          const deniedShell=await call('pwsh',{command:`$ErrorActionPreference='Stop'; Set-Content -LiteralPath '${escaped}' -Value 'should-not-write'`,description:'Check that a disposable file outside writable roots is protected',timeoutMs:10000})
          check('os_process_write_boundary',readFileSync(outside,'utf8')==='boundary marker',deniedShell)
          const begin=join(rt.workspace,'cancel-started.txt'), end=join(rt.workspace,'cancel-finished.txt')
          const controller=new AbortController()
          const execution=ctx.tools.execute({callId:`cancel-${randomUUID()}`,name:'pwsh',
            arguments:{command:"Set-Content cancel-started.txt 'started'; Start-Sleep -Seconds 20; Set-Content cancel-finished.txt 'finished'",description:'Verify cancellation of a running native process',timeoutMs:30000},
            agent:handle.agent,signal:controller.signal})
          const deadline=Date.now()+15000
          while(!existsSync(begin)&&Date.now()<deadline) await new Promise(r=>setTimeout(r,50))
          controller.abort()
          const cancelled=await execution
          check('native_process_cancel',existsSync(begin)&&!existsSync(end)&&cancelled.isError===true,cancelled)
        }
        handle.agent.session.append('turn/start',{turn:1})
        const {setApprovalPolicy}=await runtimeImport('@deepseek-ai/dsh-user-approval','@deepseek-ai/dsh-tools')
        setApprovalPolicy(handle.agent.session,'never')
        const rejected=await ctx.approval.request({agent:handle.agent,toolName:'write',reason:'Reject outside-workspace write',signal:AbortSignal.timeout(3000)})
        check('approval_rejection',rejected==='rejected' && readFileSync(outside,'utf8')==='boundary marker',rejected)
        setApprovalPolicy(handle.agent.session,'ask')
        const {Context}=await runtimeImport('@deepseek-ai/cordis')
        const {default:ApprovalService}=await runtimeImport('@deepseek-ai/dsh-user-approval','@deepseek-ai/dsh-tools')
        const noChannel=new Context()
        await noChannel.plugin(ApprovalService,{policy:'ask'})
        const unavailable=await noChannel.approval.request({agent:handle.agent,toolName:'write',reason:'Verify missing answer channel',signal:AbortSignal.timeout(3000)})
        await noChannel.fiber.dispose()
        check('approval_unavailable_denies',unavailable==='unavailable' && readFileSync(outside,'utf8')==='boundary marker',unavailable)
        handle.agent.session.append('turn/end',{turn:1,reason:{kind:'completed'}})
      }
    }
    if(live) {const {liveChecks}=await import('./live.mjs');await liveChecks(ctx,rt.workspace,report)}
    else report.pending.push({id:'model_repair_compaction_subagents_resume',reason:'Not requested; rerun verify -Live with valid model configuration.'})
  } catch(e) { check('runtime_verification',false,e.message) }
  finally {
    for(const h of handles.reverse()) await h.dispose().catch(()=>{})
    if(rt) await rt.ctx.fiber.dispose().catch(e=>check('shutdown',false,e.message))
    channel.unsubscribe(observer)
    try{unlinkSync(join(boundaryRoot,'outside.txt'));rmdirSync(boundaryRoot)}catch{}
  }
  try{const {sdkSmoke}=await import('./sdk-smoke.mjs');const sdk=await sdkSmoke();check('sdk_jsonrpc_and_shutdown',sdk.status==='pass',sdk)}catch(e){check('sdk_jsonrpc_and_shutdown',false,e.message)}
  try{const {uiSmoke}=await import('./ui-smoke.mjs');const ui=await uiSmoke({out:reportPath.replace(/\.json$/,'')+'-ui.json'});check('browser_presets_settings_approval',ui.status==='passed',ui.checks)}catch(e){check('browser_presets_settings_approval',false,e.message)}
  if(existsSync(join(serviceRoot,'inventory.json'))){const {auditPackage}=await import('./package.mjs');const audit=await auditPackage(serviceRoot);check('package_integrity_after_run',audit.ok,audit)}
  report.network_origins=[...origins]
  check('no_observed_telemetry',![...origins].some(u=>/deepseeksvc\.com|opentelemetry/i.test(u)), 'Observed Node HTTP origins during these probes only; not a machine-wide network audit.')
  report.status=report.checks.some(c=>c.status==='fail')?'failed':report.pending.length?'partial':'passed'
  mkdirSync(resolve(reportPath,'..'),{recursive:true})
  writeFileSync(reportPath,JSON.stringify(report,null,2)+'\n')
  console.log(JSON.stringify({status:report.status,checks:report.checks.map(({id,status})=>({id,status})),pending:report.pending,measurements:report.measurements,report:reportPath},null,2))
  if(report.status==='failed') process.exitCode=1
  return report
}
