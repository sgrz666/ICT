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
  // 光斑质心相对探测器中心（光轴）的偏移（场景单位）：
  // Python 侧要靠它判断像到底落在轴的哪一侧，不能只靠一个宽度标量。
  centroid_units: number;
  // 该屏在场景单位下的轴向位置（与 x_cm 同源，留作几何拟合的自变量）
  x_units: number | null;
  // 该屏捕获到的功率占所有屏最大捕获功率的比例，用于剔除"几乎全漏检"的退化读数
  power_fraction: number;
  // 探测器自身轴向长度（场景单位）。用来判断读数是不是已经被孔径截断：
  // 均匀照亮整块屏时 rms 的上限是 len/√12，接近它就说明光斑比屏还大，测不出发散。
  extent_units: number | null;
};

/**
 * 由屏阵列上的实测光斑宽度反推像面位置 —— Gate C §C.2 要求的**独立几何证据**。
 *
 * 为什么不能只比公式：虚像与无穷远这两种工况在实屏阵列上根本没有实像聚焦点，
 * 旧实现用 `u < f` / `abs(f-u) < 1e-4` 直接判通过 —— 那是公式在给自己作证。
 * 这里换成可测量的事实：出射光束的宽度随轴向位置线性变化，
 * 宽度外推为零的位置就是像点（实像在屏侧、虚像是反向延长的交点、准直则外推不收敛）。
 *
 * 返回值一律来自测量：`usable`、`fit_r2`、`screen_spacing_cm`、`resolution_cm`
 * 都要交给上层写进判据，容差来自屏间距而不是凭空挑的常数。
 * 拟合不成立时 `kind="inconclusive"` 并给出理由 —— 调用方不得把它当通过。
 */
export type BeamGeometry = {
  kind: "real" | "virtual" | "collimated" | "inconclusive";
  reason: string;
  usable: number;
  lens_x_cm: number | null;
  // 光束宽度外推为零的轴向位置（cm）；准直时无定义
  apex_x_cm: number | null;
  // apex_x_cm - lens_x_cm：实像为正，虚像为负（反向延长交点在入射侧）
  image_distance_cm: number | null;
  // 宽度对 x 的斜率（场景单位 / cm）。准直判据看它的绝对值是否足够小。
  width_slope_units_per_cm: number | null;
  fit_r2: number | null;
  screen_spacing_cm: number[];
  // 定位分辨率：像点落在两屏之间时，能分辨的精度受相邻间距的一半限制
  resolution_cm: number | null;
  // 屏阵列的轴向跨度与「本阵列至少能分辨多远的像」：
  // 超出这个范围时虚像与准直在测量上不可区分，只能判不可判，不能挑一个说通过。
  array_span_cm: number | null;
  resolvable_max_abs_distance_cm: number | null;
};

type Line = { slope: number; intercept: number; r2: number };

function fitLine(xs: number[], ys: number[]): Line | null {
  const n = xs.length;
  if (n < 2) return null;
  const sx = xs.reduce((a, b) => a + b, 0);
  const sy = ys.reduce((a, b) => a + b, 0);
  const sxx = xs.reduce((a, x) => a + x * x, 0);
  const sxy = xs.reduce((a, x, i) => a + x * ys[i], 0);
  const denom = n * sxx - sx * sx;
  if (denom === 0) return null;
  const slope = (n * sxy - sx * sy) / denom;
  const intercept = (sy - slope * sx) / n;
  const meanY = sy / n;
  const ssTot = ys.reduce((a, y) => a + (y - meanY) ** 2, 0);
  const ssRes = ys.reduce((a, y, i) => a + (y - (slope * xs[i] + intercept)) ** 2, 0);
  const r2 = ssTot > 0 ? 1 - ssRes / ssTot : 1;
  return { slope, intercept, r2 };
}

const MIN_FIT_R2 = 0.9;

