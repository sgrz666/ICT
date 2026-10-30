import { useCallback, useEffect, useState } from "react";
import type { CSSProperties } from "react";

import { MomentumStage } from "./MomentumStage";
import "./momentum.css";
import {
  configMatchesPreset,
  getPreset,
  makeInitialSample,
  momentumOf,
  predictedVelocities,
  presetToConfig,
  PRESETS,
  type ImpactRecord,
  type LabConfig,
  type SceneId,
  type SimSample,
  type SimStatus,
} from "./momentumPhysics";

type ChartMode = "momentum" | "kinetic";

const DEFAULT_CONFIG = presetToConfig(PRESETS[0]);
const SPEED_OPTIONS = [0.5, 1, 1.5];

const STATUS_LABEL: Record<SimStatus, string> = {
  ready: "待发射",
  running: "测量中",
  paused: "已暂停",
  ended: "已结束",
};

export function MomentumLabView() {
  const [config, setConfig] = useState<LabConfig>(DEFAULT_CONFIG);
  const [running, setRunning] = useState(false);
  const [resetToken, setResetToken] = useState(0);
  const [telemetry, setTelemetry] = useState<SimSample>(() => makeInitialSample(DEFAULT_CONFIG));
  const [history, setHistory] = useState<SimSample[]>([]);
  const [impacts, setImpacts] = useState<ImpactRecord[]>([]);
  const [chartMode, setChartMode] = useState<ChartMode>("momentum");
  const [showHelp, setShowHelp] = useState(false);

  const preset = getPreset(config.sceneId);
  const customized = !configMatchesPreset(config, preset);
  const isExplosion = config.sceneId === "explosion";
  const predicted = predictedVelocities(config);
  const status: SimStatus = running ? "running" : telemetry.status;
  const p1 = momentumOf(config.m1, telemetry.v1);
  const p2 = momentumOf(config.m2, telemetry.v2);
  const energyChange = telemetry.ke - telemetry.initialKe;
  const energyLossPercent =
    telemetry.initialKe > 1e-9 ? (-energyChange / telemetry.initialKe) * 100 : 0;
  const momentumDelta = telemetry.pTotal - telemetry.initialP;

  const applyConfig = useCallback((next: LabConfig) => {
    setConfig(next);
    setRunning(false);
    setTelemetry(makeInitialSample(next));
    setHistory([]);
    setImpacts([]);
    setResetToken(token => token + 1);
  }, []);

  const selectPreset = useCallback(
    (sceneId: SceneId) => {
      const nextPreset = getPreset(sceneId);
      applyConfig(presetToConfig(nextPreset));
    },
    [applyConfig]
  );

  const updateParameter = useCallback(
    <K extends keyof LabConfig>(key: K, value: LabConfig[K]) => {
      const next = { ...config, [key]: value };
      setConfig(next);
      setTelemetry(makeInitialSample(next));
      setRunning(false);
      setHistory([]);
      setImpacts([]);
      setResetToken(token => token + 1);
    },
    [config]
  );

  const restorePreset = useCallback(() => {
    applyConfig(presetToConfig(preset));
  }, [applyConfig, preset]);

  const handleReset = useCallback(() => {
    setRunning(false);
    setTelemetry(makeInitialSample(config));
    setHistory([]);
    setImpacts([]);
    setResetToken(token => token + 1);
  }, [config]);

  const handleRunToggle = useCallback(() => {
    if (running) {
      setRunning(false);
      return;
    }
    if (telemetry.status === "ended") {
      setHistory([]);
      setImpacts([]);
      setTelemetry(makeInitialSample(config));
      setResetToken(token => token + 1);
    }
    setRunning(true);
  }, [config, running, telemetry.status]);

  const handleSample = useCallback((sample: SimSample) => {
    setTelemetry(sample);
    setHistory(previous => {
      const last = previous[previous.length - 1];
      if (!last) return [sample];
      if (sample.t <= last.t + 1e-6) return previous;
      const next = [...previous, sample];
      return next.length > 280 ? next.slice(next.length - 280) : next;
    });
  }, []);

  const handleImpact = useCallback((record: ImpactRecord) => {
    setImpacts(previous => [record, ...previous].slice(0, 4));
  }, []);

  const handleEnded = useCallback(() => {
    setRunning(false);
  }, []);

  const handleSpeed = useCallback((timeScale: number) => {
    setConfig(current => ({ ...current, timeScale }));
  }, []);

  useEffect(() => {
    if (!showHelp) return;
    const onKeyDown = (event: KeyboardEvent) => {
      if (event.key === "Escape") setShowHelp(false);
    };
    window.addEventListener("keydown", onKeyDown);
    return () => window.removeEventListener("keydown", onKeyDown);
  }, [showHelp]);

  const restartLabel =
    telemetry.status === "ended" ? "再次实验" : telemetry.status === "paused" ? "继续测量" : "开始测量";

  return (
    <div className="momentum-lab">
      <aside className="lab-controls" aria-label="实验控制">
        <div className="control-brand">
          <span className="control-brand__kicker">MECHANICS / EXPERIMENT 04</span>
          <h1>
            动量<span>守恒</span>
          </h1>
          <p>气垫导轨上的一维碰撞。调节质量、初速度与恢复系数，观察碰撞前后的动量账本。</p>
          <div className="control-brand__meta">
            <span>1D COLLISION</span>
            <i />
            <span>AIR TRACK</span>
            <i />
            <span>SI UNITS</span>
          </div>
        </div>

        <div className="control-scroll">
          <section className="control-section">
            <div className="section-heading">
              <span className="section-heading__index">01</span>
              <h2>实验场景</h2>
              <em>{PRESETS.length} PRESETS</em>
            </div>
            <div className="scene-grid">
              {PRESETS.map(item => (
                <button
                  key={item.id}
                  type="button"
                  className={`scene-tile ${config.sceneId === item.id ? "is-active" : ""} ${
                    item.id === "explosion" ? "scene-tile--wide" : ""
                  }`}
                  onClick={() => selectPreset(item.id)}
                  aria-pressed={config.sceneId === item.id}
                >
                  <span className="scene-tile__index">{item.index}</span>
                  <strong>{item.name}</strong>
                  <span className="scene-tile__en">{item.en}</span>
                  <span className="scene-tile__formula">{item.formula}</span>
                </button>
              ))}
            </div>
          </section>

          <section className="control-section">
            <div className="section-heading">
              <span className="section-heading__index">02</span>
              <h2>实验参数</h2>
              <button type="button" className="text-button" onClick={restorePreset}>
                恢复预设
              </button>
            </div>

            <div className="parameter-stack">
              <ParamSlider
                label="一号车质量"
                symbol="m₁"
                value={config.m1}
                min={0.2}
                max={5}
                step={0.1}
                unit="kg"
                onChange={value => updateParameter("m1", value)}
              />
              <ParamSlider
                label="二号车质量"
                symbol="m₂"
                value={config.m2}
                min={0.2}
                max={5}
                step={0.1}
                unit="kg"
                onChange={value => updateParameter("m2", value)}
              />

              {isExplosion ? (
                <ParamSlider
                  label="弹簧冲量"
                  symbol="J"
                  value={config.impulse}
                  min={0.2}
                  max={3}
                  step={0.1}
                  unit="N·s"
                  hint="两车获得的动量等大反向：p₁′ = −p₂′"
                  onChange={value => updateParameter("impulse", value)}
                />
              ) : (
                <>
                  <ParamSlider
                    label="一号车初速度"
                    symbol="v₁"
                    value={config.v1}
                    min={-4}
                    max={4}
                    step={0.1}
                    unit="m/s"
                    hint="向右为正方向"
                    onChange={value => updateParameter("v1", value)}
                  />
                  <ParamSlider
                    label="二号车初速度"
                    symbol="v₂"
                    value={config.v2}
                    min={-4}
                    max={4}
                    step={0.1}
                    unit="m/s"
                    onChange={value => updateParameter("v2", value)}
                  />
                  <ParamSlider
                    label="恢复系数"
                    symbol="e"
                    value={config.restitution}
                    min={0}
                    max={1}
                    step={0.01}
                    unit=""
                    hint="e = 1 完全弹性 / e = 0 完全非弹性"
                    onChange={value => updateParameter("restitution", value)}
                  />
                </>
              )}
            </div>

            {isExplosion ? (
              <p className="control-note">
                两车初始静止，总动量为零。弹簧释放只提供内力，因此分离后仍有
                <code>m₁v₁′ + m₂v₂′ = 0</code>。
              </p>
            ) : (
              <p className="control-note">
                碰后速度由动量守恒与恢复系数共同决定；改变质量或初速度会重新布置实验车。
              </p>
            )}
          </section>
        </div>

        <div className="run-dock">
          <button type="button" className="run-button" onClick={handleRunToggle}>
            {running ? <PauseIcon /> : <PlayIcon />}
            <span>
              <strong>{running ? "暂停测量" : restartLabel}</strong>
              <em>{running ? "PAUSE SAMPLING" : "LAUNCH RUN"}</em>
            </span>
          </button>
          <button type="button" className="reset-button" onClick={handleReset} title="复位实验">
            <ResetIcon />
            <span>复位</span>
          </button>
        </div>
      </aside>

      <header className="lab-topbar">
        <div className="lab-topbar__title">
          <span className="lab-topbar__kicker">AIR TRACK / ONE-DIMENSIONAL COLLISION</span>
          <div>
            <h2>动量守恒实验台</h2>
            <span className="lab-topbar__sub">AIR TRACK 04 · 6.5 m</span>
          </div>
        </div>

        <div className="lab-topbar__tools">
          <div className={`lab-status lab-status--${status}`} aria-live="polite">
            <i />
            <span>{STATUS_LABEL[status]}</span>
            <em>t = {telemetry.t.toFixed(2)} s</em>
          </div>
          <div className="speed-switch" aria-label="时间倍率">
            {SPEED_OPTIONS.map(option => (
              <button
                key={option}
                type="button"
                className={config.timeScale === option ? "is-active" : ""}
                onClick={() => handleSpeed(option)}
                title={`时间倍率 ${option}x`}
              >
                {option}×
              </button>
            ))}
          </div>
          <button type="button" className="topbar-action" onClick={() => setShowHelp(true)}>
            <HelpIcon />
            <span>说明</span>
          </button>
          <button
            type="button"
            className="topbar-run"
            onClick={handleRunToggle}
            aria-label={running ? "暂停测量" : restartLabel}
            title={running ? "暂停测量" : restartLabel}
          >
            {running ? <PauseIcon /> : <PlayIcon />}
          </button>
        </div>
      </header>

      <div className="lab-stage-wrap">
        <MomentumStage
          config={config}
          running={running}
          resetToken={resetToken}
          onSample={handleSample}
          onImpact={handleImpact}
          onEnded={handleEnded}
        />
        {!running ? (
          <button type="button" className="stage-start" onClick={handleRunToggle}>
            <span className="stage-start__icon">
              <PlayIcon />
            </span>
            <span>
              <strong>{restartLabel}</strong>
              <em>{telemetry.status === "paused" ? "从当前时刻继续" : "让两辆实验车进入轨道"}</em>
            </span>
          </button>
        ) : null}
        <div className="stage-readout">
          <span>Σp</span>
          <strong>{telemetry.pTotal.toFixed(3)}</strong>
          <em>kg·m/s</em>
          <i>Δp {formatDelta(momentumDelta)}</i>
        </div>
        <div className="stage-caption">
          <span>
            {preset.index} / {preset.en}
            {customized ? " · 自定义参数" : ""}
          </span>
          <strong>{preset.name}</strong>
          <p>{preset.description.split("。")[0]}。</p>
        </div>
      </div>

      <aside className="lab-readouts" aria-label="实时测量">
        <header className="readout-heading">
          <div>
            <span>LIVE MEASUREMENT</span>
            <h2>实时测量</h2>
          </div>
          <div className={`compact-status compact-status--${status}`}>
            <i />
            {STATUS_LABEL[status]}
          </div>
        </header>

        <div className="total-momentum">
          <div className="total-momentum__label">
            <span>系统总动量</span>
            <em>Σp = p₁ + p₂</em>
          </div>
          <div className="total-momentum__value">
            <strong>{telemetry.pTotal.toFixed(3)}</strong>
            <span>kg·m/s</span>
          </div>
          <div className="total-momentum__delta">
            <span>相对于初始值</span>
            <b>{formatDelta(momentumDelta)}</b>
            <i>{Math.abs(momentumDelta) < 5e-4 ? "守恒" : "检查外力"}</i>
          </div>
          <div className="conservation-bar">
            <span className="conservation-bar__center" />
            <MomentumTick value={p1} scale={Math.max(Math.abs(p1), Math.abs(p2), 0.1)} tone="a" />
            <MomentumTick value={p2} scale={Math.max(Math.abs(p1), Math.abs(p2), 0.1)} tone="b" />
          </div>
          <div className="conservation-legend">
            <span><i className="tone-a" />p₁ {signed(p1, 2)}</span>
            <span><i className="tone-b" />p₂ {signed(p2, 2)}</span>
          </div>
        </div>

        <div className="cart-metrics">
          <CartMetric
            index="01"
            tone="a"
            mass={config.m1}
            velocity={telemetry.v1}
            momentum={p1}
          />
          <CartMetric
            index="02"
            tone="b"
            mass={config.m2}
            velocity={telemetry.v2}
            momentum={p2}
          />
        </div>

        <div className="energy-block">
          <div className="energy-block__head">
            <span>动能账本</span>
            <em>单位 J</em>
          </div>
          <div className="energy-grid">
            <div>
              <span>初始动能</span>
              <strong>{telemetry.initialKe.toFixed(2)}</strong>
            </div>
            <div>
              <span>当前动能</span>
              <strong>{telemetry.ke.toFixed(2)}</strong>
            </div>
            <div className={energyChange < -1e-6 ? "is-loss" : energyChange > 1e-6 ? "is-gain" : ""}>
              <span>{isExplosion ? "弹簧做功" : "动能变化"}</span>
              <strong>
                {energyChange > 1e-6 ? "+" : ""}
                {energyChange.toFixed(2)}
              </strong>
            </div>
          </div>
          {!isExplosion && energyChange < -1e-6 ? (
            <p>
              机械能损失 <b>{energyLossPercent.toFixed(1)}%</b>，动量仍然守恒。损失的动能转化为内能与形变能。
            </p>
          ) : (
            <p>
              {isExplosion
                ? "弹簧的内力做功，把弹性势能转化为两车的动能；总动量保持为零。"
                : "完全弹性碰撞不损失动能；两车的动量在碰撞中重新分配。"}
            </p>
          )}
        </div>

        <div className="prediction-block">
          <div className="small-heading">
            <span>{isExplosion ? "理论反冲速度" : "理论碰后速度"}</span>
            <em>{isExplosion ? "由 J 与质量给出" : "由 p 与 e 联立"}</em>
          </div>
          <div className="prediction-values">
            <span><i className="tone-a" />v₁′ <b>{signed(predicted.v1, 2)}</b> m/s</span>
            <span><i className="tone-b" />v₂′ <b>{signed(predicted.v2, 2)}</b> m/s</span>
          </div>
        </div>

        <div className="impact-block">
          <div className="small-heading">
            <span>事件记录</span>
            <em>{telemetry.collisions} EVENTS</em>
          </div>
          {impacts.length === 0 ? (
            <div className="impact-empty">
              <span>暂无事件</span>
              <p>启动实验后，碰撞或弹簧释放会记录在这里。</p>
            </div>
          ) : (
            <div className="impact-list">
              {impacts.slice(0, 3).map(record => (
                <div className="impact-row" key={`${record.serial}-${record.t.toFixed(3)}`}>
                  <span className="impact-row__index">
                    {String(record.serial).padStart(2, "0")}
                  </span>
                  <div className="impact-row__body">
                    <span>
                      {record.kind === "explosion" ? "弹簧释放" : "正碰"} · t ={" "}
                      {record.t.toFixed(2)} s
                    </span>
                    <code>
                      v₁ {signed(record.v1Before, 1)} → {signed(record.v1After, 2)}
                      <i>/</i>
                      v₂ {signed(record.v2Before, 1)} → {signed(record.v2After, 2)}
                    </code>
                  </div>
                  <em>Δp {formatDelta(record.pAfter - record.pBefore)}</em>
                </div>
              ))}
            </div>
          )}
        </div>

      </aside>

      <section className="lab-chart" aria-label="随时间变化的曲线">
        <header className="chart-heading">
          <div className="chart-heading__title">
            <span className="section-heading__index">03</span>
            <div>
              <h2>{chartMode === "momentum" ? "动量 — 时间" : "动能 — 时间"}</h2>
              <em>{chartMode === "momentum" ? "MOMENTUM / TIME" : "KINETIC ENERGY / TIME"}</em>
            </div>
          </div>
          <div className="chart-switch">
            <button
              type="button"
              className={chartMode === "momentum" ? "is-active" : ""}
              onClick={() => setChartMode("momentum")}
            >
              动量 p(t)
            </button>
            <button
              type="button"
              className={chartMode === "kinetic" ? "is-active" : ""}
              onClick={() => setChartMode("kinetic")}
            >
              动能 E(t)
            </button>
          </div>
          <div className="chart-legend">
            <span><i className="tone-a" />CART 01</span>
            <span><i className="tone-b" />CART 02</span>
            <span><i className="tone-total" />TOTAL</span>
          </div>
          <div className="chart-window">
            <span>WINDOW</span>
            <strong>
              {Math.max(4, Math.ceil(telemetry.t))} s
            </strong>
          </div>
        </header>

        <MomentumChart
          history={history}
          impacts={impacts}
          mode={chartMode}
          initialP={telemetry.initialP}
          initialKe={telemetry.initialKe}
          now={telemetry.t}
        />
      </section>

      {showHelp ? (
        <div className="lab-help-backdrop" role="presentation" onClick={() => setShowHelp(false)}>
          <section
            className="lab-help"
            role="dialog"
            aria-modal="true"
            aria-labelledby="momentum-help-title"
            onClick={event => event.stopPropagation()}
          >
            <header>
              <div>
                <span>OPERATING NOTES</span>
                <h2 id="momentum-help-title">怎么使用这台实验台</h2>
              </div>
              <button type="button" onClick={() => setShowHelp(false)} aria-label="关闭说明">
                <CloseIcon />
              </button>
            </header>
            <div className="lab-help__grid">
              <div>
                <span className="lab-help__index">01</span>
                <h3>选场景</h3>
                <p>从五个预设中选一个，或直接拖动参数。任何参数变化都会重新布置实验，并从 t = 0 开始。</p>
              </div>
              <div>
                <span className="lab-help__index">02</span>
                <h3>看碰撞</h3>
                <p>按「开始测量」后观察两车、速度箭头与右侧动量账本。绿色总动量线应始终保持水平。</p>
              </div>
              <div>
                <span className="lab-help__index">03</span>
                <h3>转视角</h3>
                <p>在 3D 区域拖拽旋转、滚轮缩放、双击复位视角。时间倍率只改变播放速度，不改变物理量。</p>
              </div>
              <div>
                <span className="lab-help__index">04</span>
                <h3>读数据</h3>
                <p>底部曲线可切换动量与动能。碰撞事件会标出碰前/碰后速度以及总动量偏差。</p>
              </div>
            </div>
            <div className="lab-help__scene">
              <span>
                当前场景 · {preset.index} / {preset.name}
              </span>
              <p>{preset.description}</p>
            </div>
            <div className="lab-help__note">
              <span>模型边界</span>
              <p>
                一维、无摩擦、两车正碰。轨道端点只用于结束实验，不模拟墙壁碰撞。恢复系数 e
                取值 0–1，e = 1 时动能守恒，e = 0 时碰后共速。
              </p>
            </div>
            <button type="button" className="lab-help__close" onClick={() => setShowHelp(false)}>
              返回实验
            </button>
          </section>
        </div>
      ) : null}
    </div>
  );
}

