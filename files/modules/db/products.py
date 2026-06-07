"""
CRUD-репозиторій для позицій магазину.

Всі методи — async, приймають asyncpg.Connection або Database.pool.

Приклад:
    async with Database() as db:
        repo = ProductRepository(db)
        pid = await repo.upsert("1K0407151BC", "Шрус зовнішній", category="ходова")
        await repo.set_stock("1K0407151BC", price=2850.00, quantity=3)
        products = await repo.search("шрус")
        await repo.deactivate("1K0407151BC")
"""

from __future__ import annotations

from decimal import Decimal
from typing import Optional

from modules.db.connection import Database


class ProductRepository:

    def __init__(self, db: Database):
        self._db = db

    # ----------------------------------------------------------------- CREATE / UPDATE

    async def upsert(
        self,
        article: str,
        name: str,
        category: Optional[str] = None,
        brand: Optional[str] = None,
        description: Optional[str] = None,
    ) -> int:
        """Додати або оновити позицію. Повертає id."""
        async with self._db.acquire() as conn:
            row = await conn.fetchrow(
                "SELECT upsert_product($1, $2, $3, $4, $5)",
                article, name, category, brand, description,
            )
            return row[0]

    async def set_stock(
        self,
        article: str,
        price: Optional[Decimal | float],
        quantity: int = 0,
        currency: str = "UAH",
        warehouse: Optional[str] = None,
        changed_by: Optional[str] = None,
    ) -> None:
        """Встановити ціну та залишок. Автоматично пише в product_stock_history."""
        async with self._db.acquire() as conn:
            await conn.execute(
                "SELECT set_stock($1, $2, $3, $4, $5, $6)",
                article,
                Decimal(str(price)) if price is not None else None,
                quantity,
                currency,
                warehouse,
                changed_by,
            )

    async def update_fields(
        self,
        article: str,
        *,
        name: Optional[str] = None,
        description: Optional[str] = None,
        is_active: Optional[bool] = None,
        category: Optional[str] = None,
        brand: Optional[str] = None,
    ) -> bool:
        """Оновити окремі поля позиції. Повертає True якщо знайдено."""
        async with self._db.acquire() as conn:
            # Категорія
            if category is not None:
                await conn.execute(
                    "INSERT INTO categories (slug, name) VALUES ($1, $1) ON CONFLICT (slug) DO NOTHING",
                    category,
                )
            # Бренд
            if brand is not None:
                await conn.execute(
                    "INSERT INTO brands (name) VALUES ($1) ON CONFLICT (name) DO NOTHING",
                    brand,
                )

            sets, params = [], [article]

            if name is not None:
                params.append(name)
                sets.append(f"name = ${len(params)}")
            if description is not None:
                params.append(description)
                sets.append(f"description = ${len(params)}")
            if is_active is not None:
                params.append(is_active)
                sets.append(f"is_active = ${len(params)}")
            if category is not None:
                params.append(category)
                sets.append(f"category_id = (SELECT id FROM categories WHERE slug = ${len(params)})")
            if brand is not None:
                params.append(brand)
                sets.append(f"brand_id = (SELECT id FROM brands WHERE name = ${len(params)})")

            if not sets:
                return True

            result = await conn.execute(
                f"UPDATE products SET {', '.join(sets)} WHERE article = $1",
                *params,
            )
            return result.split()[-1] != "0"

    # ----------------------------------------------------------------- READ

    async def get(self, article: str) -> Optional[dict]:
        """Отримати одну позицію з ціною та залишком."""
        async with self._db.acquire() as conn:
            row = await conn.fetchrow(
                "SELECT * FROM v_products WHERE article = $1",
                article,
            )
            return dict(row) if row else None

    async def list_all(
        self,
        active_only: bool = True,
        category: Optional[str] = None,
        brand: Optional[str] = None,
        limit: int = 200,
        offset: int = 0,
    ) -> list[dict]:
        """Список позицій з фільтрацією."""
        conditions = []
        params: list = []

        if active_only:
            conditions.append("is_active = true")
        if category:
            params.append(category)
            conditions.append(f"category = ${len(params)}")
        if brand:
            params.append(brand)
            conditions.append(f"brand = ${len(params)}")

        where = ("WHERE " + " AND ".join(conditions)) if conditions else ""
        params += [limit, offset]

        async with self._db.acquire() as conn:
            rows = await conn.fetch(
                f"SELECT * FROM v_products {where} ORDER BY article LIMIT ${len(params)-1} OFFSET ${len(params)}",
                *params,
            )
            return [dict(r) for r in rows]

    async def search(self, query: str, limit: int = 50) -> list[dict]:
        """Пошук по артикулу або назві (ILIKE)."""
        async with self._db.acquire() as conn:
            rows = await conn.fetch(
                "SELECT * FROM search_products($1) LIMIT $2",
                query, limit,
            )
            return [dict(r) for r in rows]

    async def price_history(self, article: str, limit: int = 100) -> list[dict]:
        """Повна історія змін ціни та залишку для позиції."""
        async with self._db.acquire() as conn:
            rows = await conn.fetch(
                """
                SELECT h.price, h.currency, h.quantity, h.changed_at, h.changed_by
                FROM product_stock_history h
                JOIN products p ON p.id = h.product_id
                WHERE p.article = $1
                ORDER BY h.changed_at DESC
                LIMIT $2
                """,
                article, limit,
            )
            return [dict(r) for r in rows]

    async def price_comparison(self, article: Optional[str] = None) -> list[dict]:
        """Порівняння наших цін з ринком (з v_price_comparison)."""
        async with self._db.acquire() as conn:
            if article:
                rows = await conn.fetch(
                    "SELECT * FROM v_price_comparison WHERE article = $1",
                    article,
                )
            else:
                rows = await conn.fetch(
                    "SELECT * FROM v_price_comparison ORDER BY price_position NULLS LAST, article"
                )
            return [dict(r) for r in rows]

    # ----------------------------------------------------------------- DELETE

    async def deactivate(self, article: str) -> None:
        """М'яке видалення — позиція залишається в БД з is_active=false."""
        async with self._db.acquire() as conn:
            await conn.execute("SELECT deactivate_product($1)", article)

    async def activate(self, article: str) -> None:
        """Відновити деактивовану позицію."""
        async with self._db.acquire() as conn:
            result = await conn.execute(
                "UPDATE products SET is_active = true WHERE article = $1",
                article,
            )
            if result.split()[-1] == "0":
                raise ValueError(f"Product with article {article!r} not found")

    async def delete(self, article: str) -> None:
        """Повне видалення позиції з усіма пов'язаними даними (каскадно)."""
        async with self._db.acquire() as conn:
            await conn.execute("SELECT delete_product($1)", article)
