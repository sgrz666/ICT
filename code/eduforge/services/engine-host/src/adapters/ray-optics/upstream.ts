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
  // 屏阵列的轴向跨度
  array_span_cm: number | null;
  // 拟合斜率的标准误（单位/cm）：由屏上读数的残差算出，不是挑的常数。
  // 「测不出发散」= |slope| 落在这个标准误的 2 倍以内，是可算的判据。
  slope_stderr_units_per_cm: number | null;
  // 宽度外推交点（=像点）的标准误（cm）。只在整段线性外推的工况给出：
  // 像点落在两屏之间时由屏分辨率说话（null），外推上百 cm 时这个数才是容差的来源。
  vertex_stderr_cm: number | null;
  // 本套屏还能把像点定到多远：|slope| 小于 2 倍标准误时外推交点失去意义。
  // = 平均宽度 / (2 × 斜率标准误)，与被判工况的实测数据同一来源。
  resolvable_max_abs_distance_cm: number | null;
  // 被孔径截断而剔除的屏数（读数贴到探测器满幅上限的那些）
  clipped_screens: number;
  // 证据出自哪套屏：交付的 7 块屏，还是加宽半高并在透镜面加光阑的观测副本。
  // 读数被孔径截断时只能标 delivered_screens，此时判不可判是量具的实话。
  measured_on: "delivered_screens" | "wide_aperture_probe";
};

type Line = { slope: number; intercept: number; r2: number; stderr: number; x0Stderr: number };

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
  const xbar = sx / n;
  const meanY = sy / n;
  const ssTot = ys.reduce((a, y) => a + (y - meanY) ** 2, 0);
  const ssRes = ys.reduce((a, y, i) => a + (y - (slope * xs[i] + intercept)) ** 2, 0);
  const r2 = ssTot > 0 ? 1 - ssRes / ssTot : 1;
  // 斜率标准误 = se/sqrt(Sxx)。读数完全共线时 se=0（理想薄透镜的准直工况就是），
  // 那时「与零不可区分」成立得最弱：量具越干净，越不能把 σ=0 当成"测到无穷远也能分辨"。
  const sxxc = xs.reduce((a, x) => a + (x - xbar) ** 2, 0);
  const se = Math.sqrt(ssRes / Math.max(n - 2, 1));
  // 回归线与横轴交点（宽度外推为零处）的标准误——外推像距的可信度就是它
  const x0Stderr =
    slope !== 0 && sxxc > 0
      ? (se / Math.abs(slope)) * Math.sqrt(1 / n + (xbar * xbar) / sxxc)
      : Infinity;
  return { slope, intercept, r2, stderr: sxxc > 0 ? se / Math.sqrt(sxxc) : Infinity, x0Stderr };
}

