# tests — pytest 套件

工程根的 `pyproject.toml` 配置 `testpaths = ["tests/python"]`，所以**工程根的 `uv run pytest` 跑的就是这里**。目前只有 Python 一套：**[`python/`](python/README.md)**。

注意区分：TypeScript 侧的 vitest 用例**不在这里**，在各包自己的 `tests/` 目录（主要是 [`../services/engine-host/tests/`](../services/engine-host/README.md)）。两个套件的当前计数（vitest 54 / pytest 62）唯一记在 [`../catalog/engines/ray-optics.yaml`](../catalog/engines/ray-optics.yaml) 的 `test_totals`。

约定：Python 测试一律放 `tests/python/`，不要在 `python/src/` 里散放测试文件。
