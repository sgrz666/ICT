# src — REA 冒烟样本源码目录

**职责**：`rea-smoke-test` 这个最小 JS 应用的业务代码所在处，用来给 `rea analyze-javascript-application` 一个**有调用图可挖**的目标：一个入口函数调一个分级函数和一个求平均函数，够小、能跑、可静态解析。不是产品代码。

## 内容（逐文件）

| 文件 | 行数 | 职责 | 导出 |
|---|---|---|---|
| `index.js` | 6 | 入口：`report(scores)` 先算平均分、再定级，把两者组成结果返回——REA 调用图的根 | `report` |
| `grading.js` | 11 | 两个纯函数：`grade(score)` 按 A/B/C/F 分段定级；`average(values)` 求均值，**空数组返回 0**（这条边界是给分析器留的可核对语义） | `grade`, `average` |

模块系统：ESM（上层 `package.json` 声明 `type: module`），`import`/`export` 写法即 REA 依赖解析所依赖的形式。

## 与上下层的关系

- 上层入口：[`../package.json`](../README.md) 的入口指向 `src/index.js`；分析与删除的约定都写在 [`../README.md`](../README.md)。
- 所属分组：[`../../README.md`](../../README.md)（`input/` = REA 逆向分析的输入样本）。
- 分析产物：Evidence JSON **154,888 字节**（含 `JavaScriptApplicationGraph`、`root_artifact_sha256`、`integrity_contradictions`、`limitations`）落在 [`../../../output/rea-smoke-test.json`](../../../output/README.md)，stderr 在同名 `.err`。
- 部署与分析约定：[`../../../plan/26.10.15-REA部署.md`](../../../plan/README.md)。

## 已知的坑与纪律

- **改这里等于改测试夹具**：删函数、改名或换成 CommonJS，都会让 `rea analyze-javascript-application` 的图和上面对照 JSON 的哈希失效。要改就重跑分析并更新 `output/rea-smoke-test.json`，别留着旧产物当「已通过」。
- 保持最小：本目录的存在价值是「小到能一眼核对分析结果对不对」。往里加真实逻辑会让冒烟样本变成第二个被测工程，那时候它就不该待在 `input/` 里。
- 不需要时可以直接删（`plan/26.10.15-REA部署.md` 的结论），删除时同步 [`../README.md`](../README.md) 与 [`../../README.md`](../../README.md) 的描述，别留下指向空目录的链接。
- 真实逆向目标放 [`../../research-targets/`](../../research-targets/README.md)，不要混进这个冒烟目录。
