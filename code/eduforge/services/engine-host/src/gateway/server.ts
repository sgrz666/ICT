import {
  createServer,
  request as upstreamRequest,
  type IncomingMessage,
  type Server,
  type ServerResponse,
} from "node:http";
import { existsSync, readFileSync, statSync } from "node:fs";
import { extname, resolve, sep } from "node:path";

import { MIME, type PreviewHandler } from "../preview/server.js";

// 浏览器网关：教师前端 + 上游模拟器 + 业务 API 合成**一个源**。
//
// 为什么必须是同一个源：§5.3 的桥接脚本对入站消息做同源校验
// （`e.origin === location.origin`），这是刻意的安全边界。若把前端放在另一个端口，
// 要么放宽这条校验、要么给 postMessage 开一个 targetOrigin 白名单——两者都比现在弱。
// 所以这里用反向代理把 API 挪到同源的 /api 路径下，桥接协议一个字都不改。
export type GatewayOptions = {
  preview: PreviewHandler;
  /** 教师前端构建产物目录（vite build 的输出）；为空则只服务预览与代理 */
  appDir?: string;
  /** Python 业务 API；只允许回环地址，见 assertLoopback */
  apiBase?: string;
};

const HOP_BY_HOP = new Set([
  "connection", "keep-alive", "proxy-authenticate", "proxy-authorization",
  "te", "trailer", "transfer-encoding", "upgrade",
]);

/** 这个代理只面向本机开发与演示，绝不能变成任意地址转发器（SSRF）。 */
export function assertLoopback(base: string): URL {
  const url = new URL(base);
  const local = ["127.0.0.1", "localhost", "[::1]", "::1"];
  if (!["http:", "https:"].includes(url.protocol)) throw new Error(`不支持的协议：${url.protocol}`);
  if (!local.includes(url.hostname)) throw new Error(`只允许回环 API 地址，拒绝：${url.hostname}`);
  return url;
}

const send = (res: ServerResponse, status: number, type: string, body: string | Buffer) => {
  res.writeHead(status, { "content-type": type, "cache-control": "no-store" });
  res.end(body);
};

function staticFile(appRoot: string, path: string): { body: Buffer; filePath: string } | null {
  const rel = (path === "/" ? "/index.html" : path).replace(/^([/\\])+/, "");
  const target = resolve(appRoot, rel);
  if (target !== appRoot && !target.startsWith(appRoot + sep)) return null; // 越界直接当没有
  if (!existsSync(target) || !statSync(target).isFile()) return null;
  return { body: readFileSync(target), filePath: target };
}

function proxyApi(o: GatewayOptions, req: IncomingMessage, res: ServerResponse, url: URL): Promise<void> {
  return new Promise<void>(finish => {
    if (!o.apiBase) {
      send(res, 501, "application/json", JSON.stringify({ code: "API_NOT_CONFIGURED" }));
      return finish();
    }
    let target: URL;
    try {
      target = assertLoopback(o.apiBase);
    } catch (e) {
      send(res, 403, "application/json", JSON.stringify({ code: "API_BASE_REJECTED", detail: String(e) }));
      return finish();
    }

    const headers: Record<string, string | string[]> = {};
    for (const [k, v] of Object.entries(req.headers)) {
      if (v === undefined || HOP_BY_HOP.has(k.toLowerCase()) || k.toLowerCase() === "host") continue;
      headers[k] = v as string | string[];
    }
    headers["host"] = target.host;

    const up = upstreamRequest(
      {
        protocol: target.protocol,
        hostname: target.hostname,
        port: target.port || (target.protocol === "https:" ? 443 : 80),
        path: `${url.pathname}${url.search}`,
        method: req.method,
        headers,
      },
      upRes => {
        const out: Record<string, string | string[]> = {};
        for (const [k, v] of Object.entries(upRes.headers)) {
          if (v === undefined || HOP_BY_HOP.has(k.toLowerCase())) continue;
          out[k] = v as string | string[];
        }
        res.writeHead(upRes.statusCode ?? 502, out);
        upRes.pipe(res);
        upRes.on("end", () => finish());
        upRes.on("error", () => finish());
      }
    );
    up.on("error", e => {
      send(res, 502, "application/json", JSON.stringify({ code: "API_UNREACHABLE", detail: String(e) }));
      finish();
    });
    req.pipe(up);
  });
}

export function createGateway(o: GatewayOptions): Server {
  const appRoot = o.appDir ? resolve(o.appDir) : "";

  return createServer(async (req: IncomingMessage, res: ServerResponse) => {
    const url = new URL(req.url ?? "/", "http://127.0.0.1");
    const path = decodeURIComponent(url.pathname);

    if (path.startsWith("/api/")) return void (await proxyApi(o, req, res, url));

    if (appRoot && (req.method === "GET" || req.method === "HEAD")) {
      const hit = staticFile(appRoot, path);
      if (hit !== null) {
        // 类型按**实际文件**取，不按请求路径取："/" 命中 index.html 时必须回 text/html，
        // 回成 application/octet-stream 浏览器就当附件下载了（e2e 第一跑就是这么暴露的）。
        return send(res, 200, MIME[extname(hit.filePath).toLowerCase()] ?? "application/octet-stream", hit.body);
      }
    }
    return o.preview(req, res);
  });
}
