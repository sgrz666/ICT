# file — 文件管理子系统 (File Management Subsystem)

**职责**：提供安全、受控、原子化的文件与工作区目录操作能力。负责带行号与窗口切片的文件读取、同文件系统原子暂存写与替换、精确唯一子串替换（`StrReplaceEditor`）、3 行上下文的统一差异（Unified Diff）生成、纯 Python 递归检索（`grep`/`glob`）以及零提权工作区边界防逃逸校验（`assert_path_contained`）。

## 内容

| 文件 | 状态 | 说明 |
|---|---|---|
| [`containment.py`](containment.py) | 已实测 | 工作区路径受控边界校验，通过绝对规范化路径检测越界与相对穿透异常 |
| [`observation.py`](observation.py) | 已实测 | 先读后写/先读后改门禁（`FsObservationPolicy`）：对标 `@deepseek-ai/dsh-fs-observation-policy`，拦截未读覆写（`FS_NOT_OBSERVED`）与外部并发修改冲突（`FS_STALE` CAS 校验） |
| [`str_replace.py`](str_replace.py) | 已实测 | 精确字符串替换器，严格校验目标子串唯一性，多处命中即报错防误伤 |
| [`diff.py`](diff.py) | 已实测 | 统一 Diff 生成器与 Markdown 格式化卡片，默认保留 3 行上下文 |
| [`search.py`](search.py) | 已实测 | 纯 Python 递归 grep（正则/字面量）与 glob 通配符搜索，内建缓存与二进制过滤 |
| [`manager.py`](manager.py) | 已实测 | 文件管理器核心类 `FileManager`，集成内存锁、原子写、分片读与目录列表 |
| [`__init__.py`](__init__.py) | 已实测 | 子系统 API 导出入口 |

## 与上下层的关系

- **上层依赖**：被顶级包 [`../__init__.py`](../__init__.py) 统一导出；供会话子系统 [`../session/`](../session/README.md) 用于持久化日志存取。
- **平级协同**：沙箱子系统 [`../sandbox/`](../sandbox/README.md) 的策略检查器依赖 `containment.py` 确保命令工作目录不越界。
- **外部应用**：供教育智能体读取学生代码文件、批改并产生精确差异卡片、检索实验数据。

## 已知的坑与纪律

1. **唯一替换纪律**：`StrReplaceEditor.replace_exact()` 在目标子串出现 2 次及以上时必须报错（`FsAmbiguousEditError`），严禁在未指定 `replace_all=True` 时擅自替换第一处，防止大模型幻觉破坏代码上下文。
2. **原子写入安全**：暂存临时文件必须与目标文件生成在**同一父目录下**（同卷文件系统），避免跨驱动器或跨挂载点导致 `os.replace` 失败。
3. **行号 1-indexed**：读文件切片的 `offset` 统一采用 1 序数，与大模型代码认知保持一致。