interface ParamSliderProps {
  label: string;
  symbol: string;
  value: number;
  min: number;
  max: number;
  step: number;
  unit: string;
  hint?: string;
  onChange: (value: number) => void;
}

function ParamSlider({
  label,
  symbol,
  value,
  min,
  max,
  step,
  unit,
  hint,
  onChange,
}: ParamSliderProps) {
  const fill = ((value - min) / (max - min)) * 100;
  const digits = step >= 1 ? 0 : step >= 0.1 ? 1 : 2;
  return (
    <label className="param-slider">
      <span className="param-slider__meta">
        <span className="param-slider__name">
          {label}
          <i>{symbol}</i>
        </span>
        <output>
          {value.toFixed(digits)}
          {unit ? <small>{unit}</small> : null}
        </output>
      </span>
      <input
        type="range"
        min={min}
        max={max}
        step={step}
        value={value}
        style={{ "--fill": `${fill}%` } as CSSProperties}
        onChange={event => onChange(Number(event.target.value))}
        aria-label={label}
      />
      <span className="param-slider__scale">
        <span>{min}</span>
        <span>{max}</span>
      </span>
      {hint ? <span className="param-slider__hint">{hint}</span> : null}
    </label>
  );
}

interface CartMetricProps {
  index: string;
  tone: "a" | "b";
  mass: number;
  velocity: number;
  momentum: number;
}

