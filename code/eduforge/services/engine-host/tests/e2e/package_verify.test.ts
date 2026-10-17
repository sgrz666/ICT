import { existsSync, mkdtempSync, readFileSync, rmSync, writeFileSync } from "node:fs";
import { tmpdir } from "node:os";
import { join } from "node:path";

import { afterAll, beforeAll, describe, expect, it } from "vitest";

import { loadTemplateScene, rayOpticsAdapter } from "../../src/adapters/ray-optics/adapter";
import { buildOfflinePackage } from "../../src/export/offline-package";
import { verifyOfflinePackage } from "../../src/verify/offline-runner";

// Gate C §C.5 的判据来源：一份离线包必须由**真浏览器**说"跑得出光"，
// 不能只由"入口文件在盘上"说话。这里同时钉反面——
// 把模拟器的运行时脚本删掉之后必须判不过，否则这条闸门就是个装饰。

const roots: string[] = [];

async function packageOf(focalCm: number): Promise<string> {
  const root = mkdtempSync(join(tmpdir(), "pkg-verify-"));
  roots.push(root);
  const cand = rayOpticsAdapter.apply(loadTemplateScene(), {
    op: "set_parameter",
    entity_id: "lens_1",
    parameter: "focal_length_cm",
    value: focalCm,
  });
  expect(cand.validation.ok).toBe(true);
  const pkg = await buildOfflinePackage(cand.native, join(root, "offline_package"), {
    title: "凸透镜成像 §C.5",
  });
  return pkg.dir;
}

let goodDir = "";

beforeAll(async () => {
  goodDir = await packageOf(15);
}, 240000);

afterAll(() => {
  for (const r of roots) rmSync(r, { recursive: true, force: true });
});

const ids = (r: { checks: { id: string; passed: boolean }[] }) =>
  r.checks.filter(c => !c.passed).map(c => c.id);

describe("离线包浏览器实测（§C.5）", () => {
  it("一份好包：逐项判据全过，光层真的画出了像素", async () => {
    const r = await verifyOfflinePackage(goodDir, { settleMs: 8000 });
    expect(r.checks.map(c => c.id)).toEqual([
      "entry_declared",
      "entry_file_present",
      "scene_loaded",
      "rays_rendered",
      "zero_egress",
      "no_page_errors",
      "screenshot_taken",
    ]);
    expect(ids(r)).toEqual([]);
    expect(r.ok).toBe(true);
    // 「点亮像素」必须是个正数：空白页也可能一切正常地加载完
    expect(String(r.checks.find(c => c.id === "rays_rendered")!.observed)).toMatch(/点亮像素 [1-9]\d*/);
    expect(r.screenshot_sha256).toMatch(/^[0-9a-f]{64}$/);
    expect(r.off_origin).toEqual([]);
    expect(r.errors).toEqual([]);
  }, 240000);

  it("删掉模拟器运行时脚本：必须判不过（这条存在的全部理由）", async () => {
    const broken = await packageOf(15);
    rmSync(join(broken, "www", "simulator", "main.js"), { force: true });
    const r = await verifyOfflinePackage(broken, { settleMs: 6000 });
    expect(r.ok).toBe(false);
    // 页面仍能"打开"，所以失败的必须是场景载入与光层，而不是入口在不在
    expect(ids(r)).toContain("rays_rendered");
    expect(ids(r)).toContain("scene_loaded");
    expect(ids(r)).not.toContain("entry_declared");
  }, 240000);

  it("没有清单的目录：不启动浏览器也直接判不过", async () => {
    const empty = mkdtempSync(join(tmpdir(), "pkg-empty-"));
    roots.push(empty);
    const r = await verifyOfflinePackage(join(empty, "nope"), { settleMs: 1000 });
    expect(r.ok).toBe(false);
    expect(r.checks).toEqual([{ id: "manifest_present", passed: false, observed: expect.any(String) }]);
    expect(existsSync(join(empty, "nope"))).toBe(false);
  }, 60000);

  it("把清单里的 entry 指到不存在的文件：判不过且不开浏览器", async () => {
    const dir = await packageOf(15);
    const manifestPath = join(dir, "manifest.json");
    const raw = JSON.parse(readFileSync(manifestPath, "utf8"));
    raw.entry = "www/nope.html";
    writeFileSync(manifestPath, JSON.stringify(raw));
    const r = await verifyOfflinePackage(dir, { settleMs: 1000 });
    expect(r.ok).toBe(false);
    expect(ids(r)).toEqual(["entry_file_present"]);
  }, 120000);
});
