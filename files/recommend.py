"""
Генератор рекомендацій цін.

Читає список артикулів → скрапить конкурентів → запускає нечітку логіку →
зберігає файл рекомендацій у data/recommendations_YYYYMMDD_HHMMSS.json

Формат вхідного файлу (articles.json):
[
  {
    "article":         "1K0407151BC",     -- обов'язково
    "name":            "...",             -- опціонально
    "current_price":   2100.00,           -- опціонально
    "own_stock_level": 0.2,               -- 0=залишки, 1=багато  (за замовч. 0.5)
    "demand_velocity": 0.7                -- 0=не продається, 1=ходовий (за замовч. 0.5)
  }
]

Запуск:
    recommend.bat
    recommend.bat --articles articles.json
    recommend.bat --articles articles.json --headed -v
"""

from __future__ import annotations

import argparse
import asyncio
import json
import logging
import sys

if sys.platform == "win32":
    sys.stdout.reconfigure(encoding="utf-8")
    sys.stderr.reconfigure(encoding="utf-8")

from datetime import datetime, timezone
from pathlib import Path

from modules.scraping import PriceScraper, SourceRegistry
from modules.fuzzy import FuzzyPricingEngine
from schema import ScrapingBundle

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
    datefmt="%H:%M:%S",
)
log = logging.getLogger("recommend")


# ─────────────────────────────────────────────────────────────────────────────
# Формування одного запису рекомендації
# ─────────────────────────────────────────────────────────────────────────────

def build_recommendation(
    item: dict,
    bundle: ScrapingBundle,
) -> dict:
    """Формує запис рекомендації для одного артикулу."""
    article          = item["article"]
    own_stock_level  = float(item.get("own_stock_level", 0.5))
    demand_velocity  = float(item.get("demand_velocity", 0.5))

    rec = FuzzyPricingEngine().recommend(
        bundle,
        own_stock_level=own_stock_level,
        demand_velocity=demand_velocity,
    )

    competitors = [
        {
            "domain":   s.domain,
            "price":    s.price,
            "currency": s.currency,
            "in_stock": s.in_stock,
            "url":      s.url,
            "title":    s.title,
        }
        for s in sorted(bundle.valid_sources, key=lambda s: s.price)
    ]

    current_price = item.get("current_price")
    price_delta   = None
    if rec.recommended_price is not None and current_price is not None:
        price_delta = round(rec.recommended_price - current_price, 2)

    return {
        "article":       article,
        "name":          item.get("name", ""),
        "current_price": current_price,
        "recommendation": {
            "price":      rec.recommended_price,
            "delta":      price_delta,           # різниця від поточної ціни
            "strategy":   rec.strategy,
            "confidence": rec.confidence,
            "reasoning":  rec.reasoning,
        },
        "market": {
            "min":    rec.market_min,
            "median": rec.market_median,
            "max":    rec.market_max,
            "wap":    rec.market_wap,
        },
        "fuzzy": {
            "market_position": rec.market_position,
            "own_adjustment":  rec.own_adjustment,
            "final_position":  rec.fuzzy_position,
        },
        "own_conditions": {
            "stock_level":     own_stock_level,
            "demand_velocity": demand_velocity,
        },
        "competitors":   competitors,
        "scraped_at":    bundle.scraped_at,
        "error":         None,
    }


def build_error_record(item: dict, reason: str) -> dict:
    return {
        "article":       item["article"],
        "name":          item.get("name", ""),
        "current_price": item.get("current_price"),
        "recommendation": None,
        "market":        None,
        "fuzzy":         None,
        "own_conditions": {
            "stock_level":     item.get("own_stock_level", 0.5),
            "demand_velocity": item.get("demand_velocity", 0.5),
        },
        "competitors": [],
        "scraped_at":  datetime.now(timezone.utc).isoformat(),
        "error":       reason,
    }


# ─────────────────────────────────────────────────────────────────────────────
# Виведення прогресу в консоль
# ─────────────────────────────────────────────────────────────────────────────

