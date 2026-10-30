/** 六个工具共用的输出 schema 与文本投影。 */

export function resultSchema() {
  return {
    type: 'object',
    additionalProperties: false,
    properties: {
      ok: { type: 'boolean', required: true },
      stage: { type: 'string', description: 'L1 / L2 / RENDER / L3 / DONE / LOAD' },
      code: { type: 'string' },
      summary: { type: 'string', required: true },
      data: { type: 'object', additionalProperties: true, properties: {} },
      hints: { type: 'array', items: { type: 'string' } },
    },
  }
}

export function renderResult(_args, value) {
  const hints = Array.isArray(value.hints) ? value.hints.filter(Boolean) : []
  const text = hints.length
    ? `${value.summary}\n\n建议：\n- ${hints.join('\n- ')}`
    : value.summary
  return [{ type: 'text', text }]
}

export function designParams() {
  return {
    recipe_id: {
      type: 'string',
      required: true,
      description: '配方 id：horizontal / oblique45 / complementary。先调 experiment_recipes 获取。',
    },
    params: {
      type: 'object',
      required: true,
      additionalProperties: true,
      properties: {},
      description: '按模板传参：抛体 {v0, angle_deg, h0} 或互补角 {v0, h0, angles_deg:[θ1,θ2]}；单摆 {}（配方固定扫描）；电路 {voltage_v, resistance_ohm, r2_ohm?}。不确定就传 {}，用配方默认值。',
    },
    why_recipe: {
      type: 'string',
      required: true,
      description: '为什么选这个配方。必须点到配方关键词与物理量，并写出因果（因为/因此/所以）。',
    },
    student_task: {
      type: 'string',
      required: true,
      description: '学生要做什么、看什么。必须包含操作动词与观测量。',
    },
    expected_numbers: {
      type: 'object',
      additionalProperties: true,
      properties: {},
      description: '可选。若提供，会与解析值对账（容差 1%）；不确定就省略，工具会补全。',
    },
    template_id: {
      type: 'string',
      description: '模板 id：mechanics.projectile（抛体）/ mechanics.pendulum（单摆）/ circuits.ohms_law（直流电路）。先调 experiment_recipes 获取。',
    },
    out_name: {
      type: 'string',
      description: '可选输出文件名（不含扩展名），只允许字母数字下划线连字符。',
    },
  }
}
