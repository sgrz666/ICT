# routes — API 路由子包（占位，未拆分）

**职责**：**空目录**。它是「路由按资源拆分成多个文件」这一常见布局的预留位，实际未启用——所有 HTTP 路由集中在上一层的 `main.py`。

## 内容（逐文件）

| 文件 | 字节 | 职责 |
|---|---|---|
| `__init__.py` | 0 | 仅把本目录标记为 Python 子包。无代码、无再导出 |

## 与上下层的关系

- 真实路由实现：[`../main.py`](../README.md)（273 行，`create_app()` 应用工厂 + 全部端点 + owner 注入中间件 + 下载安全三重校验）。端点清单、下载防护细节都在 [`../README.md`](../README.md)。
- 全仓检索确认：`python/src` 与 `tests/python` 里**没有任何模块 import `eduforge.api.routes`**（`grep` 命中的 `routes` 全是模板 `manifest.yaml` 的 `routes: [config, code]` 字段，与本包无关——那是「允许的路由」语义，别混）。
- 契约下游：改了 `main.py` 的路由形状要跑 `uv run python tools/export_contracts.py` 重新生成前端 TS 契约，见 [`../../../../../packages/contracts/README.md`](../../../../../packages/contracts/README.md)。

## 已知的坑与纪律

- **别按目录名臆测代码位置**：`api/routes/` 存在，不代表路由在里面。上一级 README 的纪律节也写了同一条。
- 真要拆分时，一并处理三件事：owner 注入中间件的挂载点（现在在 `create_app` 内）、下载接口的三重防护不能被拆散、以及本目录 README 与 [`../README.md`](../README.md) 的状态描述要同轮改掉。
- 空包不影响 `uv`/pytest 采集，但它会让「API 在哪」这个问题产生歧义；保留它的唯一价值是提示将来拆分方向。
