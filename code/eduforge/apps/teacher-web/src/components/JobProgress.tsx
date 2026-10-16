import type { JobView } from "@eduforge/contracts";
import { ErrorNotice } from "./ErrorNotice";

const STAGES: { id: string; label: string }[] = [
  { id: "planning", label: "理解需求" },
  { id: "editing", label: "改场景" },
  { id: "building", label: "算读数" },
  { id: "validating", label: "对照物理" },
  { id: "packaging", label: "发布版本" },
];

export function JobProgress({ job, pollError }: { job: JobView | null; pollError: string | null }) {
  if (!job) {
    return (
      <section aria-live="polite">
        <h2>进度</h2>
        <p className="muted">{pollError ? `查不到任务：${pollError}` : "提交后这里会跟着阶段走。"}</p>
      </section>
    );
  }

  const done = new Set(job.events.filter(e => e.event_type === "stage_done").map(e => e.stage));
  const failed = job.status === "failed";

  return (
    <section aria-live="polite">
      <h2>
        进度 · <span className="code">{job.status}</span>
      </h2>
      <ul className="stages">
        {STAGES.map(s => (
          <li
            key={s.id}
            className={done.has(s.id) ? "done" : failed && job.stage === s.id ? "failed" : job.stage === s.id ? "active" : ""}
          >
            {s.label}
          </li>
        ))}
      </ul>
      {done.has("validating") ? (
        <p className="muted">验证报告已生成；只有通过的版本才会出现在版本历史里。</p>
      ) : null}
      {failed ? <ErrorNotice code={job.error_code ?? "UNKNOWN"} /> : null}
      {job.status === "cancelled" ? <div className="notice ok">任务已取消，已发布版本不受影响。</div> : null}
    </section>
  );
}
