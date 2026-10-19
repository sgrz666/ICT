// 组件可加载性实测：在 Node 里真装真导入，记录谁能在无浏览器环境下跑起来。
// 跑法：node source/components/probe_components.mjs
import { createRequire } from "node:module";
import fs from "node:fs";
const pkgVersion = (n) => JSON.parse(fs.readFileSync(new URL(`./node_modules/${n}/package.json`, import.meta.url), "utf-8")).version;
const require = createRequire(import.meta.url);

const out = [];
async function t(name, fn) {
  try {
    out.push({ pkg: name, result: "pass", ...(await fn()) });
  } catch (e) {
    out.push({ pkg: name, result: "fail", error: String(e && e.message ? e.message : e).slice(0, 220) });
  }
}

await t("three", async () => {
  const THREE = await import("three");
  const v = new THREE.Vector3(1, 2, 2);
  return { version: THREE.REVISION, probe: "Vector3.length()", value: v.length() };
});

await t("matter-js", async () => {
  const M = require("matter-js");
  const engine = M.Engine.create({ gravity: { x: 0, y: 1 } });
  const body = M.Bodies.circle(0, 0, 20, { mass: 2 });
  M.Composite.add(engine.world, body);
  // Runner 需要 window.requestAnimationFrame，无头验证只能用 Engine.update 逐步推进
  for (let i = 0; i < 60; i++) M.Engine.update(engine, 1000 / 60);
  return { version: pkgVersion("matter-js"), probe: "60 步(1s)后 y", value: Number(body.position.y.toFixed(3)) };
});

await t("@dimforge/rapier3d", async () => {
  const R = await import("@dimforge/rapier3d/rapier.js");
  return { version: pkgVersion("@dimforge/rapier3d"), probe: "ESM 入口能否被 Node 解析", value: Object.keys(R).length + " exports" };
});

await t("@dimforge/rapier3d-compat", async () => {
  const R = (await import("@dimforge/rapier3d-compat")).default;
  await R.init();
  const world = new R.World({ x: 0, y: -9.81, z: 0 });
  const body = R.RigidBodyDesc.dynamic().setTranslation(0, 20, 0);
  const rb = world.createRigidBody(body);
  world.createCollider(R.ColliderDesc.ball(0.5), rb);
  for (let i = 0; i < 60; i++) world.step();
  return {
    version: pkgVersion("@dimforge/rapier3d-compat"),
    probe: "自由落体 1s 后 y（理论 15.1 m）",
    value: Number(rb.translation().y.toFixed(3)),
  };
});

console.log(JSON.stringify(out, null, 2));
