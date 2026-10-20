# dsh-labkit — dsh 原生实验构建工具

**职责**：把 [`code/eduforge/tools/labkit`](../../../code/eduforge/tools/labkit/README.md) 的能力注册成 **DeepSeek Harness（dsh）原生工具**，让模型在工具表里直接看到 `experiment_*`，用户说一句「做一个抛体实验」就能触发，不需要先读 skill、也不需要拼命令行。

**位置刻意放在 `deep-agent/local-tools/` 而不是 `deep-agent/deepseek-harness/packages/`**：上游树是 2.7 GB 的验证对象，不入库、不手改；插件通过 profile patch 的相对路径加载，删除目录即可彻底回滚。

## 1. 工具表

| 工具 | 何时用 | 关键入参 | 超时 |
|---|---|---|---|
| `experiment_recipes` | 任何实验请求的第一步：拿配方、默认参数、量程、容差 | `template_id?` | 15 s |
| `experiment_validate` | 想先确认参数/理由是否合规，或要看解析预测 | `recipe_id, params, why_recipe, student_task, expected_numbers?` | 15 s |
| `experiment_simulate` | 只跑 L2 物理对账，不渲染 | 同上 | 60 s |
| `experiment_render` | 只渲染单文件（内部仍跑 L1/L2 以带证据），不做浏览器实测 | 同上 + `out_name?` | 60 s |
| `experiment_verify` | 对已有 HTML 重跑 L3 离线实测 | `html_path, evidence_path` | 120 s |
| `experiment_build` | **标准请求直接用这个**：L1→L2→渲染→L3 一次完成 | `recipe_id, params, why_recipe, student_task, out_name?` | 240 s |

领域失败不抛异常，返回 `{ok:false, stage, code, summary, hints}`；模型可按 `hints` 调整参数或理由后重试（建议最多 3 次）。完整证据落盘在 `output/eduforge/candidates/labkit/<recipe>/`。

系统提示里还注入了一段行为约束（`ctx.systemPrompt.section`）：优先 `experiment_build`；不得自行编写物理公式、手写 HTML 或修改验收容差。

## 2. 安装（不改上游，可回滚）

插件是普通 ESM 文件，**零 npm 依赖**；`defineTool` 从上游已构建的 `packages/core/tools/lib/index.js` 相对导入。

### 2.1 在 profile patch 里插入一行

编辑 `.dsh-home/profiles/web/cordis.patch.yml` 与 `.dsh-home/profiles/headless/cordis.patch.yml`，追加：

```yaml
- insert:
    - id: eduforge-labkit
      name: ../../../local-tools/dsh-labkit/index.mjs
```

`name` 相对 profile 根（`.dsh-home/profiles/<profile>/`）。dsh 的 loader 会把它解析成 `file:///D:/codeplus/ICT/deep-agent/local-tools/dsh-labkit/index.mjs`。

> `.dsh-home/` 是本地运行配置，不入库。换机器或重置 `DSH_HOME` 后要重新加这一段。

### 2.2 重启并自检

profile 是静态组合，改完必须重启 dsh。自检不看 UI 也能做：

```bash
cd D:/codeplus/ICT/deep-agent/deepseek-harness
DSH_HOME=D:/codeplus/ICT/deep-agent/.dsh-home \
  "C:/Program Files/nodejs/node.exe" apps/cli/lib/bin.js --profile headless --dump-config \
  | grep -A 2 eduforge-labkit
# 期望：id: eduforge-labkit / name: file:///…/local-tools/dsh-labkit/index.mjs
```

再跑一次真实会话：

```bash
set -a; . ./.env; set +a
DSH_HOME=… "C:/Program Files/nodejs/node.exe" apps/cli/lib/bin.js \
  --profile headless --json \
  "做一个抛体实验，讲互补角：30 度和 60 度射程相同。要求 HTML 双击就能打开。"
```

实测结果（2026-10-20）：

- 互补角 prompt → 模型先调 `experiment_recipes`，再调一次 `experiment_build`，产出 `output/eduforge/candidates/labkit/complementary/complementary_angles_30_60.html`（113.8 KB，三层验收全过）。
- 斜抛 45° prompt → 同样 2 次工具调用，产出 `output/eduforge/candidates/labkit/oblique45/oblique45-range-max.html`（113.4 KB）。
- 早期版本在 `experiment_build` 之后会额外用 `grep/read` 检查 HTML；在工具摘要与系统提示里写明「页面已嵌入教学内容，构建成功后直接汇报」后，复跑稳定为 **2 次调用**，不再读产物。

### 2.3 回退

删掉两处 patch 行并重启；插件目录可直接删除。若曾用 `dsh plugin add file:` 安装，再执行
`dsh plugin --profile <p> remove @eduforge/dsh-labkit`。

## 3. 安全边界（重要）

- 工具 handler 运行在 dsh **宿主进程**内，直接用 `node:fs`，**绕过** dsh 对模型 shell 的沙箱。这是可信本地工具的取舍：只读 `catalog/templates/**` 与 `tools/labkit/**`，只写 `output/eduforge/candidates/labkit/**`。
- `out_name` 经过 `safeName()`，只留字母数字下划线连字符；渲染器再用 `assertUnder()` 做一次根目录校验。
- L3 启动的 Chromium 是 `offline: true` + 请求拦截；页面本身也有 `default-src 'none'` CSP。
- **不要把本插件装到不可信工作区**：它能读仓库内模板与核心库，并向固定输出目录写文件。

## 4. 版本耦合与已知风险

1. **上游 API 耦合**：`lib/dsh.mjs` 相对导入 `packages/core/tools/lib/index.js`。dsh 升级若改导出，插件启动即报错；当前锚定 `dsh-v0.2.1-rc.2` / commit `687f282e`。启动时有 `typeof defineTool === 'function'` 自检，失败信息会提示先 `pnpm run build`。
2. **patch 相对路径依赖 loader 的 baseUrl**：本机实测可行（`--dump-config` 已解析为 `file://`）；若换 dsh 版本失效，回退到 `dsh plugin --profile <p> add file:///…/dsh-labkit`。
3. **工具结果 token**：`render` 只输出摘要与路径，不倾倒完整 evidence；失败时才带逐项错误。
4. **并发**：两个构建同时写同一 `out_name` 会互相覆盖；需要并行时给不同 `out_name`。

## 5. 文件

| 文件 | 作用 |
|---|---|
| [`index.mjs`](index.mjs) | Cordis 插件入口：`name` / `inject` / `apply`，系统提示 + 六个工具注册 |
| [`lib/dsh.mjs`](lib/dsh.mjs) | 相对导入上游 `defineTool` |
| [`lib/labkit.mjs`](lib/labkit.mjs) | 核心库单一入口 |
| [`lib/paths.mjs`](lib/paths.mjs) | 仓库根、输出根、`safeName` / `outPaths` |
| [`lib/tool-schema.mjs`](lib/tool-schema.mjs) | 共用输出 schema、参数 schema、文本投影 |
| [`lib/format.mjs`](lib/format.mjs) | 场景表、错误块、建议块 |
| [`tools/recipes.mjs`](tools/recipes.mjs) | `experiment_recipes` |
| [`tools/validate.mjs`](tools/validate.mjs) | `experiment_validate` |
| [`tools/simulate.mjs`](tools/simulate.mjs) | `experiment_simulate` |
| [`tools/render.mjs`](tools/render.mjs) | `experiment_render` |
| [`tools/verify.mjs`](tools/verify.mjs) | `experiment_verify` |
| [`tools/build.mjs`](tools/build.mjs) | `experiment_build`（一次完成） |
