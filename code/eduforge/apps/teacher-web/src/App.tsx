import { useCallback, useEffect, useState } from "react";

import type { ExperimentDetail, ExperimentCreated, RevisionSummary, TemplateSummary } from "@eduforge/contracts";
import { ApiError, api, downloadVerified } from "./api/client";
import { ExperimentWorkspace } from "./components/ExperimentWorkspace";
import { TemplateLibrary } from "./components/TemplateLibrary";
import { useJob } from "./hooks/useJob";

export function App() {
  const [templates, setTemplates] = useState<TemplateSummary[]>([]);
  const [templateError, setTemplateError] = useState<string | null>(null);
  const [exp, setExp] = useState<ExperimentCreated | null>(null);
  const [jobId, setJobId] = useState<string | null>(null);
  const [detail, setDetail] = useState<ExperimentDetail | null>(null);
  const [revisions, setRevisions] = useState<RevisionSummary[]>([]);
  const [selected, setSelected] = useState<string | null>(null);
  const [preview, setPreview] = useState<{ path: string; revision: string } | null>(null);
  const [artifact, setArtifact] = useState<{ id: string; sha256: string } | null>(null);
  const [loadErrorCode, setLoadErrorCode] = useState<string | null>(null);
  const [loadErrorDetail, setLoadErrorDetail] = useState<string | null>(null);
  const [rollingBack, setRollingBack] = useState(false);

  const { job, error: pollError } = useJob(jobId);

  useEffect(() => {
    api
      .templates()
      .then(r => setTemplates(r.templates))
      .catch(e => setTemplateError(e instanceof ApiError ? e.code : String(e)));
  }, []);

  /**
   * 载入某个已发布版本：先取产物清单登记的 sha256，再下载并重算比对，
   * 通过之后才把这份字节交给预览服务。预览展示的永远是交付的那份东西。
   */
  const loadRevision = useCallback(async (revisionId: string) => {
    setLoadErrorCode(null);
    setLoadErrorDetail(null);
    try {
      const listed = await api.artifacts(revisionId);
      const first = listed.artifacts[0];
      if (!first) {
        setLoadErrorCode("ARTIFACT_NOT_FOUND");
        setPreview(null);
        setArtifact(null);
        return;
      }
      const got = await downloadVerified(first.artifact_id, first.sha256);
      const scene = JSON.parse(new TextDecoder().decode(got.bytes)) as unknown;
      const reg = await api.registerPreview(scene);
      setPreview({ path: reg.path, revision: revisionId });
      setArtifact({ id: first.artifact_id, sha256: got.sha256 });
    } catch (e) {
      setPreview(null);
      setArtifact(null);
      if (e instanceof ApiError) setLoadErrorCode(e.code);
      else setLoadErrorDetail(String((e as Error).message ?? e));
    }
  }, []);

  const refreshExperiment = useCallback(
    async (experimentId: string) => {
      const [d, r] = await Promise.all([api.experiment(experimentId), api.revisions(experimentId)]);
      setDetail(d);
      setRevisions(r.revisions);
      return d;
    },
    []
  );

  // 任务成功后才刷新版本区：失败的任务没有可交付版本，不能把上一版当成新结果
  useEffect(() => {
    if (!job || job.status !== "succeeded" || !exp) return;
    void (async () => {
      const d = await refreshExperiment(exp.experiment_id);
      if (d.head_revision) {
        setSelected(d.head_revision);
        await loadRevision(d.head_revision);
      }
    })();
  }, [job, exp, refreshExperiment, loadRevision]);

  const pick = async (templateId: string) => {
    setLoadErrorCode(null);
    setLoadErrorDetail(null);
    try {
      const created = await api.createExperiment(templateId);
      setExp(created);
      setJobId(null);
      setPreview(null);
      setArtifact(null);
      setSelected(null);
      await refreshExperiment(created.experiment_id);
    } catch (e) {
      setLoadErrorCode(e instanceof ApiError ? e.code : "UNKNOWN");
    }
  };

  const handleRollback = async (targetRev: string) => {
    if (!exp) return;
    setRollingBack(true);
    setLoadErrorCode(null);
    setLoadErrorDetail(null);
    try {
      const updated = await api.rollbackExperiment(exp.experiment_id, targetRev);
      setDetail(updated);
      setSelected(targetRev);
      await loadRevision(targetRev);
    } catch (e) {
      if (e instanceof ApiError) setLoadErrorCode(e.code);
      else setLoadErrorDetail(String((e as Error).message ?? e));
    } finally {
      setRollingBack(false);
    }
  };

  const currentTemplate = templates.find(t => t.template_id === exp?.template_id);
  const controls = currentTemplate?.controls;

  return (
    <main>
      <aside>
        <h1>EduForge 教师工作台</h1>
        <TemplateLibrary
          templates={templates}
          loading={templates.length === 0 && !templateError}
          error={templateError}
          selected={exp?.template_id ?? null}
          onPick={id => void pick(id)}
        />
        {exp ? (
          <section>
            <h2>当前实验</h2>
            <div className="muted">实验 <code>{exp.experiment_id.slice(0, 8)}</code></div>
            <div className="muted">基础版本 <code>{exp.base_revision.slice(0, 8)}</code></div>
            <div className="muted">head <code>{detail?.head_revision?.slice(0, 8) ?? "—"}</code></div>
          </section>
        ) : null}
      </aside>
      <ExperimentWorkspace
        experimentId={exp?.experiment_id ?? null}
        baseRevision={exp?.base_revision ?? null}
        jobId={jobId}
        job={job}
        pollError={pollError}
        busy={job?.status === "queued" || job?.status === "running"}
        onSubmitted={setJobId}
        onCancel={() => {
          if (jobId) void api.cancelJob(jobId).then(() => refreshExperiment(exp!.experiment_id));
        }}
        revisions={revisions}
        headRevision={detail?.head_revision ?? null}
        selectedRevision={selected}
        onSelectRevision={id => {
          setSelected(id);
          void loadRevision(id);
        }}
        onRollback={id => void handleRollback(id)}
        rollingBack={rollingBack}
        preview={preview}
        artifact={artifact}
        controls={controls}
        loadErrorCode={loadErrorCode}
        loadErrorDetail={loadErrorDetail}
      />
    </main>
  );
}
