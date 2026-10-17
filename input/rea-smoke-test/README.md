# rea-smoke-test — REA 冒烟样本

为验证 `rea analyze-javascript-application` 全链路而造的**最小 JS 应用**（3 个文件），不是产品代码。`plan/26.10.15-REA部署.md` 注明：不需要可以直接删。

## 内容

- `package.json` — `name: rea-smoke-test`，ESM（`type: module`），入口 `src/index.js`。
- [`src/`](src/README.md) — 源码目录，逐文件说明与「改这里会废掉分析产物哈希」的纪律见 [`src/README.md`](src/README.md)：
  - `src/index.js` — `report(scores)`：算平均分并定级，导出给 REA 做调用图分析。
  - `src/grading.js` — `grade(score)`（A/B/C/F 分段）与 `average(values)`（空数组返回 0）。

## 验证结果（2026-10-15 实测）

```
rea analyze-javascript-application ./input/rea-smoke-test   # 退出码 0
```

产出规范 Evidence JSON **154,888 字节**（含 JavaScriptApplicationGraph、root_artifact_sha256、integrity_contradictions、limitations），落在 [`../../output/rea-smoke-test.json`](../../output/README.md)（stderr 在同目录 `.err` 文件）。

## 与其他层的关系

- 分析对象来自 [`../README.md`](../README.md) 的分工；REA 本体部署记录见 [`../../plan/26.10.15-REA部署.md`](../../plan/26.10.15-REA部署.md)。
- 真实逆向目标将来放 [`../research-targets/`](../research-targets/README.md)。
