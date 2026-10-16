import { useEffect, useRef, useState } from "react";

import { api } from "../api/client";
import type { JobView } from "@eduforge/contracts";

/**
 * 任务轮询。三条硬要求（§6.2）：
 *  ① 不重叠——下一次请求在本次 settle 之后才排定时器，而不是 setInterval 硬发；
 *  ② 终态即停——succeeded/failed/cancelled 之后不再打服务端；
 *  ③ 卸载即停——清定时器并 abort 在途请求。
 */
export function useJob(jobId: string | null, intervalMs = 1200) {
  const [job, setJob] = useState<JobView | null>(null);
  const [error, setError] = useState<string | null>(null);
  const inflight = useRef<AbortController | null>(null);

  useEffect(() => {
    setJob(null);
    setError(null);
    if (!jobId) return;

    let stopped = false;
    let timer: number | undefined;

    const tick = async () => {
      const ctrl = new AbortController();
      inflight.current = ctrl;
      try {
        const got = await api.job(jobId, ctrl.signal);
        if (stopped) return;
        setJob(got);
        setError(null);
        if (got.status === "queued" || got.status === "running") {
          timer = window.setTimeout(tick, intervalMs);
        }
      } catch (e) {
        if (stopped) return;
        if ((e as Error)?.name === "AbortError") return;
        setError(String((e as Error).message ?? e));
        // 出错也要重试，否则任务看起来永远卡住；但同样走"settle 后再排"
        timer = window.setTimeout(tick, Math.max(intervalMs, 3000));
      } finally {
        if (inflight.current === ctrl) inflight.current = null;
      }
    };

    void tick();
    return () => {
      stopped = true;
      if (timer !== undefined) window.clearTimeout(timer);
      inflight.current?.abort();
    };
  }, [jobId, intervalMs]);

  return { job, error };
}
