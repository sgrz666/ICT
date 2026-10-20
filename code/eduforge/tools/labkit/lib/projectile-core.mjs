/**
 * 抛体运动的单一物理内核。
 *
 * 同一份源码同时被 Node（L2 物理对账）与浏览器（单文件页面的运行时）使用：
 *   - Node:    createProjectileCore(require('matter-js'))
 *   - 浏览器:  createProjectileCore(window.Matter)
 * 这样「验收时的读数」与「学生页面上的读数」不是两套实现，避免漂移。
 *
 * Matter.js 活在「像素 + 毫秒」世界里，而教学单位是米和秒；更麻烦的是它默认
 * frictionAir = 0.01（逐步衰减），不显式置 0 的抛体根本不是抛物线。本内核把
 * 单位标定成一条实测定律（calibrate），并要求调用方显式传 frictionAir。
 *
 * 口径（与 source/library/projectile_lab.mjs 完全一致，改动会让历史证据失效）：
 *   - gravity = 9.8 m/s²，gravity.scale = 1e-6，dt = 1/240 s
 *   - 初速必须走 Body.setVelocity(v/60)；手写 positionPrev 会缩水 4 倍
 *   - 落点用相邻帧线性插值求穿地时刻，不造地面碰撞体
 */

/** 默认引擎配置；调用方可覆盖，但验收口径锁在默认值上。 */
export const PROJECTILE_CONFIG = Object.freeze({
  gravity: 9.8,
  gravityScale: 1e-6,
  dtS: 1 / 240,
  radius: 0.25,
})

/**
 * 与引擎无关的解析解。h0 > 0 时飞行时间要解二次方程，不能用 h0=0 的 2v0sinθ/g。
 * 独立导出：L1 参数校验只需要公式，不需要加载 matter-js。
 *
 * @param {{h0?:number,v0:number,angleDeg:number,aEff:number}} opts
 */
export function analyticProjectile(opts) {
  const { h0 = 0, v0, angleDeg, aEff } = opts
  const th = (angleDeg * Math.PI) / 180
  const vx = v0 * Math.cos(th)
  const vy = v0 * Math.sin(th)
  const T = (vy + Math.sqrt(vy * vy + 2 * aEff * h0)) / aEff
  const R = vx * T
  const H = h0 + (vy * vy) / (2 * aEff)
  return { T, R, H, apex_y: H }
}

/**
 * @param {object} Matter matter-js 模块（Node 或浏览器均可）
 * @param {Partial<typeof PROJECTILE_CONFIG>} [config]
 */
export function createProjectileCore(Matter, config = {}) {
  const cfg = { ...PROJECTILE_CONFIG, ...config }
  const DT_MS = cfg.dtS * 1000

  function makeEngine() {
    const engine = Matter.Engine.create()
    engine.gravity.x = 0
    engine.gravity.y = cfg.gravity
    engine.gravity.scale = cfg.gravityScale
    return engine
  }

  /**
   * 无初速落体：从 0 掉到 H，用实测反算这个配置下的真实加速度。
   * Matter 的离散轨迹是 y_n = ½·a·(n²+n)·dt²（比连续式多半个步长的相位），
   * 所以用它反解 a，而不是拿配置值糊人。
   */
  function calibrate() {
    const engine = makeEngine()
    const body = Matter.Bodies.circle(0, 0, cfg.radius, { frictionAir: 0, mass: 1 })
    Matter.Composite.add(engine.world, body)
    const H = 20
    let n = 0
    while (body.position.y < H && n < 20000) {
      Matter.Engine.update(engine, DT_MS)
      n += 1
    }
    const y = body.position.y
    const a_measured = (2 * y) / ((n * n + n) * cfg.dtS * cfg.dtS)
    const t = n * cfg.dtS
    Matter.World.clear(engine.world, false)
    Matter.Engine.clear(engine)
    return {
      a_measured,
      t,
      y,
      n,
      config: { gravity_y: cfg.gravity, gravity_scale: cfg.gravityScale, dt_s: cfg.dtS },
    }
  }

  /**
   * 投一个物体并逐步采样；Matter 的 y 向下为正，对外一律翻成「高度向上为正」。
   * 返回 landed/apex/steps（与历史 lab 一致）以及 samples（供页面绘制）。
   *
   * @param {{h0:number,v0:number,angleDeg:number,frictionAir?:number,maxT?:number}} opts
   */
  function fly(opts) {
    const { h0, v0, angleDeg, frictionAir = 0, maxT = 60 } = opts
    const engine = makeEngine()
    const th = (angleDeg * Math.PI) / 180
    const vx = v0 * Math.cos(th)
    const vy = -v0 * Math.sin(th)
    const body = Matter.Bodies.circle(0, -h0, cfg.radius, { frictionAir, mass: 1 })
    // Matter 的 velocity 单位是「每个 baseDelta(16.667 ms) 的位移」，不是每秒。
    // 必须走 Body.setVelocity，让它按 deltaTime/baseDelta 自己换算。
    Matter.Body.setVelocity(body, { x: vx / 60, y: vy / 60 })
    Matter.Composite.add(engine.world, body)

    let t = 0
    let px = 0
    let py = h0
    let apex = { t: 0, y: h0 }
    let landed = null
    let steps = 0
    const samples = [{ t: 0, x: 0, y: h0 }]
    while (t < maxT) {
      Matter.Engine.update(engine, DT_MS)
      t += cfg.dtS
      steps += 1
      const nx = body.position.x
      const ny = -body.position.y
      samples.push({ t, x: nx, y: ny })
      if (ny > apex.y) apex = { t, y: ny }
      if (py > 0 && ny <= 0) {
        const f = py / (py - ny)
        landed = { t: t - cfg.dtS + f * cfg.dtS, x: px + f * (nx - px) }
        break
      }
      px = nx
      py = ny
      if (ny < -500 || Math.abs(nx) > 5000) break
    }
    Matter.World.clear(engine.world, false)
    Matter.Engine.clear(engine)
    return { landed, apex, steps, samples }
  }

  /**
   * @param {{h0?:number,v0:number,angleDeg:number,aEff:number}} opts
   */
  function analytic(opts) {
    return analyticProjectile(opts)
  }

  return { config: cfg, makeEngine, calibrate, fly, analytic }
}
