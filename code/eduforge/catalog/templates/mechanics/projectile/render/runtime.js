/* 抛体实验页面运行时。由 render-single-file.mjs 内联；不依赖网络、不依赖构建工具。 */
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
    v0: design.params.v0,
    h0: design.params.h0,
    angles: recipe.params_mode === 'pair'
      ? design.params.angles_deg.slice()
      : [design.params.angle_deg],
    keepComplementary: true,
    playing: true,
    time: 0,
    speed: 1,
  }

  var core = null
  var aEff = 0
  var computed = []
  var lastFrame = 0

  function clamp(v, lo, hi) { return Math.min(hi, Math.max(lo, v)) }
  function fmt(v, d) { return Number(v).toFixed(d === undefined ? 2 : d) }
  function el(id) { return document.getElementById(id) }

  function scenarioDefs() {
    if (recipe.params_mode === 'pair') {
      return state.angles.map(function (angle, i) {
        return {
          id: (recipe.scenarios[i] && recipe.scenarios[i].id) || ('s' + (i + 1)),
          label: fmt(angle, 0) + '°',
          params: { v0: state.v0, angle_deg: angle, h0: state.h0 },
        }
      })
    }
    return [{
      id: recipe.scenarios[0].id,
      label: recipe.id === 'horizontal' ? '平抛' : fmt(state.angles[0], 0) + '°',
      params: { v0: state.v0, angle_deg: state.angles[0], h0: state.h0 },
    }]
  }

  function measuredOf(flight) {
    return {
      T: flight.landed ? flight.landed.t : 0,
      R: flight.landed ? flight.landed.x : 0,
      H: flight.apex.y,
      apex_y: flight.apex.y,
    }
  }

  function recompute() {
    var defs = scenarioDefs()
    computed = defs.map(function (d) {
      var flight = core.fly({
        h0: d.params.h0,
        v0: d.params.v0,
        angleDeg: d.params.angle_deg,
        frictionAir: 0,
      })
      var analytic = core.analytic({
        h0: d.params.h0,
        v0: d.params.v0,
        angleDeg: d.params.angle_deg,
        aEff: aEff,
      })
      var apexSample = flight.samples.reduce(function (best, s) {
        return s.y > best.y ? s : best
      }, flight.samples[0])
      return {
        id: d.id,
        label: d.label,
        params: d.params,
        samples: flight.samples,
        landed: flight.landed,
        apex: flight.apex,
        apexSample: apexSample,
        measured: measuredOf(flight),
        analytic: analytic,
      }
    })
    state.time = 0
    updateResult()
    renderReadouts()
    draw()
  }

  function updateResult() {
    var result = {
      params: recipe.params_mode === 'pair'
        ? { v0: state.v0, h0: state.h0, angles_deg: state.angles.slice() }
        : { v0: state.v0, h0: state.h0, angle_deg: state.angles[0] },
      scenarios: computed.map(function (c) {
        return {
          id: c.id,
          params: c.params,
          measured: {
            T: Number(c.measured.T.toFixed(6)),
            R: Number(c.measured.R.toFixed(6)),
            H: Number(c.measured.H.toFixed(6)),
            apex_y: Number(c.measured.apex_y.toFixed(6)),
          },
          analytic: {
            T: Number(c.analytic.T.toFixed(6)),
            R: Number(c.analytic.R.toFixed(6)),
            H: Number(c.analytic.H.toFixed(6)),
            apex_y: Number(c.analytic.apex_y.toFixed(6)),
          },
        }
      }),
      design_hash: DATA.meta.design_hash,
      engine: { id: DATA.engine.id, version: DATA.engine.version, calibrated_acceleration: aEff },
    }
    if (recipe.params_mode === 'pair' && computed.length === 2) {
      result.ratio_R = computed[0].measured.R / computed[1].measured.R
    }
    window.__RESULT = result
  }

  function buildControls() {
    var box = el('controls')
    box.innerHTML = ''
    angleInputs = []

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
      row.appendChild(lab)
      row.appendChild(val)
      var input = document.createElement('input')
      input.type = 'range'
      input.min = String(opts.min)
      input.max = String(opts.max)
      input.step = String(opts.step)
      input.value = String(opts.get())
      input.addEventListener('input', function () {
        opts.set(Number(input.value))
        val.textContent = opts.format(opts.get())
        recompute()
      })
      wrap.appendChild(row)
      wrap.appendChild(input)
      if (opts.hint) {
        var hint = document.createElement('div')
        hint.className = 'hint'
        hint.textContent = opts.hint
        wrap.appendChild(hint)
      }
      box.appendChild(wrap)
      return { input: input, val: val, format: opts.format, get: opts.get }
    }

    slider({
      label: '初速度 v₀',
      min: decision.v0_range[0], max: decision.v0_range[1], step: 0.5,
      get: function () { return state.v0 },
      set: function (v) { state.v0 = clamp(v, decision.v0_range[0], decision.v0_range[1]) },
      format: function (v) { return fmt(v, 1) + ' m/s' },
      hint: '水平方向速度。斜抛时它同时决定射程与最高点。',
    })

    slider({
      label: '初始高度 h₀',
      min: decision.h0_range[0], max: decision.h0_range[1], step: 0.5,
      get: function () { return state.h0 },
      set: function (v) { state.h0 = clamp(v, decision.h0_range[0], decision.h0_range[1]) },
      format: function (v) { return fmt(v, 1) + ' m' },
      hint: '抛出点离地高度。平抛时它单独决定飞行时间。',
    })

    if (recipe.id === 'horizontal') {
      var note = document.createElement('div')
      note.className = 'hint'
      note.textContent = '平抛配方固定发射角为 0°；改角度会变成斜抛，不属于本配方。'
      box.appendChild(note)
    } else if (recipe.params_mode === 'pair') {
      state.angles.forEach(function (_, i) {
        var handle = slider({
          label: '发射角 θ' + (i + 1),
          min: decision.angle_range_oblique[0], max: decision.angle_range_oblique[1], step: 1,
          get: function () { return state.angles[i] },
          set: function (v) {
            state.angles[i] = clamp(v, decision.angle_range_oblique[0], decision.angle_range_oblique[1])
            if (state.keepComplementary) {
              state.angles[1 - i] = 90 - state.angles[i]
            }
            syncAngleInputs()
          },
          format: function (v) { return fmt(v, 0) + '°' },
        })
        angleInputs.push(handle)
      })
      var toggle = document.createElement('label')
      toggle.className = 'toggle'
      var cb = document.createElement('input')
      cb.type = 'checkbox'
      cb.checked = state.keepComplementary
      cb.addEventListener('change', function () {
        state.keepComplementary = cb.checked
        if (cb.checked) {
          state.angles[1] = 90 - state.angles[0]
          syncAngleInputs()
          recompute()
        }
      })
      toggle.appendChild(cb)
      toggle.appendChild(document.createTextNode('保持互补（θ₁ + θ₂ = 90°）'))
      box.appendChild(toggle)
    } else {
      slider({
        label: '发射角 θ',
        min: decision.angle_range_oblique[0], max: decision.angle_range_oblique[1], step: 1,
        get: function () { return state.angles[0] },
        set: function (v) { state.angles[0] = clamp(v, decision.angle_range_oblique[0], decision.angle_range_oblique[1]) },
        format: function (v) { return fmt(v, 0) + '°' },
        hint: '拖动角度观察射程变化；45° 附近射程最大。',
      })
    }
  }

  var angleInputs = []
  function syncAngleInputs() {
    angleInputs.forEach(function (item) {
      item.input.value = String(item.get())
      item.val.textContent = item.format(item.get())
    })
  }

  function renderReadouts() {
    var box = el('readouts')
    var heads = '<thead><tr><th>场景</th><th>R (m)</th><th>T (s)</th><th>H (m)</th></tr></thead>'
    var rows = ''
    computed.forEach(function (c) {
      rows += '<tr><td>' + c.label + '</td><td>' + fmt(c.measured.R) + '</td><td>' + fmt(c.measured.T) + '</td><td>' + fmt(c.measured.H) + '</td></tr>'
      rows += '<tr><td style="color:#5b6663">解析式</td><td>' + fmt(c.analytic.R) + '</td><td>' + fmt(c.analytic.T) + '</td><td>' + fmt(c.analytic.H) + '</td></tr>'
      var devR = Math.abs(c.measured.R - c.analytic.R) / Math.abs(c.analytic.R || 1) * 100
      var devT = Math.abs(c.measured.T - c.analytic.T) / Math.abs(c.analytic.T || 1) * 100
      var devH = Math.abs(c.measured.H - c.analytic.H) / Math.abs(c.analytic.H || 1) * 100
      var worst = Math.max(devR, devT, devH)
      rows += '<tr><td style="color:#5b6663">偏差</td><td colspan="3" class="' + (worst <= 1 ? 'ok' : 'bad') + '">最大 ' + fmt(worst, 2) + '%（容差 1%）</td></tr>'
    })
    if (recipe.params_mode === 'pair' && computed.length === 2) {
      var ratio = computed[0].measured.R / computed[1].measured.R
      rows += '<tr><td>R(θ₁)/R(θ₂)</td><td colspan="3" class="' + (Math.abs(ratio - 1) * 100 <= 1 ? 'ok' : 'bad') + '">' + fmt(ratio, 4) + '（理论 1）</td></tr>'
    }
    box.innerHTML = '<table class="readout">' + heads + '<tbody>' + rows + '</tbody></table>'
  }

  function niceStep(maxValue, targetTicks) {
    var raw = maxValue / targetTicks
    var pow = Math.pow(10, Math.floor(Math.log10(Math.max(raw, 1e-6))))
    var candidates = [1, 2, 5, 10].map(function (m) { return m * pow })
    for (var i = 0; i < candidates.length; i++) {
      if (candidates[i] >= raw) return candidates[i]
    }
    return candidates[candidates.length - 1]
  }

  function draw() {
    var ml = 62, mr = 26, mt = 26, mb = 46
    ctx.setTransform(dpr, 0, 0, dpr, 0, 0)
    ctx.clearRect(0, 0, W, H)
    ctx.fillStyle = '#fbfcfa'
    ctx.fillRect(0, 0, W, H)

    var maxR = 1
    var maxH = 1
    computed.forEach(function (c) {
      maxR = Math.max(maxR, c.measured.R, c.analytic.R)
      maxH = Math.max(maxH, c.measured.H, c.analytic.H, c.params.h0)
    })
    var xMax = Math.max(1, maxR * decision.viewport_pad)
    var yMax = Math.max(1, maxH * decision.viewport_pad + 2)

    function sx(x) { return ml + (x / xMax) * (W - ml - mr) }
    function sy(y) { return H - mb - (y / yMax) * (H - mt - mb) }

    var stepX = niceStep(xMax, 9)
    var stepY = niceStep(yMax, 7)

    ctx.lineWidth = 1
    ctx.font = '12px system-ui, sans-serif'
    ctx.fillStyle = '#6b7570'
    ctx.strokeStyle = '#e5e9e3'

    for (var gx = 0; gx <= xMax + 1e-9; gx += stepX) {
      var px = sx(gx)
      ctx.beginPath(); ctx.moveTo(px, mt); ctx.lineTo(px, H - mb); ctx.stroke()
      ctx.fillText(fmt(gx, stepX < 1 ? 1 : 0), px - 6, H - mb + 18)
    }
    for (var gy = 0; gy <= yMax + 1e-9; gy += stepY) {
      var py = sy(gy)
      ctx.beginPath(); ctx.moveTo(ml, py); ctx.lineTo(W - mr, py); ctx.stroke()
      if (gy > 0) ctx.fillText(fmt(gy, stepY < 1 ? 1 : 0), 14, py + 4)
    }

    ctx.strokeStyle = '#9aa39d'
    ctx.lineWidth = 1.5
    ctx.beginPath(); ctx.moveTo(ml, sy(0)); ctx.lineTo(W - mr, sy(0)); ctx.stroke()

    ctx.fillStyle = '#4b5551'
    ctx.fillText('x (m)', W - mr - 34, sy(0) + 18)
    ctx.fillText('y (m)', ml + 4, mt + 12)

    computed.forEach(function (c, i) {
      var color = renderCfg.colors[i % renderCfg.colors.length]

      if (renderCfg.overlay_analytic) {
        ctx.save()
        ctx.setLineDash([6, 5])
        ctx.strokeStyle = 'rgba(90, 102, 97, 0.55)'
        ctx.lineWidth = 1.6
        ctx.beginPath()
        var n = 80
        for (var k = 0; k <= n; k++) {
          var t = (k / n) * c.analytic.T
          var th = (c.params.angle_deg * Math.PI) / 180
          var x = c.params.v0 * Math.cos(th) * t
          var y = c.params.h0 + c.params.v0 * Math.sin(th) * t - 0.5 * aEff * t * t
          if (k === 0) ctx.moveTo(sx(x), sy(y)); else ctx.lineTo(sx(x), sy(y))
        }
        ctx.stroke()
        ctx.restore()
      }

      ctx.strokeStyle = color
      ctx.lineWidth = 2.4
      ctx.beginPath()
      c.samples.forEach(function (s, idx) {
        if (idx === 0) ctx.moveTo(sx(s.x), sy(s.y)); else ctx.lineTo(sx(s.x), sy(s.y))
      })
      ctx.stroke()

      if (renderCfg.show_apex_marker) {
        var ax = c.apexSample.x
        var ay = c.apexSample.y
        ctx.fillStyle = color
        ctx.beginPath(); ctx.arc(sx(ax), sy(ay), 4, 0, Math.PI * 2); ctx.fill()
        ctx.fillStyle = '#33403c'
        ctx.fillText('H=' + fmt(ay, 1) + ' m', sx(ax) + 8, sy(ay) - 8)
      }

      if (c.landed) {
        ctx.strokeStyle = color
        ctx.lineWidth = 1.5
        ctx.beginPath(); ctx.moveTo(sx(c.landed.x), sy(0) - 7); ctx.lineTo(sx(c.landed.x), sy(0) + 7); ctx.stroke()
        ctx.fillStyle = color
        ctx.fillText('R=' + fmt(c.landed.x, 1) + ' m', sx(c.landed.x) - 24, sy(0) + 34)
      }

      var s = c.samples[Math.min(c.samples.length - 1, Math.floor(state.time / DATA.engine.dt_s))]
      if (s) {
        ctx.fillStyle = color
        ctx.beginPath(); ctx.arc(sx(s.x), sy(s.y), 6, 0, Math.PI * 2); ctx.fill()
        ctx.strokeStyle = '#ffffff'; ctx.lineWidth = 2; ctx.stroke()
      }
    })
  }

  function loop(now) {
    if (!state.playing) { lastFrame = now; requestAnimationFrame(loop); return }
    var dt = lastFrame ? Math.min(0.05, (now - lastFrame) / 1000) : 0.016
    lastFrame = now
    state.time += dt * state.speed
    var maxT = 0
    computed.forEach(function (c) { maxT = Math.max(maxT, c.analytic.T) })
    if (state.time > maxT + 0.4) {
      state.time = maxT + 0.4
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

      core = createProjectileCore(window.Matter, {
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
      el('formula').textContent = DATA.acceptance.formulas_display.R + '；' + DATA.acceptance.formulas_display.H
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
      legend.innerHTML = ''
      computedLabelsForLegend(legend)
      buildControls()
      recompute()

      el('play').addEventListener('click', function () {
        if (state.time > 0 && !state.playing) {
          var maxT = 0
          computed.forEach(function (c) { maxT = Math.max(maxT, c.analytic.T) })
          if (state.time >= maxT) state.time = 0
        }
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
            if (typeof next.v0 === 'number') state.v0 = clamp(next.v0, decision.v0_range[0], decision.v0_range[1])
            if (typeof next.h0 === 'number') state.h0 = clamp(next.h0, decision.h0_range[0], decision.h0_range[1])
            if (typeof next.angle_deg === 'number' && recipe.params_mode !== 'pair' && recipe.id !== 'horizontal') {
              state.angles[0] = clamp(next.angle_deg, decision.angle_range_oblique[0], decision.angle_range_oblique[1])
            }
            if (Array.isArray(next.angles_deg) && recipe.params_mode === 'pair') {
              state.angles = next.angles_deg.slice(0, 2).map(function (a) {
                return clamp(a, decision.angle_range_oblique[0], decision.angle_range_oblique[1])
              })
            }
          }
          syncControls()
          syncAngleInputs()
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

  function computedLabelsForLegend(legend) {
    var defs = scenarioDefs()
    defs.forEach(function (d, i) {
      var item = document.createElement('span')
      item.className = 'item'
      var sw = document.createElement('span')
      sw.className = 'swatch'
      sw.style.background = renderCfg.colors[i % renderCfg.colors.length]
      item.appendChild(sw)
      item.appendChild(document.createTextNode(d.label + '（引擎）'))
      legend.appendChild(item)
    })
    var ana = document.createElement('span')
    ana.className = 'item'
    var dash = document.createElement('span')
    dash.className = 'swatch'
    dash.style.background = 'repeating-linear-gradient(90deg,#5a6661 0 5px,transparent 5px 9px)'
    ana.appendChild(dash)
    ana.appendChild(document.createTextNode('解析式'))
    legend.appendChild(ana)
  }

  function syncControls() {
    var inputs = document.querySelectorAll('#controls input[type="range"]')
    if (inputs.length >= 2) {
      inputs[0].value = String(state.v0)
      inputs[0].previousSibling.querySelector('.val').textContent = fmt(state.v0, 1) + ' m/s'
      inputs[1].value = String(state.h0)
      inputs[1].previousSibling.querySelector('.val').textContent = fmt(state.h0, 1) + ' m'
    }
  }

  if (document.readyState === 'loading') {
    document.addEventListener('DOMContentLoaded', init)
  } else {
    init()
  }
})()
