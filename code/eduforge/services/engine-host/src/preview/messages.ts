// §5.3 预览通信协议。只表达确实实现了的三类消息。
export type PreviewMessage =
  | { type: "eduforge.ready"; revision_id: string }
  | { type: "eduforge.parameter_changed"; entity_id: string; parameter: string; value: number }
  | { type: "eduforge.error"; code: string; message: string };

/**
 * 包装页里的桥接脚本：
 *  - 上游不暴露场景全局，所以"就绪"用同源可及的 #welcome 隐藏来判定（第 3/4 轮已证该遮罩
 *    只在无场景时显示）；
 *  - 收到父页的 set_parameter 就换掉 iframe 的场景 hash 重新加载，再报一次 ready；
 *  - 入站消息必须同源，否则忽略；出站用显式 targetOrigin，不用 "*"。
 */
export const BRIDGE_SCRIPT = `
(function () {
  const revision = document.body.dataset.revision || "";
  const sim = document.getElementById("sim");
  const sameOrigin = (o) => o === location.origin;

  function post(msg) {
    if (window.parent === window) return;
    window.parent.postMessage(msg, location.origin);
  }

  async function waitReady(timeoutMs) {
    const started = Date.now();
    while (Date.now() - started < timeoutMs) {
      try {
        const d = sim.contentDocument;
        const w = d && d.getElementById("welcome");
        if (d && w) {
          const s = d.defaultView.getComputedStyle(w);
          const hidden = s.display === "none" || s.visibility === "hidden" || Number(s.opacity) === 0;
          if (hidden) return true;
        }
      } catch (e) { /* 还没载入 */ }
      await new Promise(r => setTimeout(r, 300));
    }
    return false;
  }

  async function announce() {
    if (await waitReady(30000)) post({ type: "eduforge.ready", revision_id: revision });
    else post({ type: "eduforge.error", code: "SCENE_NOT_LOADED", message: "上游场景在 30s 内未载入" });
  }

  // 每个 src 只报一次 ready。最初版本在脚本末尾直接 announce() 又挂了 load 监听，
  // 导致同一次载入报两条 ready（用例断言"一次且只一次"把它逮住了）。
  let announcedFor = null;
  function announceOnce() {
    const src = sim.getAttribute("src");
    if (announcedFor === src) return;
    announcedFor = src;
    announce();
  }

  window.addEventListener("message", async (e) => {
    if (!sameOrigin(e.origin)) return;                       // 非同源一律忽略
    const d = e.data || {};
    if (d.type !== "eduforge.set_parameter") return;
    if (!d.entity_id || !d.parameter || !Number.isFinite(d.value)) {
      post({ type: "eduforge.error", code: "BAD_MESSAGE", message: "set_parameter 需要 entity_id/parameter/有限的 value" });
      return;
    }
    try {
      // 先取新地址，换 src，等它真的载入完，再报就绪与变更。
      // 提前把去重标记设成新 src：否则 load 监听与这里的 announce0 会各报一次 ready。
      const next = await window.__applyParameter(d.entity_id, d.parameter, d.value);
      const loaded = new Promise(r => sim.addEventListener("load", r, { once: true }));
      announcedFor = next;
      sim.src = next;
      await loaded;
      await announce0(next);
      post({
        type: "eduforge.parameter_changed",
        entity_id: d.entity_id,
        parameter: d.parameter,
        value: d.value,
      });
    } catch (err) {
      post({ type: "eduforge.error", code: "APPLY_FAILED", message: String((err && err.message) || err) });
    }
  });

  async function announce0(src) {
    if (await waitReady(30000)) {
      announcedFor = src;
      // revision_id 报告的是"当前展示的版本"，由服务端在 src 里带上（?rev=）
      // wrapperPage 初次 render 时 src 是相对路径且已带 ?rev=；announceOnce 读的是属性
      const m = /[?&]rev=([^&#]+)/.exec(src);
      post({ type: "eduforge.ready", revision_id: m ? decodeURIComponent(m[1]) : revision });
    } else {
      post({ type: "eduforge.error", code: "SCENE_NOT_LOADED", message: "上游场景在 30s 内未载入" });
    }
  }

  sim.addEventListener("load", () => { announceOnce(); });
  announceOnce();
})();
`;

/** 宿主页（教师前端里 PreviewFrame 的最小等价物）：嵌包装页并把收到的消息显示出来。 */
export function hostPage(wrapperPath: string, revision: string): string {
  return `<!doctype html>
<html lang="zh-CN"><head><meta charset="utf-8"><title>EduForge 宿主 ${revision}</title>
<style>body{margin:0;font:13px/1.5 system-ui}#log{padding:8px;white-space:pre-wrap;background:#111;color:#8f8;
height:6em;overflow:auto}iframe{width:100%;height:70vh;border:0;display:block}</style>
</head><body>
<div id="log" data-revision="${revision}"></div>
<iframe id="wrap" src="${wrapperPath}"></iframe>
<script>
const log = document.getElementById("log");
const wrap = document.getElementById("wrap");
window.addEventListener("message", (e) => {
  if (e.origin !== location.origin) return;
  log.textContent += JSON.stringify(e.data) + "\\n";
});
window.__setParam = (entity_id, parameter, value) =>
  wrap.contentWindow.postMessage({ type: "eduforge.set_parameter", entity_id, parameter, value }, location.origin);
</script>
</body></html>`;
}
