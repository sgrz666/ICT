/** 把不同实验的 L2 结果投影成模型可读的摘要表。 */
import { fmt, scenarioTable } from './format.mjs'

export function simulationSummary(sim, templateId) {
  const head = sim.verdict === 'pass' ? 'L2 物理对账通过。' : 'L2 物理对账未通过。'

  if (templateId === 'mechanics.projectile') {
    const lines = [head, scenarioTable(sim.scenarios)]
    if (sim.drag_control) {
      lines.push(
        '',
        `阻力对照：无阻力偏离 ${fmt(sim.drag_control.deviation_no_drag_pct, 3)}%，开阻力偏离 ${fmt(sim.drag_control.deviation_with_drag_pct, 3)}%，比值 ${fmt(sim.drag_control.ratio, 1)}×（要求 >5× 且开阻力偏离 >1%）→ ${sim.drag_control.verdict}`,
      )
    }
    return lines.join('\n')
  }

  if (templateId === 'mechanics.pendulum') {
    const rows = ['场景 | L (m) | θ₀ (°) | T 实测 (s) | T 精确 (s) | 偏差']
    for (const s of sim.scenarios ?? []) {
      if (s.id === 'ratio') {
        const rel = Math.abs(s.measured.ratio - 2) / 2 * 100
        rows.push(`T(2.0)/T(0.5) | — | — | ${fmt(s.measured.ratio, 4)} | 2 | ${fmt(rel, 2)}%`)
        continue
      }
      const dev = Math.abs(s.measured.T - s.analytic.Texact) / s.analytic.Texact * 100
      rows.push(`${s.id} | ${fmt(s.params.length_m, 2)} | ${fmt(s.params.angle0_deg, 0)} | ${fmt(s.measured.T, 4)} | ${fmt(s.analytic.Texact, 4)} | ${fmt(dev, 3)}%`)
    }
    return `${head}\n${rows.join('\n')}`
  }

  if (templateId === 'circuits.ohms_law') {
    const s = sim.scenarios?.[0]
    const rows = ['量 | 实测 | 解析 | 偏差']
    for (const [k, v] of Object.entries(s?.measured ?? {})) {
      const a = s.analytic?.[k]
      const rel = a === 0 ? 0 : Math.abs((v - a) / a) * 100
      rows.push(`${k} | ${fmt(v, 6)} | ${a === undefined ? '—' : fmt(a, 6)} | ${rel < 1e-6 ? '0' : rel.toExponential(1) + '%'}`)
    }
    const x = sim.cross_check
    rows.push('', `CircuitJS1 交叉验证：${x?.verdict ?? 'na'}（${x?.checks?.length ?? 0} 项）`)
    return `${head}\n${rows.join('\n')}`
  }

  return `${head}\n${scenarioTable(sim.scenarios)}`
}
