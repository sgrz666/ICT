import { createServer } from "node:http";
import { mkdtempSync, writeFileSync } from "node:fs";
import { tmpdir } from "node:os";
import { join } from "node:path";

import { afterAll, beforeAll, describe, expect, it } from "vitest";

import { assertLoopback, createGateway } from "../../src/gateway/server.js";
import { createPreviewRoutes } from "../../src/preview/server.js";
import { loadTemplateScene } from "../../src/adapters/ray-optics/adapter.js";

// 网关的全部意义在于"浏览器只面对一个源"，所以这里逐条验它的路由归属：
// /api 归 Python、应用文件归构建产物、其余归预览。混一条就等于把桥接的同源边界让掉。

let appDir: string;
let stub: ReturnType<typeof createServer>;
let stubPort = 0;
let gateway: ReturnType<typeof createGateway>;
let base = "";

beforeAll(async () => {
  appDir = mkdtempSync(join(tmpdir(), "eduforge-app-"));
  writeFileSync(join(appDir, "index.html"), "<!doctype html><title>EduForge 教师端</title><div id=root></div>");
  writeFileSync(join(appDir, "assets.js"), "export const x = 1;");
  writeFileSync(join(appDir, "secret-outside.txt"), "must-not-serve");

  stub = createServer((req, res) => {
    const chunks: Buffer[] = [];
    req.on("data", c => chunks.push(c as Buffer));
    req.on("end", () => {
      res.writeHead(200, { "content-type": "application/json", "x-stub": "yes" });
      res.end(JSON.stringify({
        method: req.method, url: req.url, body: Buffer.concat(chunks).toString("utf8"),
        idempotency: req.headers["idempotency-key"] ?? null,
      }));
    });
  });
  stubPort = await new Promise<number>(r => stub.listen(0, "127.0.0.1", () => {
    const a = stub.address();
    r(typeof a === "object" && a ? a.port : 0);
  }));

  gateway = createGateway({
    preview: createPreviewRoutes().handler,
    appDir,
    apiBase: `http://127.0.0.1:${stubPort}`,
  });
  const port = await new Promise<number>(r => gateway.listen(0, "127.0.0.1", () => {
    const a = gateway.address();
    r(typeof a === "object" && a ? a.port : 0);
  }));
  base = `http://127.0.0.1:${port}`;
});

afterAll(() => {
  gateway?.close();
  stub?.close();
});

describe("浏览器网关", () => {
  it("根路径与构建产物由应用目录服务", async () => {
    const root = await fetch(`${base}/`);
    expect(root.status).toBe(200);
    // 必须是 text/html：按请求路径而不是按命中文件取类型时，"/" 会被判成
    // application/octet-stream，浏览器直接把首页当附件下载（e2e 第一跑就是这样）
    expect(root.headers.get("content-type")).toContain("text/html");
    expect(await root.text()).toContain("EduForge 教师端");

    const asset = await fetch(`${base}/assets.js`);
    expect(asset.status).toBe(200);
    expect(asset.headers.get("content-type")).toContain("text/javascript");
  });

  it("应用目录之外的路径不会被当作静态文件读出来", async () => {
    // 归预览处理，最终 404；关键是绝不能把 appDir 外的字节交付出去
    const res = await fetch(`${base}/../${appDir.split(/[\\/]/).pop()}/secret-outside.txt`);
    expect([200, 403, 404]).toContain(res.status);
    if (res.status === 200) expect(await res.text()).not.toContain("must-not-serve");
  });

  it("/api 反代保留方法、路径、查询、请求体与自定义头", async () => {
    const res = await fetch(`${base}/api/v1/jobs?x=1`, {
      method: "POST",
      headers: { "content-type": "application/json", "Idempotency-Key": "abc-123" },
      body: JSON.stringify({ prompt: "把焦距改成 15 厘米" }),
    });
    expect(res.status).toBe(200);
    expect(res.headers.get("x-stub")).toBe("yes");
    const got = (await res.json()) as Record<string, string | null>;
    expect(got.method).toBe("POST");
    expect(got.url).toBe("/api/v1/jobs?x=1");
    expect(got.idempotency).toBe("abc-123");
    expect(JSON.parse(String(got.body))).toEqual({ prompt: "把焦距改成 15 厘米" });
  });

  it("其余路径交给预览处理，注册场景后 /p 能出包装页", async () => {
    const reg = await fetch(`${base}/scene`, {
      method: "POST",
      headers: { "content-type": "application/json" },
      body: JSON.stringify(loadTemplateScene()),
    });
    expect(reg.status).toBe(201);
    const { path } = (await reg.json()) as { path: string };
    const page = await fetch(`${base}${path}`);
    expect(page.status).toBe(200);
    const html = await page.text();
    expect(html).toContain('id="sim"');
    expect(html).toContain("eduforge.ready"); // 桥接脚本必须在，否则 PreviewFrame 收不到就绪
  });

  it("API 连不上时明确 502，而不是静默回落到预览", async () => {
    const down = createGateway({
      preview: createPreviewRoutes().handler,
      appDir,
      apiBase: "http://127.0.0.1:1", // 不可能有监听
    });
    const port = await new Promise<number>(r => down.listen(0, "127.0.0.1", () => {
      const a = down.address();
      r(typeof a === "object" && a ? a.port : 0);
    }));
    const res = await fetch(`http://127.0.0.1:${port}/api/v1/templates`);
    expect(res.status).toBe(502);
    expect(((await res.json()) as { code: string }).code).toBe("API_UNREACHABLE");
    down.close();
  });

  it("未配置 API 时返回 501，不假装成功", async () => {
    const bare = createGateway({ preview: createPreviewRoutes().handler, appDir });
    const port = await new Promise<number>(r => bare.listen(0, "127.0.0.1", () => {
      const a = bare.address();
      r(typeof a === "object" && a ? a.port : 0);
    }));
    const res = await fetch(`http://127.0.0.1:${port}/api/v1/templates`);
    expect(res.status).toBe(501);
    expect(((await res.json()) as { code: string }).code).toBe("API_NOT_CONFIGURED");
    // 没配 API 也不影响预览可用
    expect((await fetch(`http://127.0.0.1:${port}/simulator/`)).status).toBe(200);
    bare.close();
  });

  it("反向代理只允许回环地址，挡掉被当成任意转发器的用法", () => {
    expect(assertLoopback("http://127.0.0.1:8000").hostname).toBe("127.0.0.1");
    expect(() => assertLoopback("http://169.254.169.254")).toThrow(/回环/);
    expect(() => assertLoopback("http://example.com")).toThrow(/回环/);
    expect(() => assertLoopback("file:///etc/passwd")).toThrow(/协议/);
  });
});
