"""
Точка входу CLI.

Вся логіка — у modules/scraping/ та modules/fuzzy/.
schema.py та utils.py — спільні між модулями.
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
from datetime import datetime
from pathlib import Path

from modules.scraping import PriceScraper, SourceRegistry
from modules.fuzzy import FuzzyPricingEngine
from schema import ScrapingBundle


logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
    datefmt="%H:%M:%S",
)

log = logging.getLogger("scraper")


# ---------------------------------------------------------------------------
# Вивід
# ---------------------------------------------------------------------------
def print_bundle(bundle: ScrapingBundle) -> None:
    sources = sorted(bundle.valid_sources, key=lambda s: s.price)

    print("\n" + "=" * 70)
    print(f"  АРТИКУЛ: {bundle.article}")
    print(f"  ЗНАЙДЕНО: {len(sources)} / {len(sources) + len(bundle.errors)}")
    if bundle.weighted_avg_price:
        print(f"  ЗВАЖЕНА СЕРЕДНЯ: {bundle.weighted_avg_price:.2f} UAH")
    print("=" * 70)

    for s in sources:
        stock_str = (
            " ✓ в наявності" if s.in_stock is True
            else " ✗ немає" if s.in_stock is False
            else ""
        )
        print(f"\n● {s.domain}{stock_str}  [w={s.effective_weight:.2f}]")
        if s.title:
            print(f"  {s.title[:60]}")
        print(f"  Ціна: {s.price:.2f} {s.currency}")
        print(f"  {s.url}")

    if bundle.errors:
        print("\n" + "-" * 70)
        print("  НЕ ЗНАЙДЕНО:")
        for e in bundle.errors:
            print(f"  ✗ {e['domain']}: {e['reason']}")

    # Рекомендація нечіткої логіки
    rec = FuzzyPricingEngine().recommend(bundle)
    print("\n" + "=" * 70)
    if rec.recommended_price is not None:
        print(f"  💡 РЕКОМЕНДОВАНА ЦІНА: {rec.recommended_price:.2f} UAH")
        print(f"  Стратегія: {rec.strategy}  |  Впевненість: {rec.confidence:.2f}")
        print(f"  {rec.reasoning}")
    else:
        print("  💡 Рекомендацію не вдалося сформувати (немає даних).")
    print("=" * 70)

    print()


def print_registry_stats(registry: SourceRegistry) -> None:
    stats = registry.all_stats()
    if not stats:
        print("Реєстр порожній. Запустіть скрапінг для накопичення статистики.")
        return
    print(f"\n{'Домен':<35} {'Появи':>7} {'Хіти':>6} {'Вага':>7}  {'Остання дата'}")
    print("-" * 70)
    for s in stats:
        print(
            f"{s['domain']:<35} {s['appearances']:>7} {s['hits']:>6} "
            f"{s['weight']:>7.3f}  {s['last_seen'] or '-'}"
        )
    print()


# ---------------------------------------------------------------------------
# CLI
# ---------------------------------------------------------------------------
async def main() -> None:
    parser = argparse.ArgumentParser(description="Скрапер цін автозапчастин")

    parser.add_argument("article", nargs="?", help="Артикул (наприклад: 1K0407151BC)")
    parser.add_argument("--batch", metavar="FILE",
                        help="JSON-файл зі списком артикулів для пакетного скрапінгу")
    parser.add_argument("--batch-out", metavar="FILE",
                        help="Куди зберегти результати пакету (за замовч. data/batch_TIMESTAMP.json)")
    parser.add_argument("--delay", type=float, default=3.0,
                        help="Пауза між артикулами у пакеті (секунди, за замовч. 3)")
    parser.add_argument("--json", dest="json_out", help="Зберегти результат одного артикулу у JSON")
    parser.add_argument("--headed", action="store_true", help="Браузер з GUI")
    parser.add_argument("--proxy", help="HTTP(S)-проксі")
    parser.add_argument("--concurrency", type=int, default=3, help="Паралельних магазинів")
    parser.add_argument("--search-limit", type=int, default=8, help="Скільки магазинів шукати")
    parser.add_argument("--no-block", action="store_true", help="Не блокувати ресурси")
    parser.add_argument("--registry", action="store_true", help="Показати статистику джерел")
    parser.add_argument("--openai-key", metavar="KEY", default="",
                        help="OpenAI API key (або задайте OPENAI_API_KEY у середовищі)")
    parser.add_argument("-v", "--verbose", action="store_true", help="Детальний лог")

    args = parser.parse_args()

    if args.verbose:
        logging.getLogger().setLevel(logging.DEBUG)

    registry = SourceRegistry()

    if args.registry:
        print_registry_stats(registry)
        return

    scraper = PriceScraper(
        headless=not args.headed,
        proxy=args.proxy,
        concurrency=args.concurrency,
        block_resources=not args.no_block,
        search_limit=args.search_limit,
        registry=registry,
        openai_api_key=args.openai_key,
    )

    # ---------------------------------------------------------------- batch --
    if args.batch:
        with open(args.batch, encoding="utf-8") as f:
            items = json.load(f)

        articles = [
            item["article"] if isinstance(item, dict) else str(item)
            for item in items
        ]

        ts = datetime.now().strftime("%Y%m%d_%H%M%S")
        out_path = Path(args.batch_out or f"data/batch_{ts}.json")
        out_path.parent.mkdir(parents=True, exist_ok=True)

        all_results: list[dict] = []

        def on_done(n: int, total: int, bundle: ScrapingBundle) -> None:
            print_bundle(bundle)
            all_results.append(bundle.to_dict())
            # Зберігаємо після кожного артикулу — якщо процес впаде, дані не загубляться
            out_path.write_text(
                json.dumps(all_results, ensure_ascii=False, indent=2),
                encoding="utf-8",
            )
            log.info(f"[{n}/{total}] збережено → {out_path}")

        print(f"\nПакетний скрапінг: {len(articles)} артикулів")
        print(f"Результати: {out_path}\n")

        await scraper.scrape_articles_batch(
            articles,
            delay_between=args.delay,
            on_done=on_done,
        )

        print(f"\nГотово. Всього: {len(all_results)} артикулів → {out_path}")
        return

    # -------------------------------------------------------------- single --
    if not args.article:
        parser.print_help()
        sys.exit(1)

    bundle = await scraper.scrape_article(args.article)
    print_bundle(bundle)

    if args.json_out:
        with open(args.json_out, "w", encoding="utf-8") as f:
            json.dump(bundle.to_dict(), f, ensure_ascii=False, indent=2)
        log.info(f"Збережено у {args.json_out}")


if __name__ == "__main__":
    try:
        asyncio.run(main())
    except KeyboardInterrupt:
        sys.exit(130)
