import { tmpdir } from "node:os";
import { dirname, resolve, sep } from "node:path";
import { existsSync, realpathSync } from "node:fs";
import { fileURLToPath } from "node:url";

const here = dirname(fileURLToPath(import.meta.url));
// src/security -> engine-host -> services -> eduforge -> 工作区根，共 5 层
const WORKSPACE_ROOT = resolve(here, "../../../../../..");

export class PathTraversalError extends Error {
  constructor(message: string) {
    super(message);
    this.name = "PathTraversalError";
  }
}

/**
 * 获取允许写入与读取的沙箱根目录列表。
 * 默认包括：EDUFORGE_ARTIFACT_DIR, output/eduforge/candidates, 系统临时目录 tmpdir()。
 */
export function getAllowedRoots(): string[] {
  const roots: string[] = [];

  if (process.env.EDUFORGE_ARTIFACT_DIR) {
    roots.push(resolve(process.env.EDUFORGE_ARTIFACT_DIR));
  } else {
    roots.push(resolve(WORKSPACE_ROOT, "output/eduforge/artifacts"));
  }

  roots.push(resolve(WORKSPACE_ROOT, "output/eduforge/candidates"));
  roots.push(resolve(tmpdir()));

  if (process.env.EDUFORGE_ALLOWED_ROOTS) {
    for (const r of process.env.EDUFORGE_ALLOWED_ROOTS.split(/[;,]/)) {
      if (r.trim()) roots.push(resolve(r.trim()));
    }
  }

  return roots;
}

/**
 * 校验路径是否位于允许的沙箱目录内，防止路径逃逸（..、绝对路径跳出、符号链接逃逸）。
 */
export function assertWithinSandbox(targetPath: string, allowedRoots = getAllowedRoots()): string {
  if (typeof targetPath !== "string" || !targetPath.trim()) {
    throw new PathTraversalError("PATH_TRAVERSAL_REJECTED: Path must be a non-empty string");
  }

  if (targetPath.includes("\0")) {
    throw new PathTraversalError("PATH_TRAVERSAL_REJECTED: Path must not contain null bytes");
  }

  const normalized = resolve(targetPath);

  const inAllowedRoot = allowedRoots.some(root => {
    const resolvedRoot = resolve(root);
    if (normalized === resolvedRoot || normalized.startsWith(resolvedRoot + sep)) {
      if (existsSync(normalized)) {
        try {
          const realTarget = realpathSync(normalized);
          const realRoot = existsSync(resolvedRoot) ? realpathSync(resolvedRoot) : resolvedRoot;
          return realTarget === realRoot || realTarget.startsWith(realRoot + sep);
        } catch {
          return false;
        }
      }
      return true;
    }
    return false;
  });

  if (!inAllowedRoot) {
    throw new PathTraversalError(
      `PATH_TRAVERSAL_REJECTED: Path "${targetPath}" resolves to "${normalized}" which is outside allowed roots: [${allowedRoots.join(", ")}]`
    );
  }

  return normalized;
}