function CartMetric({ index, tone, mass, velocity, momentum }: CartMetricProps) {
  return (
    <article className={`cart-metric cart-metric--${tone}`}>
      <header>
        <span>CART {index}</span>
        <strong>{mass.toFixed(1)}<em>kg</em></strong>
      </header>
      <div className="cart-metric__row">
        <span>v</span>
        <b className={velocity > 0.004 ? "is-positive" : velocity < -0.004 ? "is-negative" : ""}>
          {signed(velocity, 2)}
        </b>
        <em>m/s</em>
      </div>
      <div className="cart-metric__row cart-metric__row--momentum">
        <span>p</span>
        <b>{signed(momentum, 2)}</b>
        <em>kg·m/s</em>
      </div>
    </article>
  );
}

function MomentumTick({ value, scale, tone }: { value: number; scale: number; tone: "a" | "b" }) {
  const width = Math.min(50, (Math.abs(value) / scale) * 50);
  const left = value >= 0 ? 50 : 50 - width;
  return (
    <i
      className={`momentum-tick momentum-tick--${tone}`}
      style={{ left: `${left}%`, width: `${width}%` }}
    />
  );
}

interface MomentumChartProps {
  history: SimSample[];
  impacts: ImpactRecord[];
  mode: ChartMode;
  initialP: number;
  initialKe: number;
  now: number;
}

