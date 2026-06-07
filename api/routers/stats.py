from __future__ import annotations

from fastapi import APIRouter, Depends, Query

from deps import get_db

import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).parent.parent.parent / "files"))

from modules.db.scraping import ScrapingRepository
from modules.db.connection import Database

router = APIRouter(prefix="/stats", tags=["stats"])


@router.get("/sources")
async def top_sources(
    limit: int = Query(20, ge=1, le=100),
    db: Database = Depends(get_db),
):
    repo = ScrapingRepository(db)
    return await repo.top_sources(limit=limit)


@router.get("/categories")
async def list_categories(db: Database = Depends(get_db)):
    async with db.acquire() as conn:
        rows = await conn.fetch("SELECT slug, name FROM categories ORDER BY name")
        return [dict(r) for r in rows]


@router.get("/brands")
async def list_brands(db: Database = Depends(get_db)):
    async with db.acquire() as conn:
        rows = await conn.fetch("SELECT name FROM brands ORDER BY name")
        return [r["name"] for r in rows]


@router.get("/dashboard")
async def dashboard(db: Database = Depends(get_db)):
    async with db.acquire() as conn:
        total_products = await conn.fetchval("SELECT COUNT(*) FROM products WHERE is_active = true")
        total_sessions = await conn.fetchval("SELECT COUNT(*) FROM scraping_sessions")
        total_sources = await conn.fetchval("SELECT COUNT(*) FROM competitor_sources")
        avg_market = await conn.fetchval(
            "SELECT AVG(weighted_avg) FROM scraping_sessions WHERE scraped_at > now() - INTERVAL '7 days'"
        )
        recent_sessions = await conn.fetch(
            """
            SELECT article, scraped_at, sources_found, weighted_avg, min_price, max_price
            FROM scraping_sessions
            ORDER BY scraped_at DESC
            LIMIT 10
            """
        )
        price_positions = await conn.fetch(
            """
            SELECT price_position, COUNT(*) as count
            FROM v_price_comparison
            WHERE price_position IS NOT NULL
            GROUP BY price_position
            """
        )

    return {
        "total_products": total_products,
        "total_sessions": total_sessions,
        "total_sources": total_sources,
        "avg_market_price_7d": float(avg_market) if avg_market else None,
        "recent_sessions": [dict(r) for r in recent_sessions],
        "price_positions": [dict(r) for r in price_positions],
    }
