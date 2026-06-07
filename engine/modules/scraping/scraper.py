"""
Оркестратор скрапінгу.

Приймає артикул → знаходить магазини → паралельно скрапить →
повертає ScrapingBundle з усіма спостереженнями та вагами джерел.

Два режими:
  scrape_article(article)           — один артикул, новий браузер
  scrape_articles_batch(articles)   — багато артикулів, один браузер на всіх
"""

from __future__ import annotations

import asyncio
import logging
from collections.abc import Callable
from datetime import datetime, timezone
from typing import Optional
from urllib.parse import urljoin

from schema import ScrapingBundle, SourceRecord
from modules.scraping.browser import BrowserManager
from modules.scraping.parsers import SITE_PARSERS, GenericParser, PriceResult, AiPriceParser
from modules.scraping.registry import SourceRegistry
from modules.scraping.search import find_shop_urls, normalize_domain


log = logging.getLogger("scraper")


def _to_source_record(result: PriceResult, registry: SourceRegistry) -> SourceRecord:
    return SourceRecord(
        domain=result.site,
        url=result.url,
        price=result.price or 0.0,
        currency=result.currency or "UAH",
        in_stock=result.in_stock,
        confidence=result.confidence,
        source_weight=registry.get_weight(result.site),
        parser_source=result.meta.get("source", "unknown"),
        title=result.title,
        raw_price=result.raw_price,
    )


class PriceScraper:
    """Скрапер цін автозапчастин за артикулом."""

    def __init__(
        self,
        headless: bool = True,
        proxy: Optional[str] = None,
        concurrency: int = 6,
        block_resources: bool = True,
        search_limit: int = 8,
        registry: Optional[SourceRegistry] = None,
        openai_api_key: str = "",
    ):
        self.headless = headless
        self.proxy = proxy
        self.concurrency = concurrency
        self.block_resources = block_resources
        self.search_limit = search_limit
        self.registry = registry or SourceRegistry()
        self.openai_api_key = openai_api_key

    # ---------------------------------------------------------------- public --

    async def scrape_article(self, article: str) -> ScrapingBundle:
        """Один артикул — окремий браузер."""
        async with BrowserManager(
            headless=self.headless,
            proxy=self.proxy,
            block_resources=self.block_resources,
        ) as browser:
            bundle = await self._scrape(browser, article)
        self.registry.save()
        return bundle

    async def scrape_articles_batch(
        self,
        articles: list[str],
        delay_between: float = 3.0,
        on_done: Optional[Callable[[int, int, ScrapingBundle], None]] = None,
    ) -> list[ScrapingBundle]:
        """
        Багато артикулів — один браузер для всіх (швидше, менше overhead).

        Args:
            articles:       список артикулів
            delay_between:  пауза між артикулами (секунди)
            on_done:        callback(index, total, bundle) після кожного артикулу
        """
        results: list[ScrapingBundle] = []

        async with BrowserManager(
            headless=self.headless,
            proxy=self.proxy,
            block_resources=self.block_resources,
        ) as browser:
            for i, article in enumerate(articles):
                bundle = await self._scrape(browser, article)
                results.append(bundle)
                if on_done:
                    on_done(i + 1, len(articles), bundle)
                if i < len(articles) - 1:
                    await asyncio.sleep(delay_between)

        self.registry.save()
        return results

    # --------------------------------------------------------------- private --

    async def _scrape(self, browser: BrowserManager, article: str) -> ScrapingBundle:
        """Скрапить один артикул у межах вже відкритого браузера."""
        article = article.strip()
        if not article:
            raise ValueError("Артикул не може бути порожнім")

        bundle = ScrapingBundle(
            article=article,
            scraped_at=datetime.now(timezone.utc).isoformat(),
        )

        log.info(f"Пошук магазинів для '{article}'")

        found_urls = await find_shop_urls(browser, article, limit=self.search_limit)

        if not found_urls:
            bundle.errors.append({
                "domain": "search", "url": "",
                "reason": "не знайдено жодного магазину",
            })
            return bundle

        for url in found_urls:
            self.registry.record_appearance(normalize_domain(url))

        prioritized = self.registry.sort_urls_by_weight(found_urls)
        log.info(f"Знайдено {len(prioritized)} магазинів (відсортовано за вагою)")

        semaphore = asyncio.Semaphore(self.concurrency)
        tasks = [
            self._scrape_with_limit(browser, semaphore, url, article)
            for url in prioritized
        ]
        raw_results = await asyncio.gather(*tasks, return_exceptions=True)

        for url, res in zip(prioritized, raw_results):
            domain = normalize_domain(url)
            if isinstance(res, Exception):
                bundle.errors.append({
                    "domain": domain, "url": url,
                    "reason": f"{type(res).__name__}: {res}",
                })
            elif res is not None and res.price is not None:
                self.registry.record_success(domain)
                bundle.sources.append(_to_source_record(res, self.registry))
            else:
                bundle.errors.append({
                    "domain": domain, "url": url,
                    "reason": (res.error if res else None) or "ціну не знайдено",
                })

        return bundle

    async def _scrape_with_limit(self, browser, semaphore, url, article):
        async with semaphore:
            return await self._scrape_url(browser, url, article)

    async def _scrape_url(
        self,
        browser: BrowserManager,
        url: str,
        article: str,
    ) -> Optional[PriceResult]:
        domain = normalize_domain(url)
        # Site-specific parser — used only for WAIT_FOR_SELECTOR and product_link()
        parser_cls = SITE_PARSERS.get(domain, GenericParser)
        parser = parser_cls(shop_name=domain, domain=domain)
        ai_parser = AiPriceParser(
            shop_name=domain, domain=domain, api_key=self.openai_api_key
        )

        try:
            log.info(f"[{domain}] → {url}")
            html = await browser.fetch_html(url, wait_for_selector=parser.WAIT_FOR_SELECTOR)
            if not html:
                return PriceResult(
                    site=domain, url=url, article=article,
                    error="не вдалося завантажити сторінку",
                )

            result = await ai_parser.parse(html, article, url)

            if result is None or result.price is None:
                product_path = parser.product_link(html)
                if product_path:
                    product_url = urljoin(url, product_path)
                    log.info(f"[{domain}] перехід на товар: {product_url}")
                    prod_html = await browser.fetch_html(
                        product_url, wait_for_selector=parser.WAIT_FOR_SELECTOR
                    )
                    if prod_html:
                        result = await ai_parser.parse(prod_html, article, product_url)

            if result is None:
                return PriceResult(
                    site=domain, url=url, article=article, error="ціну не знайдено"
                )

            log.info(
                f"[{domain}] ✓ {result.price} {result.currency} "
                f"({'в наявності' if result.in_stock else 'немає' if result.in_stock is False else '?'}) "
                f"[{result.meta.get('source', '?')} conf={result.confidence:.2f}]"
            )
            return result

        except Exception as e:
            log.exception(f"[{domain}] помилка")
            return PriceResult(
                site=domain, url=url, article=article,
                error=f"{type(e).__name__}: {e}",
            )
