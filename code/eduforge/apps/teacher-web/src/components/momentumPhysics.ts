/**
 * 一维动量守恒实验的纯物理内核。
 *
 * 约定：轨道沿 +x 方向，速度向右为正；碰撞只发生在两车之间，
 * 因此除轨道端点越界（实验自动停止）外没有外力。所有量均为 SI 单位。
 */

export const TRACK_HALF_LENGTH = 6.5;
export const CART_LENGTH = 0.96;
export const CART_HALF_LENGTH = CART_LENGTH / 2;
export const TRACK_LIMIT = TRACK_HALF_LENGTH - CART_HALF_LENGTH - 0.08;

export type SceneId = "elastic" | "heavy" | "inelastic" | "chase" | "explosion";
export type SimStatus = "ready" | "running" | "paused" | "ended";

export interface LabConfig {
  sceneId: SceneId;
  m1: number;
  m2: number;
  v1: number;
  v2: number;
  /** 恢复系数 e：1 为完全弹性碰撞，0 为完全非弹性碰撞。 */
  restitution: number;
  /** 弹簧反冲场景中释放的冲量，单位 N·s。 */
  impulse: number;
  timeScale: number;
}

export interface Preset {
  id: SceneId;
  index: string;
  name: string;
  en: string;
  kind: "collision" | "explosion";
  formula: string;
  description: string;
  initial: Omit<LabConfig, "sceneId" | "timeScale">;
  x1: number;
  x2: number;
}

export interface ImpactRecord {
  serial: number;
  t: number;
  kind: "collision" | "explosion";
  x: number;
  v1Before: number;
  v2Before: number;
  v1After: number;
  v2After: number;
  pBefore: number;
  pAfter: number;
  keBefore: number;
  keAfter: number;
}

export interface SimSample {
  t: number;
  x1: number;
  x2: number;
  v1: number;
  v2: number;
  p1: number;
  p2: number;
  pTotal: number;
  ke1: number;
  ke2: number;
  ke: number;
  initialP: number;
  initialKe: number;
  collisions: number;
  status: SimStatus;
  exploded: boolean;
}

export type SimEvent =
  | { type: "impact"; record: ImpactRecord }
  | { type: "end" };

export const PRESETS: Preset[] = [
  {
    id: "elastic",
    index: "01",
    name: "等质量正碰",
    en: "SYMMETRIC ELASTIC",
    kind: "collision",
    formula: "m₁ = m₂ · e = 1",
    description:
      "两车质量相同，左车以 2.2 m/s 撞向静止的右车。完全弹性碰撞后速度交换：左车停下，右车以 2.2 m/s 离开。",
    initial: { m1: 1.2, m2: 1.2, v1: 2.2, v2: 0, restitution: 1, impulse: 1.3 },
    x1: -2.6,
    x2: 0.4,
  },
  {
    id: "heavy",
    index: "02",
    name: "轻车撞重车",
    en: "LIGHT INTO HEAVY",
    kind: "collision",
    formula: "m₁ ≪ m₂ · e = 1",
    description:
      "0.6 kg 轻车撞上 3.0 kg 重车。轻车几乎原速反弹，重车缓慢前移；系统总动量仍然守恒，但动能更多留在轻车上。",
    initial: { m1: 0.6, m2: 3, v1: 3, v2: 0, restitution: 1, impulse: 1.3 },
    x1: -3.4,
    x2: 0.8,
  },
  {
    id: "inelastic",
    index: "03",
    name: "完全非弹性",
    en: "PERFECTLY INELASTIC",
    kind: "collision",
    formula: "e = 0 · 碰后共速",
    description:
      "两车相向而行，碰撞后粘在一起共同运动。动量守恒依旧成立，损失的最大动能转化为内能与形变能。",
    initial: { m1: 1.8, m2: 1, v1: 2.4, v2: -0.6, restitution: 0, impulse: 1.3 },
    x1: -2.2,
    x2: 1.6,
  },
  {
    id: "chase",
    index: "04",
    name: "追及碰撞",
    en: "CHASE & IMPACT",
    kind: "collision",
    formula: "e = 0.55 · 同向",
    description:
      "快车从后方追上慢车。恢复系数 0.55 表示部分弹性：两车碰后仍同向运动，但速度差被压缩。",
    initial: { m1: 2.2, m2: 0.7, v1: 2.6, v2: 1.2, restitution: 0.55, impulse: 1.3 },
    x1: -3,
    x2: 0.2,
  },
  {
    id: "explosion",
    index: "05",
    name: "弹簧反冲",
    en: "SPRING RECOIL",
    kind: "explosion",
    formula: "Σp = 0 · 内力做功",
    description:
      "两车由压缩弹簧连接，初始总动量为零。弹簧释放后两车反向运动，动量等大反向，系统总动量仍为零。",
    initial: { m1: 1.4, m2: 0.8, v1: 0, v2: 0, restitution: 0, impulse: 1.3 },
    x1: -0.64,
    x2: 0.64,
  },
];

