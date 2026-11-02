# src — dsh-core 源码层

**职责**：存放 `dsh-core` 纯 Python 核心库的源码实现。遵循现代 Python `src` 布局结构，防止测试和本地脚本产生隐式就地包导入污染，保证 wheel 打包与安装行为严格一致。

## 内容

| 目录 | 状态 | 说明 |
|---|---|---|
| [`dsh_core/`](dsh_core/README.md) | 已实测 | 核心包顶级命名空间，集成四大核心基础设施子系统并提供顶级统一 API |

## 与上下层的关系

- **上层**：父目录 [`../`](README.md) 提供工程级配置与依赖说明（`pyproject.toml`, `requirements.txt`）。
- **下层**：[`dsh_core/`](dsh_core/README.md) 包含四大子系统实现（`file/`, `sandbox/`, `session/`, `memory/`）。
- **外部调用方**：通过 `pip install .` 或将 `src` 加入 `PYTHONPATH` 进行导入：`from dsh_core import ...`。

## 已知的坑与纪律

1. **导入规范**：内部跨子系统引用一律使用显式包名导入（如 `from dsh_core.file import ...` 或标准相对导入），禁止跨越 `src` 的裸导入。
2. **零副作用**：各模块的导入过程不得产生磁盘写入、网络连接或不可控子进程。
