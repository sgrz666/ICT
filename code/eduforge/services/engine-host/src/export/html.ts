/**
 * 实验离线 HTML 组装器与直开预注入补丁。
 *
 * 对齐方案 §1.2 和 §5.5：
 * 攻克上游 i18next 在 file:// 协议或独立打开时取 ../locales/*.json 的 CORS/网络限制，
 * 内联关键 locale 词条并注入 fetch/XHR 拦截器，使离线页面具备纯静态直开能力。
 */
import { existsSync, readFileSync } from "node:fs";
import { dirname, join, resolve } from "node:path";
import { fileURLToPath } from "node:url";

const here = dirname(fileURLToPath(import.meta.url));
const UPSTREAM = resolve(here, "../../../../../../source/upstream/ray-optics");

export function loadEmbeddedLocales(): Record<string, unknown> {
  const locales: Record<string, unknown> = {};
  const targets = [
    { key: "zh-CN/simulator.json", rel: "locales/zh-CN/simulator.json" },
    { key: "zh-CN/main.json", rel: "locales/zh-CN/main.json" },
    { key: "en/simulator.json", rel: "locales/en/simulator.json" },
    { key: "en/main.json", rel: "locales/en/main.json" },
  ];

  for (const t of targets) {
    const p = join(UPSTREAM, t.rel);
    if (existsSync(p)) {
      try {
        locales[t.key] = JSON.parse(readFileSync(p, "utf8"));
      } catch {
        // fallback
      }
    }
  }
  return locales;
}

export function generateI18nPatchScript(): string {
  const locales = loadEmbeddedLocales();
  return `
<script>
/* EduForge 离线直开补丁：拦截 locales 请求，消除 file:// 跨域拦截 */
(function() {
  const LOCALES = ${JSON.stringify(locales)};
  const origFetch = window.fetch;
  if (typeof origFetch === 'function') {
    window.fetch = function(input, init) {
      const url = typeof input === 'string' ? input : (input && input.url ? input.url : '');
      for (const [key, val] of Object.entries(LOCALES)) {
        if (url.indexOf(key) !== -1 || url.endsWith(key)) {
          return Promise.resolve(new Response(JSON.stringify(val), {
            status: 200,
            headers: { 'Content-Type': 'application/json' }
          }));
        }
      }
      return origFetch.apply(this, arguments);
    };
  }
  const origOpen = XMLHttpRequest.prototype.open;
  const origSend = XMLHttpRequest.prototype.send;
  XMLHttpRequest.prototype.open = function(method, url) {
    this._eduforge_url = url;
    return origOpen.apply(this, arguments);
  };
  XMLHttpRequest.prototype.send = function() {
    const url = this._eduforge_url || '';
    for (const [key, val] of Object.entries(LOCALES)) {
      if (url.indexOf(key) !== -1 || url.endsWith(key)) {
        Object.defineProperty(this, 'status', { get: () => 200 });
        Object.defineProperty(this, 'responseText', { get: () => JSON.stringify(val) });
        Object.defineProperty(this, 'response', { get: () => JSON.stringify(val) });
        Object.defineProperty(this, 'readyState', { get: () => 4 });
        setTimeout(() => {
          if (typeof this.onreadystatechange === 'function') this.onreadystatechange();
          if (typeof this.onload === 'function') this.onload();
        }, 0);
        return;
      }
    }
    return origSend.apply(this, arguments);
  };
})();
</script>
`;
}

export function buildIndexHtml(hash: string, title: string = "EduForge 实验"): string {
  const patch = generateI18nPatchScript();
  return `<!doctype html>
<html lang="zh-CN"><head><meta charset="utf-8">
<title>${title}</title>
<meta http-equiv="Content-Security-Policy" content="default-src 'self' 'unsafe-inline' 'unsafe-eval' data: blob:">
${patch}
<style>html,body{margin:0;height:100%;background:#111}iframe{width:100%;height:100%;border:0;display:block}</style>
</head><body>
<iframe id="sim" src="./simulator/#${hash}" allow="fullscreen"></iframe>
</body></html>`;
}
