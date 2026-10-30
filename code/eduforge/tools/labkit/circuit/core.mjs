/**
 * 直流电路的自包含求解内核（改进节点法 MNA）。
 *
 * 为什么不是 CircuitJS1：CircuitJS1 的 GWT 产物是 15 MB 多文件站点、需要同源加载，
 * 无法做成真正的单文件 HTML。这里用标准 MNA 求解线性 DC 网络，结果对电阻电路是精确解；
 * L2 同时把 CircuitJS1 在 2026-10-19 记录的实测值作为外部交叉验证（见 simulate.mjs）。
 *
 * 节点编号：0 = 地；其余为正整数。未知量顺序：V1..Vn, Is1..Ism。
 */

/** 高斯消元（部分主元）。A 为 n×n，b 为 n。 */
function solveLinear(A, b) {
  const n = b.length
  const M = A.map((row, i) => [...row, b[i]])
  for (let col = 0; col < n; col += 1) {
    let piv = col
    for (let r = col + 1; r < n; r += 1) {
      if (Math.abs(M[r][col]) > Math.abs(M[piv][col])) piv = r
    }
    if (Math.abs(M[piv][col]) < 1e-14) {
      const err = new Error('SINGULAR_MATRIX: 电路无解或存在悬空节点')
      err.code = 'SINGULAR_MATRIX'
      throw err
    }
    if (piv !== col) [M[col], M[piv]] = [M[piv], M[col]]
    const p = M[col][col]
    for (let c = col; c <= n; c += 1) M[col][c] /= p
    for (let r = 0; r < n; r += 1) {
      if (r === col) continue
      const f = M[r][col]
      if (f === 0) continue
      for (let c = col; c <= n; c += 1) M[r][c] -= f * M[col][c]
    }
  }
  return M.map(row => row[n])
}

export function assertNetlist(netlist) {
  if (!netlist || !Array.isArray(netlist.resistors) || !Array.isArray(netlist.sources)) {
    const e = new Error('NETLIST_INVALID: 需要 {resistors:[], sources:[]}')
    e.code = 'NETLIST_INVALID'
    throw e
  }
  if (netlist.sources.length === 0) {
    const e = new Error('NETLIST_INVALID: 至少需要一个电压源')
    e.code = 'NETLIST_INVALID'
    throw e
  }
  for (const r of netlist.resistors) {
    if (!(r.r > 0)) {
      const e = new Error(`RESISTANCE_INVALID: ${r.id} 的阻值必须 >0`)
      e.code = 'RESISTANCE_INVALID'
      throw e
    }
  }
  const maxNode = Math.max(
    0,
    ...netlist.resistors.flatMap(r => [r.from, r.to]),
    ...netlist.sources.flatMap(s => [s.from, s.to]),
  )
  if (!Number.isInteger(maxNode) || maxNode > 50) {
    const e = new Error('NETLIST_INVALID: 节点编号必须是 0..50 的整数')
    e.code = 'NETLIST_INVALID'
    throw e
  }
  return { ...netlist, nodeCount: maxNode }
}

