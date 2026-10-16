import { useState } from "react";

import { ApiError, downloadVerified } from "../api/client";

/**
 * 下载产物。
 *
 * 先重算并比对哈希，再决定要不要把文件交给用户——"点了就存盘"的下载按钮
 * 等于把校验责任推给还没拿到文件的老师。
 */
export function DownloadButton({
  artifactId,
  expectedSha,
  fileName,
}: {
  artifactId: string | null;
  expectedSha: string | null;
  fileName: string;
}) {
  const [state, setState] = useState<{ busy: boolean; message: string | null; ok: boolean }>({
    busy: false,
    message: null,
    ok: false,
  });

  const save = async () => {
    if (!artifactId || !expectedSha) return;
    setState({ busy: true, message: null, ok: false });
    try {
      const got = await downloadVerified(artifactId, expectedSha);
      const url = URL.createObjectURL(new Blob([got.bytes], { type: got.mediaType }));
      const a = document.createElement("a");
      a.href = url;
      a.download = fileName;
      a.click();
      URL.revokeObjectURL(url);
      setState({ busy: false, message: `已校验并保存：sha256 ${got.sha256.slice(0, 12)}…`, ok: true });
    } catch (e) {
      setState({
        busy: false,
        ok: false,
        message: e instanceof ApiError ? `${e.status} ${e.code}` : String((e as Error).message ?? e),
      });
    }
  };

  return (
    <div className="row">
      <button type="button" onClick={() => void save()} disabled={!artifactId || state.busy}>
        {state.busy ? "校验中…" : "下载原生场景"}
      </button>
      {state.message ? (
        <span className={state.ok ? "notice ok" : "notice"} style={{ padding: ".2rem .6rem" }}>
          {state.message}
        </span>
      ) : null}
    </div>
  );
}
