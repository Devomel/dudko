"""
Пул з'єднань asyncpg.

Конфігурація через змінні середовища або явний DSN:
    DB_DSN      — повний рядок підключення (пріоритет)
    DB_HOST     — хост (default: localhost)
    DB_PORT     — порт (default: 5433)
    DB_NAME     — назва бази (default: scrapper)
    DB_USER     — користувач (default: scrapper)
    DB_PASSWORD — пароль (default: scrapper)

Використання:
    async with Database() as db:
        async with db.acquire() as conn:
            row = await conn.fetchrow("SELECT ...")
"""

from __future__ import annotations

import asyncpg
import os
from typing import Optional


def _dsn_from_env() -> str:
    if dsn := os.getenv("DB_DSN"):
        return dsn
    host     = os.getenv("DB_HOST",     "localhost")
    port     = os.getenv("DB_PORT",     "5433")
    name     = os.getenv("DB_NAME",     "scrapper")
    user     = os.getenv("DB_USER",     "scrapper")
    password = os.getenv("DB_PASSWORD", "scrapper")
    return f"postgresql://{user}:{password}@{host}:{port}/{name}"


class Database:
    """Обгортка над asyncpg.Pool з підтримкою async with."""

    def __init__(self, dsn: Optional[str] = None, min_size: int = 2, max_size: int = 10):
        self._dsn      = dsn or _dsn_from_env()
        self._min_size = min_size
        self._max_size = max_size
        self._pool: Optional[asyncpg.Pool] = None

    # ----------------------------------------------------------------- lifecycle

    async def connect(self) -> None:
        self._pool = await asyncpg.create_pool(
            self._dsn,
            min_size=self._min_size,
            max_size=self._max_size,
        )

    async def disconnect(self) -> None:
        if self._pool:
            await self._pool.close()
            self._pool = None

    async def __aenter__(self) -> "Database":
        await self.connect()
        return self

    async def __aexit__(self, *_) -> None:
        await self.disconnect()

    # ----------------------------------------------------------------- access

    def acquire(self):
        """Отримати з'єднання з пулу (async context manager)."""
        if not self._pool:
            raise RuntimeError("Database not connected. Use 'async with Database() as db'.")
        return self._pool.acquire()

    @property
    def pool(self) -> asyncpg.Pool:
        if not self._pool:
            raise RuntimeError("Database not connected.")
        return self._pool