const MIN_FIT_R2 = 0.9;
// 判定「测不出发散」的显著性倍数：|slope| ≤ 2σ 时认为斜率与零不可区分
const SIGNIFICANCE = 2;

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
    slope_stderr_units_per_cm: null,
    vertex_stderr_cm: null,
    resolvable_max_abs_distance_cm: null,
    clipped_screens: 0,
    measured_on: "delivered_screens" as const,
  };

  const lit = probes
    .filter(p => p.power_fraction >= 0.2 && Number.isFinite(p.rms_units) && p.x_cm !== null)
    .sort((a, b) => (a.x_cm as number) - (b.x_cm as number));
  if (lit.length < 3) {
    return { ...base, reason: `可用屏不足 3 块（实际 ${lit.length}），无法做光束几何拟合` };
  }

  // 孔径截断的读数要剔除：贴到满幅上限的光斑宽度不是真实宽度，
  // 留着它们拟合会把斜率压平，于是「发散」被读成「平行」。
  const extents = lit.map(p => p.extent_units).filter((x): x is number => x !== null && x > 0);
  const uniformCeiling = extents.length
    ? Math.max(...extents) / Math.sqrt(12)
    : Number.POSITIVE_INFINITY;
  const ceiling = 0.9 * uniformCeiling;
  const clipped = lit.filter(p => p.rms_units > ceiling);
  const usable = lit.filter(p => p.rms_units <= ceiling);
  if (usable.length < 3) {
    return {
      ...base,
      clipped_screens: clipped.length,
      reason:
        `全部 ${lit.length} 块屏的读数都接近各自满幅上限（均匀照明时 rms 理论上限 ` +
        `${uniformCeiling.toFixed(1)} 场景单位），光斑被孔径截断：发散与平行在这套屏上读不出来`,
    };
  }

  const xs = usable.map(p => p.x_cm as number);
  const ws = usable.map(p => p.rms_units);
  const spacings = xs.slice(1).map((x, i) => x - xs[i]);
  const resolution = Math.min(...spacings) / 2;
  const span = xs[xs.length - 1] - xs[0];
  const meanW = ws.reduce((a, b) => a + b, 0) / ws.length;
  const allFit = fitLine(xs, ws);
  const slopeStderr = allFit?.stderr ?? null;
  // 可分辨的最远像距：|slope| 小到与 0 不可区分（≤2σ）时，外推交点就没有意义了。
  const resolvable =
    slopeStderr !== null && slopeStderr > 0 ? meanW / (SIGNIFICANCE * slopeStderr) : Infinity;
  const withMeta = {
    ...base,
    usable: usable.length,
    screen_spacing_cm: spacings,
    resolution_cm: resolution,
    array_span_cm: span,
    slope_stderr_units_per_cm: slopeStderr,
    resolvable_max_abs_distance_cm: Number.isFinite(resolvable) ? resolvable : null,
    clipped_screens: clipped.length,
  };

  let iMin = 0;
  for (let i = 1; i < ws.length; i++) if (ws[i] < ws[iMin]) iMin = i;

  // —— 情形一：最窄屏在阵列中间 ⇒ 光束先收后散，两侧直线交点就是实测像面（实像）
  if (iMin > 0 && iMin < ws.length - 1) {
    const left = usable.slice(0, iMin + 1);
    const right = usable.slice(iMin);
    const fitL = fitLine(left.map(p => p.x_cm as number), left.map(p => p.rms_units));
    const fitR = fitLine(right.map(p => p.x_cm as number), right.map(p => p.rms_units));
    if (!fitL || !fitR) return { ...withMeta, reason: "像点一侧的屏数不足以拟合" };
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
      reason: `两侧光束宽度线性收敛于 ${apex.toFixed(1)}cm（最窄屏 ${xs[iMin].toFixed(0)}cm 处 rms ${ws[iMin].toFixed(1)}），实测像面即该交点`,
      apex_x_cm: apex,
      image_distance_cm: lensXcm === null ? null : apex - lensXcm,
      width_slope_units_per_cm: fitR.slope,
      fit_r2: r2,
    };
  }

  if (!allFit) return { ...withMeta, reason: "屏数不足以拟合宽度趋势" };

  // —— 情形二：宽度单调（最窄屏在阵列端点）⇒ 像面在阵列之外，只能整段外推
  const totalChange = Math.abs(allFit.slope) * span;
  if (Math.abs(allFit.slope) <= SIGNIFICANCE * allFit.stderr || totalChange < 0.01 * meanW) {
    // 平行度本身就是观测量：斜率与 0 不可区分，且这个「不可区分」有算出来的门槛
    return {
      ...withMeta,
      kind: "collimated",
      reason:
        `实测宽度在 ${span.toFixed(0)}cm 跨度内变化 ${totalChange.toFixed(1)} 场景单位` +
        `（均值 ${meanW.toFixed(1)}，斜率 ${allFit.slope.toFixed(4)}±${allFit.stderr.toFixed(4)} 单位/cm），` +
        `与零不可区分：出射光束为高平行度。本阵列可分辨的像距上限 ` +
        `${Number.isFinite(resolvable) ? `约 ${resolvable.toFixed(0)}cm` : "不受限（各屏读数完全一致）"}，` +
        "比这更远的虚像与准直在测量上不可区分",
      width_slope_units_per_cm: allFit.slope,
      fit_r2: allFit.r2,
      slope_stderr_units_per_cm: allFit.stderr,
    };
  }
  if (allFit.r2 < MIN_FIT_R2) {
    return {
      ...withMeta,
      reason: `宽度单调变化但线性拟合不成立（R²=${allFit.r2.toFixed(2)}），不能据此外推像面`,
      width_slope_units_per_cm: allFit.slope,
      fit_r2: allFit.r2,
    };
  }
  const apex = -allFit.intercept / allFit.slope;
  if (lensXcm === null) {
    return { ...withMeta, reason: "提不出透镜位置，无法把交点换算成像距", fit_r2: allFit.r2 };
  }
  const distance = apex - lensXcm;
  const spreadNote = clipped.length ? `（已剔除 ${clipped.length} 块被孔径截断的屏）` : "";
  if (apex > lensXcm) {
    // 交点在屏侧：光束确实会聚，只是聚焦点落在阵列之外（最窄在末屏）或阵列之前（最窄在首屏）
    return {
      ...withMeta,
      kind: "real",
      reason:
        `宽度沿阵列${allFit.slope < 0 ? "单调收窄，光束会在屏阵列之后" : "单调展宽，反向延长说明光束早在阵列之前"}会聚于 ${apex.toFixed(1)}cm${spreadNote}，` +
        `线性外推（R²=${allFit.r2.toFixed(3)}，斜率 ${allFit.slope.toFixed(3)}±${allFit.stderr.toFixed(3)} 单位/cm）给出实像`,
      apex_x_cm: apex,
      image_distance_cm: distance,
      width_slope_units_per_cm: allFit.slope,
      fit_r2: allFit.r2,
      slope_stderr_units_per_cm: allFit.stderr,
      vertex_stderr_cm: Number.isFinite(allFit.x0Stderr) ? allFit.x0Stderr : null,
    };
  }
  if (allFit.slope <= 0) {
    return {
      ...withMeta,
      reason: `交点 ${apex.toFixed(1)}cm 落在透镜入射侧但宽度并不发散，几何不自洽，不判虚像`,
      apex_x_cm: apex,
      fit_r2: allFit.r2,
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
      slope_stderr_units_per_cm: allFit.stderr,
    };
  }
  return {
    ...withMeta,
    kind: "virtual",
    reason:
      `出射光束发散：宽度自 ${ws[0].toFixed(1)} 增至 ${ws[ws.length - 1].toFixed(1)} 场景单位` +
      `（R²=${allFit.r2.toFixed(3)}，斜率 ${allFit.slope.toFixed(3)}±${allFit.stderr.toFixed(3)} 单位/cm）${spreadNote}，` +
      `反向延长交点在 ${apex.toFixed(1)}cm（入射侧）⇒ 虚像`,
    apex_x_cm: apex,
    image_distance_cm: distance,
    width_slope_units_per_cm: allFit.slope,
    fit_r2: allFit.r2,
    slope_stderr_units_per_cm: allFit.stderr,
    vertex_stderr_cm: Number.isFinite(allFit.x0Stderr) ? allFit.x0Stderr : null,
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

// 量具极限的修法：交付场景里的屏只有 ±12cm 半高，虚像与准直工况下光斑铺满探测器，
// 宽度读数被孔径截断 → 发散与平行根本测不出来（实测 rms 已达均匀照明上限的 98%）。
// 上游不导出光线折线，那就**另跑一次只用于观测的宽屏副本**：
// 1) 探测器半高加宽到 PROBE_HALF_HEIGHT_UNITS，但 binSize 一字不改——
//    加宽只增加 bin 数量，宽度分辨率保持 0.2cm。（实测把 binSize 同比放大会把像面
//    附近的读数量化掉，f=15 的实像被误判成准直。）
// 2) 在透镜面处加一块带孔光阑（Aperture，孔 = 透镜口径）：点光源发出的光里那些
//    **根本没经过透镜**的光线会直接铺满宽屏，二矩被这条直光扇主导，读数变成
//    "每块屏都一样宽"（实测 rms≈450 且斜率≈0，虚像工况也被读成准直）。
//    挡掉直光扇之后，宽屏只收集被透镜折射过的光，宽度才是像的函数。
// 交付的那份场景一个字节都不改，这条仿真只是量具；几何判据因此来自实测而非公式。
const PROBE_HALF_HEIGHT_UNITS = 1200;
const LENS_TYPES = ["IdealLens", "SphericalLens"];

type RawPoint = { x: number; y: number } | undefined;
type RawObj = {
  type?: string;
  name?: string;
  binSize?: number;
  p1?: RawPoint;
  p2?: RawPoint;
  p3?: RawPoint;
  p4?: RawPoint;
};

export function buildProbeScene(sceneJson: unknown): unknown {
  const clone = JSON.parse(JSON.stringify(sceneJson)) as { objs?: RawObj[] };
  const objs = clone.objs ?? [];
  for (const obj of objs) {
    if (obj.type !== "Detector" && obj.type !== "Screen") continue;
    const half = Math.abs(Number(obj.p1?.y ?? 0)) || HALF_SPAN_CM * 10;
    const scale = Math.max(1, PROBE_HALF_HEIGHT_UNITS / half);
    if (obj.p1) obj.p1.y = Number(obj.p1.y) * scale;
    if (obj.p2) obj.p2.y = Number(obj.p2.y) * scale;
  }

  // 光阑开在透镜面上：孔与透镜口径重合，于是只有经过透镜的光能继续走
  const lens = objs.find(o => LENS_TYPES.includes(o.type ?? "") && o.p1 && o.p2);
  if (lens?.p1 && lens.p2) {
    const holeHalf = Math.max(Math.abs(Number(lens.p1.y)), Math.abs(Number(lens.p2.y)));
    objs.push({
      type: "Aperture",
      name: "eduforge_probe_stop",
      p1: { x: Number(lens.p1.x), y: -PROBE_HALF_HEIGHT_UNITS },
      p2: { x: Number(lens.p2.x), y: PROBE_HALF_HEIGHT_UNITS },
      p3: { x: Number(lens.p1.x), y: -holeHalf },
      p4: { x: Number(lens.p2.x), y: holeHalf },
    });
  }
  return clone;
}

async function simulateScene(sceneJson: unknown): Promise<Omit<SimulationResult, 'geometry'>> {
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
  };
}

