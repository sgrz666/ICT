import { mkdtempSync, rmSync, writeFileSync } from "node:fs";
import { tmpdir } from "node:os";
import { join } from "node:path";
import { createServer } from "node:http";
import { afterAll, beforeAll, describe, expect, it } from "vitest";

import { assertWithinSandbox, getAllowedRoots, PathTraversalError } from "../../src/security/path-sandbox.js";
import { createEngineHost } from "../../src/main.js";
import { verifyOfflinePackage } from "../../src/verify/offline-runner.js";

const roots: string[] = [];

afterAll(() => {
  for (const r of roots) {
    try {
      rmSync(r, { recursive: true, force: true });
    } catch {}
  }
});

describe("路径沙箱安全（Gate C.0）", () => {
  it("合法路径在允许目录（如 tmpdir）内允许通过", () => {
    const safeDir = mkdtempSync(join(tmpdir(), "safe-pkg-"));
    roots.push(safeDir);
    const resolved = assertWithinSandbox(safeDir);
    expect(resolved).toBeTruthy();
  });

  it("跨目录相对逃逸（..）被坚决拒绝", () => {
    expect(() => {
      assertWithinSandbox(join(tmpdir(), "../../../../etc/passwd"));
    }).toThrow(PathTraversalError);
  });

  it("系统绝对路径逃逸（如 Windows System32 或 UNIX /etc）被坚决拒绝", () => {
    const sysPath = process.platform === "win32" ? "C:\\Windows\\System32" : "/etc/shadow";
    expect(() => {
      assertWithinSandbox(sysPath);
    }).toThrow(PathTraversalError);
  });

  it("包含空字节（null byte）的畸形路径被拦截", () => {
    expect(() => {
      assertWithinSandbox("/tmp/safe\0/evil");
    }).toThrow(PathTraversalError);
  });

  it("空路径或空字符串被拦截", () => {
    expect(() => {
      assertWithinSandbox("   ");
    }).toThrow(PathTraversalError);
  });
});

describe("Engine Host 内部端点防越权与大包防护（Gate C.0）", () => {
  let server: ReturnType<typeof createEngineHost>;
  let baseUrl = "";

  beforeAll(async () => {
    server = createEngineHost();
    await new Promise<void>(resolve => {
      server.listen(0, "127.0.0.1", () => {
        const addr = server.address();
        const port = typeof addr === "object" && addr ? addr.port : 0;
        baseUrl = `http://127.0.0.1:${port}`;
        resolve();
      });
    });
  });

  afterAll(async () => {
    await new Promise<void>(resolve => server.close(() => resolve()));
  });

  it("POST /export/offline_package 越权路径返回 403 FORBIDDEN", async () => {
    const res = await fetch(`${baseUrl}/export/offline_package`, {
      method: "POST",
      headers: { "content-type": "application/json" },
      body: JSON.stringify({
        scene: { objs: [] },
        outDir: process.platform === "win32" ? "C:\\Windows\\Temp\\evil" : "/var/run/evil",
      }),
    });
    expect(res.status).toBe(403);
    const data = await res.json();
    expect(data.code).toBe("FORBIDDEN");
  });

  it("POST /verify/offline_package 越权路径返回 403 FORBIDDEN", async () => {
    const res = await fetch(`${baseUrl}/verify/offline_package`, {
      method: "POST",
      headers: { "content-type": "application/json" },
      body: JSON.stringify({
        dir: process.platform === "win32" ? "C:\\Program Files\\evil" : "/root/evil",
      }),
    });
    expect(res.status).toBe(403);
    const data = await res.json();
    expect(data.code).toBe("FORBIDDEN");
  });

  it("超限 Body 请求返回 413 PAYLOAD_TOO_LARGE", async () => {
    // 超过 10MB 的大包
    const hugeBody = JSON.stringify({ scene: "a".repeat(11 * 1024 * 1024) });
    const res = await fetch(`${baseUrl}/export/offline_package`, {
      method: "POST",
      headers: { "content-type": "application/json" },
      body: hugeBody,
    });
    expect(res.status).toBe(413);
    const data = await res.json();
    expect(data.code).toBe("PAYLOAD_TOO_LARGE");
  });
});

describe("离线包 Manifest entry 安全性检查（Gate C.0）", () => {
  it("清单 entry 越权逃逸出 www/ 目录被拦截，且不开浏览器", async () => {
    const safePkg = mkdtempSync(join(tmpdir(), "pkg-entry-traversal-"));
    roots.push(safePkg);

    // 伪造包含路径逃逸 entry 的 manifest.json
    const manifest = {
      engine_id: "ray_optics",
      entry: "www/../../secret.txt",
      scene_sha256: "dummy",
    };
    writeFileSync(join(safePkg, "manifest.json"), JSON.stringify(manifest), "utf8");

    const result = await verifyOfflinePackage(safePkg, { settleMs: 1000 });
    expect(result.ok).toBe(false);
    const entryCheck = result.checks.find(c => c.id === "entry_declared");
    expect(entryCheck?.passed).toBe(false);
    expect(String(entryCheck?.observed)).toMatch(/越权逃逸/);
  });

  it("清单 entry 为绝对路径时被拦截", async () => {
    const safePkg = mkdtempSync(join(tmpdir(), "pkg-entry-abs-"));
    roots.push(safePkg);

    const absPath = process.platform === "win32" ? "C:\\Windows\\notepad.exe" : "/bin/sh";
    const manifest = {
      engine_id: "ray_optics",
      entry: absPath,
      scene_sha256: "dummy",
    };
    writeFileSync(join(safePkg, "manifest.json"), JSON.stringify(manifest), "utf8");

    const result = await verifyOfflinePackage(safePkg, { settleMs: 1000 });
    expect(result.ok).toBe(false);
    const entryCheck = result.checks.find(c => c.id === "entry_declared");
    expect(entryCheck?.passed).toBe(false);
    expect(String(entryCheck?.observed)).toMatch(/非法 entry/);
  });
});
