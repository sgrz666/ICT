"""PostgreSQL 数据库会话与连接池管理。

对齐方案 §1.2：封装 asyncpg 连接池获取与释放。
"""
from __future__ import annotations

import asyncpg

from eduforge.infrastructure.settings import settings


class DatabaseSessionManager:
    """数据库连接池管理器。"""

    def __init__(self, dsn: str | None = None):
        self.dsn = dsn or settings.database_url
        self._pool: asyncpg.Pool | None = None

    async def init(self) -> asyncpg.Pool:
        if self._pool is None:
            self._pool = await asyncpg.create_pool(self.dsn, min_size=1, max_size=10)
        return self._pool

    async def close(self) -> None:
        if self._pool is not None:
            await self._pool.close()
            self._pool = None

    @property
    def pool(self) -> asyncpg.Pool:
        if self._pool is None:
            raise RuntimeError("Database pool not initialized. Call init() first.")
        return self._pool
