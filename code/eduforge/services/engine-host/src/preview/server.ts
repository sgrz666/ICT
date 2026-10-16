import { createServer, type IncomingMessage, type Server, type ServerResponse } from "node:http";
import { readFile } from "node:fs/promises";
import { extname, join, normalize, resolve, sep } from "node:path";

// 预览服务：把候选场景用上游自己的分享 URL 机制（json-url lzma + #hash）塞进上游模拟器的
// iframe，渲染完全由上游产生，我们只决定喂进去哪份场景。
//
// 桥接（§5.2/§5.3）不许自己编造场景编辑：改参数走 POST /param，那里复用与 API 同一套
// rayOpticsAdapter —— 上游 loadJSON 不接受就 422，不返回"看起来改了"的结果。
import { lzmaCodec, UPSTREAM_DIST } from "../upstream_paths.js";
import { rayOpticsAdapter, loadBindings, loadTemplateScene } from "../adapters/ray-optics/adapter.js";
import type { SetParameter } from "../contracts.js";
import { BRIDGE_SCRIPT, hostPage } from "./messages.js";

export const MIME: Record<string, string> = {
  ".html": "text/html; charset=utf-8",
  ".js": "text/javascript; charset=utf-8",
  ".mjs": "text/javascript; charset=utf-8",
  ".json": "application/json; charset=utf-8",
  ".css": "text/css; charset=utf-8",
  ".map": "application/json",
  ".png": "image/png",
  ".jpg": "image/jpeg",
  ".jpeg": "image/jpeg",
  ".svg": "image/svg+xml",
  ".gif": "image/gif",
  ".ico": "image/x-icon",
  ".ttf": "font/ttf",
  ".woff": "font/woff",
  ".woff2": "font/woff2",
  ".eot": "application/vnd.ms-fontobject",
  ".webmanifest": "application/manifest+json",
};

export type PreviewServer = {
  server: Server;
  register: (scene: unknown) => Promise<{ id: string; url: (port: number) => string }>;
  close: () => Promise<void>;
  listen: (port?: number) => Promise<number>;
};

function wrapperPage(id: string, hash: string): string {
  return `<!doctype html>
<html lang="zh-CN"><head><meta charset="utf-8"><title>EduForge 预览 ${id}</title>
<style>html,body{margin:0;height:100%;background:#111}iframe{width:100%;height:100%;border:0;display:block}</style>
</head><body data-revision="${id}">
<iframe id="sim" src="/simulator/?rev=${id}#${hash}" allow="fullscreen"></iframe>
<script>
window.__applyParameter = async (entityId, parameter, value) => {
  const res = await fetch("/param", {
    method: "POST",
    headers: { "content-type": "application/json" },
    body: JSON.stringify({ revision: document.body.dataset.revision, entity_id: entityId, parameter, value }),
  });
  const body = await res.json().catch(() => ({}));
  if (!res.ok) throw new Error((body && body.code) || ("HTTP " + res.status));
  return body.src;
};
</script>
<script>${BRIDGE_SCRIPT}</script>
</body></html>`;
}

export type PreviewHandler = (req: IncomingMessage, res: ServerResponse) => void;

/**
 * 预览路由本体，拆成处理器是为了让浏览器网关能把"应用静态 + /api 反代"接在前面，
 * 其余全部原样交给它——桥接的同源校验因此不需要放宽。
 */
