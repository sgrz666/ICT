/**
 * 教学视图面板（Gate C §C.3）。
 *
 * 数据只有一个来源：`GET /api/v1/revisions/{id}/views`，也就是发布时冻结在
 * `experiment_revisions.lesson` 里的那一份。前端不自己拼表头、不自己算像距——
 * 那样界面上出现的数字就没有交付凭据可言。
 * 因为是外部输入，这里在边界上做运行时校验：形状不对就如实说"读不出来"，
 * 而不是猜一个默认结构渲染半张表。
 */

type Column = { key: string; label: string; unit: string };

const VIEW_LABELS: Record<string, string> = {
  scene: "场景",
  controls: "控件",
  measurement_table: "测量记录表",
};

function isRecord(v: unknown): v is Record<string, unknown> {
  return typeof v === "object" && v !== null && !Array.isArray(v);
}

function columnsOf(raw: unknown): Column[] | null {
  if (!Array.isArray(raw)) return null;
  const out: Column[] = [];
  for (const c of raw) {
    if (!isRecord(c) || typeof c.key !== "string") return null;
    out.push({
      key: c.key,
      label: typeof c.label === "string" ? c.label : String(c.key),
      unit: typeof c.unit === "string" ? c.unit : "",
    });
  }
  return out;
}

function cell(v: unknown): string {
  if (v === null || v === undefined || v === "") return "—";
  if (typeof v === "number") return Number.isInteger(v) ? String(v) : v.toFixed(2);
  return String(v);
}

export function TeachingViews({ views }: { views: Record<string, unknown> | null }) {
  const enabled = Object.entries(views ?? {}).flatMap(([id, cfg]) =>
    isRecord(cfg) && cfg.visible === true ? [[id, cfg] as [string, Record<string, unknown>]] : []
  );

  return (
    <section id="teaching-views">
      <h2>教学视图（取自已发布版本）</h2>
      {!views || enabled.length === 0 ? (
        <p className="muted">这个版本没有开启任何教学视图。</p>
      ) : (
        <p className="muted">已开启：{enabled.map(([id]) => VIEW_LABELS[id] ?? id).join("、")}</p>
      )}

      {enabled.map(([id, cfg]) => {
        if (id !== "measurement_table") {
          return <p key={id} className="muted">{VIEW_LABELS[id] ?? id}：由预览与控件承载，无独立表格。</p>;
        }
        const columns = columnsOf(cfg.columns);
        const records = Array.isArray(cfg.records) ? cfg.records.filter(isRecord) : null;
        if (!columns || columns.length === 0 || records === null) {
          return (
            <p key="mt" className="notice">
              测量记录表的结构读不出来（缺 columns/records），不猜一份表头来凑数。
            </p>
          );
        }
        return (
          <table key="mt">
            <caption className="muted">测量记录表（{records.length} 行）</caption>
            <thead>
              <tr>
                {columns.map(c => (
                  <th key={c.key}>{c.unit ? `${c.label}（${c.unit}）` : c.label}</th>
                ))}
              </tr>
            </thead>
            <tbody>
              {records.map((r, i) => (
                <tr key={i}>
                  {columns.map(c => (
                    <td key={c.key}>{cell(r[c.key])}</td>
                  ))}
                </tr>
              ))}
            </tbody>
          </table>
        );
      })}
    </section>
  );
}
