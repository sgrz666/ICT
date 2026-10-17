# input — REA 逆向分析的输入

这一层放**喂给 REA**（Reverse Engineer Anything，见根 `package.json`）做静态分析的目标。原则：只放分析对象，不放分析结果——结果在 [`../output/`](../output/README.md)。

## 内容

| 目录 | 状态 | 说明 |
|---|---|---|
| [`rea-smoke-test/`](rea-smoke-test/README.md) | 冒烟样本，3 个文件（`package.json` + `src/` 两份 js） | 为验证 `rea analyze-javascript-application` 全链路而造的最小 JS 应用；源码目录另有 [`src/README.md`](rea-smoke-test/src/README.md) |
| [`research-targets/`](research-targets/README.md) | 预留，当前只有一份 README | 计划放后续要逆向研究的真实目标（如上游引擎的发布产物） |

## 与上层的关系

根目录的 `package.json` 提供了 REA 的 npm 脚本入口（`npm run rea:analyze` 等）；部署与验证记录见 [`../plan/26.10.15-REA部署.md`](../plan/26.10.15-REA部署.md)。冒烟测试的产出（Evidence JSON 154,888 字节）落在 `../output/rea-smoke-test.json`，不放在本层。
