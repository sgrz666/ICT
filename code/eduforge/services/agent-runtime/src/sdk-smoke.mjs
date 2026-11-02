import { spawn } from 'node:child_process'
import { mkdtempSync } from 'node:fs'
import { tmpdir } from 'node:os'
import { join } from 'node:path'
import { serviceRoot } from './layout.mjs'

export async function sdkSmoke() {
  const data=mkdtempSync(join(tmpdir(),'eduforge-sdk-smoke-'))
  const child=spawn(process.execPath,[join(serviceRoot,'src/cli.mjs'),'sdk','--data',data],{stdio:['pipe','pipe','pipe'],windowsHide:true})
  let sequence=0,buffer='',stderr=''
  const pending=new Map()
  const closed=new Promise(resolve=>child.once('close',resolve))
  child.stderr.on('data',b=>{stderr=(stderr+b.toString()).slice(-3000)})
  child.stdout.on('data',b=>{
    buffer+=b.toString()
    while(buffer.includes('\n')){
      const at=buffer.indexOf('\n'),line=buffer.slice(0,at);buffer=buffer.slice(at+1)
      try{const msg=JSON.parse(line);const wait=pending.get(msg.id);if(wait){pending.delete(msg.id);wait.resolve(msg)}}
      catch{for(const wait of pending.values())wait.reject(new Error('SDK stdout contains non-JSON output'))}
    }
  })
  const request=(method,params={})=>new Promise((resolve,reject)=>{
    const id=++sequence
    const timer=setTimeout(()=>{pending.delete(id);reject(new Error(`SDK request timed out: ${method}; ${stderr}`))},20000)
    pending.set(id,{resolve:msg=>{clearTimeout(timer);resolve(msg)},reject:e=>{clearTimeout(timer);reject(e)}})
    child.stdin.write(JSON.stringify({jsonrpc:'2.0',id,method,params})+'\n')
  })
  try{
    const init=await request('initialize',{cwd:data,provider:'deepseek-official',model:'deepseek-flash'})
    if(init.error)throw new Error(init.error.message)
    const working=await request('session/working-directory/get',{sessionId:'sdk-fixture'})
    const missing=await request('session/resume',{sessionId:'must-not-exist'})
    await request('shutdown')
    const exit=await Promise.race([closed,new Promise(resolve=>setTimeout(()=>resolve('timeout'),5000))])
    if(exit==='timeout')throw new Error('SDK shutdown did not exit')
    return {status:init.result?.serverInfo?.name==='deepseek-harness-sdk-runtime'&&!working.error&&!!missing.error&&exit===0?'pass':'fail',
      initialize:init.result,working_directory:working.result,missing_resume_rejected:!!missing.error,exit}
  }finally{if(child.exitCode===null)child.kill();child.stdin.destroy()}
}
