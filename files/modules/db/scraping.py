"""
Репозиторій для збереження результатів скрапінгу в БД.

Зберігає ScrapingBundle → scraping_sessions + scraping_observations.
Оновлює competitor_sources (ваги доменів).

Приклад:
    async with Database() as db:
        repo = ScrapingRepository(db)
        session_id = await repo.save_bundle(bundle)
"""

from __future__ import annotations

import logging
from decimal import Decimal

from schema import ScrapingBundle
from modules.db.connection import Database


log = logging.getLogger("scraper.db")


class ScrapingRepository:

    def __init__(self, db: Database):
        self._db = db

    async def save_bundle(self, bundle: ScrapingBundle) -> int:
        """
        Зберегти повний результат одного циклу скрапінгу.
        Повертає scraping_session.id.
        """
        summary = bundle.to_dict()["summary"]

        async with self._db.acquire() as conn:
            async with conn.transaction():
                # 1. Сесія
                session_id = await conn.fetchval(
                    """
                    INSERT INTO scraping_sessions
                        (article, scraped_at, sources_found, errors_count,
                         weighted_avg, min_price, max_price, median_price)
                    VALUES ($1, $2, $3, $4, $5, $6, $7, $8)
                    RETURNING id
                    """,
                    bundle.article,
                    bundle.scraped_at,
                    summary["total_sources"],
                    len(bundle.errors),
                    _dec(summary["weighted_avg_price"]),
                    _dec(summary["min_price"]),
                    _dec(summary["max_price"]),
                    _dec(summary["median_price"]),
                )

                # 2. Спостереження + оновлення competitor_sources
                for src in bundle.sources:
                    source_id = await self._upsert_source(conn, src.domain)

                    await conn.execute(
                        """
                        INSERT INTO scraping_observations
                            (session_id, source_id, domain, url, title,
                             price, raw_price, currency, in_stock,
                             confidence, source_weight, effective_weight,
                             parser_source, scraped_at)
                        VALUES ($1,$2,$3,$4,$5,$6,$7,$8,$9,$10,$11,$12,$13,$14)
                        """,
                        session_id,
                        source_id,
                        src.domain,
                        src.url,
                        src.title,
                        Decimal(str(src.price)),
                        src.raw_price,
                        src.currency,
                        src.in_stock,
                        Decimal(str(src.confidence)),
                        Decimal(str(src.source_weight)),
                        Decimal(str(src.effective_weight)),
                        src.parser_source,
                        src.scraped_at,
                    )

                # 3. Оновити лічильники для доменів з помилками
                for err in bundle.errors:
                    domain = err.get("domain", "")
                    if domain and domain != "search":
                        await conn.execute(
                            """
                            INSERT INTO competitor_sources (domain, appearances, hits, last_seen)
                            VALUES ($1, 1, 0, CURRENT_DATE)
                            ON CONFLICT (domain) DO UPDATE SET
                                appearances = competitor_sources.appearances + 1,
                                last_seen   = CURRENT_DATE,
                                updated_at  = now()
                            """,
                            domain,
                        )

        log.info(f"[DB] bundle збережено: article={bundle.article!r} session_id={session_id}")
        return session_id

    async def save_bundles(self, bundles: list[ScrapingBundle]) -> list[int]:
        """Зберегти список bundle (один за одним у спільному з'єднанні)."""
        ids = []
        for bundle in bundles:
            sid = await self.save_bundle(bundle)
            ids.append(sid)
        return ids

    # ----------------------------------------------------------------- READ

    async def latest_session(self, article: str) -> dict | None:
        """Остання сесія скрапінгу для артикулу."""
        async with self._db.acquire() as conn:
            row = await conn.fetchrow(
                "SELECT * FROM scraping_sessions WHERE article = $1 ORDER BY scraped_at DESC LIMIT 1",
                article,
            )
            return dict(row) if row else None

    async def sessions_history(self, article: str, limit: int = 30) -> list[dict]:
        """Історія сесій скрапінгу для артикулу (для графіку динаміки цін)."""
        async with self._db.acquire() as conn:
            rows = await conn.fetch(
                """
                SELECT scraped_at, sources_found, weighted_avg, min_price, max_price
                FROM scraping_sessions
                WHERE article = $1
                ORDER BY scraped_at DESC
                LIMIT $2
                """,
                article, limit,
            )
            return [dict(r) for r in rows]

    async def competitor_prices(self, article: str) -> list[dict]:
        """Остання ціна кожного конкурента для артикулу."""
        async with self._db.acquire() as conn:
            rows = await conn.fetch(
                "SELECT * FROM v_competitor_prices WHERE article = $1 ORDER BY price",
                article,
            )
            return [dict(r) for r in rows]

    async def top_sources(self, limit: int = 20) -> list[dict]:
        """Конкуренти з найвищою вагою (найнадійніші джерела)."""
        async with self._db.acquire() as conn:
            rows = await conn.fetch(
                """
                SELECT domain, appearances, hits, weight, last_seen
                FROM competitor_sources
                ORDER BY weight DESC, appearances DESC
                LIMIT $1
                """,
                limit,
            )
            return [dict(r) for r in rows]

    # ----------------------------------------------------------------- private

    @staticmethod
    async def _upsert_source(conn, domain: str) -> int:
        """Додати або оновити competitor_sources, повернути id."""
        return await conn.fetchval(
            """
            INSERT INTO competitor_sources (domain, appearances, hits, last_seen)
            VALUES ($1, 1, 1, CURRENT_DATE)
            ON CONFLICT (domain) DO UPDATE SET
                appearances = competitor_sources.appearances + 1,
                hits        = competitor_sources.hits + 1,
                last_seen   = CURRENT_DATE,
                updated_at  = now()
            RETURNING id
            """,
            domain,
        )


def _dec(value) -> Decimal | None:
    return Decimal(str(value)) if value is not None else None
