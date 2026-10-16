import { createRequire } from "node:module";
import { existsSync } from "node:fs";
import { dirname, join, resolve } from "node:path";
import { fileURLToPath } from "node:url";

// 工作区根靠向上找，不手数 ../。
// 本会话已在 parents 层数上错过四次（preview 的 UPSTREAM_DIR、探针 DIST、测试 DIST、
// python 侧 CATALOG），每次症状都是"路径指向一个不存在的位置"，排查代价高。
const moduleDir = dirname(fileURLToPath(import.meta.url));

function findRoot(start: string): string {
  let dir = resolve(start);
  for (let i = 0; i < 14; i++) {
    if (existsSync(join(dir, "source", "upstream", "ray-optics", "package.json"))) return dir;
    const up = resolve(dir, "..");
    if (up === dir) break;
    dir = up;
  }
  throw new Error(
    "WORKSPACE_ROOT_NOT_FOUND: 从 " + start + " 上溯未找到 source/upstream/ray-optics/package.json"
  );
}

export const WORKSPACE_ROOT = findRoot(moduleDir);
export const UPSTREAM_DIR = join(WORKSPACE_ROOT, "source", "upstream", "ray-optics");
export const UPSTREAM_DIST = join(UPSTREAM_DIR, "dist");
export const UPSTREAM_NODE_BUNDLE = join(UPSTREAM_DIR, "dist-node", "rayOptics.js");
export const CATALOG_DIR = join(WORKSPACE_ROOT, "code", "eduforge", "catalog");
export const OUTPUT_DIR = join(WORKSPACE_ROOT, "output", "eduforge");

const upstreamRequire = createRequire(join(UPSTREAM_DIR, "package.json"));

/** 复用上游那份 json-url：npm 上的 json-url@3.1.0 未声明 @babel/runtime 依赖，自己装会挂。 */
export function lzmaCodec(): { compress(v: unknown): Promise<string>; decompress(s: string): Promise<any> } {
  return upstreamRequire("json-url")("lzma");
}

export async function decodeShareUrl(url: string): Promise<any | null> {
  const hash = url.split("#")[1];
  if (!hash) return null;
  return await lzmaCodec().decompress(hash);
}
