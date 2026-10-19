# source — 上游源码、实验组件与资源目录

EduForge 的思路是「复用成熟实验环境」，所以把上游开源引擎的源码请进工作区，**原样保留、定点锁定**，适配代码全部写在 [`../code/eduforge`](../code/eduforge/README.md) 一侧，不改上游一行。2026-10-19 这一轮把资源库要装的东西补齐：引擎源码、npm 组件、以及一层让 Agent 能直接消费的实验目录。

## 内容

- [`upstream/`](upstream/README.md) — 上游源码区。自有文件是 `upstream.lock.json`（身份与构建结论的唯一权威）、五个安装/度量脚本（`fetch_upstreams.sh`、`fetch_phet_sims.py`、`fetch_large.sh`、本轮新增 `fetch_osp_family.sh`、`3jcn/fetch_3jcn_index.py`）、脚本生成的 `inventory.json`，以及 **16 个**引擎/资源目录（原有 `ray-optics/`、`myphysicslab/`、`circuitjs1/`、`matter-js/`、`rapier-js/`、`three/`、`stellarium-web-engine/`、`webots/`、`phet/{libs,sims}/`，本轮新增 OSP 家族 `osp/`、`osp_ejs/`、`webejs/`、`resources/`、`STP/`、`csm/` 与 `3jcn/` 目录镜像）。
- [`components/`](components/README.md) — npm 组件区：`three@0.186.1`、`@dimforge/rapier3d@0.21.0`、`@dimforge/rapier3d-compat@0.21.0`、`matter-js@0.20.0` 钉版本安装，附可加载性实测脚本与结果。这类库的 wasm/编译产物只随 npm 发布，克隆仓库拿不到。
- [`library/`](library/README.md) — 实验资源目录：`experiments.json` 把 18 个实验（P0 9 / P1 7 / P2 2）映射到具体引擎、种子文件、Agent 可改参数与独立验收公式；`check_catalog.py` 负责证明里面每条路径在磁盘上真实存在（2026-10-19 本轮实测 `paths checked: 65 | missing: 0`）。

## 安装实况（2026-10-19）