/** 解一个 DC 网络，返回节点电压、支路电流/电压、电源电流。 */
export function solveDC(rawNetlist) {
  const netlist = assertNetlist(rawNetlist)
  const n = netlist.nodeCount
  const m = netlist.sources.length
  const size = n + m
  const A = Array.from({ length: size }, () => new Array(size).fill(0))
  const b = new Array(size).fill(0)

  for (const r of netlist.resistors) {
    const g = 1 / r.r
    const a = r.from
    const c = r.to
    if (a > 0) A[a - 1][a - 1] += g
    if (c > 0) A[c - 1][c - 1] += g
    if (a > 0 && c > 0) {
      A[a - 1][c - 1] -= g
      A[c - 1][a - 1] -= g
    }
  }
  for (const [k, s] of netlist.sources.entries()) {
    const idx = n + k
    if (s.from > 0) {
      A[s.from - 1][idx] += 1
      A[idx][s.from - 1] += 1
    }
    if (s.to > 0) {
      A[s.to - 1][idx] -= 1
      A[idx][s.to - 1] -= 1
    }
    b[idx] = s.v
  }

  const x = solveLinear(A, b)
  const nodeVoltages = [0]
  for (let i = 1; i <= n; i += 1) nodeVoltages[i] = x[i - 1]
  const sourceCurrents = {}
  for (const [k, s] of netlist.sources.entries()) sourceCurrents[s.id] = x[n + k]
  const resistorCurrents = {}
  const resistorVoltages = {}
  for (const r of netlist.resistors) {
    const diff = nodeVoltages[r.from] - nodeVoltages[r.to]
    resistorVoltages[r.id] = diff
    resistorCurrents[r.id] = diff / r.r
  }
  return { nodeVoltages, sourceCurrents, resistorCurrents, resistorVoltages }
}

/** 欧姆定律：一个电压源 + 一个电阻。 */
export function buildOhm({ voltage_v: V, resistance_ohm: R }) {
  return {
    sources: [{ id: 'V1', from: 1, to: 0, v: V }],
    resistors: [{ id: 'R1', from: 1, to: 0, r: R }],
  }
}

/** 串联：V1 — R1 — R2 — 地，节点 2 为分压点。 */
export function buildSeries({ voltage_v: V, resistance_ohm: R1, r2_ohm: R2 }) {
  return {
    sources: [{ id: 'V1', from: 1, to: 0, v: V }],
    resistors: [
      { id: 'R1', from: 1, to: 2, r: R1 },
      { id: 'R2', from: 2, to: 0, r: R2 },
    ],
  }
}

/** 并联：R1、R2 都接在节点 1 与地之间。 */
export function buildParallel({ voltage_v: V, resistance_ohm: R1, r2_ohm: R2 }) {
  return {
    sources: [{ id: 'V1', from: 1, to: 0, v: V }],
    resistors: [
      { id: 'R1', from: 1, to: 0, r: R1 },
      { id: 'R2', from: 1, to: 0, r: R2 },
    ],
  }
}

/** 与引擎无关的解析参考。 */
export function analyticOhm({ voltage_v: V, resistance_ohm: R }) {
  return { I: V / R, U: V, Req: R }
}
export function analyticSeries({ voltage_v: V, resistance_ohm: R1, r2_ohm: R2 }) {
  const I = V / (R1 + R2)
  return { I, U1: I * R1, U2: I * R2, Req: R1 + R2 }
}
export function analyticParallel({ voltage_v: V, resistance_ohm: R1, r2_ohm: R2 }) {
  const I1 = V / R1
  const I2 = V / R2
  return { I1, I2, I: I1 + I2, Req: (R1 * R2) / (R1 + R2) }
}

/**
 * 把 MNA 结果映射成教学读数（与解析参考同名）。
 */
export function measureFromSolution(recipeId, sol) {
  if (recipeId === 'ohms-law') {
    return { I: sol.resistorCurrents.R1, U: sol.resistorVoltages.R1, Req: 1 / (sol.resistorCurrents.R1 / sol.resistorVoltages.R1) }
  }
  if (recipeId === 'series') {
    return {
      I: sol.resistorCurrents.R1,
      U1: sol.resistorVoltages.R1,
      U2: sol.resistorVoltages.R2,
    }
  }
  if (recipeId === 'parallel') {
    return {
      I1: sol.resistorCurrents.R1,
      I2: sol.resistorCurrents.R2,
      I: sol.resistorCurrents.R1 + sol.resistorCurrents.R2,
      Req: sol.nodeVoltages[1] / (sol.resistorCurrents.R1 + sol.resistorCurrents.R2),
    }
  }
  throw new Error(`RECIPE_UNKNOWN: ${recipeId}`)
}
