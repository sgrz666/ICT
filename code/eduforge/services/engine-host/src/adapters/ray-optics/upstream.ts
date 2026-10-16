import { createRequire } from "node:module";

// 复用上游自己构建的无头核心（npm run build-node 产出 dist-node/rayOptics.js）。
// 观测值全部来自上游真实仿真，不在这里重算公式，避免自我验证。
const require = createRequire(import.meta.url);

type UpstreamObject = {
  constructor: { type: string };
  name?: string;
  power?: number;
  binData?: number[] | Float64Array | null;
  binSize?: number;
  irradMap?: boolean;
  p1?: { x: number; y: number };
  p2?: { x: number; y: number };
  focalLength?: number;
};

type UpstreamScene = {
  objs: UpstreamObject[];
  error: string | null;
  warning: string | null;
  loadJSON(json: string, cb: (needFullUpdate: boolean, completed: boolean) => void): void;
  toJSON(): string;
};

type UpstreamSimulator = {
  on(event: "simulationComplete", cb: () => void): void;
  on(event: "error", cb: (err: unknown) => void): void;
  updateSimulation(skipLight: boolean, skipGrid: boolean): void;
  processedRayCount: number;
  totalTruncation: number;
  error: string | null;
  warning: string | null;
};

type Upstream = {
  Scene: new () => UpstreamScene;
  Simulator: new (...args: unknown[]) => UpstreamSimulator;
};

// 从 src/adapters/ray-optics 上溯 7 层到工作区根 D:\codeplus\ICT
const BUNDLE =
  process.env.EDUFORGE_RAYOPTICS_BUNDLE ??
  require.resolve(
    "../../../../../../../source/upstream/ray-optics/dist-node/rayOptics.js"
  );

let cached: Upstream | null = null;

export function upstream(): Upstream {
  if (!cached) cached = require(BUNDLE) as Upstream;
  return cached;
}

export type Probe = {
  name: string | undefined;
  x_cm: number | null;
  power: number;
  peak_share: number;
  peak_offset_units: number;
  // 光斑宽度的二矩度量（场景单位）。越小越接近像面。
  rms_units: number;
  // 该屏捕获到的功率占所有屏最大捕获功率的比例，用于剔除"几乎全漏检"的退化读数
  power_fraction: number;
};

/**
 * 选最清晰的屏。
 * 为什么不能用 peak_share（max_bin/total）判向：像面远离该屏时光斑半径远超屏的
 * 接收范围，绝大多数光线落在屏外，total 塌到只剩一两条光线，max/total 反而趋近 1，
 * 产生"最远屏最清晰"的假阳性（f=5、预测像距 6cm 时实测把 40cm 屏判成 argmax）。
 * ⇒ 先用捕获功率比例设下限剔除退化读数，再取光斑 RMS 最小者。
 */
export function sharpestProbe(probes: Probe[]): Probe | null {
  const usable = probes.filter(p => p.power_fraction >= 0.2);
  if (usable.length === 0) return null;
  return usable.reduce((best, p) => (p.rms_units < best.rms_units ? p : best));
}

export type SceneValidation = {
  ok: boolean;
  error: string | null;
  warning: string | null;
  version: number | null;
  objs: { type: string; name?: string }[];
};

// 版本策略交给上游：无 version 迁移、字符串或大于 DATA_VERSION 拒绝、小于则迁移。
// 我们只读回 scene.error，不自己写 `!== 5`。
export function validateNative(sceneJson: unknown): SceneValidation {
  const scene = new (upstream().Scene)();
  let completed = false;
  scene.loadJSON(JSON.stringify(sceneJson), (_full, done) => {
    if (done) completed = true;
  });
  const out: SceneValidation = {
    ok: !scene.error && completed,
    error: scene.error,
    warning: scene.warning,
    version: null,
    objs: scene.objs.map(o => ({ type: o.constructor.type, name: o.name })),
  };
  if (!scene.error) {
    try {
      out.version = JSON.parse(scene.toJSON()).version ?? null;
    } catch {
      out.version = null;
    }
  }
  return out;
}

export type SimulationResult = {
  probes: Probe[];
  processedRayCount: number;
  totalTruncation: number;
  error: string | null;
  warning: string | null;
};

const HALF_SPAN_CM = 12; // 与模板探测器一致，仅用于把场景单位换算成厘米报告

export async function simulate(sceneJson: unknown): Promise<SimulationResult> {
  const scene = new (upstream().Scene)();
  await new Promise<void>((resolve, reject) => {
    scene.loadJSON(JSON.stringify(sceneJson), (_full, done) => {
      if (scene.error) return reject(new Error(scene.error));
      if (done) resolve();
    });
  });

  const sim = new (upstream().Simulator)(
    scene, null, null, null, null, null, false, Infinity, null, null, null
  );

  const probes: Probe[] = [];
  await new Promise<void>((resolve, reject) => {
    sim.on("simulationComplete", () => {
      const raw: {
        name: string | undefined;
        x_cm: number | null;
        power: number;
        peak_share: number;
        peak_offset_units: number;
        rms_units: number;
      }[] = [];

      for (const obj of scene.objs) {
        if (obj.constructor.type !== "Detector") continue;
        const bins =
          obj.irradMap && obj.binData ? Array.from(obj.binData as number[]) : [];
        const total = bins.reduce((a, b) => a + b, 0);
        const max = bins.length ? Math.max(...bins) : 0;
        const idx = bins.length ? bins.indexOf(max) : -1;
        const len =
          obj.p1 && obj.p2
            ? Math.hypot(obj.p2.x - obj.p1.x, obj.p2.y - obj.p1.y)
            : 0;
        const bin = obj.binSize ?? 1;

        // 光斑二矩：以探测器中心（光轴）为原点，按 bin 位置加权
        let rms = Number.NaN;
        if (total > 0) {
          const centroid =
            bins.reduce((acc, w, i) => acc + w * ((i + 0.5) * bin - len / 2), 0) / total;
          rms = Math.sqrt(
            bins.reduce(
              (acc, w, i) => acc + w * ((i + 0.5) * bin - len / 2 - centroid) ** 2,
              0
            ) / total
          );
        }

        raw.push({
          name: obj.name,
          x_cm: obj.p1 ? obj.p1.x / 10 : null,
          power: obj.power ?? 0,
          peak_share: total > 0 ? max / total : 0,
          peak_offset_units: idx >= 0 ? (idx + 0.5) * bin - len / 2 : Number.NaN,
          rms_units: rms,
        });
      }

      const maxPower = raw.reduce((m, p) => Math.max(m, p.power), 0);
      for (const p of raw) {
        probes.push({ ...p, power_fraction: maxPower > 0 ? p.power / maxPower : 0 });
      }
      resolve();
    });
    sim.on("error", (e: unknown) => reject(new Error(String(e))));
    // 构造 Simulator 不会自动开跑；漏这句会静默不产出
    sim.updateSimulation(false, false);
  });

  return {
    probes,
    processedRayCount: sim.processedRayCount,
    totalTruncation: sim.totalTruncation,
    error: sim.error,
    warning: sim.warning,
  };
}

export const bundlePath = BUNDLE;
export const halfSpanCm = HALF_SPAN_CM;