export function beamGeometry(probes: Probe[], lensXcm: number | null): BeamGeometry {
  const base = {
    kind: "inconclusive" as const,
    reason: "",
    usable: 0,
    lens_x_cm: lensXcm,
    apex_x_cm: null,
    image_distance_cm: null,
    width_slope_units_per_cm: null,
    fit_r2: null,
    screen_spacing_cm: [] as number[],
    resolution_cm: null,
    array_span_cm: null,
    resolvable_max_abs_distance_cm: null,
  };

  const usable = probes
    .filter(p => p.power_fraction >= 0.2 && Number.isFinite(p.rms_units) && p.x_cm !== null)
    .sort((a, b) => (a.x_cm as number) - (b.x_cm as number));
  if (usable.length < 3) {
    return { ...base, reason: `可用屏不足 3 块（实际 ${usable.length}），无法做光束几何拟合` };
  }
  const xs = usable.map(p => p.x_cm as number);
  const ws = usable.map(p => p.rms_units);
  const spacings = xs.slice(1).map((x, i) => x - xs[i]);
  const resolution = Math.min(...spacings) / 2;
  const span = xs[xs.length - 1] - xs[0];
  // 阵列能分辨的最远像距：宽度变化要至少达到测量分辨率量级才谈得上「测到了发散」。
  // 比这更远的虚像与准直在本阵列上不可区分，只能判不可判。
  const resolvable = span * (Math.max(...ws) / resolution);
  const withMeta = {
    ...base,
    usable: usable.length,
    screen_spacing_cm: spacings,
    resolution_cm: resolution,
    array_span_cm: span,
    resolvable_max_abs_distance_cm: resolvable,
  };

  let iMin = 0;
  for (let i = 1; i < ws.length; i++) if (ws[i] < ws[iMin]) iMin = i;

  // 孔径截断判据：探测器均匀照亮时 rms 的理论上限是 len/√12。
  // 最窄的读数都贴近这个上限 ⇒ 光斑比屏还大，发散与平行在这块屏上根本读不出来，
  // 这时只能报不可判 —— 把「看不出变化」说成「测得平行」就是过度断言。
  const extents = usable.map(p => p.extent_units).filter((x): x is number => x !== null && x > 0);
  const uniformCeiling = extents.length
    ? Math.max(...extents) / Math.sqrt(12)
    : Number.POSITIVE_INFINITY;
  const minW = Math.min(...ws);
  const apertureLimited = minW > 0.9 * uniformCeiling;

  const allFit = fitLine(xs, ws);
  const meanW = ws.reduce((a, b) => a + b, 0) / ws.length;
  const totalChange = allFit ? Math.abs(allFit.slope) * span : Infinity;
  const parallel = allFit !== null && meanW > 0 && totalChange < 0.15 * meanW;
  if (parallel && apertureLimited) {
    return {
      ...withMeta,
      reason:
        `全部屏的读数都接近探测器满幅（最窄 rms ${minW.toFixed(1)} vs 均匀上限 ` +
        `${uniformCeiling.toFixed(1)} 场景单位），光斑被孔径截断：` +
        "发散与否在这套屏上读不出来，不能判平行也不能判虚像",
      width_slope_units_per_cm: allFit?.slope ?? null,
      fit_r2: allFit?.r2 ?? null,
    };
  }
  if (parallel) {
    // 平行度本身就是这里的观测量：光束宽度在整段阵列上变化不到 15%。
    // 但「准直」与「像距很远的虚像」在这个分辨率下无法区分，理由必须写出来。
    return {
      ...withMeta,
      kind: "collimated",
      reason:
        `出射光束宽度在 ${span.toFixed(0)}cm 跨度内相对变化仅 ${(totalChange / meanW * 100).toFixed(1)}%，` +
        `实测为高平行度；本阵列可分辨的像距上限约 ${resolvable.toFixed(0)}cm，更远处无法与准直区分`,
      width_slope_units_per_cm: allFit!.slope,
      fit_r2: allFit!.r2,
    };
  }

  if (iMin === 0 && apertureLimited) {
    return { ...withMeta, reason: "光斑已铺满探测器（孔径截断），发散度测不出来，不判虚像" };
  }
  if (iMin === 0) {
    // 宽度单调增大：出射光束发散。反向延长交点就是虚像位置。
    if (!allFit || allFit.slope <= 0 || allFit.r2 < MIN_FIT_R2) {
      return { ...withMeta, reason: "宽度单调变化但线性拟合不成立，不能据此判虚像", fit_r2: allFit?.r2 ?? null };
    }
    const apex = -allFit.intercept / allFit.slope;
    if (lensXcm === null) return { ...withMeta, reason: "提不出透镜位置，无法把交点换算成像距", fit_r2: allFit.r2 };
    const distance = apex - lensXcm;
    if (apex >= lensXcm) {
      return {
        ...withMeta,
        reason: `发散光束的反向延长交点落在屏侧（${apex.toFixed(1)}cm ≥ 透镜 ${lensXcm.toFixed(1)}cm），与虚像几何不符`,
        apex_x_cm: apex,
        fit_r2: allFit.r2,
        width_slope_units_per_cm: allFit.slope,
      };
    }
    if (Math.abs(distance) > resolvable) {
      return {
        ...withMeta,
        reason:
          `反推像距 ${distance.toFixed(0)}cm 超出本阵列可分辨范围（±${resolvable.toFixed(0)}cm），` +
          "无法与准直区分，不能判虚像通过",
        apex_x_cm: apex,
        fit_r2: allFit.r2,
        width_slope_units_per_cm: allFit.slope,
      };
    }
    return {
      ...withMeta,
      kind: "virtual",
      reason: `出射光束发散，宽度外推为零的交点在入射侧（反向延长交点 ${apex.toFixed(1)}cm）`,
      apex_x_cm: apex,
      image_distance_cm: distance,
      width_slope_units_per_cm: allFit.slope,
      fit_r2: allFit.r2,
    };
  }

  if (iMin === ws.length - 1) {
    return {
      ...withMeta,
      reason: `最窄屏已在阵列最外侧（${xs[iMin].toFixed(0)}cm），像面在阵列之外或恰好压边，无法独立观测像距`,
    };
  }

  // 两侧各自拟合，且都带上最窄那一屏：像面正好落在某块屏上时，另一侧只剩一个点，
  // 用「最窄点 + 相邻点」两点定线，比要求每侧各两个点更贴近这套屏阵列的布置。
  const left = usable.slice(0, iMin + 1);
  const right = usable.slice(iMin);
  const fitL = fitLine(left.map(p => p.x_cm as number), left.map(p => p.rms_units));
  const fitR = fitLine(right.map(p => p.x_cm as number), right.map(p => p.rms_units));
  if (!fitL || !fitR) {
    return { ...withMeta, reason: "像点一侧的屏数不足以拟合" };
  }
  if (fitL.r2 < MIN_FIT_R2 || fitR.r2 < MIN_FIT_R2) {
    return {
      ...withMeta,
      reason: `光束宽度线性外推的拟合度不足（R²=${fitL.r2.toFixed(2)}/${fitR.r2.toFixed(2)}），不判像面`,
      fit_r2: Math.min(fitL.r2, fitR.r2),
    };
  }
  if (fitL.slope >= 0 || fitR.slope <= 0) {
    return {
      ...withMeta,
      reason: "两侧宽度没有出现「先收后散」的夹角，光束不像在阵列内成像",
      fit_r2: Math.min(fitL.r2, fitR.r2),
    };
  }
  // 两条边的交点 = 宽度为零的轴向位置 = 实测像面
  const apex = (fitR.intercept - fitL.intercept) / (fitL.slope - fitR.slope);
  const r2 = Math.min(fitL.r2, fitR.r2);
  if (lensXcm !== null && apex <= lensXcm) {
    return {
      ...withMeta,
      reason: `宽度为零的交点落在透镜入射侧（${apex.toFixed(1)}cm），与实像几何不符`,
      apex_x_cm: apex,
      fit_r2: r2,
    };
  }
  return {
    ...withMeta,
    kind: "real",
    reason: `两侧光束宽度线性收敛于 ${apex.toFixed(1)}cm，实测像面即该交点`,
    apex_x_cm: apex,
    image_distance_cm: lensXcm === null ? null : apex - lensXcm,
    width_slope_units_per_cm: fitR.slope,
    fit_r2: r2,
  };
}

