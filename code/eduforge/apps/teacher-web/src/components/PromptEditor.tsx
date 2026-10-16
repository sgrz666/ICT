import { useState } from "react";

import { ApiError, api } from "../api/client";
import { ErrorNotice } from "./ErrorNotice";

/**
 * 需求输入与提交。幂等键在这里生成并持有：
 * 同一次点击造成的重发必须复用同一个键（服务端据此去重），
 * 拿到 job_id 之后才换新键。
 */
export function PromptEditor({
  experimentId,
  baseRevision,
  busy,
  onSubmitted,
}: {
  experimentId: string | null;
  baseRevision: string | null;
  busy: boolean;
  onSubmitted: (jobId: string) => void;
}) {
  const [prompt, setPrompt] = useState("把凸透镜焦距改成 15 厘米，并显示测量记录表");
  const [key, setKey] = useState<string>(() => crypto.randomUUID());
  const [sending, setSending] = useState(false);
  const [error, setError] = useState<string | null>(null);

  const submit = async () => {
    if (!experimentId || !baseRevision) {
      setError("EXPERIMENT_NOT_FOUND");
      return;
    }
    setSending(true);
    setError(null);
    try {
      const accepted = await api.submitJob(
        { experiment_id: experimentId, base_revision: baseRevision, prompt: prompt.trim() },
        key
      );
      setKey(crypto.randomUUID());
      onSubmitted(accepted.job_id);
    } catch (e) {
      setError(e instanceof ApiError ? e.code : "UNKNOWN");
    } finally {
      setSending(false);
    }
  };

  return (
    <section>
      <h2>你想怎么改这个实验？</h2>
      <textarea rows={3} value={prompt} onChange={e => setPrompt(e.target.value)} />
      <div className="row" style={{ marginTop: ".6rem" }}>
        <button
          type="button"
          onClick={() => void submit()}
          disabled={!experimentId || busy || sending || prompt.trim().length === 0}
        >
          {sending ? "提交中…" : "提交给 Agent"}
        </button>
        <span className="muted">
          本次提交的幂等键 <code>{key.slice(0, 8)}</code>
        </span>
      </div>
      {error ? <ErrorNotice code={error} /> : null}
      {!experimentId ? <p className="muted">先在左侧选一个实验环境。</p> : null}
    </section>
  );
}
