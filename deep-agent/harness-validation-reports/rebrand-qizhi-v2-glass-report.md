# 启智AGENT 前端品牌重构 第二版：毛玻璃页面（v2 glass）

- 日期：2026-10-18
- 目标：`开第二版的,用毛玻璃页面` — 把 v1 明确推迟的「统一主题色 / sidebar 视觉 / 聊天区细节」做成一套毛玻璃（frosted glass）主题层。
- 边界：与 v1 相同，只动表现层。判定方法与白名单见 [`rebrand-qizhi-report.md`](rebrand-qizhi-report.md)，本轮结束后重新实测，结果在第 7 节。
- 代码落点：改动全在被 `.gitignore` 屏蔽的上游克隆里，累计补丁（v1+v2，29 个文件）已重生成于 [`rebrand-qizhi.patch`](rebrand-qizhi.patch)。

## 1. 结论先说

毛玻璃页面已生效并实测：应用画布与侧栏透出氛围底色（`bg-base` α=0.60、`sidebar-fill` α=0.68），品牌强调色在 DOM 里实算为 `#0e9cc0`（浅色）；客户端全量类型检查与打包通过，前端 849 个测试与新增的 5 个主题层测试全绿。

**但第一版做到一半被用户实测否掉了**：页面右半像被擦掉一样糊成一片。根因不是颜色，而是我把 `backdrop-filter` 加在了**自身没有填充的透明容器**上——模糊一个透明容器等于把它范围内的内容搅成一团。修法与教训记在第 7 节，那一节是本轮真正的技术内容。

一个关键改道值得单独说：v2 最初用样式表 + 提高选择器权重（`:root body[…]`）压上游调色板，这条路能走通但与仓库的设计规矩相冲突；后来发现 `ui-theme` 为第三方主题保留了 `ctx.theme.overrideTokens()` 通道，于是**删掉全部 token 型 CSS 覆盖，改走官方通道**，样式表只留 token 表达不了的三件事。这个改道是本轮最重要的工程决定。

## 2. 为什么必须改道：token 生效了，页面仍然不透明

第一版玻璃写完实测，token 确实被覆盖（`--dsw-alias-bg-layer-1` 读到 `rgba(255, 255, 255, .66)`），但截图区域里页面还是纯白。逐元素枚举「谁画了不透明背景」才看清问题：大面积表面根本不消费我覆盖的那批 token。

| 表面 | 实际读取的变量 | v2 之前是否被我覆盖 |
|---|---|---|
| 应用外壳 `_3wGgGG_frame`、会话根 `U1tg7q_root` | `--dsw-alias-bg-base` | 否 |
| 侧栏列（2 处） | `--dsw-specific-sidebar-fill` | 否 |
| 首屏卡片 `nMswsa_card` | `--dsw-specific-input-major` | 否 |

也就是说：不透明的责任集中在 **3 个变量**上，而我覆盖的是一批「听起来像表面」的变量。用 `document.styleSheets` 反查每个不透明元素的匹配规则，才把这 3 个变量找出来——这一步决定了 v2 是否真的是一张毛玻璃页面，而不是加了渐变的白页。

## 3. 官方通道取代选择器权重

`packages/client/ui-theme/README.md` 第 12 行写明：「Third-party themes can register alias-token overrides through `ctx.theme`」。读 `ThemeRuntime.overrideTokens()` 的实现确认后（`packages/client/ui-theme/src/client/index.ts:369`，注释即「stacks partial token layers over the active theme without touching the registry」），`ui-layout/src/client/theme-presenter.ts:87` 把快照里的 token 逐个 `body.style.setProperty(name, value)` 写成行内变量。

于是本轮的分工是：

- `src/client/glass.ts`（新）：`buildGlassTokens(glass)` 产出 `{ light, dark }` 双模式的 alias 层，`applyGlassTheme(ctx)` 在 `ctx.effect` 里注册，卸载即撤层。
- `src/styles/qizhi-theme.css`（重写）：只保留三件 token 表达不了的事——`#root::before` 的固定径向氛围底、文档画布底色、`backdrop-filter`。
- `src/client/index.ts`：`inject` 从 `['slots']` 变为 `['slots', 'theme']`。

行内变量天然高于任何样式表规则，所以 `:root body[…]` 这类权重对抗全部删除；`main.ts` 里 CSS 的导入顺序也不再影响调色板。

实测证据（浅色、`system` 解析出的当前方案）：

```
themeSource        system
inlineDswVars      20        # body 上由呈现器写入的本层变量数
--dsw-alias-bg-base            rgba(255, 255, 255, 0.60)
--dsw-specific-sidebar-fill    rgba(255, 255, 255, 0.68)
--dsw-specific-input-major     rgba(255, 255, 255, 0.74)
--dsw-alias-brand-primary      #0e9cc0
--dsw-alias-border-l4          rgba(124, 92, 255, 0.28)
inlineDswVars      20
```

第 3 节这批数字是**修复前**测的，当时 `blurredCount` 为 6、大面积不透明面板为 0——那正是坏掉的状态。修复后的实测见第 5 节末。

## 4. 三条上游规矩当作硬约束