function MomentumChart({ history, impacts, mode, initialP, initialKe, now }: MomentumChartProps) {
  const samples = history.length > 0 ? history : [];
  const chartEnd = Math.max(4, Math.ceil(now));
  const maxMomentum = Math.max(
    1,
    Math.abs(initialP),
    ...samples.map(sample => Math.max(Math.abs(sample.p1), Math.abs(sample.p2)))
  );
  const maxEnergy = Math.max(1, initialKe, ...samples.map(sample => sample.ke)) * 1.12;

  const x = (t: number) => (Math.min(t, chartEnd) / chartEnd) * 1000;
  const yMomentum = (value: number) =>
    100 - (value / maxMomentum) * 88;
  const yEnergy = (value: number) =>
    190 - (Math.max(0, value) / maxEnergy) * 170;

  const makePoints = (key: "p1" | "p2" | "pTotal" | "ke1" | "ke2" | "ke") =>
    samples
      .map(sample => {
        const value = sample[key];
        const y = mode === "momentum" ? yMomentum(value) : yEnergy(value);
        return `${x(sample.t).toFixed(2)},${y.toFixed(2)}`;
      })
      .join(" ");

  const totalPoints = makePoints(mode === "momentum" ? "pTotal" : "ke");
  const aPoints = makePoints(mode === "momentum" ? "p1" : "ke1");
  const bPoints = makePoints(mode === "momentum" ? "p2" : "ke2");

  const yLabels =
    mode === "momentum"
      ? [maxMomentum.toFixed(1), "0", `−${maxMomentum.toFixed(1)}`]
      : [maxEnergy.toFixed(1), (maxEnergy / 2).toFixed(1), "0"];
  const gridLines =
    mode === "momentum" ? [12, 56, 100, 144, 188] : [20, 62.5, 105, 147.5, 190];
  const zeroY = mode === "momentum" ? 100 : 190;
  const initialLineY =
    mode === "momentum" ? yMomentum(initialP) : yEnergy(initialKe);

  return (
    <div className={`momentum-chart momentum-chart--${mode}`}>
      <div className="chart-y">
        {yLabels.map(label => (
          <span key={label}>{label}</span>
        ))}
      </div>
      <div className="chart-plot">
        <svg viewBox="0 0 1000 200" preserveAspectRatio="none" role="img" aria-label="动量与动能随时间变化曲线">
          <defs>
            <linearGradient id="chartFade" x1="0" y1="0" x2="0" y2="1">
              <stop offset="0%" stopColor="#d8ff63" stopOpacity="0.13" />
              <stop offset="100%" stopColor="#d8ff63" stopOpacity="0" />
            </linearGradient>
          </defs>
          {gridLines.map(y => (
            <line
              key={y}
              x1="0"
              y1={y}
              x2="1000"
              y2={y}
              className="chart-gridline"
            />
          ))}
          <line
            x1="0"
            y1={zeroY}
            x2="1000"
            y2={zeroY}
            className="chart-zeroline"
          />
          <line
            x1="0"
            y1={initialLineY}
            x2="1000"
            y2={initialLineY}
            className="chart-initial-line"
          />
          {impacts.map(record => (
            <line
              key={`${record.serial}-${record.t}`}
              x1={x(record.t)}
              y1="12"
              x2={x(record.t)}
              y2="190"
              className="chart-eventline"
            />
          ))}
          {samples.length > 1 ? (
            <>
              {mode === "kinetic" ? (
                <polygon points={`0,190 ${totalPoints} 1000,190`} fill="url(#chartFade)" />
              ) : null}
              <polyline points={aPoints} className="chart-line chart-line--a" />
              <polyline points={bPoints} className="chart-line chart-line--b" />
              <polyline points={totalPoints} className="chart-line chart-line--total" />
            </>
          ) : (
            <circle cx={x(0)} cy={initialLineY} r="4" className="chart-dot" />
          )}
        </svg>
        {samples.length <= 1 ? (
          <div className="chart-empty">
            <span>等待数据</span>
            <p>按下开始测量，曲线会随时间生长。</p>
          </div>
        ) : null}
        <div className="chart-x">
          <span>0.0 s</span>
          <span>{(chartEnd / 2).toFixed(1)} s</span>
          <span>{chartEnd.toFixed(1)} s</span>
        </div>
      </div>
      <div className="chart-note">
        <span className="chart-equation">
          m₁v₁ + m₂v₂ <i>=</i> m₁v₁′ + m₂v₂′
        </span>
        <span className="chart-explainer">
          {mode === "momentum"
            ? "绿色总动量线应保持水平 —— 这就是动量守恒。"
            : "非弹性碰撞后总动能下降；动量仍然守恒。"}
        </span>
        <em>Δt = 72 ms</em>
      </div>
    </div>
  );
}

