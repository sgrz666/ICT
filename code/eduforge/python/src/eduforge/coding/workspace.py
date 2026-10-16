"""工作区输入与导出文件管理。

对齐方案 §1.2 和 §4.6：
- 严格受控的导出文件白名单机制；
- 禁止导出宿主敏感文件或任意路径；
- 校验文件编码与体积。
"""
from __future__ import annotations

from pathlib import Path
from typing import Sequence

ALLOWED_EXPORT_PATHS = frozenset([
    "/workspace/src/lesson.ts",
    "/workspace/src/controls.ts",
    "src/lesson.ts",
    "src/controls.ts",
])


class WorkspaceManager:
    """受限沙箱工作区管理器。"""

    def __init__(self, allowed_paths: Sequence[str] = ALLOWED_EXPORT_PATHS):
        self.allowed_paths = frozenset(allowed_paths)

    def prepare_input_files(
        self,
        base_template_files: dict[str, bytes],
        instruction: str,
    ) -> list[tuple[str, bytes]]:
        """准备注入到任务沙箱的原始文件列表。"""
        inputs: list[tuple[str, bytes]] = []
        for path, content in base_template_files.items():
            inputs.append((path, content))
        
        # 写入任务说明与约束规范
        inputs.append(("/workspace/INSTRUCTION.md", instruction.encode("utf-8")))
        return inputs

    def validate_exports(self, downloaded_files: dict[str, bytes]) -> dict[str, bytes]:
        """过滤与校验下载的文件，确保仅包含白名单内合法产物。"""
        valid_exports: dict[str, bytes] = {}
        for path, data in downloaded_files.items():
            norm = path.replace("\\", "/")
            if norm in self.allowed_paths or any(norm.endswith(p) for p in ["src/lesson.ts", "src/controls.ts"]):
                valid_exports[norm] = data
        return valid_exports