`docs/web-styling.md` 的 Component rules 里有三条会直接被「主题化」撞坏的规矩，本轮选择遵守而不是绕过：

| 上游规矩 | 原文位置 | 本轮做法 |
|---|---|---|
| 模态遮罩保持半透明暗掩、**不加模糊**，主题把 `--dsw-mask-blur` 定为 `none` | 第 27 行 | 删掉 v2 初版对 `[role=dialog]` 的模糊，遮罩完全不碰 |
| 菜单材质是主题所有的 `--dsw-menu-surface-fill` + `--dsw-menu-backdrop-filter`，「feature and platform CSS must not override either」 | 第 26 行 | 两个变量都不重定义；上游菜单本来已是 `blur(40px) saturate(150%)`，与毛玻璃方向一致，直接沿用 |
| 抬升表面 `border: 0`，靠 `--dsw-elevation-*` 阴影，且 0.5px 描边取自 `--dsw-elevation-stroke-color`；不得把 `border-l*` 描边与抬升阴影叠用 | 第 25 行 | 删掉自制的 `inset 0 0 0 1px` 描边，改为重绑 `border-l4`，让官方描边自然换成品牌细线 |

文字类 token 一个都不覆盖，强调色在浅色方案里降到 `#0e9cc0`（不是发光的 `#38e1ff`）——同一个 cyan 在白底上对比度不足，深浅两套各给了能读的值。

## 5. 用户实测发现的缺陷与修复

### 症状

用户截图：右半页像被橡皮擦过——首屏标题在一条竖直硬边处被切断，边右侧只剩白底和两团淡青/淡紫的糊影。

### 根因

`backdrop-filter` 的语义是「把这个元素**背后**的东西模糊掉」，它不需要元素自己有背景就能生效。我按「哪些表面听起来像面板」挑选择器，于是命中了：

| 选择器 | 命中的元素 | 它自己的填充 | 结果 |
|---|---|---|---|
| `[class*='_panel']` | `ytj8dG_panel` / `panelBody`（右侧面板容器） | `rgba(0,0,0,0)` 透明 | 把整个右半区的会话内容模糊成白雾，硬边就是它自己的盒子边界 |
| `[class*='_composer']` | `U1tg7q_composerSeat` / `composerStack` | 透明 | 会话流在输入区周围被糊（卡片自身不透明，所以被盖住了） |
| `header` | `U1tg7q_header` | 透明 | 同上，无填充却吃模糊 |
| `nav` | `_7p_g4W_panelList`（左栏图标列表，36×84） | 透明 | 同一类错误，只是面积小 |

诊断的关键一步是把「元素有模糊」和「元素有半透明填充」两件事分开量：第一版我只数了 `blurredCount`，6 个听起来很合理，没有一个数字告诉我这 6 个里有 5 个是透明的。

### 修法

两条规则，都写进了代码注释：

1. **模糊只给「自己画半透明填充」的元素。** 最终列表只剩 `[class*='_sidebarCol']`（它取 `--dsw-specific-sidebar-fill`）与 `aside`（当前构建里不存在，作为语义兜底）。
2. **盖在应用内容之上的表面必须接近不透明。** `bg-layer-1/2/3`、`bg-overlay`、`bg-module-platform`、`specific-input-major` 的 α 从 0.58–0.84 提到 0.94–0.97；只有直接坐在氛围底上的画布（`bg-base` 0.60）和侧栏（0.68）保持透。上游把 composer 保持不透明不是保守，是它下面就是滚动文本。

新增 `keeps surfaces that paint over app content near-opaque` 测试把这条不变量钉住（盖内容的 α ≥ 0.94，坐在底上的 α ≤ 0.7），并把「透明容器吃模糊」写进样式表注释，防止下一轮又按名字挑选择器。

### 修复后实测

```
myBlurAppliedTo    ["DIV._3wGgGG_sidebarCol bg=rgba(255,255,255,0.68) 56x665"]   # 唯一一个
nMswsa_card        α=0.97     # 首屏/输入卡片恢复可读
layer1 / input     rgba(...,0.94) / rgba(...,0.97)
base / sidebar     rgba(...,0.60) / rgba(...,0.68)   # 页面玻璃感仍在
heroText           "启智AGENT
预览版"
```

毛玻璃的观感没有丢：整张应用画布仍然透出紫/青/绿三团氛围底，侧栏是真磨砂；变的是内容表面不再互相渗透。

## 6. 能力降级

`buildGlassTokens(glass)` 只有一个入参，`applyGlassTheme` 在激活时算一次：`CSS.supports('backdrop-filter', 'blur(1px)')` 为假，或 `prefers-reduced-transparency: reduce` 命中时，同一批键改用**不填充值**发布。原因是行内 token 高于样式表，`@supports not (backdrop-filter)` 这种样式表兜底根本压不住它——兜底必须在注册前决定，不能写在 CSS 里。

样式表侧仍保留 `@media (prefers-reduced-transparency: reduce)`，关掉氛围底与模糊两层装饰；窄于 720px 时模糊半径降到 12px。

