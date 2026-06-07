"""
Спеціалізовані парсери для конкретних магазинів.

Кожен клас перевизначає лише те, що відрізняється від GenericParser.
Щоб додати новий магазин — наслідуй GenericParser і додай домен до SITE_PARSERS.
"""

from __future__ import annotations

import re
from typing import Optional

from bs4 import BeautifulSoup

from modules.scraping.parsers.base import (
    GenericParser, PriceResult, PARSER_CONFIDENCE,
)
from utils import clean_text, normalize_price


# ---------------------------------------------------------------------------
class RozetkaParser(GenericParser):
    """Розетка — SPA, ціна підвантажується через JS."""

    WAIT_FOR_SELECTOR = (
        ".goods-tile__price-value, "
        "p.product-prices__big, "
        "[data-testid='price-value']"
    )
    PRICE_SELECTORS = [
        ".goods-tile__price-value", ".product-price__big",
        "p.product-prices__big", "[data-testid='price-value']",
    ] + GenericParser.PRICE_SELECTORS
    PRODUCT_LINK_SELECTORS = [
        "a.goods-tile__heading", "a.product-link", "a.tile-link",
    ] + GenericParser.PRODUCT_LINK_SELECTORS
    TITLE_SELECTORS = [
        ".goods-tile__title", "h1.product__title",
    ] + GenericParser.TITLE_SELECTORS


# ---------------------------------------------------------------------------
class PromParser(GenericParser):
    """Prom.ua — маркетплейс.

    Сторінка товару: читаємо data-qaprice / data-qacurrency безпосередньо
    з елемента [data-qaid="product_price"] — найнадійніший спосіб, без
    парсингу тексту. Кнопка купити: data-qaid="buy-button" або "buy_now_btn".

    Сторінка пошуку: беремо найменшу ціну серед карток, що містять артикул.
    """

    WAIT_FOR_SELECTOR = "[data-qaid='product_price'], .x-product-tile__price"
    PRICE_SELECTORS = [
        # product page — span всередині блоку ціни
        "[data-qaid='product_price'] span",
        "span.x-product-tile__price",
        "[data-qaid='product_price']",
        ".x-product-tile__price",
    ] + GenericParser.PRICE_SELECTORS
    PRODUCT_LINK_SELECTORS = [
        "a[data-qaid='product_link']",
        "a.x-product-tile__picture-link",
    ] + GenericParser.PRODUCT_LINK_SELECTORS

    # ── product page ────────────────────────────────────────────────────────

    def _extract_product(self, soup: BeautifulSoup, article: str, url: str) -> Optional[PriceResult]:
        # Prom-specific: data-qaprice / data-qacurrency attribute — точне числове
        # значення без необхідності парсити текст (648, "₴/шт.").
        price_el = soup.find(attrs={"data-qaid": "product_price"})
        if price_el and price_el.get("data-qaprice"):
            try:
                price_val = float(price_el["data-qaprice"])
            except (ValueError, TypeError):
                price_val = None
            if price_val and price_val > 0:
                raw_currency = price_el.get("data-qacurrency", "₴")
                # "₴/шт." → "UAH"
                currency = "UAH" if "₴" in raw_currency else raw_currency
                in_stock = self._prom_in_stock(soup)
                return PriceResult(
                    site=self.shop_name, url=url, article=article,
                    title=self._extract_text(soup, self.TITLE_SELECTORS),
                    price=price_val, currency=currency,
                    raw_price=f"{price_val} {raw_currency}",
                    in_stock=in_stock,
                    confidence=PARSER_CONFIDENCE["css"],
                    meta={"source": "prom-data-qaprice"},
                )
        # fallback: JSON-LD / microdata / OpenGraph / generic CSS
        return super()._extract_product(soup, article, url)

    def _prom_in_stock(self, soup: BeautifulSoup) -> Optional[bool]:
        """Перевірка наявності по кнопці купити або тексту presence."""
        buy = soup.find(attrs={"data-qaid": re.compile(r"buy[_-]?(now_btn|button)$")})
        if buy:
            return True
        presence = soup.find(attrs={"data-qaid": "product_presence"})
        if presence:
            txt = presence.get_text().lower()
            if any(w in txt for w in ("готов", "є в наявн", "in stock")):
                return True
            if any(w in txt for w in ("немає", "відсутн", "out of stock")):
                return False
        return None

    # ── search page ─────────────────────────────────────────────────────────

    def parse_search_page(self, html: str, article: str, url: str) -> Optional[PriceResult]:
        soup = BeautifulSoup(html, "html.parser")
        article_lower = article.lower()
        prices = []
        for sel in self.PRICE_SELECTORS:
            for el in soup.select(sel):
                if self._is_old_price(el):
                    continue
                # Перевіряємо, що батьківська картка містить шуканий артикул
                card = el.find_parent(
                    ["article", "div", "li"],
                    class_=re.compile(r"tile|item|card|product"),
                )
                if card and article_lower not in card.get_text(" ", strip=True).lower():
                    continue
                p, c, raw = normalize_price(el.get_text(" "))
                if p is not None and p > 1:
                    prices.append((p, c, raw, el))
        if not prices:
            return super().parse_search_page(html, article, url)
        prices.sort(key=lambda x: x[0])
        best_p, best_c, best_raw, best_el = prices[0]
        title = None
        card = best_el.find_parent(
            ["article", "div", "li"],
            class_=re.compile(r"tile|item|card|product"),
        )
        if card:
            t_el = card.find(class_=re.compile(r"title|name|heading"))
            if t_el:
                title = clean_text(t_el.get_text())
        in_stock = self._detect_in_stock(card) if card else None
        return PriceResult(
            site=self.shop_name, url=url, article=article,
            title=title, price=best_p, currency=best_c,
            raw_price=best_raw, in_stock=in_stock,
            confidence=PARSER_CONFIDENCE["prom-min-price"],
            meta={"source": "prom-min-price"},
        )