function signed(value: number, digits: number): string {
  if (Math.abs(value) < 0.5 * 10 ** -digits) return (0).toFixed(digits);
  return `${value > 0 ? "+" : ""}${value.toFixed(digits)}`;
}

function formatDelta(value: number): string {
  if (Math.abs(value) < 5e-4) return "0.0000";
  return `${value > 0 ? "+" : ""}${value.toFixed(4)}`;
}

function PlayIcon() {
  return (
    <svg viewBox="0 0 24 24" aria-hidden="true">
      <path d="M8 5.5 18.5 12 8 18.5z" fill="currentColor" />
    </svg>
  );
}

function PauseIcon() {
  return (
    <svg viewBox="0 0 24 24" aria-hidden="true">
      <path d="M7.5 5.5h3.2v13H7.5zM13.3 5.5h3.2v13h-3.2z" fill="currentColor" />
    </svg>
  );
}

function ResetIcon() {
  return (
    <svg viewBox="0 0 24 24" aria-hidden="true">
      <path
        d="M5.2 9.2A7.6 7.6 0 1 1 4.8 14M5.2 9.2V4.6m0 4.6h4.6"
        fill="none"
        stroke="currentColor"
        strokeWidth="1.6"
        strokeLinecap="round"
        strokeLinejoin="round"
      />
    </svg>
  );
}

function HelpIcon() {
  return (
    <svg viewBox="0 0 24 24" aria-hidden="true">
      <circle cx="12" cy="12" r="8.2" fill="none" stroke="currentColor" strokeWidth="1.5" />
      <path
        d="M9.8 9.1a2.4 2.4 0 1 1 3.4 2.2c-.8.4-1.1.9-1.1 1.8"
        fill="none"
        stroke="currentColor"
        strokeWidth="1.5"
        strokeLinecap="round"
      />
      <circle cx="12" cy="16.5" r="0.9" fill="currentColor" />
    </svg>
  );
}

function CloseIcon() {
  return (
    <svg viewBox="0 0 24 24" aria-hidden="true">
      <path
        d="M6.5 6.5 17.5 17.5M17.5 6.5 6.5 17.5"
        fill="none"
        stroke="currentColor"
        strokeWidth="1.6"
        strokeLinecap="round"
      />
    </svg>
  );
}
