# tools — 验证探针与代码生成工具

EduForge 的工程自带工具：**验证探针**（切片推进时证明「这件事真的成立」的一次性脚本，产出落在 `output/eduforge/reports/`）和**代码生成**（契约导出）。都不属于产品运行时路径。

## 内容

| 文件 | 语言 | 行数 | 用途 |
|---|---|---|---|
| `rayoptics_probe.cjs` | Node | 212 | 第一切片探针：证明上游接受我们手写的场景、场景可往返保存、对象能被稳定定位并改焦距、改完的仿真与独立薄透镜公式吻合。观测端只用上游仿真，参考公式独立算，不参与观测 |
| `gate2_binding.cjs` | Node | 170 | GATE-2 验证：适配器修改协议在分层物距（u<f / u=f / f<u<2f / u=2f / u>2f 五档）下是否可判真假；三条纪律——控制组、阈值落点、分层 |
| `browser_gate1.py` | Python | 144 | GATE-1 的人工那一半：Playwright 起真实 Chromium，经官方分享 URL 载入种子场景，在 UI 代码页签改焦距再读回序列化结果（内置浏览器视口不可用，这条路不是可选装饰） |
| `browser_gate1_edit.py` | Python | 163 | 上一项的续跑：UI 内改焦距 → 应用同步 → 复制分享链接导出 → 解回校验 |
| `export_contracts.py` | Python | 107 | 从 FastAPI OpenAPI 生成 TS 类型到 `packages/contracts/src/generated/api.ts`（§6.2：不手写第二套业务 DTO）。改了 API 必跑 |
| `run_db.py` | Python | 77 | 启动本地 PostgreSQL 服务（基于 pgserver），包含安全异常保护（杜绝暴力 kill 其它 Postgres 实例与破坏性删库），供一键启动与本地开发使用 |


## 环境约定

- Node 探针默认从工作区根定位上游（`EDUFORGE_RAYOPTICS` 环境变量可覆盖），需要 `source/upstream/ray-optics/dist-node/rayOptics.js` 已构建。
- Python 工具用工程环境跑：`uv run python tools/export_contracts.py`；Playwright 探针需要本机 Chromium。

## 与其他层的关系

探针的输入是 [`../catalog/templates/`](../catalog/templates/README.md) 的模板场景；输出是 [`../../../output/eduforge/reports/`](../../../output/eduforge/reports/README.md) 的 JSON/截图证据；引擎侧事实基准是 [`../catalog/engines/ray-optics.yaml`](../catalog/engines/README.md) 的 `verification_baseline`。
