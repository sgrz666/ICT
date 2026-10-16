# upstream — 上游源码区

EduForge「复用成熟实验环境」的原料库。原则：**上游原样克隆、定点锁定；适配全部写在 EduForge 一侧**（`code/eduforge/services/engine-host/src/adapters/`），不改上游一行。

## 内容

- `upstream.lock.json` — **本目录唯一的自有文件**，上游的权威记录。每条记录要么是上游文件里读到的，要么是本机真实跑过的输出；未跑的一律标 `pending`，不写成已完成。当前三条：
  - `ray-optics`（**已接通，首批唯一**）：Ray Optics Simulation 5.5.0，Apache-2.0，master @ `daf76772`（与 `git ls-remote` 一致），浅克隆 20M / 1080 文件。含安装（901 包 / 56 s / 324M）、构建（`dist-node/rayOptics.js` 1,715,044 字节；静态完整构建产物含全量 81 个案例场景 JSON 与 770 个多语言页面）、无头调用方式、序列化与对象身份实测、已知坑（optionalDependencies 静默失败、webpack 构建必须在目录内跑、`updateSimulation` 必须显式调、浅克隆 buildPages 需要退化静态贡献者兜底等）。
  - `myphysicslab`、`circuitjs1`：**deferred**，本轮不进首批，只保留目录位与 `engine_id` 取值；理由（三套构建链同时接是主要进度风险 / Java-GWT 工具链与 Docker 未就绪）记在 lock 文件内。
- `ray-optics/` — 上游仓库本体（`git clone --depth 1`）。**它自带的 README.md 及各级文档是上游资产，保持原样，不要覆盖**；项目侧对本引擎的说明在 `code/eduforge/catalog/engines/ray-optics.yaml`。该检出不纳入 git 版本控制（628M、自带 `.git` 与 node_modules），需要时按 lock 记录的 commit 重新克隆。

## 消费方

- `code/eduforge/services/engine-host`：适配器 `require` 上游 `dist-node/rayOptics.js` 做无头仿真；预览服务与浏览器网关托管完整 `dist/`（提供 `/simulator/`、`/gallery/`、`/cn/` 等原版路由）；离线导出复刻上游 dist。
- `code/eduforge/apps/teacher-web`：在「⚡ 光学仿真模拟器」和「📚 81 演示案例库」中直接集成并消费上游原生场景与模拟器。
- `code/eduforge/tools/`：探针脚本（`EDUFORGE_RAYOPTICS` 环境变量可指到别处的上游检出）。

## 纪律

- 升级上游 = 重新克隆 + 更新 lock 文件的 commit 与实测记录，**不**在旧检出上打补丁。
- lock 文件里的「实测」条目必须可复现；写新条目时把命令和输出一起记。
