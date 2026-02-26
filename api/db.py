"""
asyncpg connection pool singleton, managed by FastAPI lifespan.

Usage
-----
    from api import db

    # In lifespan:
    await db.init_pool()
    ...
    await db.close_pool()

    # In route handlers / services:
    pool = db.get_pool()
    async with pool.acquire() as conn:
        row = await conn.fetchrow("SELECT ...")
"""
from __future__ import annotations

from typing import Optional

import asyncpg


_pool: Optional[asyncpg.Pool] = None


async def init_pool(database_url: str) -> None:
    """Create the connection pool. Called once from the lifespan hook."""
    global _pool
    _pool = await asyncpg.create_pool(
        dsn=database_url,
        min_size=2,
        max_size=10,
        command_timeout=30,
    )


async def close_pool() -> None:
    """Gracefully close all connections. Called on shutdown."""
    global _pool
    if _pool is not None:
        await _pool.close()
        _pool = None


def get_pool() -> asyncpg.Pool:
    """Return the active pool or raise if not initialised."""
    if _pool is None:
        raise RuntimeError("Database pool is not initialised. Call init_pool() first.")
    return _pool
