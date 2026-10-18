# rebrand-qizhi-report.md — 启智AGENT 前端品牌重构（第一版）

范围：只改 Web 前端的品牌层、首屏表现层与静态资源。后端、Agent Loop、工具系统、会话与模型调用链一律未动，并有清单证明。基线：`master` @ `687f282e8625c6b8d11ff58211a90524be2e4317`（`dsh-v0.2.1-rc.2`）。

## 1. 品牌注入点清单（先审查后动手的结果）

官方结构比预想的更配合：品牌不是散落的字符串，而是三个**通用槽位** + 几处 locale 文案 + 构建期静态资源。

| 注入点 | 文件 | 机制 | 出厂值 |
|---|---|---|---|
| 侧栏标志 | `packages/client/ui-sidebar/src/client/SidebarRoot.tsx:189,225` | `renderSlot('sidebar.brand.mark', {size:24}, {fallback:<FishLogo/>})` | 鲸鱼 `FishLogo` |
| 侧栏名称 | 同上 `:228-233` | `renderSlot('sidebar.brand.name', {}, {fallback: t('brand.localBuild')})` | 「DSH 本地构建」 |
| 官方品牌占用者 | `packages/client/ui-brand-official/src/client/{index.ts,Brand.tsx}` | 挂 `DSH_CLIENT_BUILD_PROFILE === 'official'` 门控 | 官方包 |
| **首屏徽标** | `packages/client/ui-conversation/src/client/skeleton/EmptyHero.tsx:148` | `renderSlot('conversation.hero.brand.mark', {size:34, className}, {fallback:<HeroFish/>})` —— 动画鱼只是**回退** | 34px 动画鱼（SMIL 形变） |
| 首屏文案 | `packages/client/ui-conversation/src/client/locales.ts:77,457`（zh/en 两份） | `hero.headline` / `hero.preview` / `hero.chooseWorkspace` | 探索未至之境 / Into the Unknown |
| 文档标题 | `packages/client/locale/src/locales/{zh,en}.ts` 的 `brand.localBuild`（`ui-layout` 的 `DocumentTitle` 以它为 productTitle） + `apps/web/index.html` 的 `<title>` | 两处 | DSH 本地构建 / DSH Local Build |
| 图标资源 | `apps/web/public/favicon.svg`、`favicon-dark.svg`（`index.html` 按 prefers-color-scheme 二选一） | 静态文件 | 鲸鱼路径 |
| PWA 名称 | `apps/web/public/manifest.webmanifest` | `name` / `short_name` | DeepSeek Harness / DSH |
| loading / splash | **无独立文件**：`apps/web/index.html` 只有一个 `<div id="root">` 空壳，加载期表现由客户端骨架渲染 | — | 因此「换 loading 页」这一项没有可改的载体；首屏骨架随首屏徽标一起换掉了 |
| 组合装配 | `packages/bundle/web-app/cordis.patch.yml:336-337` + `web-app/package.json` 依赖行 | 品牌包挂载点 | 挂 `ui-brand-official` |

## 2. 采用的改法：新增品牌包占槽位，不做字符串海搜

新增 `packages/client/ui-brand-qizhi`（官方 README 明说「使用其他品牌的部署应提供替代品牌包」），一次注册**三个**槽位：

```ts
ctx.slots.register({ name: 'sidebar.brand.mark' }, QizhiBrandMark)
ctx.slots.register({ name: 'sidebar.brand.name' }, QizhiBrandName)
ctx.slots.register({ name: 'conversation.hero.brand.mark' }, QizhiHeroEmblem)
```

官方包**故意不注册**首屏槽位（把动画鱼留作回退），本包注册它，于是鲸鱼在 UI 上彻底消失。注册是 effect，卸载本包即把三个槽位交回外壳回退。`ui-brand-official` 仍安装但不挂载，保留官方构建路径。

槽位之外够不着的文案，按就近原则就地改：`hero.headline`、新增 `hero.subheading`、`brand.localBuild`、`index.html` 标题、两个 favicon、manifest。首屏主视觉的字级样式（28–44px 渐变标题 + 副标题行）加在 `HeroShell.module.css` 末尾，并在 `EmptyHero.tsx` 里挂 `heroTitle` / `subtitle` 两个 class —— 只加表现层节点，不碰会话逻辑。

### 修改文件清单（全部 15 项 + 8 个新文件）

修改：`apps/web/index.html`、`apps/web/public/{favicon.svg,favicon-dark.svg,manifest.webmanifest}`、`packages/bundle/web-app/{cordis.patch.yml,package.json}`、`packages/client/locale/src/locales/{zh,en}.ts`、`packages/client/ui-conversation/src/client/{locales.ts,skeleton/EmptyHero.tsx,skeleton/HeroShell.module.css}`、`packages/client/ui-conversation/tests/skeleton.client.spec.tsx`、`tsconfig.client.json`、`pnpm-lock.yaml`。

新增：`packages/client/ui-brand-qizhi/` 下 `package.json`、`tsconfig.json`、`tsdown.config.ts`、`src/index.ts`、`src/css-modules.d.ts`、`src/client/{index.ts,Brand.tsx,ParticleField.tsx,brand.module.css}`、`README.md`、`README.zh.md`。

可复现补丁：[`rebrand-qizhi.patch`](rebrand-qizhi.patch)（49,436 字节，`git apply` 可重放；上游克隆目录被 ICT 的 `.gitignore` 排除，故以补丁形式留档）。

## 3. 设计说明