/**
 * 只量读数：给任意（含探针副本）场景跑出各屏 Probe。
 * 导出来是给测试做「有光阑 / 没光阑」对照用的，不在生产路径上单独调。
 */
export async function probeReadings(sceneJson: unknown): Promise<Probe[]> {
  return (await simulateScene(sceneJson)).probes;
}

/**
 * 交付屏 + 观测副本各跑一次：
 * `probes` 是教师会看到的那 7 块屏的读数（像面判据用它），
 * `geometry` 来自**观测副本**：屏加宽且不截断光斑，并在透镜面加一块与口径同宽的光阑，
 * 只让经过透镜的光进入读数。虚像的发散与无穷远的平行度因此第一次有了可测的证据。
 * 交付场景一字不改；探针仿真纯粹是量具，`geometry.measured_on` 会写清证据出自哪套屏。
 */
export async function simulate(sceneJson: unknown): Promise<SimulationResult> {
  const delivered = await simulateScene(sceneJson);
  let source: Probe[] = delivered.probes;
  let measuredOn: BeamGeometry["measured_on"] = "delivered_screens";
  try {
    const wide = await simulateScene(buildProbeScene(sceneJson));
    if (wide.probes.length >= 3) {
      source = wide.probes;
      measuredOn = "wide_aperture_probe";
    }
  } catch {
    // 副本跑不起来就退回交付屏读数，理由会写在 geometry.reason 里，不假装测到
  }
  return {
    ...delivered,
    geometry: { ...beamGeometry(source, lensAxisXcm(sceneJson)), measured_on: measuredOn },
  };
}

export const bundlePath = BUNDLE;
export const halfSpanCm = HALF_SPAN_CM;