// 透镜轴向位置：IdealLens 的 p1/p2 中点（与 Python 侧 _extract_lens_and_source 同一算法）
export function lensAxisXcm(sceneJson: unknown, unitsPerUnit = 10): number | null {
  const objs = (sceneJson as { objs?: { type?: string; p1?: { x?: number }; p2?: { x?: number } }[] })?.objs ?? [];
  const lens = objs.find(o => o.type === "IdealLens");
  if (!lens) return null;
  const x1 = Number(lens.p1?.x);
  const x2 = Number(lens.p2?.x);
  if (!Number.isFinite(x1) || !Number.isFinite(x2)) return null;
  return ((x1 + x2) / 2) / unitsPerUnit;
}

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
  // 由屏读数算出的光束几何（实像/虚像/准直/不可判）。判据要有独立观测来源就靠它。
  geometry: BeamGeometry;
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
        centroid_units: number;
        x_units: number | null;
        extent_units: number | null;
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
        let centroid = Number.NaN;
        if (total > 0) {
          centroid =
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
          centroid_units: centroid,
          x_units: obj.p1 ? obj.p1.x : null,
          extent_units: len,
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
    geometry: beamGeometry(probes, lensAxisXcm(sceneJson)),
  };
}

export const bundlePath = BUNDLE;
export const halfSpanCm = HALF_SPAN_CM;
