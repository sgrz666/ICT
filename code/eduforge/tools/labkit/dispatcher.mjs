/**
 * LabKit 模板分派器：插件只认这层，不直接依赖某个实验的实现。
 *
 * 三个实验共用同一套 design 结构（template_id / recipe_id / params / why_recipe /
 * student_task / expected_numbers），但 L1/L2/渲染/验证的细节各自独立。
 */
import { readFileSync } from 'node:fs'
import { join } from 'node:path'
import { assertUnder } from './lib/fs-safe.mjs'
import { checkDesign as projectileCheck } from './lib/check.mjs'
import { simulateDesign as projectileSimulate } from './lib/simulate.mjs'
import { renderSingleFile as projectileRender } from './lib/render-single-file.mjs'
import { verifySingleFile as projectileVerify } from './lib/verify-single-file.mjs'
import { checkDesign as pendulumCheck } from './pendulum/check.mjs'
import { simulateDesign as pendulumSimulate } from './pendulum/simulate.mjs'
import { renderSingleFile as pendulumRender } from './pendulum/render.mjs'
import { checkDesign as circuitCheck } from './circuit/check.mjs'
import { simulateDesign as circuitSimulate } from './circuit/simulate.mjs'
import { renderSingleFile as circuitRender } from './circuit/render.mjs'

const TABLE = {
  'mechanics.projectile': {
    check: projectileCheck,
    simulate: projectileSimulate,
    render: projectileRender,
    verify: projectileVerify,
    verifyOptions: {
      probe: { param: 'v0', factor: 1.25, metric: 'R' },
      metricKeys: ['T', 'R', 'H'],
    },
  },
  'mechanics.pendulum': {
    check: pendulumCheck,
    simulate: pendulumSimulate,
    render: pendulumRender,
    verify: projectileVerify,
    verifyOptions: {
      probe: { param: 'length_m', factor: 1.25, metric: 'T' },
      metricKeys: ['T'],
    },
  },
  'circuits.ohms_law': {
    check: circuitCheck,
    simulate: circuitSimulate,
    render: circuitRender,
    verify: projectileVerify,
    verifyOptions: (evidence) => ({
      probe: { param: 'resistance_ohm', factor: 1.5, metric: 'I' },
      metricKeys: evidence.recipe_id === 'ohms-law'
        ? ['I', 'U']
        : evidence.recipe_id === 'series'
          ? ['I', 'U1', 'U2']
          : ['I1', 'I2', 'I', 'Req'],
    }),
  },
}

export const TEMPLATE_IDS = Object.keys(TABLE)

function entryFor(templateId) {
  return TABLE[templateId] ?? null
}

function unknown(templateId, stage) {
  return {
    ok: false,
    stage,
    code: 'TEMPLATE_NOT_FOUND',
    summary: `未知模板：${templateId}`,
    data: { available: TEMPLATE_IDS },
    hints: [`可用模板：${TEMPLATE_IDS.join(' / ')}`],
  }
}

export function checkDesign(args) {
  const id = args?.design?.template_id ?? 'mechanics.projectile'
  const entry = entryFor(id)
  return entry ? entry.check(args) : unknown(id, 'L1')
}

export function simulateDesign(args) {
  const id = args?.design?.template_id ?? 'mechanics.projectile'
  const entry = entryFor(id)
  return entry ? entry.simulate(args) : unknown(id, 'L2')
}

export function renderSingleFile(args) {
  const id = args?.design?.template_id ?? 'mechanics.projectile'
  const entry = entryFor(id)
  return entry ? entry.render(args) : unknown(id, 'RENDER')
}

export function verifySingleFile(args) {
  let evidence
  try {
    const root = args.outRoot ?? join(args.repoRoot, 'output/eduforge/candidates/labkit')
    assertUnder(root, args.htmlPath)
    assertUnder(root, args.evidencePath)
    evidence = JSON.parse(readFileSync(args.evidencePath, 'utf8'))
  } catch (e) {
    return {
      ok: false, stage: 'L3', code: e.code === 'PATH_ESCAPE' ? 'PATH_ESCAPE' : 'EVIDENCE_UNREADABLE',
      detail: `读不到 evidence：${e.message}`,
      hints: ['先跑 experiment_simulate 生成 evidence.json。'],
    }
  }
  const entry = entryFor(evidence.template_id)
  if (!entry) return unknown(evidence.template_id, 'L3')
  const options = typeof entry.verifyOptions === 'function' ? entry.verifyOptions(evidence) : entry.verifyOptions
  return entry.verify({ ...args, ...options })
}
