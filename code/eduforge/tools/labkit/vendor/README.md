# vendor — 内联引擎副本

**职责**：存放单文件 HTML 需要整体内联的浏览器引擎副本。这里不是 npm 依赖目录，文件随仓库入库，保证离线构建可重放。

## 内容

| 文件 | 来源 | 版本 | 体积 | sha256 |
|---|---|---|---|---|
| [`matter.min.js`](matter.min.js) | `source/components/node_modules/matter-js/build/matter.min.js` | 0.20.0 | 83,476 字节 | `72d30be0f579eb02ce1e0b6f9d359a4f392e6837e5a26ba8be5dbee7f88e24ae` |
| [`LICENSE.matter.txt`](LICENSE.matter.txt) | 同包 `LICENSE` | — | 1,092 字节 | — |

## 为什么放这里

单文件交付要求「双击即开、零网络」，所以引擎不能从 CDN 或 `node_modules` 现取；`render-single-file.mjs` 直接读本目录的文件并整段内联。上游 `node_modules` 不入库，若只从那里读，换机器或清理依赖后产物就不可重放。

## 升级步骤

1. 从 `source/components/node_modules/matter-js` 复制新版本 `build/matter.min.js` 与 `LICENSE`。
2. 更新本表的版本、体积、sha256。
3. 同步 `catalog/templates/mechanics/projectile/recipes.json` 的 `engine.version`。
4. 跑 `node code/eduforge/tools/labkit/selftest.mjs`；三配方必须仍 3/3 pass（matter 升级可能改变离散轨迹，容差不是橡皮筋）。
5. 若体积或 API 变化导致 L3 失败，先查 `frictionAir` 默认值与 `Engine.update` 语义有没有改。

## 纪律

- **不要**在这里放未固定版本的构建产物；每个文件都要有版本与哈希。
- **不要**手工改 `matter.min.js`；需要改行为就换引擎或在上层适配，不改 vendor。
- 内联时渲染器会剥掉横幅里的 URL（保留 MIT 署名），避免产物里出现可被误判为外链的字符串。

## 产物里的引擎溯源（2026-10-20 起）

`render-single-file.mjs` 只剥 **许可横幅之外** 的 URL（横幅里的 `http://brm.io/matter-js/` 保留——那是 MIT
署名义务，且注释里的 URL 不产生请求，L3 数的是运行时请求数）。因此产物内联的字节与本文档记录的
`72d30be0…` **逐字节相同**，不再出现「同一份引擎两个哈希」的假不一致。

同时 `DATA.engine` 里多了三个可机械核对的字段：`vendor_path`、`vendor_sha256`（读进来那份）、
`inlined_sha256`（真正嵌进产物那份）；产物目录还会自动带一份 `README.md`（配方、参数、设计指纹、
引擎哈希、复现命令）和 `LICENSE.matter.txt` 副本，使单个交付 HTML 不依赖仓库上下文也能自证。

> 反例留档：上一版那条 `https?:\/\/\S+ → ''` 的通吃正则让产物内联比 vendor 少 24 字节，
> 拿 sha256 直接对必然判成「不是同一份」；而比 sha 前若不先归一行尾，`vendor` 与
> `source/upstream/matter-js` 那份也会因 5 个 CRLF 差而"不一致"。两个坑都是哈希口径造成的，不是文件不同。
