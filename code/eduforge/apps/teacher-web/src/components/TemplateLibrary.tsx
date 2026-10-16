import type { TemplateSummary } from "@eduforge/contracts";

/** 模板库：只显示后端清单里真实存在的东西。引擎未接的模板不会出现在这里。 */
export function TemplateLibrary({
  templates,
  loading,
  error,
  selected,
  onPick,
}: {
  templates: TemplateSummary[];
  loading: boolean;
  error: string | null;
  selected: string | null;
  onPick: (id: string) => void;
}) {
  return (
    <section>
      <h2>可选实验环境</h2>
      {loading ? <p className="muted">读取模板清单…</p> : null}
      {error ? <div className="notice">模板清单读取失败：{error}</div> : null}
      {!loading && !error && templates.length === 0 ? (
        <p className="muted">清单为空——目录里没有可用模板。</p>
      ) : null}
      <ul className="stages" style={{ display: "grid", gap: ".4rem" }}>
        {templates.map(t => (
          <li key={t.template_id} style={{ borderRadius: 6, padding: ".4rem .6rem" }}>
            <button
              type="button"
              className={selected === t.template_id ? "" : "ghost"}
              onClick={() => onPick(t.template_id)}
            >
              {t.title}
            </button>
            <div className="muted">
              引擎 <code>{t.engine_id}</code>
            </div>
          </li>
        ))}
      </ul>
    </section>
  );
}