const PRESET_MAP = new Map(PRESETS.map(p => [p.id, p]));

export function getPreset(sceneId: SceneId): Preset {
  return PRESET_MAP.get(sceneId) ?? PRESETS[0];
}

export function presetToConfig(preset: Preset): LabConfig {
  return { ...preset.initial, sceneId: preset.id, timeScale: 1 };
}

export function configMatchesPreset(config: LabConfig, preset: Preset): boolean {
  const keys: Array<keyof Omit<LabConfig, "sceneId" | "timeScale">> = [
    "m1",
    "m2",
    "v1",
    "v2",
    "restitution",
    "impulse",
  ];
  return keys.every(key => Math.abs(config[key] - preset.initial[key]) < 1e-9);
}

export function clampConfig(config: LabConfig): LabConfig {
  return {
    ...config,
    m1: clamp(config.m1, 0.2, 5),
    m2: clamp(config.m2, 0.2, 5),
    v1: clamp(config.v1, -4, 4),
    v2: clamp(config.v2, -4, 4),
    restitution: clamp(config.restitution, 0, 1),
    impulse: clamp(config.impulse, 0.2, 3),
    timeScale: clamp(config.timeScale, 0.25, 2),
  };
}

export function momentumOf(mass: number, velocity: number): number {
  return mass * velocity;
}

export function kineticEnergyOf(mass: number, velocity: number): number {
  return 0.5 * mass * velocity * velocity;
}

export function totalMomentumOf(config: LabConfig): number {
  return momentumOf(config.m1, config.v1) + momentumOf(config.m2, config.v2);
}

export function totalKineticEnergyOf(config: LabConfig): number {
  return kineticEnergyOf(config.m1, config.v1) + kineticEnergyOf(config.m2, config.v2);
}

/** 理论碰后速度：由动量守恒与恢复系数定义联立得到。 */
export function predictedVelocities(config: LabConfig): { v1: number; v2: number } {
  if (config.sceneId === "explosion") {
    return {
      v1: -config.impulse / config.m1,
      v2: config.impulse / config.m2,
    };
  }
  const { m1, m2, v1, v2, restitution } = config;
  const total = m1 + m2;
  return {
    v1: ((m1 - restitution * m2) * v1 + (1 + restitution) * m2 * v2) / total,
    v2: ((m2 - restitution * m1) * v2 + (1 + restitution) * m1 * v1) / total,
  };
}

export function makeInitialSample(config: LabConfig): SimSample {
  const preset = getPreset(config.sceneId);
  const { x1, x2 } = preset;
  const v1 = config.sceneId === "explosion" ? 0 : config.v1;
  const v2 = config.sceneId === "explosion" ? 0 : config.v2;
  return {
    t: 0,
    x1,
    x2,
    v1,
    v2,
    p1: momentumOf(config.m1, v1),
    p2: momentumOf(config.m2, v2),
    pTotal: momentumOf(config.m1, v1) + momentumOf(config.m2, v2),
    ke1: kineticEnergyOf(config.m1, v1),
    ke2: kineticEnergyOf(config.m2, v2),
    ke: kineticEnergyOf(config.m1, v1) + kineticEnergyOf(config.m2, v2),
    initialP: momentumOf(config.m1, v1) + momentumOf(config.m2, v2),
    initialKe: kineticEnergyOf(config.m1, v1) + kineticEnergyOf(config.m2, v2),
    collisions: 0,
    status: "ready",
    exploded: false,
  };
}

function clamp(value: number, min: number, max: number): number {
  return Math.min(max, Math.max(min, value));
}

/**
 * 可重复推进的确定性模拟器。外部只需按真实时间传入 dt，
 * 内部自行细分为 1/240 s 的子步，避免高速穿透。
 */
export class MomentumSim {
  config: LabConfig;
  t = 0;
  x1 = 0;
  x2 = 0;
  v1 = 0;
  v2 = 0;
  status: SimStatus = "ready";
  collisions = 0;
  exploded = false;
  initialP = 0;
  initialKe = 0;

  private events: SimEvent[] = [];

  constructor(config: LabConfig) {
    this.config = clampConfig(config);
    this.reset(this.config);
  }

  reset(config: LabConfig): void {
    this.config = clampConfig(config);
    const preset = getPreset(this.config.sceneId);
    this.t = 0;
    this.x1 = preset.x1;
    this.x2 = preset.x2;
    this.v1 = this.config.sceneId === "explosion" ? 0 : this.config.v1;
    this.v2 = this.config.sceneId === "explosion" ? 0 : this.config.v2;
    this.status = "ready";
    this.collisions = 0;
    this.exploded = false;
    this.initialP = momentumOf(this.config.m1, this.v1) + momentumOf(this.config.m2, this.v2);
    this.initialKe =
      kineticEnergyOf(this.config.m1, this.v1) + kineticEnergyOf(this.config.m2, this.v2);
    this.events = [];
  }

