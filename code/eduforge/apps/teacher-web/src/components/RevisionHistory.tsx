import type { RevisionSummary } from "@eduforge/contracts";

/**
 * 版本历史。
 *
 * 列表来自实验的真实 revision 链，head 由服务端标记——前端不自己推断"哪个是最新"。
 * 回滚（把 head 指回旧版本）在 §6.1 里还没有对应端点，因此这里不做按钮，
 * 也不拿"重新提交一次改回去的需求"冒充恢复功能。
 */
export function RevisionHistory({
  revisions,
  headRevision,
  selected,
  onSelect,
  onRollback,
  rollingBack,
}: {
  revisions: RevisionSummary[];
  headRevision: string | null;
  selected: string | null;
  onSelect: (id: string) => void;
  onRollback?: (id: string) => void;
  rollingBack?: boolean;
}) {
  return (
    <section>
      <h2>版本历史</h2>
      {revisions.length === 0 ? <p className="muted">还没有版本。</p> : null}
      <table>
        <thead>
          <tr>
            <th>版本</th>
            <th>父版本</th>
            <th>引擎</th>
            <th>时间</th>
            <th>操作</th>
          </tr>
        </thead>
        <tbody>
          {revisions.map(r => (
            <tr key={r.revision_id}>
              <td>
                <button
                  type="button"
                  className={selected === r.revision_id ? "" : "ghost"}
                  onClick={() => onSelect(r.revision_id)}
                >
                  {r.revision_id.slice(0, 8)}
                  {headRevision === r.revision_id ? " · head" : ""}
                </button>
              </td>
              <td className="muted">{r.parent_id ? r.parent_id.slice(0, 8) : "（种子）"}</td>
              <td className="muted">{r.engine_id}</td>
              <td className="muted">{new Date(r.created_at).toLocaleString("zh-CN")}</td>
              <td>
                {headRevision !== r.revision_id && onRollback ? (
                  <button
                    type="button"
                    className="ghost"
                    disabled={rollingBack}
                    onClick={() => onRollback(r.revision_id)}
                  >
                    {rollingBack ? "回滚中…" : "回滚到此版本"}
                  </button>
                ) : (
                  <span className="muted">当前 head</span>
                )}
              </td>
            </tr>
          ))}
        </tbody>
      </table>
    </section>
  );
}
