# local-tools — dsh 的本地插件（不修改上游树）

**职责**：存放挂到 DeepSeek Harness 上的本地插件源码。这里的东西不是上游 `deepseek-harness/` 的一部分，也不进上游的 pnpm workspace；它们由 `.dsh-home/profiles/<profile>/cordis.patch.yml` 以相对路径 `insert` 进 profile，重启 dsh 后生效。

这样做的原因：`deepseek-harness/` 是 2.7 GB 的第三方验证对象，自带 `.git` 且被根 `.gitignore` 挡住。往里加包等于把改动写进一个不可入库、随时会被重新克隆覆盖的地方；放在 `local-tools/` 才能被本仓库跟踪、评审与回滚。

## 内容

| 条目 | 状态 | 说明 |
|---|---|---|
| [`dsh-labkit/`](dsh-labkit/README.md) | 已实测 | 把 EduForge LabKit 注册成六个 `experiment_*` 原生工具；带 `physics-lab` agent preset（教师端工具白名单）、交付包（教师手册/学生任务单/包清单）；覆盖抛体 3、单摆 2、电路 3 共 8 个配方 |

## 装配方式（所有插件通用）

1. 插件是一个普通 ESM 模块，导出 Cordis 约定：`name`、`inject`、`apply(ctx)`。
2. 在目标 profile 的 `cordis.patch.yml` 末尾插入：
   ```yaml
   - insert:
       - id: <插件 id>
         name: ../../../local-tools/<插件目录>/index.mjs
   ```
3. 重启 dsh（profile 是静态组合，无热重载），用 `--dump-config` 确认 `name` 被解析成 `file:///…`。
4. 回滚 = 删除 patch 行 + 重启；插件目录可整体删除。

> `dsh-labkit` 的**教师端**不走上面这条全局行，而是走它自己的 [`preset.patch.yml`](dsh-labkit/preset.patch.yml)：preset 子行只挂教师需要的工具，标准模式不持有实验工具。preset 子行必须用绝对 `file://` URL，原因见该目录 README 第 4 节。

## 与上下层的关系

- 被谁加载：[`../.dsh-home/profiles/`](../.dsh-home)（本地配置，不入库）；上游 profile 组合规则见 [`../README.md`](../README.md) 与 [`../deepseek-harness/packages/bundle/base/cordis.patch.yml`](../deepseek-harness/packages/bundle/base/cordis.patch.yml)。
- 插件调用的核心能力：[`../../code/eduforge/tools/labkit/`](../../code/eduforge/tools/labkit/README.md)；模板在 [`../../code/eduforge/catalog/templates/mechanics/projectile/`](../../code/eduforge/catalog/templates/mechanics/projectile/README.md)。
- 上游树：**只读**。升级 dsh 只需重新构建 `deepseek-harness/`，本目录不动；但插件对 `defineTool` 的导入路径有版本耦合，升级后要重跑自检。

## 纪律

- 每个插件目录必须有 README，写清工具表、安装/回滚、安全边界与版本耦合。
- 插件不得静默吞错：领域失败返回结构化 `{ok:false, code, hints}`，只有未预期异常才抛。
- 插件若直接使用 `node:fs`（绕过 dsh 沙箱），必须在 README 里写明路径白名单与理由。
