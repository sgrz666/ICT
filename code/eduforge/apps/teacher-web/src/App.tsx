import { useCallback, useEffect, useState } from "react";

import type { ExperimentDetail, ExperimentCreated, RevisionSummary, TemplateSummary } from "@eduforge/contracts";
import { ApiError, api, downloadVerified } from "./api/client";
import { ExperimentWorkspace } from "./components/ExperimentWorkspace";
import { TemplateLibrary } from "./components/TemplateLibrary";
import { SimulatorView } from "./components/SimulatorView";
import { GalleryView } from "./components/GalleryView";
import { useJob } from "./hooks/useJob";

type TabKey = "studio" | "simulator" | "gallery";

export function App() {
  // 根据 URL Hash 决定初始 Tab，默认可在 studio / simulator 之间平滑切换
  const initialTab = ((): TabKey => {
    const hash = window.location.hash.toLowerCase();
    if (hash.includes("sim")) return "simulator";
    if (hash.includes("gallery")) return "gallery";
    return "studio";
  })();

  const [activeTab, setActiveTab] = useState<TabKey>(initialTab);
  const [simulatorScene, setSimulatorScene] = useState<string>("../cn/gallery/convex-lens");

  const [templates, setTemplates] = useState<TemplateSummary[]>([]);
  const [templateError, setTemplateError] = useState<string | null>(null);
  const [exp, setExp] = useState<ExperimentCreated | null>(null);
  const [jobId, setJobId] = useState<string | null>(null);
  const [detail, setDetail] = useState<ExperimentDetail | null>(null);
  const [revisions, setRevisions] = useState<RevisionSummary[]>([]);
  const [selected, setSelected] = useState<string | null>(null);
  const [preview, setPreview] = useState<{ path: string; revision: string } | null>(null);
  const [artifact, setArtifact] = useState<{ id: string; sha256: string } | null>(null);
  const [zipArtifact, setZipArtifact] = useState<{ id: string; sha256: string } | null>(null);
  // §C.3：教学视图配置随版本一起载入，面板只渲染后端给的那一份
  const [views, setViews] = useState<Record<string, unknown> | null>(null);
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
      const [listed, viewData] = await Promise.all([api.artifacts(revisionId), api.views(revisionId)]);
      setViews(viewData.views);
      // 按 storage_key 认领交付场景，不靠数组下标：一次发布现在登记 native、
      // 教学视图、离线包清单与离线运行包 ZIP。
      const native = listed.artifacts.find(a =>
        a.storage_key.replace(/\\/g, "/").endsWith("native.json")
      );
      const zip = listed.artifacts.find(a =>
        a.media_type === "application/zip" || a.storage_key.replace(/\\/g, "/").endsWith(".zip")
      );
      setZipArtifact(zip ? { id: zip.artifact_id, sha256: zip.sha256 } : null);
      if (!native) {
        // §C.5c：未发布的原始种子 revision 没有产物时，按该 revision 自己存储的 native_data 实体校验后展示。
        // 绝不静默退回到通用模板 /adapters/ray_optics/template。
        const seed = await api.revisionNative(revisionId);
        if (seed && seed.native_data && typeof seed.native_data === "object" && Object.keys(seed.native_data).length > 0) {
          const reg = await api.registerPreview(seed.native_data);
          setPreview({ path: reg.path, revision: revisionId });
          setArtifact(null);
          setZipArtifact(null);
          return;
        }
        setLoadErrorCode("INVALID_REVISION_DATA");
        setPreview(null);
        setArtifact(null);
        setZipArtifact(null);
        return;
      }
      const got = await downloadVerified(native.artifact_id, native.sha256);
      const scene = JSON.parse(new TextDecoder().decode(got.bytes)) as unknown;
      const reg = await api.registerPreview(scene);
      setPreview({ path: reg.path, revision: revisionId });
      setArtifact({ id: native.artifact_id, sha256: got.sha256 });
    } catch (e) {
      setPreview(null);
      setArtifact(null);
      setZipArtifact(null);
      setViews(null);
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
      setZipArtifact(null);
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
  const [savingTuned, setSavingTuned] = useState(false);

  const handleSaveTunedRevision = async (
    changes: Array<{ entityId: string; parameter: string; value: number }>
  ) => {
    if (!exp) return;
    setSavingTuned(true);
    setLoadErrorCode(null);
    setLoadErrorDetail(null);
    try {
      const baseRev = detail?.head_revision ?? exp.base_revision;
      const promptParts = changes.map(c => {
        const ctrl = controls?.find(x => x.entity_id === c.entityId && x.parameter === c.parameter);
        if (ctrl?.label) {
          return `把${ctrl.label}改成 ${c.value}${ctrl.unit || ""}`;
        }
        return `把 ${c.entityId} 的 ${c.parameter} 设为 ${c.value}`;
      });
      const prompt = promptParts.join("，并");
      const key = crypto.randomUUID();
      const accepted = await api.submitJob(
        { experiment_id: exp.experiment_id, base_revision: baseRev, prompt },
        key
      );
      setJobId(accepted.job_id);
    } catch (e) {
      if (e instanceof ApiError) setLoadErrorCode(e.code);
      else setLoadErrorDetail(String((e as Error).message ?? e));
    } finally {
      setSavingTuned(false);
    }
  };

  // 从案例库一键载入模拟器
  const handleOpenInSimulator = (sceneUrl: string) => {
    setSimulatorScene(sceneUrl);
    setActiveTab("simulator");
    window.location.hash = "simulator";
  };

  // 从模拟器或案例库导入到 AI 定制工坊
  const handleImportToStudio = (sceneUrl: string, title: string) => {
    setActiveTab("studio");
    window.location.hash = "studio";
    // 优先匹配对应案例的模板
    const matched = templates.find(t => title.includes(t.title) || (t.title.includes("凸透镜") && title.includes("凸透镜")));
    if (matched) {
      if (!exp || exp.template_id !== matched.template_id) {
        void pick(matched.template_id);
      }
    } else {
      // 保留所选实际场景信息
      setSimulatorScene(sceneUrl);
    }
  };

  return (
    <div className="app-root">
      {/* 顶层导航栏 */}
      <header className="app-header">
        <div className="brand-section">
          <span className="brand-logo">🔬</span>
          <div>
            <div className="brand-title">Ray Optics 射线光学模拟</div>
            <div className="brand-subtitle">二维几何光学仿真与 AI 教学定制平台</div>
          </div>
        </div>

        <nav className="nav-tabs">
          <button
            className={`nav-tab-btn ${activeTab === "studio" ? "active" : ""}`}
            onClick={() => { setActiveTab("studio"); window.location.hash = "studio"; }}
          >
            🤖 AI 教学定制工坊
          </button>
          <button
            className={`nav-tab-btn ${activeTab === "simulator" ? "active" : ""}`}
            onClick={() => { setActiveTab("simulator"); window.location.hash = "simulator"; }}
          >
            ⚡ 光学仿真模拟器
          </button>
          <button
            className={`nav-tab-btn ${activeTab === "gallery" ? "active" : ""}`}
            onClick={() => { setActiveTab("gallery"); window.location.hash = "gallery"; }}
          >
            📚 81 演示案例库
          </button>
        </nav>

        <div className="header-links">
          <a
            href="/simulator/?zh-CN"
            target="_blank"
            rel="noreferrer"
            className="link-button"
            title="新窗口打开原生模拟器"
          >
            原生模拟器 ↗
          </a>
          <a
            href="/cn/gallery/"
            target="_blank"
            rel="noreferrer"
            className="link-button"
            title="新窗口打开原版案例库"
          >
            原版案例库 ↗
          </a>
        </div>
      </header>

      {/* 主界面内容切换 */}
      <div className="app-content">
        {activeTab === "simulator" ? (
          <SimulatorView
            activeScene={simulatorScene}
            onSelectScene={setSimulatorScene}
            onImportToStudio={handleImportToStudio}
          />
        ) : null}

        {activeTab === "gallery" ? (
          <GalleryView
            onOpenInSimulator={handleOpenInSimulator}
            onImportToStudio={handleImportToStudio}
          />
        ) : null}

        {activeTab === "studio" ? (
          <main className="studio-layout">
            <aside>
              <h1>EduForge 教师工作台</h1>
              <TemplateLibrary
                templates={templates}
                loading={templates.length === 0 && !templateError}
                error={templateError}
                selected={exp?.template_id ?? null}
                onPick={id => void pick(id)}
              />
              <div style={{ marginTop: "0.5rem" }}>
                <button
                  className="ghost"
                  style={{ width: "100%", textAlign: "left" }}
                  onClick={() => { setActiveTab("gallery"); window.location.hash = "gallery"; }}
                >
                  📚 从 81 个光学案例库中挑选 →
                </button>
              </div>
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
              baseRevision={detail?.head_revision ?? exp?.base_revision ?? null}
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
              zipArtifact={zipArtifact}
              views={views}
              controls={controls}
              onSaveTunedRevision={changes => void handleSaveTunedRevision(changes)}
              savingTuned={savingTuned}
              loadErrorCode={loadErrorCode}
              loadErrorDetail={loadErrorDetail}
            />
          </main>
        ) : null}
      </div>
    </div>
  );
}
