/* 直流电路页面运行时。由 circuit/render.mjs 内联；零网络、零构建。 */
(function () {
  'use strict'

  var DATA = window.__LAB_DATA__
  var recipe = DATA.recipe
  var decision = DATA.decision
  var renderCfg = DATA.render
  var design = DATA.design

  var canvas = document.getElementById('canvas')
  var ctx = canvas.getContext('2d')
  var dpr = Math.min(window.devicePixelRatio || 1, 2)
  var W = renderCfg.canvas.width
  var H = renderCfg.canvas.height

  var state = {
    voltage_v: DATA.initial.voltage_v,
    resistance_ohm: DATA.initial.resistance_ohm,
    r2_ohm: DATA.initial.r2_ohm || 220,
  }
  var current = null

  function clamp(v, lo, hi) { return Math.min(hi, Math.max(lo, v)) }
  function fmt(v, d) { return Number(v).toFixed(d === undefined ? 3 : d) }
  function el(id) { return document.getElementById(id) }

  function paramsOfState() {
    var p = { voltage_v: state.voltage_v, resistance_ohm: state.resistance_ohm }
    if (recipe.id !== 'ohms-law') p.r2_ohm = state.r2_ohm
    return p
  }

  function analyticOf(p) {
    if (recipe.id === 'ohms-law') return analyticOhm(p)
    if (recipe.id === 'series') return analyticSeries(p)
    return analyticParallel(p)
  }

  function buildNetlist(p) {
    if (recipe.id === 'ohms-law') return buildOhm(p)
    if (recipe.id === 'series') return buildSeries(p)
    return buildParallel(p)
  }

  function recompute() {
    var p = paramsOfState()
    var sol = solveDC(buildNetlist(p))
    var measured = measureFromSolution(recipe.id, sol)
    var analytic = analyticOf(p)
    current = { params: p, sol: sol, measured: measured, analytic: analytic }
    updateResult()
    renderReadouts()
    draw()
  }

  function updateResult() {
    var m = {}
    var a = {}
    recipe.metric_keys.forEach(function (k) {
      m[k] = Number(current.measured[k].toFixed(9))
      a[k] = Number(current.analytic[k].toFixed(9))
    })
    window.__RESULT = {
      params: current.params,
      scenarios: [{ id: 'main', params: current.params, measured: m, analytic: a }],
      design_hash: DATA.meta.design_hash,
      engine: { id: DATA.engine.id, version: DATA.engine.version },
    }
  }

  function buildControls() {
    var box = el('controls')
    box.innerHTML = ''
    function slider(opts) {
      var wrap = document.createElement('div')
      wrap.className = 'control'
      var row = document.createElement('div')
      row.className = 'row'
      var lab = document.createElement('span'); lab.textContent = opts.label
      var val = document.createElement('span'); val.className = 'val'; val.textContent = opts.format(opts.get())
      row.appendChild(lab); row.appendChild(val)
      var input = document.createElement('input')
      input.type = 'range'; input.min = String(opts.min); input.max = String(opts.max); input.step = String(opts.step)
      input.value = String(opts.get())
      input.addEventListener('input', function () {
        opts.set(Number(input.value)); val.textContent = opts.format(opts.get()); recompute()
      })
      wrap.appendChild(row); wrap.appendChild(input)
      if (opts.hint) {
        var h = document.createElement('div'); h.className = 'hint'; h.textContent = opts.hint; wrap.appendChild(h)
      }
      box.appendChild(wrap)
    }
    slider({
      label: '电源电压 U',
      min: decision.voltage_range[0], max: decision.voltage_range[1], step: 0.5,
      get: function () { return state.voltage_v },
      set: function (v) { state.voltage_v = clamp(v, decision.voltage_range[0], decision.voltage_range[1]) },
      format: function (v) { return fmt(v, 1) + ' V' },
      hint: '电压源固定为直流；改变电压会按比例改变所有电流。',
    })
    slider({
      label: recipe.id === 'ohms-law' ? '电阻 R' : '电阻 R1',
      min: decision.resistance_range[0], max: decision.resistance_range[1], step: 10,
      get: function () { return state.resistance_ohm },
      set: function (v) { state.resistance_ohm = clamp(v, decision.resistance_range[0], decision.resistance_range[1]) },
      format: function (v) { return fmt(v, 0) + ' Ω' },
      hint: recipe.id === 'ohms-law' ? '电压不变时，电流与电阻成反比。' : '改变 R1 会同时改变总电流与分压。',
    })
    if (recipe.id !== 'ohms-law') {
      slider({
        label: '电阻 R2',
        min: decision.resistance_range[0], max: decision.resistance_range[1], step: 10,
        get: function () { return state.r2_ohm },
        set: function (v) { state.r2_ohm = clamp(v, decision.resistance_range[0], decision.resistance_range[1]) },
        format: function (v) { return fmt(v, 0) + ' Ω' },
        hint: recipe.id === 'series' ? '串联时 R2 越大，分到的电压越大。' : '并联时 R2 越小，支路电流越大。',
      })
    }
  }

  function renderReadouts() {
    var keys = recipe.metric_keys
    var labels = {
      I: '电流 I (A)', U: '电压 U (V)', U1: 'U1 (V)', U2: 'U2 (V)',
      I1: 'I1 (A)', I2: 'I2 (A)', Req: '等效电阻 (Ω)',
    }
    var rows = '<thead><tr><th>量</th><th>实测</th><th>解析</th><th>偏差</th></tr></thead><tbody>'
    keys.forEach(function (k) {
      var m = current.measured[k]
      var a = current.analytic[k]
      var rel = a === 0 ? 0 : Math.abs((m - a) / a) * 100
      rows += '<tr><td>' + (labels[k] || k) + '</td><td>' + fmt(m, 6) + '</td><td>' + fmt(a, 6) +
        '</td><td class="' + (rel <= 1e-4 ? 'ok' : 'bad') + '">' + (rel < 1e-4 ? '0' : rel.toExponential(1)) + '%</td></tr>'
    })
    el('readouts').innerHTML = '<table class="readout">' + rows + '</tbody></table>'
  }

  function wire(x1, y1, x2, y2) {
    ctx.strokeStyle = '#33403c'
    ctx.lineWidth = 2.5
    ctx.beginPath(); ctx.moveTo(x1, y1); ctx.lineTo(x2, y2); ctx.stroke()
  }

  function resistor(x, y, w, h, label, value) {
    ctx.fillStyle = '#ffffff'
    ctx.strokeStyle = '#0f766e'
    ctx.lineWidth = 2.5
    ctx.fillRect(x, y, w, h)
    ctx.strokeRect(x, y, w, h)
    ctx.fillStyle = '#0f766e'
    ctx.font = '13px system-ui, sans-serif'
    ctx.fillText(label, x + 4, y - 8)
    ctx.fillStyle = '#5b6663'
    ctx.font = '12px system-ui, sans-serif'
    ctx.fillText(value, x + 4, y + h + 16)
  }

  function battery(x, y1, y2, label) {
    wire(x, y1, x, y1 + 40)
    wire(x, y2 - 40, x, y2)
    ctx.strokeStyle = '#b45309'
    ctx.lineWidth = 3
    ctx.beginPath(); ctx.moveTo(x - 18, y1 + 40); ctx.lineTo(x + 18, y1 + 40); ctx.stroke()
    ctx.beginPath(); ctx.moveTo(x - 10, y1 + 55); ctx.lineTo(x + 10, y1 + 55); ctx.stroke()
    ctx.fillStyle = '#b45309'
    ctx.font = '13px system-ui, sans-serif'
    ctx.fillText(label, x + 24, (y1 + y2) / 2)
  }

  function draw() {
    ctx.setTransform(dpr, 0, 0, dpr, 0, 0)
    ctx.clearRect(0, 0, W, H)
    ctx.fillStyle = '#fbfcfa'
    ctx.fillRect(0, 0, W, H)
    ctx.font = '14px system-ui, sans-serif'

    var left = 190, right = 790, top = 150, bottom = 420

    if (recipe.id === 'ohms-law') {
      battery(left, top, bottom, 'U=' + fmt(state.voltage_v, 1) + ' V')
      wire(left, top, 420, top); wire(540, top, right, top)
      wire(right, top, right, bottom); wire(right, bottom, left, bottom)
      resistor(420, top - 14, 120, 28, 'R1', fmt(state.resistance_ohm, 0) + ' Ω')
      ctx.fillStyle = '#0f766e'
      ctx.fillText('I = ' + fmt(current.measured.I, 4) + ' A', 470, top - 34)
    } else if (recipe.id === 'series') {
      battery(left, top, bottom, 'U=' + fmt(state.voltage_v, 1) + ' V')
      wire(left, top, 320, top); wire(440, top, 560, top); wire(680, top, right, top)
      wire(right, top, right, bottom); wire(right, bottom, left, bottom)
      resistor(320, top - 14, 120, 28, 'R1', fmt(state.resistance_ohm, 0) + ' Ω')
      resistor(560, top - 14, 120, 28, 'R2', fmt(state.r2_ohm, 0) + ' Ω')
      ctx.fillStyle = '#0f766e'
      ctx.fillText('I = ' + fmt(current.measured.I, 4) + ' A（串联处处相同）', 300, top - 44)
      ctx.fillStyle = '#5b6663'
      ctx.fillText('U1=' + fmt(current.measured.U1, 3) + ' V', 330, top + 44)
      ctx.fillText('U2=' + fmt(current.measured.U2, 3) + ' V', 570, top + 44)
    } else {
      battery(left, top, bottom, 'U=' + fmt(state.voltage_v, 1) + ' V')
      // 上支路 R1、中支路 R2，左右竖轨
      wire(left, top, right, top)
      wire(left, 285, right, 285)
      wire(right, top, right, bottom)
      wire(right, 285, right, bottom)
      wire(left, top, left, 285)
      wire(left, 285, left, bottom)
      wire(left, bottom, right, bottom)
      resistor(420, top - 14, 120, 28, 'R1', fmt(state.resistance_ohm, 0) + ' Ω')
      resistor(420, 271, 120, 28, 'R2', fmt(state.r2_ohm, 0) + ' Ω')
      ctx.fillStyle = '#0f766e'
      ctx.fillText('I1 = ' + fmt(current.measured.I1, 4) + ' A', 560, top - 10)
      ctx.fillText('I2 = ' + fmt(current.measured.I2, 4) + ' A', 560, 300)
      ctx.fillStyle = '#5b6663'
      ctx.fillText('总电流 I = ' + fmt(current.measured.I, 4) + ' A', 300, bottom + 26)
      ctx.fillText('等效电阻 Req = ' + fmt(current.measured.Req, 2) + ' Ω', 560, bottom + 26)
    }

    // 标题与说明
    ctx.fillStyle = '#33403c'
    ctx.font = '16px system-ui, sans-serif'
    ctx.fillText(recipe.title, 40, 50)
    ctx.fillStyle = '#5b6663'
    ctx.font = '12px system-ui, sans-serif'
    ctx.fillText('MNA 求解 · 与解析式对照 · 读数实时更新', 40, 72)
  }

  function init() {
    try {
      canvas.width = W * dpr
      canvas.height = H * dpr
      canvas.style.aspectRatio = W + ' / ' + H

      el('title').textContent = DATA.meta.title
      el('subtitle').textContent = DATA.recipe.title + ' · 可调参实时仿真'
      el('purpose').textContent = DATA.design.why_recipe
      el('task').textContent = DATA.design.student_task
      var f = DATA.acceptance.formulas_display
      el('formula').textContent = recipe.id === 'ohms-law' ? f.ohm : recipe.id === 'series' ? f.series : f.parallel
      el('engine-line').textContent = '引擎 ' + DATA.engine.id + ' ' + DATA.engine.version + ' · 改进节点法（MNA）· CircuitJS1 交叉验证见 evidence'
      el('hash-line').textContent = '设计指纹 ' + DATA.meta.design_hash.slice(0, 19) + '…'

      var badge = el('badge')
      if (DATA.evidence && DATA.evidence.verdict === 'pass') {
        badge.className = 'badge pass'
        badge.textContent = '物理验收通过（L2）'
      } else {
        badge.className = 'badge fail'
        badge.textContent = '物理验收未通过'
      }

      el('legend').innerHTML = '<span class="item"><span class="swatch" style="background:#0f766e"></span>电阻</span>' +
        '<span class="item"><span class="swatch" style="background:#b45309"></span>电源</span>' +
        '<span class="item">读数由 MNA 实时求解</span>'

      buildControls()
      recompute()

      window.__LAB = {
        setParams: function (next) {
          if (next && typeof next === 'object') {
            if (typeof next.voltage_v === 'number') state.voltage_v = clamp(next.voltage_v, decision.voltage_range[0], decision.voltage_range[1])
            if (typeof next.resistance_ohm === 'number') state.resistance_ohm = clamp(next.resistance_ohm, decision.resistance_range[0], decision.resistance_range[1])
            if (typeof next.r2_ohm === 'number') state.r2_ohm = clamp(next.r2_ohm, decision.resistance_range[0], decision.resistance_range[1])
          }
          syncControls()
          recompute()
          return window.__RESULT
        },
        getState: function () { return JSON.parse(JSON.stringify(state)) },
        recompute: recompute,
      }

      window.__STATUS = 'ready'
    } catch (e) {
      window.__STATUS = 'error'
      window.__RESULT = { error: String(e && e.message || e) }
      var b = el('badge')
      b.className = 'badge fail'
      b.textContent = '页面初始化失败：' + String(e && e.message || e)
    }
  }

  function syncControls() {
    var inputs = document.querySelectorAll('#controls input[type="range"]')
    var values = [state.voltage_v, state.resistance_ohm, state.r2_ohm]
    var formats = [fmt(state.voltage_v, 1) + ' V', fmt(state.resistance_ohm, 0) + ' Ω', fmt(state.r2_ohm, 0) + ' Ω']
    for (var i = 0; i < inputs.length && i < values.length; i += 1) {
      inputs[i].value = String(values[i])
      var val = inputs[i].previousSibling.querySelector('.val')
      if (val) val.textContent = formats[i]
    }
  }

  if (document.readyState === 'loading') document.addEventListener('DOMContentLoaded', init)
  else init()
})()