def print_progress(n: int, total: int, record: dict) -> None:
    art  = record["article"]
    name = record["name"]
    err  = record["error"]

    if err:
        print(f"  [{n}/{total}] ✗ {art}  ({name})  — {err}")
        return

    rec   = record["recommendation"]
    delta = rec["delta"]
    sign  = ("+" if delta > 0 else "") if delta is not None else ""
    delta_str = f"  Δ{sign}{delta:.0f} UAH" if delta is not None else ""

    print(
        f"  [{n}/{total}] ✓ {art}  {rec['price']:.2f} UAH"
        f"  [{rec['strategy']} conf={rec['confidence']:.2f}]{delta_str}"
    )
    if name:
        print(f"           {name}")


# ─────────────────────────────────────────────────────────────────────────────
# Головна функція
# ─────────────────────────────────────────────────────────────────────────────

async def main() -> None:
    parser = argparse.ArgumentParser(description="Генератор рекомендацій цін")
    parser.add_argument(
        "--articles", default="articles.json",
        help="JSON-файл зі списком артикулів (за замовч. articles.json)",
    )
    parser.add_argument(
        "--out", metavar="FILE",
        help="Куди зберегти рекомендації (за замовч. data/recommendations_TIMESTAMP.json)",
    )
    parser.add_argument("--headed",      action="store_true", help="Браузер з GUI")
    parser.add_argument("--proxy",       help="HTTP(S)-проксі")
    parser.add_argument("--concurrency", type=int, default=3, help="Паралельних магазинів")
    parser.add_argument("--delay",       type=float, default=3.0, help="Пауза між артикулами (сек)")
    parser.add_argument("--search-limit",type=int, default=8, help="Скільки магазинів шукати")
    parser.add_argument("-v", "--verbose",action="store_true", help="Детальний лог")
    args = parser.parse_args()

    if args.verbose:
        logging.getLogger().setLevel(logging.DEBUG)

    # Читаємо список артикулів
    articles_path = Path(args.articles)
    if not articles_path.exists():
        print(f"ERROR: файл не знайдено: {articles_path}")
        sys.exit(1)

    with open(articles_path, encoding="utf-8") as f:
        items: list[dict] = json.load(f)

    if not items:
        print("Список артикулів порожній.")
        sys.exit(0)

    # Вихідний файл
    ts       = datetime.now().strftime("%Y%m%d_%H%M%S")
    out_path = Path(args.out or f"data/recommendations_{ts}.json")
    out_path.parent.mkdir(parents=True, exist_ok=True)

    print(f"\n{'=' * 60}")
    print(f"  Артикулів: {len(items)}")
    print(f"  Результат: {out_path}")
    print(f"{'=' * 60}\n")

    records: list[dict] = []

    def on_done(n: int, total: int, bundle: ScrapingBundle) -> None:
        item = items[n - 1]
        if bundle.valid_sources:
            record = build_recommendation(item, bundle)
        else:
            reason = bundle.errors[0]["reason"] if bundle.errors else "не знайдено цін"
            record = build_error_record(item, reason)

        records.append(record)
        print_progress(n, total, record)

        # Зберігаємо після кожного артикулу
        _save(out_path, records)

    scraper = PriceScraper(
        headless=not args.headed,
        proxy=args.proxy,
        concurrency=args.concurrency,
        search_limit=args.search_limit,
        registry=SourceRegistry(),
    )

    article_ids = [item["article"] for item in items]

    await scraper.scrape_articles_batch(
        article_ids,
        delay_between=args.delay,
        on_done=on_done,
    )

    print(f"\n{'=' * 60}")
    ok  = sum(1 for r in records if r["error"] is None)
    err = len(records) - ok
    print(f"  Готово: {ok} успішно / {err} помилок")
    print(f"  Файл:   {out_path}")
    print(f"{'=' * 60}\n")


def _save(path: Path, records: list[dict]) -> None:
    output = {
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "total":        len(records),
        "articles":     records,
    }
    path.write_text(json.dumps(output, ensure_ascii=False, indent=2), encoding="utf-8")


if __name__ == "__main__":
    try:
        asyncio.run(main())
    except KeyboardInterrupt:
        sys.exit(130)
