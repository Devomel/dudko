"""
Модуль роботи з PostgreSQL.

Публічний API:
    Database          — пул з'єднань (asyncpg), контекстний менеджер
    ProductRepository — CRUD для позицій магазину
    ScrapingRepository — збереження результатів скрапінгу
"""

from modules.db.connection import Database
from modules.db.products import ProductRepository
from modules.db.scraping import ScrapingRepository

__all__ = ["Database", "ProductRepository", "ScrapingRepository"]