# ---------------------------------------------------------------------------
class ExistParser(GenericParser):
    """Exist.ua — спеціалізований авто-маркетплейс."""

    WAIT_FOR_SELECTOR = ".price-block .price, td.price, .tovar-price"
    PRICE_SELECTORS = [
        ".price-block .price", "td.price", ".tovar-price",
    ] + GenericParser.PRICE_SELECTORS
    PRODUCT_LINK_SELECTORS = [
        "a.tovar-name", "a.product-name-link",
    ] + GenericParser.PRODUCT_LINK_SELECTORS


# ---------------------------------------------------------------------------
class AutodocParser(GenericParser):
    """autodoc.ua — React SPA, чекаємо рендеру ціни."""

    WAIT_FOR_SELECTOR = (
        ".product-price, [class*='price-value'], [class*='price-amount'], "
        "[itemprop='price'], h1"
    )
    PRICE_SELECTORS = [
        "[class*='product-price']", "[class*='price-value']",
        "[class*='price-amount']", "[class*='price-block']",
    ] + GenericParser.PRICE_SELECTORS


# ---------------------------------------------------------------------------
class AvtomarketParser(GenericParser):
    """avtomarket.ua — WooCommerce."""

    WAIT_FOR_SELECTOR = ".woocommerce-Price-amount, .price, [itemprop='price']"
    PRICE_SELECTORS = [
        "ins .woocommerce-Price-amount bdi",
        ".woocommerce-Price-amount bdi",
        ".woocommerce-Price-amount",
    ] + GenericParser.PRICE_SELECTORS


# ---------------------------------------------------------------------------
class EmexParser(GenericParser):
    """emex.ua — агрегатор пропозицій постачальників."""

    WAIT_FOR_SELECTOR = ".price-block, .offer-price, [data-price], [itemprop='price']"
    PRICE_SELECTORS = [
        ".price-block__price", ".offer__price", ".offer-price",
        "[class*='offer-price']", "[class*='price-block']",
    ] + GenericParser.PRICE_SELECTORS
    PRODUCT_LINK_SELECTORS = [
        "a.offer-name", "a.product-name",
    ] + GenericParser.PRODUCT_LINK_SELECTORS


# ---------------------------------------------------------------------------
class ZapchastiParser(GenericParser):
    """zapchasti.ua"""

    WAIT_FOR_SELECTOR = ".price, .product-price, [itemprop='price']"
    PRICE_SELECTORS = [
        ".product-price__current", ".price-current",
        "[class*='product-price']",
    ] + GenericParser.PRICE_SELECTORS


# ---------------------------------------------------------------------------
class AutobazaParser(GenericParser):
    """autobaza.com.ua"""

    WAIT_FOR_SELECTOR = ".price, [class*='price'], [itemprop='price']"
    PRICE_SELECTORS = [
        ".product__price-value", ".catalog-price",
        "[class*='product__price']",
    ] + GenericParser.PRICE_SELECTORS


# ---------------------------------------------------------------------------
class PartsUaParser(GenericParser):
    """parts.ua — один з найбільших агрегаторів UA."""

    WAIT_FOR_SELECTOR = ".price, [class*='price'], [itemprop='price']"
    PRICE_SELECTORS = [
        ".product-price__current", "[class*='product-price']",
        ".offer-price__value",
    ] + GenericParser.PRICE_SELECTORS
    PRODUCT_LINK_SELECTORS = [
        "a.product-name", "a.catalog-item__name",
    ] + GenericParser.PRODUCT_LINK_SELECTORS


# ---------------------------------------------------------------------------
# Реєстр: домен → клас парсера
# Якщо домен не в реєстрі — використовується GenericParser
# ---------------------------------------------------------------------------
SITE_PARSERS: dict[str, type[GenericParser]] = {
    "rozetka.com.ua":    RozetkaParser,
    "prom.ua":           PromParser,
    "exist.ua":          ExistParser,
    "autodoc.ua":        AutodocParser,
    "avtomarket.ua":     AvtomarketParser,
    "emex.ua":           EmexParser,
    "zapchasti.ua":      ZapchastiParser,
    "autobaza.com.ua":   AutobazaParser,
    "parts.ua":          PartsUaParser,
}
