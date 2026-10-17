import type { ControlSummary, JobView, RevisionSummary } from "@eduforge/contracts";

import { DownloadButton } from "./DownloadButton";
import { ErrorNotice } from "./ErrorNotice";
import { JobProgress } from "./JobProgress";
import { PreviewFrame } from "./PreviewFrame";
import { PromptEditor } from "./PromptEditor";
import { RevisionHistory } from "./RevisionHistory";
import { TeachingViews } from "./TeachingViews";

/** 工作区：把输入、进度、预览、版本与下载组合在一屏里（§6.2 的组合职责）。 */
export function ExperimentWorkspace(props: {
  experimentId: string | null;
  baseRevision: string | null;
  jobId: string | null;
  job: JobView | null;
  pollError: string | null;
  busy: boolean;
  onSubmitted: (id: string) => void;
  onCancel: () => void;
  revisions: RevisionSummary[];
  headRevision: string | null;
  selectedRevision: string | null;
  onSelectRevision: (id: string) => void;
  onRollback?: (id: string) => void;
  rollingBack?: boolean;
  preview: { path: string; revision: string } | null;
  artifact: { id: string; sha256: string } | null;
  views: Record<string, unknown> | null;
  controls?: ControlSummary[];
  onSaveTunedRevision?: (changes: Array<{ entityId: string; parameter: string; value: number }>) => void;
  savingTuned?: boolean;
  loadErrorCode: string | null;
  loadErrorDetail: string | null;
}) {
  const running = props.job?.status === "queued" || props.job?.status === "running";

  return (
    <div>
      <PromptEditor
        experimentId={props.experimentId}
        baseRevision={props.baseRevision}
        busy={props.busy}
        onSubmitted={props.onSubmitted}
      />
      <JobProgress job={props.job} pollError={props.pollError} />
      {props.jobId && running ? (
        <p>
          <button type="button" className="ghost" onClick={props.onCancel}>
            取消这次任务
          </button>
        </p>
      ) : null}
      <ErrorNotice code={props.loadErrorCode} extra={props.loadErrorDetail ?? undefined} />
      <RevisionHistory
        revisions={props.revisions}
        headRevision={props.headRevision}
        selected={props.selectedRevision}
        onSelect={props.onSelectRevision}
        onRollback={props.onRollback}
        rollingBack={props.rollingBack}
      />
      <PreviewFrame
        wrapperPath={props.preview?.path ?? null}
        revision={props.preview?.revision ?? ""}
        controls={props.controls}
        onSaveTunedRevision={props.onSaveTunedRevision}
        savingTuned={props.savingTuned}
      />
      <TeachingViews views={props.views} />
      <section>
        <h2>交付</h2>
        <DownloadButton
          artifactId={props.artifact?.id ?? null}
          expectedSha={props.artifact?.sha256 ?? null}
          fileName={props.selectedRevision ? `native-${props.selectedRevision.slice(0, 8)}.json` : "native.json"}
        />
      </section>
    </div>
  );
}
