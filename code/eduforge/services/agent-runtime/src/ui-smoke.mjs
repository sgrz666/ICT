import { createRequire } from 'node:module'
import { join, resolve } from 'node:path'
import { mkdirSync, writeFileSync, mkdtempSync } from 'node:fs'
import { tmpdir } from 'node:os'
import { startRuntime } from './runtime.mjs'
import { labkitRoot } from './layout.mjs'

export async function uiSmoke({out}={}) {
  const reportFile=resolve(out||join(tmpdir(),'eduforge-ui-smoke.json'))
  const report={schema:'eduforge.agent-runtime.ui/v1',checks:[],errors:[],external_origins:[]}
  let rt,browser
  try {
    rt=await startRuntime({dataRoot:mkdtempSync(join(tmpdir(),'eduforge-ui-')),port:0,quiet:true})
    const {chromium}=createRequire(join(labkitRoot(),'code/eduforge/services/engine-host/package.json'))('playwright')
    browser=await chromium.launch({headless:true})
    const page=await browser.newPage({viewport:{width:1440,height:1000}})
    // Onboarding is mounted asynchronously after account/config state loads.
    // Dismiss it at action time as well, so a late modal cannot intercept a click.
    await page.addLocatorHandler(page.getByRole('button',{name:'稍后配置',exact:true}),async button=>{await button.click()})
    await page.addLocatorHandler(page.getByRole('button',{name:'继续',exact:true}),async button=>{await button.click()})
    page.on('pageerror',e=>report.errors.push(e.message))
    page.on('request',req=>{const url=new URL(req.url());if(['http:','https:','ws:','wss:'].includes(url.protocol)&&url.hostname!=='127.0.0.1'&&url.hostname!=='localhost') report.external_origins.push(url.origin)})
    await page.goto(rt.ctx.connection.authenticatedUrl(rt.ctx.webServer.getOrigin()),{waitUntil:'networkidle',timeout:30000})
    await page.waitForFunction(()=>document.body.innerText.includes('启智'),{timeout:15000})
    await rt.ctx.workspaceRegistry.create(rt.workspace,'验收工作区')
    await page.reload({waitUntil:'networkidle'})
    await page.getByRole('button',{name:'教学实验',exact:true}).click()
    await page.getByText('开发助手',{exact:true}).click()
    await page.getByRole('button',{name:'开发助手',exact:true}).waitFor()
    report.checks.push({id:'preset_switch',passed:true})
    await rt.ctx.loader.await()
    report.checks.push({id:'settings_reload_preserves_bundle',passed:(await rt.ctx.agentPresets.list()).length===2})
    const agent=rt.ctx.agents.list().at(-1)
    if(!agent)throw new Error('Browser did not create a session')
    agent.session.append('turn/start',{turn:1})
    const decision=rt.ctx.approval.request({agent,toolName:'write',reason:'UI approval regression: reject this request',signal:AbortSignal.timeout(10000)})
    await page.getByRole('button',{name:/拒绝|Reject/}).click({timeout:8000})
    const outcome=await decision
    report.checks.push({id:'approval_reject_button',passed:outcome==='rejected',outcome})
    agent.session.append('turn/end',{turn:1,reason:{kind:'completed'}})
    const text=await page.locator('body').innerText()
    report.checks.push({id:'brand_and_shell',passed:text.includes('启智')})
    report.checks.push({id:'no_browser_exception',passed:report.errors.length===0})
    report.checks.push({id:'no_cloud_account',passed:!text.includes('使用 DeepSeek 账号登录')})
    report.body_excerpt=text.slice(0,500)
    report.buttons=await page.getByRole('button').allTextContents()
    mkdirSync(resolve(reportFile,'..'),{recursive:true})
    report.screenshot=reportFile.replace(/\.json$/,'')+'.png'
    await page.screenshot({path:report.screenshot,fullPage:true})
    report.status=report.checks.every(c=>c.passed)?'passed':'failed'
  }catch(e){report.status='failed';report.errors.push(e.message)}
  finally{if(browser)await browser.close();if(rt)await rt.ctx.fiber.dispose()}
  writeFileSync(reportFile,JSON.stringify(report,null,2)+'\n')
  console.log(JSON.stringify(report,null,2))
  if(report.status==='failed')process.exitCode=1
  return report
}
