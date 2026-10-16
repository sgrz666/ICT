"""本地文件系统产物存储。

对齐方案 §1.2：实现 ArtifactStoragePort，负责将发布产物和离线包存储于本地目录。
"""
from __future__ import annotations

import asyncio
from pathlib import Path

from eduforge.domain.ports import ArtifactStoragePort


class LocalArtifactStorage(ArtifactStoragePort):
    """本地文件存储实现。"""

    def __init__(self, base_dir: Path | str = "output/eduforge/artifacts"):
        self.base_dir = Path(base_dir)
        self.base_dir.mkdir(parents=True, exist_ok=True)

    async def put(self, key: str, data: bytes, media_type: str) -> str:
        target = self.base_dir / key
        target.parent.mkdir(parents=True, exist_ok=True)
        await asyncio.to_thread(target.write_bytes, data)
        return str(target)

    async def get(self, key: str) -> bytes | None:
        target = self.base_dir / key
        if not target.exists():
            return None
        return await asyncio.to_thread(target.read_bytes)

    async def exists(self, key: str) -> bool:
        target = self.base_dir / key
        return await asyncio.to_thread(target.exists)
