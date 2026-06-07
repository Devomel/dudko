"""
Контракт між модулем скрапінгу та модулем нечіткої логіки.

Структура даних:
    ScrapingBundle  — повний результат одного циклу скрапінгу для артикулу
    SourceRecord    — одне спостереження ціни від одного магазину

Впевненість (confidence) відображає надійність методу витягу ціни:
    json-ld   → 0.95   Schema.org — найструктурованіше
    microdata → 0.85   itemprop — семантична розмітка
    opengraph → 0.75   og:price meta-теги
    search-card → 0.65 CSS у картці видачі
    css       → 0.50   CSS-селектори загального вигляду

Вага джерела (source_weight) — навчена надійність домену (0..1),
зберігається у SourceRegistry між запусками.

effective_weight = confidence × source_weight
"""

from __future__ import annotations

import statistics
from dataclasses import dataclass, field, asdict
from datetime import datetime, timezone
from typing import Optional


PARSER_SOURCE_CONFIDENCE: dict[str, float] = {
    "json-ld":          0.95,
    "microdata":        0.85,
    "opengraph":        0.75,
    "search-card":      0.65,
    "prom-min-price":   0.60,
    "css":              0.35,
    "unknown":          0.25,
}


@dataclass
class SourceRecord:
    """Результат скрапінгу одного магазину."""

    domain: str
    url: str
    price: float
    currency: str
    in_stock: Optional[bool]
    confidence: float       # 0..1: надійність методу витягу ціни
    source_weight: float    # 0..1: навчена надійність домену
    parser_source: str      # "json-ld" | "microdata" | "css" тощо
    title: Optional[str] = None
    raw_price: Optional[str] = None
    scraped_at: str = field(
        default_factory=lambda: datetime.now(timezone.utc).isoformat()
    )

    @property
    def effective_weight(self) -> float:
        """Комбінована вага: впевненість парсера × надійність домену."""
        return round(self.confidence * self.source_weight, 4)

    def to_dict(self) -> dict:
        d = asdict(self)
        d["effective_weight"] = self.effective_weight
        return d


@dataclass
class ScrapingBundle:
    """
    Повний вихід модуля скрапінгу для одного артикулу.
    Це і є контракт для модуля нечіткої логіки.

    Приклад використання:
        bundle = scraper.scrape_article("1K0407151BC")
        data = bundle.to_dict()   # JSON-серіалізовний словник
        sources = bundle.valid_sources  # тільки успішні спостереження
        wap = bundle.weighted_avg_price  # зважена середня ціна
    """

    article: str
    scraped_at: str = field(
        default_factory=lambda: datetime.now(timezone.utc).isoformat()
    )
    sources: list[SourceRecord] = field(default_factory=list)
    errors: list[dict] = field(default_factory=list)  # [{domain, url, reason}]

    @property
    def valid_sources(self) -> list[SourceRecord]:
        """Джерела з валідною ціною (> 0)."""
        return [s for s in self.sources if s.price > 0]

    @property
    def in_stock_sources(self) -> list[SourceRecord]:
        """Джерела, де товар підтверджено в наявності."""
        return [s for s in self.valid_sources if s.in_stock is True]

    @property
    def min_price(self) -> Optional[float]:
        prices = [s.price for s in self.valid_sources]
        return min(prices) if prices else None

    @property
    def max_price(self) -> Optional[float]:
        prices = [s.price for s in self.valid_sources]
        return max(prices) if prices else None

    @property
    def median_price(self) -> Optional[float]:
        prices = [s.price for s in self.valid_sources]
        return statistics.median(prices) if prices else None

    @property
    def weighted_avg_price(self) -> Optional[float]:
        """Середня ціна зважена за effective_weight кожного джерела."""
        sources = self.valid_sources
        if not sources:
            return None
        total_w = sum(s.effective_weight for s in sources)
        if total_w == 0:
            return round(statistics.mean(s.price for s in sources), 2)
        return round(
            sum(s.price * s.effective_weight for s in sources) / total_w,
            2,
        )

    def to_dict(self) -> dict:
        return {
            "article": self.article,
            "scraped_at": self.scraped_at,
            "sources": [s.to_dict() for s in self.sources],
            "errors": self.errors,
            "summary": {
                "total_sources": len(self.valid_sources),
                "in_stock_count": len(self.in_stock_sources),
                "min_price": self.min_price,
                "max_price": self.max_price,
                "median_price": self.median_price,
                "weighted_avg_price": self.weighted_avg_price,
            },
        }
