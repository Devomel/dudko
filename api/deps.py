"""FastAPI dependencies — Database pool lifecycle."""
from __future__ import annotations

import sys
from pathlib import Path

# Allow importing modules from engine/
sys.path.insert(0, str(Path(__file__).parent.parent / "engine"))

from modules.db.connection import Database

_db: Database | None = None


async def get_db() -> Database:
    if _db is None:
        raise RuntimeError("Database not initialized")
    return _db


async def startup() -> None:
    global _db
    _db = Database()
    await _db.connect()


async def shutdown() -> None:
    global _db
    if _db:
        await _db.disconnect()
        _db = None
