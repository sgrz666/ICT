/** Real-provider acceptance. No key means pending; mock responses never count. */
import { randomUUID } from 'node:crypto'
import { writeFileSync, readFileSync } from 'node:fs'
import { join } from 'node:path'
import { runtimeImport } from './layout.mjs'

export async function liveChecks(ctx,workspace,report) {
  if(!process.env.DEEPSEEK_API_KEY) {
    report.pending.push({id:'live_model',reason:'DEEPSEEK_API_KEY is absent in this verification process. Existing credential stores are not copied.'})
    return
  }
  const {createUserMessage}=await runtimeImport('@deepseek-ai/dsh-llm')
  const id=`live-${randomUUID()}`
  const options={provider:'deepseek-official',model:process.env.EDUFORGE_LIVE_MODEL||'deepseek-flash',maxTokens:4096}
  const setup=async agentCtx=>{await ctx.agentPresets.mount(agentCtx,'eduforge-dev')}
  let handle=await ctx.agents.create({sessionId:id,meta:{cwd:workspace,agentPreset:'eduforge-dev'},agentOptions:options,setup})
  const check=(id,ok,detail)=>report.checks.push({id,status:ok?'pass':'fail',detail})
  const children=[]
  const offChild=ctx.on('agent/created',({agent})=>{if(agent.session.header.parentSession===id)children.push(agent.id)})
  const childTools=[],childEnds=[]
  const offTools=ctx.on('tools/result',(exec,result)=>{if(exec.agent?.session.header.parentSession===id)childTools.push({agent:exec.agent.id,name:exec.name,ok:!result.isError})})
  const offEnd=ctx.on('subagent/end',info=>{if(children.includes(String(info.id)))childEnds.push({id:String(info.id),stopReason:info.stopReason,hasAnswer:Array.isArray(info.lastAssistantMessage)&&info.lastAssistantMessage.length>0})})
  async function prompt(text) {
    const agent=handle.agent
    agent.followup(createUserMessage({content:[{type:'text',text}],source:{kind:'user'}}))
    let expired=false
    const timer=setTimeout(()=>{expired=true;agent.cancel({kind:'user'})},120000)
    try {await agent.whenIdle()} finally {clearTimeout(timer)}
    if(expired)throw new Error('Live model turn exceeded 120 seconds')
    const messages=agent.session.deriveMessages()
    return JSON.stringify(messages.filter(m=>m.role==='assistant').at(-1)?.content||'')
  }
  try {
    const sentinel=`KEEP-${randomUUID()}`
    writeFileSync(join(workspace,'repair.cjs'),"module.exports=(a,b)=>a-b;\n")
    writeFileSync(join(workspace,'repair.test.cjs'),"const add=require('./repair.cjs');if(add(2,3)!==5||add(-3,8)!==5)throw Error('wrong sum');console.log('REPAIR_OK');\n")
    let transcript=await prompt(`记住验收标记 ${sentinel}。读取 repair.cjs，先用 pwsh 运行 node repair.test.cjs 观察失败，再修复加法并复测。仅修改 repair.cjs。只在此工作区操作，不要修改权限。`)
    const fixed=readFileSync(join(workspace,'repair.cjs'),'utf8')
    writeFileSync(join(workspace,'independent-check.cjs'),"const add=require('./repair.cjs');for(const [a,b]of [[2,3],[-3,8],[0,0],[11,-4]])if(add(a,b)!==a+b)throw Error('wrong sum');console.log('INDEPENDENT_REPAIR_OK');\n")
    const independent=await ctx.tools.execute({callId:`live-check-${randomUUID()}`,name:'pwsh',arguments:{command:'node independent-check.cjs',description:'Independently verify the repaired function',timeoutMs:10000},agent:handle.agent,signal:AbortSignal.timeout(20000)})
    check('live_repair',!fixed.includes('=>a-b') && !independent.isError && JSON.stringify(independent.value).includes('INDEPENDENT_REPAIR_OK'),{session:id,independent})
    transcript=await prompt('请实际派生一个子智能体，只读检查 repair.cjs 的运算，完成后把子智能体的结论告诉我。')
    await Promise.all(ctx.agents.list().filter(a=>a.session.header.parentSession===id).map(a=>a.whenIdle()))
    check('live_subagent',children.length>0&&childTools.some(t=>t.name==='read'&&t.ok)&&childEnds.some(e=>e.stopReason?.kind==='completed'&&e.hasAnswer),{session:id,children,childTools,childEnds})
    const compaction=ctx.agentPresets.serviceFor(handle.agent,'compaction')
    if(compaction) {
      const compacted=await compaction.compactNow(handle.agent,AbortSignal.timeout(60000))
      if(compacted) {
        transcript=await prompt('仅复述之前的 KEEP- 验收标记，并说明已完成及未完成的任务。')
        check('live_compaction_retention',transcript.includes(sentinel),{compaction_performed:true})
      } else report.pending.push({id:'live_compaction',reason:'Native compactor found no useful safe range in this short run.'})
    } else check('live_compaction_service',false,'No native compaction service')
    await handle.dispose()
    handle=await ctx.agents.resume({resumeSessionId:id,agentOptions:options,setup})
    check('live_session_resume',JSON.stringify(handle.agent.session.deriveMessages()).includes(sentinel),{session:id})
  } catch(e) {
    // Auth, network and model errors remain visible failures when a live run was requested.
    check('live_model_run',false,String(e.message).replace(/sk-[A-Za-z0-9_-]+/g,'[REDACTED]'))
  } finally {offEnd();offTools();offChild();await handle.dispose()}
}
