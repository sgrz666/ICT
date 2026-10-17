// Summarize one headless run: tool call order, failures, usage, and outcome.
import { readFileSync } from 'node:fs'

const [jsonlPath, metaPath] = process.argv.slice(2)
const events = readFileSync(jsonlPath, 'utf8')
  .split('\n')
  .filter((l) => l.trim())
  .map((l) => JSON.parse(l))

const clip = (s, n) => {
  const t = typeof s === 'string' ? s : JSON.stringify(s)
  if (t === undefined) return ''
  const one = t.replace(/\s+/g, ' ')
  return one.length > n ? one.slice(0, n) + `…(+${one.length - n})` : one
}

let seq = 0
const calls = new Map()
const lines = []
let usage = { inputTokens: 0, outputTokens: 0, cacheReadTokens: 0, totalTokens: 0 }
let steps = 0
let turns = 0

for (const e of events) {
  if (e.type === 'session') lines.push(`SESSION ${e.sessionId}  cwd=${e.cwd}`)
  else if (e.type === 'status' && e.phase === 'turn_start') turns += 1
  else if (e.type === 'status' && e.phase === 'step_start') {
    steps += 1
    lines.push(`--- turn ${e.turn} step ${e.step} ---`)
  } else if (e.type === 'status' && e.phase === 'step_end') {
    const u = e.usage ?? {}
    usage.inputTokens += u.inputTokens ?? 0
    usage.outputTokens += u.outputTokens ?? 0
    usage.cacheReadTokens += u.cacheReadTokens ?? 0
    usage.totalTokens += u.totalTokens ?? 0
    lines.push(
      `    step_end usage in=${u.inputTokens ?? 0} out=${u.outputTokens ?? 0} cacheRead=${u.cacheReadTokens ?? 0}`,
    )
  } else if (e.type === 'status' && e.phase === 'turn_end')
    lines.push(`TURN_END ${JSON.stringify(e.reason)}`)
  else if (e.type === 'tool_call') {
    seq += 1
    calls.set(e.callId, { n: seq, tool: e.tool })
    lines.push(`  [${seq}] CALL ${e.tool}  ${clip(e.input, 200)}`)
  } else if (e.type === 'tool_result') {
    const c = calls.get(e.callId) ?? { n: '?', tool: '?' }
    lines.push(
      `  [${c.n}] RESULT ${c.tool} status=${e.status}  ${clip(e.result, 320)}`,
    )
  } else if (e.type === 'text' && e.text.trim()) lines.push(`  TEXT ${clip(e.text, 300)}`)
  else if (e.type === 'final') lines.push(`FINAL ${clip(e.text, 700)}`)
}

const toolCounts = {}
for (const c of calls.values()) toolCounts[c.tool] = (toolCounts[c.tool] ?? 0) + 1
const failures = events.filter((e) => e.type === 'tool_result' && e.status === 'error').length

lines.push('')
lines.push(
  `SUMMARY turns=${turns} steps=${steps} tool_calls=${calls.size} tool_failures=${failures}`,
)
lines.push(`TOOLS ${JSON.stringify(toolCounts)}`)
lines.push(
  `TOKENS in=${usage.inputTokens} out=${usage.outputTokens} cacheRead=${usage.cacheReadTokens} total=${usage.totalTokens}`,
)

const meta = metaPath ? readFileSync(metaPath, 'utf8').trim() : ''
if (meta) lines.push(`META ${meta.replace(/\n/g, ' | ')}`)
console.log(lines.join('\n'))
