"""
Модуль скрапінгу цін автозапчастин.

Публічний API:
    PriceScraper   — основний клас, повертає ScrapingBundle
    SourceRegistry — реєстр надійності джерел (ваги доменів)
"""

from modules.scraping.scraper import PriceScraper
from modules.scraping.registry import SourceRegistry

__all__ = ["PriceScraper", "SourceRegistry"]
