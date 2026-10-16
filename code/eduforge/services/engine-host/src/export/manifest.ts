/**
 * 实验发布元数据 (manifest.json) 生成器。
 *
 * 对齐方案 §1.2 和 §5.5。
 */
import { readFileSync } from "node:fs";
import { join } from "node:path";

export interface ManifestOptions {
  engineId: string;
  engineVersion: string;
  nativeFormatVersion: number | null;
  sceneSha256: string;
  entry: string;
  requiresLocalStaticServer?: boolean;
  license?: string;
}

export function buildManifest(options: ManifestOptions): string {
  return JSON.stringify(
    {
      engine_id: options.engineId,
      engine_version: options.engineVersion,
      native_format_version: options.nativeFormatVersion,
      scene_sha256: options.sceneSha256,
      entry: options.entry,
      requires_local_static_server: options.requiresLocalStaticServer ?? false,
      license: options.license ?? "Apache-2.0 (Ray Optics)",
    },
    null,
    2
  );
}
