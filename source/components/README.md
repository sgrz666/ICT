# source/components — 实验组件包（npm 装的，不是克隆的）

职责：放**需要预编译产物才能用**的组件——three 渲染、Rapier 3D 物理、Matter.js 2D 刚体。这类库克隆仓库拿不到可跑的产物（Rapier 仓库实测 0 个 `.wasm`，wasm 只随 npm 包发布），所以走 npm 固定版本安装，和 [`../upstream/`](../upstream/README.md) 的「克隆源码只读参考」是两条互补的路。

## 内容

- `package.json` — 四个依赖钉版本：`three@0.186.1`、`@dimforge/rapier3d@0.21.0`、`@dimforge/rapier3d-compat@0.21.0`、`matter-js@0.20.0`（`private: true`，不进任何 workspace）。
- `package-lock.json` — 解析结果锁定，重装可复现。
- `node_modules/` — 实测 28,955 KB，被 `.gitignore` 挡住，不入库。
- `probe_components.mjs` — 可加载性实测脚本，在 Node 里真装真导入真算物理量。
- `component-probe.json` — 上面那次运行的落盘结果（2026-10-19）。
- `npm-install.log` — 安装现场（`added 3 packages` + 后续补装 compat 一次），日志类文件不入库。

跑一次实测：

```bash
node source/components/probe_components.mjs
```

## 实测结论（2026-10-19，本机 Node v24.18.0）

| 包 | 结果 | 关键数字 |
|---|---|---|
| three 0.186.1 | pass | REVISION 186；`Vector3(1,2,2).length()` = 3，纯数学可在 Node 直接用 |
| matter-js 0.20.0 | pass | `Engine.update` 步进 60 次（1 s）后圆心 y = 421.347 |
| @dimforge/rapier3d 0.21.0 | **fail** | `Cannot find module '.../rapier3d/exports'`：package.json 无 `main`/`exports`，内部用无扩展名 ESM 导入，Node 解析不了 |
| @dimforge/rapier3d-compat 0.21.0 | pass | `init()` 后建 World 步进 60 次，1 kg 球从 y=20 自由落体 1 s 后 **y = 15.075**；独立参考值 20 − 4.905 = **15.095**，偏差 0.020 m |

最后一行是整个资源库目前最强的一条证据：**3D 实验「改参 → 无头运行 → 读数 → 与解析公式对照」这条链在本机已经跑通**，不依赖浏览器。

## 与上下层的关系

- 目录层：被 [`../library/experiments.json`](../library/experiments.json) 以 `npm_component` 字段引用（校验器会把带 `@版本` 后缀的路径截断后再查盘）。
- 源码层：three 与 rapier 的仓库克隆在 `../upstream/three/`、`../upstream/rapier-js/`（第三方树内部不写项目侧 README，口径见 [`../upstream/README.md`](../upstream/README.md)），只读参考；这里装的是能直接 import 的产物。
- 工程层：`code/eduforge` 的 pnpm workspace **不共用**这里的 `node_modules`。真要进工程时按 pnpm 侧重新声明版本，别拿软链或相对路径过来。

## 已知的坑与纪律

1. **3D 物理只认 `-compat`**。裸 `@dimforge/rapier3d` 在 Node 里装得上但 import 不了（已实测），适配器一律走 `@dimforge/rapier3d-compat`；浏览器侧才可以用裸包（由打包器解析无扩展名导入）。
2. **Matter 的 `Runner` 在无头环境不能用**——它要 `window.requestAnimationFrame`（实测报错）。数值验证只能用 `Engine.update(engine, dt)` 手工步进。
3. **Matter 默认重力尺度不是教学单位**：60 步后 y=421.347 这个数本身就说明需要先标定 scale，否则「误差 ≤1%」这种验收条件是空话。模板里必须先写明单位换算。
4. 版本只在 `package.json` 钉一次；`experiments.json` 与 README 引用它，不各自另记。
5. `node_modules/` 不入库（含 three 与 rapier 的许可文本，重装即得）；一旦把某个组件的产物打进离线交付包，要连带把它的 `LICENSE` 复制进去（three = MIT，matter-js = MIT，rapier = Apache-2.0）。
