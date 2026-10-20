/** 工具结果的文本投影：模型看摘要，完整数据落盘或放在 data 里。 */

export function fmt(v, d = 2) {
  return Number(v).toFixed(d)
}

export function scenarioTable(scenarios) {
  const rows = ['场景     | R(m) 实测 / 解析 | T(s) 实测 / 解析 | H(m) 实测 / 解析']
  for (const s of scenarios ?? []) {
    if (!s.measured || !s.analytic) continue
    if (typeof s.measured.R !== 'number') continue
    const dR = Math.abs(s.measured.R - s.analytic.R) / Math.abs(s.analytic.R || 1) * 100
    const dT = Math.abs(s.measured.T - s.analytic.T) / Math.abs(s.analytic.T || 1) * 100
    const dH = Math.abs(s.measured.H - s.analytic.H) / Math.abs(s.analytic.H || 1) * 100
    rows.push(
      `${String(s.id).padEnd(8)} | ${fmt(s.measured.R)} / ${fmt(s.analytic.R)} | ${fmt(s.measured.T, 4)} / ${fmt(s.analytic.T, 4)} | ${fmt(s.measured.H)} / ${fmt(s.analytic.H)}  (max ${fmt(Math.max(dR, dT, dH))}%)`,
    )
  }
  return rows.join('\n')
}

export function hintBlock(hints) {
  const list = (hints ?? []).filter(Boolean)
  return list.length ? `\n建议：\n- ${list.join('\n- ')}` : ''
}

export function errorBlock(errors) {
  const list = errors ?? []
  return list.length
    ? list.map(e => `${e.code}${e.field ? `@${e.field}` : ''}: ${e.message}`).join('\n')
    : ''
}