export function createPreviewRoutes(distDir: string = UPSTREAM_DIST): {
  handler: PreviewHandler;
  register: (scene: unknown) => string;
} {
  const root = resolve(distDir);
  const scenes = new Map<string, unknown>();
  let seq = 0;

  const send = (res: ServerResponse, status: number, type: string, body: Buffer | string) => {
    res.writeHead(status, { "content-type": type, "cache-control": "no-store" });
    res.end(body);
  };
  const registerScene = (scene: unknown) => {
    const id = `rev-${++seq}`;
    scenes.set(id, scene);
    return id;
  };

  const handler = async (req: IncomingMessage, res: ServerResponse) => {
    const url = new URL(req.url ?? "/", "http://127.0.0.1");
    const path = decodeURIComponent(url.pathname);
    const readBody = async () => {
      const chunks: Buffer[] = [];
      for await (const c of req) chunks.push(c as Buffer);
      return JSON.parse(Buffer.concat(chunks).toString("utf8"));
    };

    try {
      if (req.method === "POST" && path === "/scene") {
        const id = registerScene(await readBody());
        return send(res, 201, "application/json", JSON.stringify({ id, path: `/p/${id}` }));
      }

      // 桥接改参数：复用与业务 API 同一个适配器与上游解释路径
      if (req.method === "POST" && path === "/param") {
        const body = await readBody();
        const base = scenes.get(String(body.revision ?? ""));
        if (!base) return send(res, 404, "application/json", JSON.stringify({ code: "REVISION_NOT_FOUND" }));
        const edit: SetParameter = {
          op: "set_parameter",
          entity_id: String(body.entity_id),
          parameter: String(body.parameter),
          value: Number(body.value),
        };
        let candidate;
        try {
          candidate = rayOpticsAdapter.apply(base as never, edit, loadBindings());
        } catch (e) {
          return send(res, 400, "application/json", JSON.stringify({ code: "REJECTED", detail: String(e) }));
        }
        if (!candidate.validation.ok) {
          return send(res, 422, "application/json", JSON.stringify({ code: "NATIVE_REJECTED", validation: candidate.validation }));
        }
        // 新场景注册成**新的** revision：编辑前的版本必须保持可恢复（§7.5 第 3 条）
        const newId = registerScene(candidate.native);
        const hash = await lzmaCodec().compress(candidate.native);
        // src 带上 rev，桥接才能报出"当前展示的是哪个版本"（§5.3）
        return send(res, 200, "application/json", JSON.stringify({ src: `/simulator/?rev=${newId}#${hash}`, revision: newId }));
      }

      const mWrap = path.match(/^\/p\/([^/]+)$/);
      if (mWrap) {
        const scene = scenes.get(mWrap[1]);
        if (!scene) return send(res, 404, "text/plain", "unknown preview");
        const hash = await lzmaCodec().compress(scene);
        return send(res, 200, "text/html; charset=utf-8", wrapperPage(mWrap[1], hash));
      }

      const mHost = path.match(/^\/host\/([^/]+)$/);
      if (mHost) {
        if (!scenes.has(mHost[1])) return send(res, 404, "text/plain", "unknown host");
        return send(res, 200, "text/html; charset=utf-8", hostPage(`/p/${mHost[1]}`, mHost[1]));
      }

      // 静态资源：只允许 root 内的文件
      let rel = normalize(path === "/" ? "/simulator/index.html" : path).replace(/^([/\\])+/, "");
      if (!extname(rel)) rel = join(rel, "index.html");
      const target = resolve(root, rel);
      if (target !== root && !target.startsWith(root + sep)) {
        return send(res, 403, "text/plain", "forbidden");
      }
      const body = await readFile(target);
      return send(res, 200, MIME[extname(target).toLowerCase()] ?? "application/octet-stream", body);
    } catch (e) {
      return send(res, 404, "text/plain", "not found: " + String((e as Error).message));
    }
  };

  return { handler, register: registerScene };
}

export function createPreviewServer(distDir: string = UPSTREAM_DIST): PreviewServer {
  const routes = createPreviewRoutes(distDir);
  const server = createServer(routes.handler);

  return {
    server,
    register: async (scene: unknown) => {
      const id = routes.register(scene ?? loadTemplateScene());
      return { id, url: (port: number) => `http://127.0.0.1:${port}/p/${id}` };
    },
    listen: (port = 0) =>
      new Promise<number>(resolve_port =>
        server.listen(port, "127.0.0.1", () => {
          const addr = server.address();
          resolve_port(typeof addr === "object" && addr ? addr.port : 0);
        })
      ),
    close: () => new Promise<void>(r => server.close(() => r())),
  };
}