  play(): void {
    if (this.status === "ended") {
      this.reset(this.config);
    }
    this.status = "running";
  }

  pause(): void {
    if (this.status === "running") this.status = "paused";
  }

  toggle(): void {
    if (this.status === "running") this.pause();
    else this.play();
  }

  sample(): SimSample {
    const p1 = momentumOf(this.config.m1, this.v1);
    const p2 = momentumOf(this.config.m2, this.v2);
    const ke1 = kineticEnergyOf(this.config.m1, this.v1);
    const ke2 = kineticEnergyOf(this.config.m2, this.v2);
    return {
      t: this.t,
      x1: this.x1,
      x2: this.x2,
      v1: this.v1,
      v2: this.v2,
      p1,
      p2,
      pTotal: p1 + p2,
      ke1,
      ke2,
      ke: ke1 + ke2,
      initialP: this.initialP,
      initialKe: this.initialKe,
      collisions: this.collisions,
      status: this.status,
      exploded: this.exploded,
    };
  }

  consumeEvents(): SimEvent[] {
    const queued = this.events;
    this.events = [];
    return queued;
  }

  step(dt: number): void {
    if (this.status !== "running" || dt <= 0) return;
    let remaining = Math.min(dt, 0.12);
    while (remaining > 1e-6 && this.status === "running") {
      const h = Math.min(1 / 240, remaining);
      this.integrate(h);
      remaining -= h;
    }
  }

  private integrate(h: number): void {
    this.t += h;
    this.x1 += this.v1 * h;
    this.x2 += this.v2 * h;

    if (this.config.sceneId === "explosion" && !this.exploded && this.t >= 0.42) {
      this.releaseSpring();
    }

    if (this.x2 - this.x1 <= CART_LENGTH && this.v1 - this.v2 > 1e-7) {
      this.resolveCollision();
    }

    if (Math.abs(this.x1) >= TRACK_LIMIT || Math.abs(this.x2) >= TRACK_LIMIT) {
      this.x1 = clamp(this.x1, -TRACK_LIMIT, TRACK_LIMIT);
      this.x2 = clamp(this.x2, -TRACK_LIMIT, TRACK_LIMIT);
      this.status = "ended";
      this.events.push({ type: "end" });
    }
  }

  private releaseSpring(): void {
    const { impulse, m1, m2 } = this.config;
    const beforeP = momentumOf(m1, this.v1) + momentumOf(m2, this.v2);
    const beforeKe = kineticEnergyOf(m1, this.v1) + kineticEnergyOf(m2, this.v2);
    this.v1 = -impulse / m1;
    this.v2 = impulse / m2;
    this.exploded = true;
    const record: ImpactRecord = {
      serial: 1,
      t: this.t,
      kind: "explosion",
      x: (this.x1 + this.x2) / 2,
      v1Before: 0,
      v2Before: 0,
      v1After: this.v1,
      v2After: this.v2,
      pBefore: beforeP,
      pAfter: momentumOf(m1, this.v1) + momentumOf(m2, this.v2),
      keBefore: beforeKe,
      keAfter: kineticEnergyOf(m1, this.v1) + kineticEnergyOf(m2, this.v2),
    };
    this.collisions += 1;
    this.events.push({ type: "impact", record });
  }

  private resolveCollision(): void {
    const { m1, m2 } = this.config;
    const overlap = CART_LENGTH - (this.x2 - this.x1);
    this.x1 -= overlap / 2;
    this.x2 += overlap / 2;

    const v1Before = this.v1;
    const v2Before = this.v2;
    const pBefore = momentumOf(m1, v1Before) + momentumOf(m2, v2Before);
    const keBefore = kineticEnergyOf(m1, v1Before) + kineticEnergyOf(m2, v2Before);

    const next = predictedVelocities({ ...this.config, v1: v1Before, v2: v2Before });
    this.v1 = next.v1;
    this.v2 = next.v2;
    this.collisions += 1;

    const record: ImpactRecord = {
      serial: this.collisions,
      t: this.t,
      kind: "collision",
      x: (this.x1 + this.x2) / 2,
      v1Before,
      v2Before,
      v1After: this.v1,
      v2After: this.v2,
      pBefore,
      pAfter: momentumOf(m1, this.v1) + momentumOf(m2, this.v2),
      keBefore,
      keAfter: kineticEnergyOf(m1, this.v1) + kineticEnergyOf(m2, this.v2),
    };
    this.events.push({ type: "impact", record });
  }
}
