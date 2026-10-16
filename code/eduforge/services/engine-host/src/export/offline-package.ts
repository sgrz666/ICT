import { createHash } from "node:crypto";
import { createRequire } from "node:module";
import { cpSync, existsSync, mkdirSync, readFileSync, rmSync, writeFileSync } from "node:fs";
import { dirname, join, resolve } from "node:path";
import { fileURLToPath } from "node:url";

const here = dirname(fileURLToPath(import.meta.url));
// src/export -> engine-host -> services -> eduforge -> 工作区根，共 4 层
const UPSTREAM = resolve(here, "../../../../../../source/upstream/ray-optics");
const compressor = createRequire(join(UPSTREAM, "package.json"))("json-url")("lzma");

import { buildIndexHtml } from "./html.js";
import { buildManifest } from "./manifest.js";

export type OfflinePackage = { dir: string; indexFile: string; warnings: string[] };

/**
 * 组装离线网页包：整份上游 dist + 把候选场景写进随包首页的 hash。
 *
 * 为什么不是单文件 HTML：上游 i18next 用 HttpBackend 在运行时取
 * `../locales/{lng}/{ns}.json`（src/app/main.js:59-70），index.html 里内联的
 * localeData 只管 Vue 挂载前的欢迎页。所以 file:// 双击打开的形态需要额外的
 * i18n 预注入层，不能靠简单打包得到——要离线可用就得保留"随包静态服务 + 同源相对路径"。
 */
export async function buildOfflinePackage(
  scene: unknown,
  outDir: string,
  options: { title?: string } = {}
): Promise<OfflinePackage> {
  const dist = join(UPSTREAM, "dist");
  if (!existsSync(dist)) {
    throw new Error("UPSTREAM_DIST_MISSING: 先跑 npm run build-app");
  }

  const www = resolve(outDir, "www");
  rmSync(www, { recursive: true, force: true });
  mkdirSync(www, { recursive: true });
  cpSync(dist, www, { recursive: true });

  // 场景同时以文件形式随包发布：manifest 的哈希锁的是这份字节，
  // 校验方不必复刻我们的序列化方式（JSON.stringify 与 json.dumps 分隔符不同，
  // 拿两边字符串互比哈希会得到一个永远对不上的数）。
  const sceneDir = join(www, "scene");
  mkdirSync(sceneDir, { recursive: true });
  const sceneBytes = Buffer.from(JSON.stringify(scene, null, 2) + "\n", "utf8");
  writeFileSync(join(sceneDir, "native.json"), sceneBytes);
  const digest = createHash("sha256").update(sceneBytes).digest("hex");

  const hash = await compressor.compress(scene);
  const indexFile = join(www, "index.html");
  writeFileSync(indexFile, buildIndexHtml(hash, options.title ?? "EduForge 实验"), "utf8");

  const enginePkg = JSON.parse(readFileSync(join(UPSTREAM, "package.json"), "utf8"));
  writeFileSync(
    join(resolve(outDir), "manifest.json"),
    buildManifest({
      engineId: "ray_optics",
      engineVersion: enginePkg.version,
      nativeFormatVersion: (scene as { version?: number }).version ?? null,
      sceneSha256: digest,
      entry: "www/index.html",
      requiresLocalStaticServer: true,
      license: "Apache-2.0 (Ray Optics)",
    }),
    "utf8"
  );

  return { dir: resolve(outDir), indexFile, warnings: [] };
}