- 已安装单元 **44 个**，工作区文件 **25,583** 个、**2,015,455 KB**（不含 `.git`，按 `upstream/inventory.json` 2026-10-19 13:38 重跑）；`upstream/` 整目录含 `.git` 实测 **4,024,957 KB ≈ 3.8 GB**，其中 Webots 的 `projects/` 稀疏检出占 1,795,644 KB、本轮新增的 OSP 家族 6 仓占 1,057,753 KB（`du -sk` 含 `.git`；工作区净体积 585,428 KB）。上一轮记的 38 / 18,473 / 1,281,191 是 CircuitJS1 构建产物落盘前的数，已被本轮重跑取代。
- 已经拿到「引擎自己算出来的读数」的有 17 条：无头 14 条（光学 5 条（平面镜 200.5 vs 解析 200、折射 449.5 vs 450、临界角落在 (40°,42°] 对上 41.81°、凹透镜束宽反解 |f|=100.00000000000037、三棱镜两 n 落点 −165.5/−186.5 vs 自写矢量斯涅尔 −165.815/−186.609，见 `library/optics-hall-evidence.json` 5/5 pass）、单摆（myPhysicsLab 积分器，2.00835 s vs 解析 2.00834 s）、弹簧振子（加速度 −1.1999976 vs −kx/m=−1.2，周期 3.14159 vs 2π√(m/k)=3.14159，能量漂移 0%）、抛体（matter-js，射程 30.2733 vs 30.3046、最高点 10.1746 vs 10.2041、互补角射程比 0.9991，`library/projectile-lab-evidence.json` 5/5 pass）、3D 自由落体（Rapier，15.075 vs 15.095）、3D 带电粒子（Rapier + 脚本每步施加 qv×B，半径 3.3597 vs mv/(|q|B)=3.3333、周期 5.23603 vs 5.23599、螺距 7.8566 vs 7.8540，`library/field3d-lab-evidence.json` 5/5 pass）、理想气体压强（Rapier 箱 + 球间碰撞关闭，压强只从引擎给出的撞墙速度反转算出：基准 p 0.855085 Pa 对有限半径修正式 0.823045 偏 3.893%、三轴各向同性 0.992606、⟨v²⟩ 漂移 0%，质点极限 R=4 mm 对课本式 p=Nm⟨v²⟩/(3L³) 偏 4.894%，玻意耳/阿蒙顿/阿伏伽德罗三条状态律分别 2.08236 / 1.99666 / 2.00013，`library/gas-lab-evidence.json` 6/6 pass）、绳波与波速（驱动上游 myPhysicsLab 的 PDE 模块 `sims/pde/StringSim`，只改它的 tension/density/damping/timeStep：v 3.179644 vs √(T/μ)=3.162278（0.549%）、μ×4 ⇒ 渡越时间比 2.0235、固定端反射峰 +0.063536 → −0.063533、扫频峰值落在 f₁ 且 f₁/1.3f₁ 振幅比 7.635、CFL 0.8282 合规 vs Δt 翻倍 1.6563 炸掉，`library/wave-lab-evidence.json` 5/5 pass）、牛顿摆（上游自带 `NewtonsCradleApp.make` + `ContactSim`/`CollisionAdvance` 的事件式碰撞：末球峰值角/释放角 0.999984、交接后其余球残余 0、二进二出、elasticity 1→0.5 时末球掉到 0.3091 倍，`library/cradle-lab-evidence.json` 5/5 pass）、开普勒定律（Rapier 关重力 + 脚本每步施加平方反比力，GM=4π² 自然单位：圆轨道周期 1.0011167 yr vs 1、两条椭圆 T²/a³ = 0.99860/0.99955、比角动量波动 0.0737%、行星质量 1→50 周期比 0.99999667、Δt 减半误差比 1.976，`library/kepler-lab-evidence.json` 6/6 pass）+ 同源浏览器里读 CircuitJS1 电气量 3 条（欧姆 R=100 ⇒ 50 mA；改 R=470 Ω ⇒ 0.010638297872340425 A，与 5/470 逐位相同；串联分压 1.563+3.438 V、并联 50 / 22.727 mA 与 Req 68.75 Ω、RC 充电 Vc 偏解析 0.39%，见 `library/circuit-lab-evidence.json`）。其余引擎（PhET、Stellarium、Webots、OSP 家族 6 仓）本轮只到「源码落盘」，构建与适配器仍 `pending`。另有两条「跑通但不及格」的实测：Matter 的自由-自由弹性正碰不守恒动能（10 J → 1.21 J），牛顿摆「n 进 n 出」Matter 与 Rapier 都复现不了（`library/collisions-lab-evidence.json` 6/9 pass）。
- CircuitJS1 的 GWT 编译本轮**首次跑通**：`compileGwt`（任务名不是 gwtCompile）58 s，产物 `upstream/circuitjs1/build/gwt/out/circuitjs1` 实测 12.4 MB / 5 个 permutation；复现方式是不碰上游——直接调用 `~/.gradle/wrapper/dists` 里已下载的 gradle-8.14.3 可执行文件（wrapper 钉的 8.7 与 Java 23 不兼容），此前为跑通而改的 `gradle-wrapper.properties` 已 `checkout` 还原。`dist.sh` 仍未通过（脚本自带 md5 校验，实测报 TestManager.java 哈希不符）。⇒ 电学三条 P0/P1 从「源码落盘」前进到「有可部署产物」，且官方 JavaScript 读数接口已实测（见下条）。
- 「无头能出数」还不等于「教师能一句话定制并拿到离线包」——上面这 17 条都还没有模板三件套与适配器接线（当前只有凸透镜那条线有），那是 `code/eduforge` 侧的下一步。
- 本轮把简报里「二、适合补充进来的 2D/3D 仿真平台」的**全部七项**落到磁盘上了：Matter.js、Three+Rapier（npm 组件）、Stellarium Web Engine（源码，无 .wasm，需 Emscripten 构建）、Webots（`projects/` 稀疏检出，本体未装）、OSP@Singapore/EJSS（6 仓 1.0 GB：`osp`、`osp_ejs`、`webejs`、`resources`、`STP`、`csm`）、3JCN（静态站目录镜像 8 页 / 90 链接）。**装齐 ≠ 可控**：OSP 的改参要「改 `.ejs` → osp_ejs 编译 → webejs 运行时加载」，这三步一个都没跑；3JCN 只有清单；Stellarium 与 Webots 没有可运行产物。
- 本机 Java 已装（实测 `java version "23" 2024-09-17`），所以 OSP/STP/csm 这类 Java 工程**不是装了解不开**，编译链在；但本轮一次都没编译，别把这句当已完成。

## 纪律

- 上游目录是「只读参考」：需要修改行为时，在 engine-host 的 adapters 层包一层，不在上游仓库里打补丁。
- 版本与构建事实以 `upstream.lock.json` 为唯一权威；它只记实测（跑过的命令与输出），未跑的一律标 `pending`。
- 新增上游引擎时，先在 lock 文件登记（含 decision/reason），再决定是否克隆。
- **来源没查清就不装；但「查不到」必须是查过的结果，不是猜的结果**。本轮把上一轮的两条「找不到权威来源」全部推翻了：OSP@Singapore/EJSS 的官方组织是 `OpenSourcePhysics`（旧记录只猜了 wejen/osp-tools/compadre-io 三个名字就判不装），3JCN 是可抓的静态站（旧记录判「Java applet 时代不可锁定」）。现在的口径：先打 `api.github.com/orgs/<候选>/repos`、`api.github.com/search/repositories`、站点 HTTP 头，拿到返回再写结论；仍装不成的才进 `library/experiments.json` 的 `not_installed`，并把实测过的命令与返回码一起写清（本轮唯一留下的就是 PhET 官方发布成品：5 种 URL 形态实测 404/TLS 失败）。
- **许可未定 = 只读参考**。`upstream/osp/` 与 `upstream/osp_ejs/` 仓库根实测没有 LICENSE/COPYING 文件，3JCN 站点未声明开源许可，Stellarium 是 AGPL-3.0 ⇒ 这三类都不进任何离线交付包，要用先取得书面授权并登记进 lock。
- **大仓不整仓克隆**。Webots 整仓 4.2 GB、three.js 整仓 1.7 GB，一律用 `--filter=blob:none` + `sparse-checkout` 只取需要的目录，并把「为什么这么装、装了多大」记进 lock 与 `fetch_large.sh`。
- **装了不等于接通**。`library/experiments.json` 的状态词分四层（`template_connected` / `resource_installed` / `component_headless_verified` / `reference_only`），写文档、写汇报时按这四层说，不许把「源码已克隆」表述成「实验已支持 AI 定制」。