已知不足：能力只在激活时读一次，系统中途切换减少透明度不会自动换成不填充值，刷新才生效。

## 7. 验证

| 检查 | 命令 | 结果 |
|---|---|---|
| 客户端类型检查 + 全部 client 产物 | `corepack pnpm run build:lib:client` | RC=0（`tsc -b tsconfig.client.json` 含新包与新 spec） |
| Web 前端构建 | `corepack pnpm run build:web` | `✓ built in 5.90s`，RC=0 |
| 受影响包既有测试 | `corepack pnpm exec vitest run packages/client/ui-conversation packages/client/locale` | 56 文件 / 849 测试全绿，日志 `_logs/vitest-v2.log` |
| 新增主题层测试 | `corepack pnpm exec vitest run packages/client/ui-brand-qizhi` | 5 测试全绿（含第 5 节那条不变量） |
| 修复后实机 DOM | 浏览器探针（第 5 节末数字） | 全页只有侧栏一元素带我的模糊；内容表面 α≥0.94；画布与侧栏仍透 |
| 上游改动边界 | `git -C deepseek-harness status --porcelain` | 16 个 tracked 修改 + 1 个新目录，全部落在第 4.3 节白名单内；`apps/cli`、`packages/{core,api,host,session,llm,tools,shell,subprocess,sandbox,mcp}` 零改动 |
| 实机 DOM | 浏览器探针（第 3 节数字） | 不透明面板 6→0，模糊表面 6 个，`启智` 文案在位，残留 DeepSeek 文本仅模型名 `DeepSeek-V4-Pro` |

第一次跑 vitest 时有 1 个测试失败，但我当时把输出接了 `tail -18`，失败详情被截掉；完整重跑同一命令得到 849 全绿（并行负载下的偶发抖动，非本轮改动导致），日志留的是这次完整重跑。

## 8. 本轮改了什么（文件级）

| 文件 | 变化 |
|---|---|
| `packages/client/ui-brand-qizhi/src/client/glass.ts` | 新增：alias token 层与能力开关 |
| `packages/client/ui-brand-qizhi/src/styles/qizhi-theme.css` | 重写：删掉全部 token 覆盖，只留氛围底、画布色、模糊与降级 |
| `packages/client/ui-brand-qizhi/src/client/index.ts` | `inject` 加 `theme`，`apply` 里先注册玻璃层 |
| `packages/client/ui-brand-qizhi/tsconfig.json` | 加 `../ui-theme/tsconfig.client.json` 引用（拆面包必须指向具名 leaf） |
| `packages/client/ui-brand-qizhi/package.json` | `devDependencies` 加 ui-theme（纯类型边）、`dsh.client.inject` 加对应信息边 |
| `packages/client/ui-brand-qizhi/tests/glass.spec.ts` | 新增：双模式完整性、只动表面不动文字、盖内容的表面必须近不透明（第 5 节回归）、无合成能力时转不透明 |
| `packages/client/ui-brand-qizhi/README.md` / `README.zh.md` | 写入通道选择、token 覆盖面、三条上游约束、四条已知限制（原「尚未做主题统一」已失效） |
| `apps/web/src/main.ts` | 保留，但注释与导入位置不再承担调色板胜负 |
| `harness-validation-reports/rebrand-qizhi.patch` | 重生成：24→29 文件，+1083 行，含 v2 全部改动 |

## 9. 诚实的限制

1. **本轮没有任何截图。** Qoder 内置浏览器面板处于隐藏状态（`visible=false`，`visibilityState=hidden`），`take_screenshot` 直接返回 `NATIVE_BROWSER_VIEWPORT_UNAVAILABLE`。所有视觉结论来自 DOM 计算样式与命中规则实测，不是像素比对。用户侧打开面板即可自行核验。
2. **深色路径不是实机证的。** 浏览器把 `system` 解析成浅色，运行中只能观测 light；dark 取值由 `tests/glass.spec.ts` 保证「每个 token 都带两套模式」，呈现器对两套走同一段取值代码。
3. **模糊依赖 CSS module 的局部名后缀。** `backdrop-filter` 没有对应 token，目前锚在 `_sidebarCol` 后缀上；上游改名会让侧栏的磨砂悄悄失效，填充与布局不受影响。
4. **多轮会话下的观感仍未实测。** 修复后的数字来自空会话首屏；长会话里画布 α=0.60 是否会让滚动的正文与氛围底互相干扰，需要下一轮带着真实会话复看。
5. **`prefers-reduced-transparency` 中途切换不重算**（第 6 节）。

## 10. 后续建议（需要后端或上游配合，本轮不做）

- 首屏文案与标题若能通过 slot 暴露，本包就不必就地改 `ui-conversation` 与 `locale` 的字符串。
- `ui-theme` 若能公开「表面模糊半径/饱和度」的语义 token（类似已有的 `--dsw-menu-backdrop-filter`），毛玻璃主题就能 entirely 走 token，样式表里那条 CSS module 后缀选择器可以删掉。
- 仓库里没有任何 `overrideTokens` 的调用者，本包是第一个使用者；若上游想把它作为正式主题生态，值得补一个官方示例与 Settings 里的主题选择。
