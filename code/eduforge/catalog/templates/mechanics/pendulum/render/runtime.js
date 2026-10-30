/* 单摆实验页面运行时。由 pendulum/render.mjs 内联；零网络、零构建。 */
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
    length_m: DATA.initial.length_m,
    angle0_deg: DATA.initial.angle0_deg,
    playing: true,
    time: 0,
  }

  var core = null
  var aEff = 0
  var current = null
  var presets = []
  var lastFrame = 0

  function clamp(v, lo, hi) { return Math.min(hi, Math.max(lo, v)) }
  function fmt(v, d) { return Number(v).toFixed(d === undefined ? 2 : d) }
  function el(id) { return document.getElementById(id) }

  function analyticFor(L, deg) {
    return pendulumAnalytic({ lengthM: L, angle0Deg: deg, gravity: aEff })
  }

  function computeOne(L, deg) {
    var run = core.swing({ lengthM: L, angle0Deg: deg, damping: 0 })
    var analytic = analyticFor(L, deg)
    return {
      params: { length_m: L, angle0_deg: deg },
      samples: run.samples,
      period: run.period,
      maxStretch: run.maxStretch,
      measured: { T: run.period },
      analytic: analytic,
    }
  }

  function recompute() {
    current = computeOne(state.length_m, state.angle0_deg)
    presets = recipe.scenarios.map(function (s) {
      var c = computeOne(s.params.length_m, s.params.angle0_deg)
      c.id = s.id
      return c
    })
    state.time = 0
    updateResult()
    renderReadouts()
    renderPresets()
    draw()
  }

  function updateResult() {
    var first = recipe.scenarios[0]
    window.__RESULT = {
      params: { length_m: state.length_m, angle0_deg: state.angle0_deg },
      scenarios: [{
        id: first.id,
        params: { length_m: state.length_m, angle0_deg: state.angle0_deg },
        measured: { T: Number(current.period.toFixed(6)) },
        analytic: {
          T0: Number(current.analytic.T0.toFixed(6)),
          Texact: Number(current.analytic.Texact.toFixed(6)),
        },
      }],
      current: {
        params: { length_m: state.length_m, angle0_deg: state.angle0_deg },
        measured: { T: Number(current.period.toFixed(6)) },
        analytic: {
          T0: Number(current.analytic.T0.toFixed(6)),
          Texact: Number(current.analytic.Texact.toFixed(6)),
        },
      },
      design_hash: DATA.meta.design_hash,
      engine: { id: DATA.engine.id, version: DATA.engine.version, calibrated_acceleration: aEff },
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
      var lab = document.createElement('span')
      lab.textContent = opts.label
      var val = document.createElement('span')
      val.className = 'val'
      val.textContent = opts.format(opts.get())
      row.appendChild(lab); row.appendChild(val)
      var input = document.createElement('input')
      input.type = 'range'
      input.min = String(opts.min); input.max = String(opts.max); input.step = String(opts.step)
      input.value = String(opts.get())
      input.addEventListener('input', function () {
        opts.set(Number(input.value))
        val.textContent = opts.format(opts.get())
        recompute()
      })
      wrap.appendChild(row); wrap.appendChild(input)
      if (opts.hint) {
        var h = document.createElement('div')
        h.className = 'hint'; h.textContent = opts.hint
        wrap.appendChild(h)
      }
      box.appendChild(wrap)
    }

    slider({
      label: '摆长 L',
      min: decision.length_range[0], max: decision.length_range[1], step: 0.05,
      get: function () { return state.length_m },
      set: function (v) { state.length_m = clamp(v, decision.length_range[0], decision.length_range[1]) },
      format: function (v) { return fmt(v, 2) + ' m' },
      hint: '周期与摆长的平方根成正比：L 变 4 倍，T 只变 2 倍。',
    })
    slider({
      label: '初始角 θ₀',
      min: decision.angle_range[0], max: decision.angle_range[1], step: 1,
      get: function () { return state.angle0_deg },
      set: function (v) { state.angle0_deg = clamp(v, decision.angle_range[0], decision.angle_range[1]) },
      format: function (v) { return fmt(v, 0) + '°' },
      hint: '小角度近似只在 θ₀ 较小时成立；30° 时周期比公式预测长约 1.7%。',
    })
  }

  function renderReadouts() {
    var c = current
    var dev = Math.abs(c.measured.T - c.analytic.Texact) / c.analytic.Texact * 100
    var dev0 = Math.abs(c.measured.T - c.analytic.T0) / c.analytic.T0 * 100
    el('readouts').innerHTML =
      '<table class="readout"><tbody>' +
      '<tr><td>周期 T（实测）</td><td><b>' + fmt(c.measured.T, 4) + ' s</b></td></tr>' +
      '<tr><td>小角度公式 T₀</td><td>' + fmt(c.analytic.T0, 4) + ' s</td></tr>' +
      '<tr><td>精确解 T（椭圆积分）</td><td>' + fmt(c.analytic.Texact, 4) + ' s</td></tr>' +
      '<tr><td>相对精确解偏差</td><td class="' + (dev <= 1 ? 'ok' : 'bad') + '">' + fmt(dev, 3) + '%（容差 1%）</td></tr>' +
      '<tr><td>小角度公式误差</td><td class="' + (dev0 <= 1 ? 'muted' : 'bad') + '">' + fmt(dev0, 3) + '%</td></tr>' +
      '</tbody></table>'
  }

  function renderPresets() {
    var rows = '<thead><tr><th>场景</th><th>L (m)</th><th>θ₀ (°)</th><th>T 实测 (s)</th><th>T 精确 (s)</th><th>偏差</th></tr></thead><tbody>'
    presets.forEach(function (p) {
      var dev = Math.abs(p.measured.T - p.analytic.Texact) / p.analytic.Texact * 100
      rows += '<tr><td>' + p.id + '</td><td>' + fmt(p.params.length_m, 2) + '</td><td>' + fmt(p.params.angle0_deg, 0) +
        '</td><td>' + fmt(p.measured.T, 4) + '</td><td>' + fmt(p.analytic.Texact, 4) +
        '</td><td class="' + (dev <= 1 ? 'ok' : 'bad') + '">' + fmt(dev, 2) + '%</td></tr>'
    })
    el('presets').innerHTML = '<table class="readout">' + rows + '</tbody></table>'
  }

  function draw() {
    var ml = 40, mr = 40, mt = 30, mb = 40
    ctx.setTransform(dpr, 0, 0, dpr, 0, 0)
    ctx.clearRect(0, 0, W, H)
    ctx.fillStyle = '#fbfcfa'
    ctx.fillRect(0, 0, W, H)

    var pivotX = W / 2
    var pivotY = mt + 40
    // 按当前摆长取景：摆球始终占画面主要高度，L 变化时整体缩放。
    var maxL = Math.max(1.0, state.length_m * 1.25)
    var scale = (H - pivotY - mb - 30) / maxL

    function sx(x) { return pivotX + x * scale }
    function sy(y) { return pivotY + y * scale }

    // 天花板
    ctx.strokeStyle = '#9aa39d'
    ctx.lineWidth = 4
    ctx.beginPath(); ctx.moveTo(pivotX - 120, pivotY - 6); ctx.lineTo(pivotX + 120, pivotY - 6); ctx.stroke()
    ctx.strokeStyle = '#d9ddd7'; ctx.lineWidth = 1
    for (var i = -110; i <= 110; i += 16) {
      ctx.beginPath(); ctx.moveTo(pivotX + i, pivotY - 6); ctx.lineTo(pivotX + i + 10, pivotY - 16); ctx.stroke()
    }

    // 竖直参考线
    ctx.save()
    ctx.setLineDash([5, 5])
    ctx.strokeStyle = '#c6cdc7'
    ctx.beginPath(); ctx.moveTo(pivotX, pivotY); ctx.lineTo(pivotX, pivotY + maxL * scale); ctx.stroke()
    ctx.restore()

    // 历史轨迹（全部样本，淡色）
    ctx.strokeStyle = 'rgba(15,118,110,0.18)'
    ctx.lineWidth = 2
    ctx.beginPath()
    current.samples.forEach(function (s, idx) {
      if (idx === 0) ctx.moveTo(sx(s.x), sy(s.y)); else ctx.lineTo(sx(s.x), sy(s.y))
    })
    ctx.stroke()

    // 当前时刻的样本
    var idx = Math.min(current.samples.length - 1, Math.floor(state.time / DATA.engine.dt_s))
    var s = current.samples[idx]
    var angle = Math.atan2(s.x, s.y)

    // 角度弧
    ctx.strokeStyle = '#b45309'
    ctx.lineWidth = 1.6
    ctx.beginPath()
    ctx.arc(pivotX, pivotY, 52, Math.PI / 2 - angle, Math.PI / 2, true)
    ctx.stroke()
    ctx.fillStyle = '#b45309'
    ctx.font = '13px system-ui, sans-serif'
    ctx.fillText('θ=' + fmt(angle * 180 / Math.PI, 1) + '°', pivotX + 58, pivotY + 58)

    // 摆杆
    ctx.strokeStyle = '#33403c'
    ctx.lineWidth = 2.5
    ctx.beginPath(); ctx.moveTo(pivotX, pivotY); ctx.lineTo(sx(s.x), sy(s.y)); ctx.stroke()

    // 支点与摆球
    ctx.fillStyle = '#33403c'
    ctx.beginPath(); ctx.arc(pivotX, pivotY, 6, 0, Math.PI * 2); ctx.fill()
    ctx.fillStyle = '#0f766e'
    ctx.beginPath(); ctx.arc(sx(s.x), sy(s.y), Math.max(8, DATA.engine.radius * scale), 0, Math.PI * 2); ctx.fill()
    ctx.strokeStyle = '#ffffff'; ctx.lineWidth = 2; ctx.stroke()

    // 摆长标注
    var midX = (pivotX + sx(s.x)) / 2
    var midY = (pivotY + sy(s.y)) / 2
    ctx.fillStyle = '#5b6663'
    ctx.font = '12px system-ui, sans-serif'
    ctx.fillText('L=' + fmt(state.length_m, 2) + ' m', midX + 10, midY)

    // 周期标注
    ctx.fillStyle = '#0f766e'
    ctx.font = '14px system-ui, sans-serif'
    ctx.fillText('T = ' + fmt(current.period, 4) + ' s', W - 180, H - 20)
  }

  function loop(now) {
    if (!state.playing) { lastFrame = now; requestAnimationFrame(loop); return }
    var dt = lastFrame ? Math.min(0.05, (now - lastFrame) / 1000) : 0.016
    lastFrame = now
    state.time += dt
    var last = current.samples[current.samples.length - 1]
    if (state.time > last.t) {
      state.time = last.t
      state.playing = false
      el('play').textContent = '播放'
    }
    draw()
    requestAnimationFrame(loop)
  }

  function init() {
    try {
      if (!window.Matter) throw new Error('Matter.js 未内联')
      canvas.width = W * dpr
      canvas.height = H * dpr
      canvas.style.aspectRatio = W + ' / ' + H

      core = createPendulumCore(window.Matter, {
        gravity: DATA.engine.gravity,
        gravityScale: DATA.engine.gravity_scale,
        dtS: DATA.engine.dt_s,
        radius: DATA.engine.radius,
      })
      aEff = core.calibrate().a_measured

      el('title').textContent = DATA.meta.title
      el('subtitle').textContent = DATA.recipe.title + ' · 可调参实时仿真'
      el('purpose').textContent = DATA.design.why_recipe
      el('task').textContent = DATA.design.student_task
      el('formula').textContent = DATA.acceptance.formulas_display.T0 + '；' + DATA.acceptance.formulas_display.Texact
      el('engine-line').textContent = '引擎 matter-js ' + DATA.engine.version + ' · 标定 g=' + fmt(aEff, 3) + ' m/s² · 固定步长 ' + fmt(DATA.engine.dt_s, 5) + ' s'
      el('hash-line').textContent = '设计指纹 ' + DATA.meta.design_hash.slice(0, 19) + '…'

      var badge = el('badge')
      if (DATA.evidence && DATA.evidence.verdict === 'pass') {
        badge.className = 'badge pass'
        badge.textContent = '物理验收通过（L2）'
      } else {
        badge.className = 'badge fail'
        badge.textContent = '物理验收未通过'
      }

      var legend = el('legend')
      legend.innerHTML = '<span class="item"><span class="swatch" style="background:#0f766e"></span>摆球轨迹</span>' +
        '<span class="item"><span class="swatch" style="background:#b45309"></span>摆角</span>'

      buildControls()
      recompute()

      el('play').addEventListener('click', function () {
        if (!state.playing && state.time >= current.samples[current.samples.length - 1].t) state.time = 0
        state.playing = !state.playing
        el('play').textContent = state.playing ? '暂停' : '播放'
      })
      el('reset').addEventListener('click', function () {
        state.time = 0
        state.playing = true
        el('play').textContent = '暂停'
        draw()
      })

      window.__LAB = {
        setParams: function (next) {
          if (next && typeof next === 'object') {
            if (typeof next.length_m === 'number') state.length_m = clamp(next.length_m, decision.length_range[0], decision.length_range[1])
            if (typeof next.angle0_deg === 'number') state.angle0_deg = clamp(next.angle0_deg, decision.angle_range[0], decision.angle_range[1])
          }
          syncControls()
          recompute()
          return window.__RESULT
        },
        getState: function () { return JSON.parse(JSON.stringify(state)) },
        recompute: recompute,
      }

      window.__STATUS = 'ready'
      requestAnimationFrame(loop)
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
    if (inputs.length >= 2) {
      inputs[0].value = String(state.length_m)
      inputs[0].previousSibling.querySelector('.val').textContent = fmt(state.length_m, 2) + ' m'
      inputs[1].value = String(state.angle0_deg)
      inputs[1].previousSibling.querySelector('.val').textContent = fmt(state.angle0_deg, 0) + '°'
    }
  }

  if (document.readyState === 'loading') {
    document.addEventListener('DOMContentLoaded', init)
  } else {
    init()
  }
})()