- **定位**：未来感 / 深色高端 / 智能体工作台。第一版有意只动品牌面与首屏，主题统一（强调色、面板材质、会话区细节、侧栏）留给第二版，避免把视觉重构做成框架重写。
- **标志**：六边形「智能核心」+ 四芒星「点火」+ 三个顶点电路节点；单一 `currentColor`，24px 折叠栏与首屏大尺寸都清晰；favicon 另出一版深色渐变（`#38e1ff → #7c5cff → #4ef0b0`）与一版浅色墨蓝。
- **名称**：`启智` 走三色渐变文字（`background-clip: text`），`AGENT` 用 0.14em 大字距；是文本不是图片，可选中、可本地化、继承界面字体。
- **首屏**：主标题 `启智AGENT` 实测渲染 `font-size: 28px / font-weight: 700 / background-clip: text`（`clamp(28px, 4.4vw, 44px)` 自适应），下方副标题「面向复杂任务的多工具智能体工作台」；徽标带 26s 一圈的虚线轨道环与 drop-shadow 辉光。
- **粒子实现**：**零第三方依赖**，单张 Canvas 2D，portal 到 `document.body`。节点数按面积取 `w*h/26000` 并夹在 24–90，DPR 封顶 2，速度 11px/s，132px 内连线、alpha 随距离衰减。`prefers-reduced-motion` 只画一帧静态，`document.hidden` 停 `requestAnimationFrame`，卸载时移除 resize/visibility/media 三个监听。`pointer-events: none` + `mix-blend-mode: screen`（深色底只加光、不糊字），故不可能截获点击。选 Canvas 而不引 tsParticles：一个欢迎页不值得新增依赖，且 `pnpm-workspace.yaml` 的 `allowBuilds` 默认拒绝第三方构建脚本。

## 4. 构建与运行验证（全部实测）

| 项 | 结果 |
|---|---|
| `pnpm install`（新增 workspace 包） | `INSTALL_EXIT=0` |
| `pnpm run build` | 通过：`host compiler`、`Host bundle`、`Desktop bundle`、`client compiler`、`Client bundle`、`Web build`、`host aggregate check` 全 PASS；前一轮 4 次失败原因逐一定位（未登记进 Client 聚合 → `TS6306 composite` → 严格模式索引/可空 → 槽位 props 型别），最终 0 错误 |
| Web UI 启动 | `dsh --profile web --no-open` 正常监听 127.0.0.1:3080，日志 `_logs/16_qizhi_web.log` |
| 品牌替换（浏览器实测） | `document.title = "跨工作区文件创建测试 — 启智AGENT"`；侧栏新标志 SVG 已挂载；首屏含「启智AGENT」与副标题；`/DeepSeek/` 全文匹配 **false**；旧标题「探索未至之境」false |
| 功能未回归 | composer `contenteditable=true` 存在；新建会话 / 添加工作区 / 选择工作区 / 访问模式 / 选择模型 / 账号菜单(设置入口) 全部在位 |
| 前端单测 | `vitest run` ui-conversation skeleton + ui-brand-official：**33 passed / 0 failed**（含我按行为同步更新的 3 处首屏文案断言） |
| 后端零改动 | `git status --porcelain` 15 项中，落在 `apps/cli`、`packages/{core,api,host,session,llm,tools,shell,subprocess,sandbox,mcp}` 的条目数 **0** |
| 越权改动 | 未改任何服务端接口、审批逻辑、工具注册、会话状态与模型调用代码 |

## 5. 前后对比

| 位置 | 改前 | 改后 |
|---|---|---|
| 浏览器标签页 | DSH 本地构建 / DSH Local Build | 启智AGENT（会话开启后为「会话标题 — 启智AGENT」） |
| 侧栏标志 | 官方鲸鱼 `FishLogo` | 六边形核心 + 四芒星 + 电路节点 |
| 侧栏名称 | 本地构建标签 | 启智（渐变）+ AGENT（大字距） |
| 空会话首屏 | 34px 动画鱼 +「探索未至之境」 | 辉光核心 + 轨道环 + 28–44px 渐变「启智AGENT」+ 副标题行 + 全屏粒子层 |
| 标签页图标 | 鲸鱼 SVG | 两套启智标志（浅色墨蓝 / 深色渐变） |
| PWA 名称 | DeepSeek Harness / DSH | 启智AGENT / 启智AGENT |
| 模型名 | 不变（`deepseek-flash` 仍是**模型**名，属事实而非品牌壳） | 同左 |

## 6. 未做与后续建议（需要更大范围或上游配合的，本轮不动）

1. **主题统一**：强调色、毛玻璃面板、侧栏与会话区细节仍为出厂值。
2. **首屏文案仍非槽位**：`hero.headline` 等是 `ui-conversation` 的 locale 键，品牌包够不着，只能就地改。若上游开一个首屏文案槽位，本包可完全接管。
3. **登录/账号与设置页里的 DeepSeek 字样**未清理（如 Settings → 模型 的「DeepSeek」卡片、「上传 Session Log 以改进 DeepSeek 模型」说明）。它们描述的是**真实模型供应商**，抹掉会让界面与后端事实不符，故保留；如要严格去品牌，需要单独决策。
4. **`pnpm run check:all` 类文档/包元数据门未跑**（`verify-package-meta`、`publint`、`verify-client-packages` 等可能对新包有清单要求）。构建与前端测试为证，全仓门禁留待下一轮；上游 `verify-*` 若要求登记新包，按其提示补一行即可。
5. **粒子的像素证据缺一项**：本机内置浏览器视口恒为 `0×0`（`innerWidth/innerHeight = 0`），因此 canvas 尺寸算得 0×0、看不到漂浮粒子。已证明的是：层确实挂载、尺寸与视口绑定、`pointer-events: none`、混合模式与透明度正确。真实浏览器里 `innerWidth > 0` 即播种 24–90 个节点。
