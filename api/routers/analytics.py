from __future__ import annotations

from fastapi import APIRouter, Depends, Query

from deps import get_db

import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).parent.parent.parent / "files"))

from modules.db.connection import Database

router = APIRouter(prefix="/analytics", tags=["analytics"])


def _db(db=Depends(get_db)) -> Database:
    return db


@router.get("/sales/monthly")
async def monthly_sales(
    months: int = Query(12, ge=1, le=36),
    db: Database = Depends(_db),
):
    async with db.acquire() as conn:
        rows = await conn.fetch(
            """
            SELECT
                TO_CHAR(DATE_TRUNC('month', sale_date), 'YYYY-MM') AS month,
                SUM(quantity)::int                                  AS total_units,
                SUM(quantity * unit_price)::float                   AS total_revenue,
                COUNT(DISTINCT product_id)::int                     AS products_sold
            FROM sales_history
            WHERE sale_date >= CURRENT_DATE - ($1 || ' months')::interval
            GROUP BY DATE_TRUNC('month', sale_date)
            ORDER BY DATE_TRUNC('month', sale_date)
            """,
            str(months),
        )
    return [dict(r) for r in rows]


@router.get("/sales/top")
async def top_sellers(
    limit: int = Query(20, ge=1, le=100),
    db: Database = Depends(_db),
):
    async with db.acquire() as conn:
        rows = await conn.fetch(
            """
            SELECT
                p.article,
                p.name,
                c.slug                          AS category,
                SUM(sh.quantity)::int           AS total_units,
                SUM(sh.quantity * sh.unit_price)::float AS total_revenue
            FROM sales_history sh
            JOIN products p ON p.id = sh.product_id
            LEFT JOIN categories c ON c.id = p.category_id
            GROUP BY p.article, p.name, c.slug
            ORDER BY total_units DESC
            LIMIT $1
            """,
            limit,
        )
    return [dict(r) for r in rows]


@router.get("/sales/seasonality")
async def seasonality(db: Database = Depends(_db)):
    async with db.acquire() as conn:
        rows = await conn.fetch(
            """
            SELECT
                COALESCE(c.slug, 'інше')        AS category,
                EXTRACT(MONTH FROM sh.sale_date)::int AS month,
                SUM(sh.quantity)::int           AS total_units
            FROM sales_history sh
            JOIN products p ON p.id = sh.product_id
            LEFT JOIN categories c ON c.id = p.category_id
            GROUP BY c.slug, EXTRACT(MONTH FROM sh.sale_date)
            ORDER BY c.slug, month
            """
        )
    return [dict(r) for r in rows]


@router.get("/stock")
async def stock_status(db: Database = Depends(_db)):
    async with db.acquire() as conn:
        rows = await conn.fetch(
            """
            SELECT
                p.article,
                p.name,
                COALESCE(c.slug, 'інше')    AS category,
                ps.quantity                  AS current_stock,
                ps.price::float             AS price,
                COALESCE(
                    (SELECT ROUND(SUM(sh.quantity)::numeric / 365.0 * 30, 1)
                     FROM sales_history sh WHERE sh.product_id = p.id),
                    0
                )::float                     AS monthly_forecast,
                CASE
                    WHEN COALESCE(
                        (SELECT SUM(sh.quantity)::numeric / 365.0
                         FROM sales_history sh WHERE sh.product_id = p.id), 0
                    ) = 0 THEN NULL
                    ELSE ROUND(
                        ps.quantity / (
                            (SELECT SUM(sh.quantity)::numeric / 365.0 * 30
                             FROM sales_history sh WHERE sh.product_id = p.id)
                        ), 1
                    )
                END::float                   AS months_of_supply
            FROM products p
            JOIN product_stock ps ON ps.product_id = p.id
            LEFT JOIN categories c ON c.id = p.category_id
            WHERE p.is_active = true
            ORDER BY months_of_supply ASC NULLS LAST, p.article
            """
        )
    return [dict(r) for r in rows]


@router.get("/sales/daily/{article}")
async def article_daily(
    article: str,
    days: int = Query(90, ge=7, le=365),
    db: Database = Depends(_db),
):
    async with db.acquire() as conn:
        rows = await conn.fetch(
            """
            SELECT
                sh.sale_date::text              AS date,
                SUM(sh.quantity)::int           AS units,
                SUM(sh.quantity * sh.unit_price)::float AS revenue
            FROM sales_history sh
            JOIN products p ON p.id = sh.product_id
            WHERE p.article = $1
              AND sh.sale_date >= CURRENT_DATE - ($2 || ' days')::interval
            GROUP BY sh.sale_date
            ORDER BY sh.sale_date
            """,
            article,
            str(days),
        )
    return [dict(r) for r in rows]
