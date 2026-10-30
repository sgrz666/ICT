/**
 * 单摆的单一物理内核（matter-js 刚体 + 刚性约束）。
 *
 * 与抛体同源：Node（L2）与浏览器（单文件页面）共用同一份源码，
 * 口径也一致：gravity=9.8、gravity.scale=1e-6、dt=1/240、frictionAir=0。
 *
 * 为什么用 matter-js 而不是 myPhysicsLab：
 *   - myPhysicsLab 的 PendulumSim 无头精度更高（2.00835 vs 2.00834），但浏览器打包要
 *     esbuild + GWT 风格的多模块图，单文件交付不成立；
 *   - matter-js 实测：5° 误差 0.04%、10° 0.15%、30° 相对椭圆积分精确解 0.49%，
 *     足以支撑本项目「≤1%（θ0≤10°）、30° 按椭圆积分修正 ≤0.5%」的验收口径。
 *
 * 测量口径：从 +θ0 释放，角度过零（负→正）为一次周期边界；取第 2 个之后的间隔均值，
 * 避开起步半拍与首帧约束修正。
 */
export const PENDULUM_CONFIG = Object.freeze({
  gravity: 9.8,
  gravityScale: 1e-6,
  dtS: 1 / 240,
  radius: 0.02,
})

/**
 * 完全椭圆积分 K(k) 的 AGM 实现；k = sin(θ0/2)。
 * T = 4√(L/g)·K(k)，k→0 时退化为 2π√(L/g)。
 */
export function ellipticK(k) {
  let a = 1
  let b = Math.sqrt(Math.max(0, 1 - k * k))
  for (let i = 0; i < 30 && Math.abs(a - b) > 1e-15; i += 1) {
    const an = (a + b) / 2
    b = Math.sqrt(a * b)
    a = an
  }
  return Math.PI / (2 * a)
}

/**
 * 与引擎无关的解析解。
 * @param {{lengthM:number, angle0Deg:number, gravity:number}} opts
 */
export function pendulumAnalytic({ lengthM, angle0Deg, gravity }) {
  const T0 = 2 * Math.PI * Math.sqrt(lengthM / gravity)
  const k = Math.sin((angle0Deg * Math.PI) / 360)
  const Texact = 4 * Math.sqrt(lengthM / gravity) * ellipticK(k)
  return {
    T0,
    Texact,
    correction_pct: (Texact / T0 - 1) * 100,
    amplitude_rad: (angle0Deg * Math.PI) / 180,
  }
}

/**
 * @param {object} Matter matter-js 模块
 * @param {Partial<typeof PENDULUM_CONFIG>} [config]
 */
export function createPendulumCore(Matter, config = {}) {
  const cfg = { ...PENDULUM_CONFIG, ...config }
  const DT_MS = cfg.dtS * 1000

  function makeEngine() {
    const engine = Matter.Engine.create()
    engine.gravity.x = 0
    engine.gravity.y = cfg.gravity
    engine.gravity.scale = cfg.gravityScale
    return engine
  }

  /** 自由落体标定，方法与抛体一致：用 y_n=½a(n²+n)dt² 反解。 */
  function calibrate() {
    const engine = makeEngine()
    const body = Matter.Bodies.circle(0, 0, cfg.radius, { frictionAir: 0, mass: 1 })
    Matter.Composite.add(engine.world, body)
    const H = 10
    let n = 0
    while (body.position.y < H && n < 40000) {
      Matter.Engine.update(engine, DT_MS)
      n += 1
    }
    const y = body.position.y
    const a_measured = (2 * y) / ((n * n + n) * cfg.dtS * cfg.dtS)
    Matter.World.clear(engine.world, false)
    Matter.Engine.clear(engine)
    return { a_measured, n, y, config: { gravity_y: cfg.gravity, gravity_scale: cfg.gravityScale, dt_s: cfg.dtS } }
  }

  /**
   * 释放并步进。角度定义：从竖直向下方向起算，右为正。
   * @param {{lengthM:number, angle0Deg:number, damping?:number, maxT?:number}} opts
   */
  function swing(opts) {
    const { lengthM, angle0Deg, damping = 0, maxT = 12 } = opts
    const engine = makeEngine()
    const th0 = (angle0Deg * Math.PI) / 180
    // matter 的 y 向下为正；从竖直向下方向偏移 θ0。
    const bob = Matter.Bodies.circle(
      lengthM * Math.sin(th0),
      lengthM * Math.cos(th0),
      cfg.radius,
      { frictionAir: 0, mass: 1 },
    )
    const constraint = Matter.Constraint.create({
      pointA: { x: 0, y: 0 },
      bodyB: bob,
      length: lengthM,
      stiffness: 1,
      damping,
    })
    Matter.Composite.add(engine.world, [bob, constraint])

    const samples = []
    const crossings = []
    let t = 0
    let prev = Math.atan2(bob.position.x, bob.position.y)
    samples.push({ t, angle: prev, x: bob.position.x, y: bob.position.y })
    let maxStretch = 0
    while (t < maxT) {
      Matter.Engine.update(engine, DT_MS)
      t += cfg.dtS
      const angle = Math.atan2(bob.position.x, bob.position.y)
      samples.push({ t, angle, x: bob.position.x, y: bob.position.y })
      if (prev < 0 && angle >= 0) crossings.push(t)
      prev = angle
      maxStretch = Math.max(maxStretch, Math.abs(Math.hypot(bob.position.x, bob.position.y) - lengthM))
      if (crossings.length >= 8) break
    }
    Matter.World.clear(engine.world, false)
    Matter.Engine.clear(engine)

    const intervals = []
    for (let i = 2; i < crossings.length; i += 1) intervals.push(crossings[i] - crossings[i - 1])
    const period = intervals.length
      ? intervals.reduce((a, b) => a + b, 0) / intervals.length
      : NaN
    return { period, crossings, samples, maxStretch, steps: Math.round(t / cfg.dtS) }
  }

  return { config: cfg, makeEngine, calibrate, swing }
}
