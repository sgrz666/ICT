import { useEffect, useRef, useState } from "react";

import type { ControlSummary, PreviewMessage } from "@eduforge/contracts";

/**
 * 预览：iframe 指向网关同源提供的包装页（/p/<id>），并按 §5.3 处理桥接消息。
 *
 * 只接受同源消息，且只认三类已实现的事件；桥接本身不能编造场景编辑，
 * 改参数必须回服务端 /param 由上游解释。
 */
export function PreviewFrame({
  wrapperPath,
  revision,
  controls,
}: {
  wrapperPath: string | null;
  revision: string;
  controls?: ControlSummary[];
}) {
  const frame = useRef<HTMLIFrameElement | null>(null);
  const [status, setStatus] = useState<string>("等待预览就绪…");
  const [error, setError] = useState<string | null>(null);
  const [paramValues, setParamValues] = useState<Record<string, number>>({});
  const [tuning, setTuning] = useState(false);

  useEffect(() => {
    if (!wrapperPath) return;
    setStatus("等待预览就绪…");
    setError(null);

    const onMessage = (e: MessageEvent<PreviewMessage>) => {
      if (e.origin !== window.location.origin) return; // 非同源一律忽略
      const m = e.data;
      if (!m || typeof m !== "object" || !("type" in m)) return;
      if (m.type === "eduforge.ready") {
        setStatus(`已载入版本 ${m.revision_id}`);
        setTuning(false);
      }
      if (m.type === "eduforge.parameter_changed") {
        setStatus(`${m.entity_id}.${m.parameter} = ${m.value} 已生效`);
        setParamValues(prev => ({ ...prev, [`${m.entity_id}.${m.parameter}`]: m.value }));
        setTuning(false);
      }
      if (m.type === "eduforge.error") {
        setError(`${m.code}：${m.message}`);
        setTuning(false);
      }
    };

    window.addEventListener("message", onMessage);
    return () => window.removeEventListener("message", onMessage);
  }, [wrapperPath]);

  const applyParam = (entityId: string, param: string, val: number) => {
    if (!frame.current?.contentWindow) return;
    setError(null);
    setTuning(true);
    setStatus(`正在向预览发送实时调节：${entityId}.${param} = ${val}…`);
    frame.current.contentWindow.postMessage(
      {
        type: "eduforge.set_parameter",
        entity_id: entityId,
        parameter: param,
        value: val,
      },
      window.location.origin
    );
  };

  return (
    <section>
      <h2>预览（由上游模拟器渲染）</h2>
      {wrapperPath ? (
        <iframe ref={frame} title="EduForge 预览" src={wrapperPath} allow="fullscreen" />
      ) : (
        <p className="muted">还没有可预览的已验证版本。</p>
      )}
      <p className="muted">
        {status}
        {revision ? ` · 当前交付版本 ${revision.slice(0, 8)}` : ""}
      </p>
      {error ? <div className="notice">{error}</div> : null}

      {controls && controls.length > 0 && wrapperPath ? (
        <div style={{ marginTop: "0.8rem", padding: "0.6rem 0.8rem", background: "rgba(255,255,255,0.05)", borderRadius: 6 }}>
          <h3 style={{ margin: "0 0 0.5rem", fontSize: "0.95rem" }}>实时参数调节（桥接直接驱动上游仿真）</h3>
          {controls.map(c => {
            const key = `${c.entity_id}.${c.parameter}`;
            const currentVal = paramValues[key] ?? c.initial ?? c.min;
            return (
              <div key={key} style={{ display: "flex", alignItems: "center", gap: "0.8rem", margin: "0.4rem 0" }}>
                <span style={{ minWidth: "110px" }}>{c.label || c.parameter} ({c.unit}):</span>
                <input
                  type="range"
                  min={c.min}
                  max={c.max}
                  step={1}
                  value={currentVal}
                  disabled={tuning}
                  onChange={e => {
                    const v = Number(e.target.value);
                    setParamValues(prev => ({ ...prev, [key]: v }));
                  }}
                  onMouseUp={e => {
                    applyParam(c.entity_id, c.parameter, Number((e.target as HTMLInputElement).value));
                  }}
                  onTouchEnd={e => {
                    applyParam(c.entity_id, c.parameter, Number((e.target as HTMLInputElement).value));
                  }}
                />
                <input
                  type="number"
                  min={c.min}
                  max={c.max}
                  value={currentVal}
                  disabled={tuning}
                  style={{ width: "70px" }}
                  onChange={e => {
                    const v = Number(e.target.value);
                    setParamValues(prev => ({ ...prev, [key]: v }));
                  }}
                  onBlur={e => {
                    applyParam(c.entity_id, c.parameter, Number(e.target.value));
                  }}
                  onKeyDown={e => {
                    if (e.key === "Enter") {
                      applyParam(c.entity_id, c.parameter, Number((e.target as HTMLInputElement).value));
                    }
                  }}
                />
                <span className="muted" style={{ fontSize: "0.85rem" }}>[{c.min} ~ {c.max} {c.unit}]</span>
                <button
                  type="button"
                  className="ghost"
                  disabled={tuning}
                  onClick={() => applyParam(c.entity_id, c.parameter, currentVal)}
                >
                  应用
                </button>
              </div>
            );
          })}
        </div>
      ) : null}
    </section>
  );
}
