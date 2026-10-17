import { createServer, type Server } from "node:http";

import { loadBindings, loadTemplateScene, rayOpticsAdapter } from "./adapters/ray-optics/adapter.js";
import { buildOfflinePackage } from "./export/offline-package.js";
import { verifyOfflinePackage } from "./verify/offline-runner.js";
import { createGateway } from "./gateway/server.js";
import { createPreviewRoutes } from "./preview/server.js";
import type { SetParameter } from "./contracts.js";

const json = (res: import("node:http").ServerResponse, status: number, body: unknown) => {
  const text = JSON.stringify(body);
  res.writeHead(status, { "content-type": "application/json; charset=utf-8" });
  res.end(text);
};

async function readBody(req: import("node:http").IncomingMessage): Promise<string> {
  const chunks: Buffer[] = [];
  for await (const c of req) chunks.push(c as Buffer);
  return Buffer.concat(chunks).toString("utf8");
}

// GATE-3 的验收面：apply 之后必须能 validate 且能 sample 出真实读数。
export function createEngineHost(): Server {
  return createServer(async (req, res) => {
    const url = new URL(req.url ?? "/", "http://127.0.0.1");
    try {
      if (req.method === "GET" && url.pathname === "/healthz") {
        return json(res, 200, { ok: true, engine_id: "ray_optics" });
      }

      if (req.method === "GET" && url.pathname === "/adapters/ray_optics/template") {
        return json(res, 200, {
          native: loadTemplateScene(),
          bindings: loadBindings(),
        });
      }

      if (req.method === "GET" && url.pathname === "/adapters/ray_optics/validate") {
        const scene = JSON.parse(await readBody(req));
        return json(res, 200, rayOpticsAdapter.validateNative(scene));
      }

      if (req.method === "POST" && url.pathname === "/adapters/ray_optics/apply") {
        const body = JSON.parse(await readBody(req)) as {
          native: ReturnType<typeof loadTemplateScene>;
          edit?: SetParameter | SetParameter[];
          edits?: SetParameter[];
        };
        const editList = body.edits ?? (Array.isArray(body.edit) ? body.edit : body.edit ? [body.edit] : []);
        const candidate = rayOpticsAdapter.apply(body.native, editList);
        if (!candidate.validation.ok) {
          // 上游拒绝了就返回不可发布，不返回一个"看起来改了"的候选
          return json(res, 422, {
            code: "NATIVE_REJECTED",
            validation: candidate.validation,
          });
        }
        const measurement = await rayOpticsAdapter.sample(candidate);
        return json(res, 200, {
          engine_id: candidate.engine_id,
          base_untouched: JSON.stringify(body.native) === JSON.stringify(candidate.base_native),
          native: candidate.native,
          validation: candidate.validation,
          measurement,
        });
      }

      if (req.method === "POST" && url.pathname === "/export/offline_package") {
        const body = JSON.parse(await readBody(req)) as {
          scene: unknown;
          outDir: string;
          options?: { title?: string };
        };
        const pkg = await buildOfflinePackage(body.scene, body.outDir, body.options);
        return json(res, 200, {
          ok: true,
          dir: pkg.dir,
          index_file: pkg.indexFile,
        });
      }

      // Gate C §C.5：发布前的浏览器实测。不返回"看起来能打开"，只返回逐项判据与总结论。
      if (req.method === "POST" && url.pathname === "/verify/offline_package") {
        const body = JSON.parse(await readBody(req)) as { dir: string; settleMs?: number };
        const result = await verifyOfflinePackage(body.dir, { settleMs: body.settleMs });
        return json(res, result.ok ? 200 : 422, result);
      }

      return json(res, 404, { code: "NOT_FOUND" });
    } catch (e) {
      return json(res, 400, { code: "BAD_REQUEST", detail: String(e) });
    }
  });
}

if (process.env.NODE_ENV !== "test") {
  const port = Number(process.env.ENGINE_HOST_PORT ?? 8010);
  createEngineHost().listen(port, "127.0.0.1", () => {
    console.log(`engine-host listening on 127.0.0.1:${port}`);
  });

  // 浏览器侧只开一个源：教师前端静态 + /api 反代 + 预览与上游模拟器
  const gatewayPort = Number(process.env.ENGINE_GATEWAY_PORT ?? 4174);
  const appDir = process.env.EDUFORGE_TEACHER_WEB_DIST || undefined;
  const apiBase = process.env.EDUFORGE_API_URL || undefined;
  const gateway = createGateway({ preview: createPreviewRoutes().handler, appDir, apiBase });
  gateway.on("error", e => {
    // 网关端口被占不该把引擎宿主也带下去：Python 侧只依赖 8010 那个端口
    console.error(`gateway 起不来（${gatewayPort}）：${String(e)}`);
  });
  gateway.listen(gatewayPort, "127.0.0.1", () => {
    console.log(
      `gateway listening on 127.0.0.1:${gatewayPort} (app=${appDir ?? "无"}, api=${apiBase ?? "无"})`
    );
  });
}
